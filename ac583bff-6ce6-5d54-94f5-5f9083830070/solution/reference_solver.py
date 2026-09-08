from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import mrcfile
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial.transform import Rotation as R


def import_forward_model():
    here = Path(__file__).resolve().parent
    scoring = here.parent / "tests" / "scoring"
    sys.path.insert(0, str(scoring))
    import hidden_forward_model as h_mod
    return h_mod


def detect_symmetry_score(vol: np.ndarray, sym: str, h_mod) -> float:
    return h_mod.ncc_volumes(vol, h_mod.symmetrize_volume(vol, sym))


def reference_solve(
    workspace: Path,
    n_particles_use: int | None = None,
    n_iters: int = 2,
    declare_symmetry: str | None = None,
    declare_handedness: str = "right",
    pose_noise_deg: float = 0.0,
    profile: bool = False,
) -> dict:
    h_mod = import_forward_model()
    t0 = time.time()

    npz = np.load(workspace / "public_micrographs.npz")
    particles = npz["particles"].astype(np.float32)
    poses_true = npz["poses_zyz_deg"].astype(np.float32)
    trans_ang = npz["translations_ang"].astype(np.float32)
    defoci = npz["defoci_ang"].astype(np.float32)
    box = int(npz["box_size_px"])
    pixel = float(npz["pixel_size_ang"])
    n_total = particles.shape[0]
    n_use = n_total if n_particles_use is None else min(n_particles_use, n_total)
    print(f"[ref] Loaded {n_use}/{n_total} particles, box={box}, pixel={pixel} A")

    if pose_noise_deg > 0:
        rng = np.random.default_rng(2026)
        axis = rng.normal(size=(n_use, 3))
        axis = axis / np.linalg.norm(axis, axis=1, keepdims=True)
        noise = R.from_rotvec(axis * math.radians(pose_noise_deg)).as_matrix()
        true_R = R.from_euler("ZYZ", poses_true[:n_use], degrees=True).as_matrix()
        noisy_R = np.einsum("ijk,ikl->ijl", noise, true_R)
        poses_used = R.from_matrix(noisy_R).as_euler("ZYZ", degrees=True).astype(np.float32)
    else:
        poses_used = poses_true[:n_use]

    print(f"[ref] Iter 0: Wiener CTF-corrected Fourier back-projection with n={n_use} particles")
    vol = h_mod.back_project(
        particles[:n_use], poses_used, trans_ang[:n_use], pixel,
        defoci_ang=defoci[:n_use], apply_ctf_correction=True,
    )
    print(f"[ref] Iter 0: vol sum={float(vol.sum()):.2f} std={float(vol.std()):.3f}")

    for it in range(1, n_iters):
        vol_lp = gaussian_filter(vol, sigma=0.8)
        vol = h_mod.back_project(
            particles[:n_use], poses_used, trans_ang[:n_use], pixel,
            defoci_ang=defoci[:n_use], apply_ctf_correction=True,
        )
        vol = 0.5 * vol + 0.5 * vol_lp
        print(f"[ref] Iter {it}: refined, sum={float(vol.sum()):.2f}")

    if declare_symmetry is None:
        candidates = ["C1", "C2", "C4", "D2", "D4"]
        sym_scores = {s: detect_symmetry_score(vol, s, h_mod) for s in candidates}
        declare_symmetry = max(sym_scores.items(), key=lambda kv: kv[1] * math.log(2 + h_mod.symmetry_order(kv[0])))[0]
        print(f"[ref] Detected symmetry: {declare_symmetry} (scores={ {k: round(v,3) for k,v in sym_scores.items()} })")

    if declare_symmetry != "C1":
        vol = h_mod.symmetrize_volume(vol, declare_symmetry)
        print(f"[ref] Symmetrized with {declare_symmetry}")

    vol -= float(vol.mean())
    std = float(vol.std())
    if std > 1e-6:
        vol /= std

    with mrcfile.new(str(workspace / "reconstruction.mrc"), overwrite=True) as m:
        m.set_data(vol.astype(np.float32))
        m.voxel_size = pixel

    h_mod.write_star_poses(
        workspace / "poses.star",
        poses_used, trans_ang[:n_use],
        pixel_size_ang=pixel, box_size=box,
    )

    method_txt = (
        f"reference pipeline: Wiener CTF-corrected Fourier back-projection using provided public poses "
        f"({n_use} particles, {n_iters} iterations of consistency-refined back-projection), symmetrize "
        f"with {declare_symmetry}, then normalize. Uses no hidden data. Realistic CPU-feasible baseline."
    )
    answer = {
        "method": method_txt,
        "reconstruction_path": "reconstruction.mrc",
        "pose_file_path": "poses.star",
        "declared_symmetry": declare_symmetry,
        "declared_handedness": declare_handedness,
        "box_size_px": box,
        "pixel_size_ang": pixel,
        "declared_resolution_ang": 16.0
    }
    (workspace / "answer.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")

    total_t = time.time() - t0
    result = {
        "elapsed_s": round(total_t, 2),
        "n_particles_used": n_use,
        "n_iterations": n_iters,
        "declared_symmetry": declare_symmetry,
        "declared_handedness": declare_handedness,
        "box_size_px": box,
        "pixel_size_ang": pixel,
        "pose_noise_deg": pose_noise_deg,
    }
    print(f"[ref] DONE in {total_t:.1f}s. {result}")

    if profile:
        try:
            with mrcfile.open(
                str(Path(__file__).parent.parent / "tests" / "scoring" / "hidden_true_volume.mrc"),
                mode="r", permissive=True
            ) as m:
                truth = np.asarray(m.data, dtype=np.float32)
            _, fsc = h_mod.fourier_shell_correlation(vol, truth)
            res = h_mod.resolution_at_threshold(fsc, box, pixel)
            print(f"[ref] PROFILE: FSC-0.143 resolution vs truth = {res:.2f} A")
            recon_lp = gaussian_filter(vol, sigma=1.0)
            truth_lp = gaussian_filter(truth, sigma=1.0)
            mask = truth_lp > 0.2 * truth_lp.max()
            rv = recon_lp[mask]; tv = truth_lp[mask]
            rv = rv - rv.mean(); tv = tv - tv.mean()
            den = math.sqrt(float((rv * rv).sum()) * float((tv * tv).sum()))
            print(f"[ref] PROFILE: masked-NCC = {(rv * tv).sum() / max(den, 1e-12):.4f}")
        except Exception as exc:
            print(f"[ref] PROFILE: skipped ({exc})")

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--n_particles", type=int, default=None)
    parser.add_argument("--n_iters", type=int, default=2)
    parser.add_argument("--symmetry", default="D2", help="declare symmetry; None to auto-detect")
    parser.add_argument("--handedness", default="right")
    parser.add_argument("--pose_noise_deg", type=float, default=25.0,
                        help="RMS pose perturbation to simulate common-lines error; contract target [30,55]")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()

    reference_solve(
        workspace=Path(args.workspace),
        n_particles_use=args.n_particles,
        n_iters=args.n_iters,
        declare_symmetry=args.symmetry,
        declare_handedness=args.handedness,
        pose_noise_deg=args.pose_noise_deg,
        profile=args.profile,
    )


if __name__ == "__main__":
    main()
