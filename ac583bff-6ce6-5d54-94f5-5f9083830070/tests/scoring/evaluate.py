from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


TASK_NAME = "cryoem_reconstruction"


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(obj: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def safe_float(x: Any, default: float = float("nan")) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def round3(x: Any) -> float:
    try:
        return round(float(x), 3)
    except Exception:
        return 0.0


def log_power_score(error: float, good: float, bad: float, points: float, gamma: float = 2.5) -> float:
    try:
        error = float(error)
        good = float(good)
        bad = float(bad)
        points = float(points)
        gamma = float(gamma)
    except Exception:
        return 0.0
    if not math.isfinite(error) or not math.isfinite(good) or not math.isfinite(bad):
        return 0.0
    if good <= 0.0 or bad <= good or points <= 0.0:
        return 0.0
    if error <= good:
        return points
    if error >= bad:
        return 0.0
    z = (math.log(bad) - math.log(error)) / (math.log(bad) - math.log(good))
    z = max(0.0, min(1.0, z))
    return points * (z ** gamma)


def smooth_linear_score(error: float, good: float, bad: float, points: float, gamma: float = 1.3) -> float:
    try:
        error = float(error)
        good = float(good)
        bad = float(bad)
        points = float(points)
        gamma = float(gamma)
    except Exception:
        return 0.0
    if not math.isfinite(error) or bad <= good or points <= 0.0:
        return 0.0
    if error <= good:
        return points
    if error >= bad:
        return 0.0
    z = (bad - error) / (bad - good)
    return points * (max(0.0, min(1.0, z)) ** gamma)


def higher_is_better_score(value: float, good: float, bad: float, points: float, gamma: float = 1.3) -> float:
    try:
        value = float(value)
        good = float(good)
        bad = float(bad)
        points = float(points)
        gamma = float(gamma)
    except Exception:
        return 0.0
    if not math.isfinite(value) or good <= bad or points <= 0.0:
        return 0.0
    if value >= good:
        return points
    if value <= bad:
        return 0.0
    z = (value - bad) / (good - bad)
    return points * (max(0.0, min(1.0, z)) ** gamma)


def scan_canary_leaks(submission_dir: Path, tokens: list[str]) -> list[str]:
    leaks: list[str] = []
    if not submission_dir.exists():
        return leaks
    for path in submission_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in ("score.json",):
            continue
        try:
            data = path.read_bytes()
        except Exception:
            continue
        for tok in tokens:
            if tok.encode() in data:
                leaks.append(f"{path.relative_to(submission_dir)}::{tok}")
    return leaks


def load_mrc_data(path: Path) -> np.ndarray | None:
    try:
        import mrcfile
        with mrcfile.open(str(path), mode="r", permissive=True) as m:
            return np.asarray(m.data, dtype=np.float32)
    except Exception:
        return None


def structural_gate(submission_dir: Path, answer: dict[str, Any] | None) -> tuple[bool, str]:
    if answer is None:
        return False, "answer.json missing or malformed"
    recon_name = answer.get("reconstruction_path", "reconstruction.mrc")
    recon_path = submission_dir / str(recon_name)
    if not recon_path.exists():
        return False, f"reconstruction.mrc not found at {recon_name}"
    vol = load_mrc_data(recon_path)
    if vol is None or vol.ndim != 3:
        return False, "reconstruction.mrc failed to load or not 3D"
    pose_name = answer.get("pose_file_path", "poses.star")
    pose_path = submission_dir / str(pose_name)
    if not pose_path.exists():
        return False, f"poses.star not found at {pose_name}"
    text = pose_path.read_text(encoding="utf-8", errors="ignore")
    if "data_particles" not in text or "loop_" not in text:
        return False, "poses.star missing data_particles or loop_ block"
    if "_rlnAngleRot" not in text or "_rlnAngleTilt" not in text or "_rlnAnglePsi" not in text:
        return False, "poses.star missing rlnAngleRot/Tilt/Psi columns"
    return True, "ok"


def score_L1_format(answer: dict[str, Any], sym_vocab: list[str], hand_vocab: list[str]) -> tuple[float, dict[str, Any]]:
    detail: dict[str, Any] = {}
    required = ["method", "reconstruction_path", "pose_file_path",
                "declared_symmetry", "declared_handedness",
                "box_size_px", "pixel_size_ang"]
    missing = [k for k in required if k not in answer]
    detail["missing_fields"] = missing
    pts = 0.0
    if not missing:
        pts += 1.0
    method = str(answer.get("method", "")).strip()
    if len(method) >= 20:
        pts += 1.0
    detail["method_length"] = len(method)
    sym_ok = str(answer.get("declared_symmetry", "")).upper() in [s.upper() for s in sym_vocab]
    hand_ok = str(answer.get("declared_handedness", "")).lower() in [h.lower() for h in hand_vocab]
    if sym_ok and hand_ok:
        pts += 1.0
    detail["symmetry_in_vocab"] = sym_ok
    detail["handedness_in_vocab"] = hand_ok
    return min(pts, 3.0), detail


def score_L2_bounds(answer: dict[str, Any], config: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    detail: dict[str, Any] = {}
    box = safe_float(answer.get("box_size_px"))
    pix = safe_float(answer.get("pixel_size_ang"))
    box_lo, box_hi = config.get("box_size_range", [32, 128])
    pix_lo, pix_hi = config.get("pixel_size_range_ang", [1.0, 4.0])
    box_ok = math.isfinite(box) and box_lo <= box <= box_hi and float(int(box)) == box
    pix_ok = math.isfinite(pix) and pix_lo <= pix <= pix_hi
    sym_vocab = [s.upper() for s in config.get("symmetry_vocabulary", [])]
    sym_ok = str(answer.get("declared_symmetry", "")).upper() in sym_vocab
    detail["box_ok"] = box_ok
    detail["pixel_ok"] = pix_ok
    detail["symmetry_ok"] = sym_ok
    if box_ok and pix_ok and sym_ok:
        return 2.0, detail
    return 0.0, detail


def compute_reconstruction_metrics(
    recon_vol: np.ndarray,
    true_vol: np.ndarray,
    pixel_size: float,
    h_mod,
) -> dict[str, float]:
    if recon_vol.shape != true_vol.shape:
        try:
            from scipy.ndimage import zoom
            factors = tuple(t / r for t, r in zip(true_vol.shape, recon_vol.shape))
            recon_vol = zoom(recon_vol, factors, order=1).astype(np.float32)
        except Exception:
            return {
                "fsc_143_resolution_ang": 1e6,
                "ncc_map": 0.0,
                "shape_mismatch": True,
            }
    _, fsc_arr = h_mod.fourier_shell_correlation(recon_vol, true_vol)
    box = recon_vol.shape[0]
    res_ang = h_mod.resolution_at_threshold(fsc_arr, box, pixel_size, threshold=0.143)
    try:
        from scipy.ndimage import gaussian_filter
        recon_lp = gaussian_filter(recon_vol, sigma=1.0)
        truth_lp = gaussian_filter(true_vol, sigma=1.0)
        mask = truth_lp > (0.2 * float(truth_lp.max()))
        if mask.sum() < 100:
            mask = np.ones_like(truth_lp, dtype=bool)
        rv = recon_lp[mask].astype(np.float64)
        tv = truth_lp[mask].astype(np.float64)
        rv = rv - rv.mean()
        tv = tv - tv.mean()
        den = float(np.sqrt((rv * rv).sum() * (tv * tv).sum()))
        ncc = float((rv * tv).sum() / max(den, 1e-12))
    except Exception:
        ncc = h_mod.ncc_volumes(recon_vol, true_vol)
    return {
        "fsc_143_resolution_ang": float(res_ang),
        "ncc_map": float(ncc),
        "shape_mismatch": False,
    }


def score_L3_public_sanity(
    metrics: dict[str, float],
    cfg: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    lane_cfg = cfg.get("L3_public_sanity", {"points": 10, "good_ang": 15.0, "bad_ang": 30.0, "gamma": 1.4})
    res = metrics.get("fsc_143_resolution_ang", 1e6)
    pts = smooth_linear_score(res, lane_cfg["good_ang"], lane_cfg["bad_ang"], lane_cfg["points"], lane_cfg["gamma"])
    return pts, {"resolution_ang": res}


def score_L4_handedness(
    recon_vol: np.ndarray,
    true_vol: np.ndarray,
    declared_handedness: str,
    true_handedness: str,
    h_mod,
) -> tuple[float, dict[str, Any]]:
    if recon_vol.shape != true_vol.shape:
        return 0.0, {"reason": "shape_mismatch"}
    ncc_orig = h_mod.ncc_volumes(recon_vol, true_vol)
    ncc_flip = h_mod.ncc_volumes(h_mod.flip_z(recon_vol), true_vol)
    detectability = abs(ncc_orig - ncc_flip)
    detected = "right" if ncc_orig >= ncc_flip else "left"
    declared = str(declared_handedness).lower()
    truth = str(true_handedness).lower()
    detail = {
        "ncc_orig": float(ncc_orig),
        "ncc_flip": float(ncc_flip),
        "detectability": float(detectability),
        "detected_via_ncc": detected,
        "truth": truth,
        "declared": declared,
    }
    if detectability < 0.02:
        detail["reason"] = "undetectable_symmetric_or_low_signal"
        return 0.0, detail
    if declared == truth:
        return 5.0, detail
    if declared in ("right", "left") and declared != truth:
        if detectability < 0.05:
            return 2.0, detail
        return 0.0, detail
    return 0.0, detail


def score_L5_symmetry(
    declared_symmetry: str,
    true_symmetry: str,
    h_mod,
) -> tuple[float, dict[str, Any]]:
    declared = str(declared_symmetry).upper()
    truth = str(true_symmetry).upper()
    d_order = h_mod.symmetry_order(declared)
    t_order = h_mod.symmetry_order(truth)
    detail = {
        "declared": declared,
        "truth": truth,
        "declared_order": d_order,
        "truth_order": t_order,
    }
    if declared == truth:
        return 5.0, detail
    if d_order > t_order:
        detail["abuse"] = True
        return 0.0, detail
    if d_order < t_order:
        return 3.0, detail
    return 2.0, detail


def score_L6_method_workflow(answer: dict[str, Any], submission_dir: Path) -> tuple[float, dict[str, Any]]:
    detail: dict[str, Any] = {}
    method = str(answer.get("method", "")).strip()
    pts = 0.0
    if len(method) >= 20:
        pts += 2.0
    detail["method_length"] = len(method)

    py_files = [p for p in submission_dir.glob("*.py") if p.name != "baseline_solver.py"]
    detail["non_baseline_py_count"] = len(py_files)
    if py_files:
        pts += 2.0

    keywords = ["fft", "back-project", "back_project", "backproject", "refine",
                "projection", "ctf", "fourier", "reconstruct"]
    code_blob = ""
    for p in py_files:
        try:
            code_blob += "\n" + p.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            pass
    hits = [k for k in keywords if k in code_blob]
    detail["keyword_hits_in_code"] = hits
    if hits:
        pts += 1.0

    return min(pts, 5.0), detail


def score_L7_reconstruction(
    metrics: dict[str, float],
    pose_error_deg: float,
    cfg: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    coarse_cfg = cfg["L7_coarse"]
    precise_cfg = cfg["L7_precise"]
    res = metrics.get("fsc_143_resolution_ang", 1e6)
    ncc = metrics.get("ncc_map", 0.0)

    fsc_c = smooth_linear_score(res, coarse_cfg["fsc_143_coarse"]["good_ang"], coarse_cfg["fsc_143_coarse"]["bad_ang"],
                                coarse_cfg["fsc_143_coarse"]["points"], coarse_cfg["fsc_143_coarse"]["gamma"])
    ncc_c = higher_is_better_score(ncc, coarse_cfg["ncc_map_coarse"]["good"], coarse_cfg["ncc_map_coarse"]["bad"],
                                   coarse_cfg["ncc_map_coarse"]["points"], coarse_cfg["ncc_map_coarse"]["gamma"])
    pose_c = smooth_linear_score(pose_error_deg, coarse_cfg["pose_angular_coarse"]["good_deg"],
                                 coarse_cfg["pose_angular_coarse"]["bad_deg"],
                                 coarse_cfg["pose_angular_coarse"]["points"], coarse_cfg["pose_angular_coarse"]["gamma"])

    fsc_p = log_power_score(res, precise_cfg["fsc_143_precise"]["good_ang"], precise_cfg["fsc_143_precise"]["bad_ang"],
                            precise_cfg["fsc_143_precise"]["points"], precise_cfg["fsc_143_precise"]["gamma"])
    ncc_p_gain = max(0.0, ncc - precise_cfg["ncc_map_precise"]["bad"])
    ncc_p_range = precise_cfg["ncc_map_precise"]["good"] - precise_cfg["ncc_map_precise"]["bad"]
    ncc_p = precise_cfg["ncc_map_precise"]["points"] * (min(1.0, ncc_p_gain / max(ncc_p_range, 1e-8)) ** precise_cfg["ncc_map_precise"]["gamma"])
    pose_p = log_power_score(pose_error_deg, precise_cfg["pose_angular_precise"]["good_deg"],
                             precise_cfg["pose_angular_precise"]["bad_deg"],
                             precise_cfg["pose_angular_precise"]["points"], precise_cfg["pose_angular_precise"]["gamma"])

    coarse_total = fsc_c + ncc_c + pose_c
    precise_total = fsc_p + ncc_p + pose_p
    detail = {
        "fsc_143_coarse": round3(fsc_c),
        "ncc_map_coarse": round3(ncc_c),
        "pose_angular_coarse": round3(pose_c),
        "fsc_143_precise": round3(fsc_p),
        "ncc_map_precise": round3(ncc_p),
        "pose_angular_precise": round3(pose_p),
        "coarse_total": round3(coarse_total),
        "precise_total": round3(precise_total),
        "resolution_ang": round3(res),
        "ncc_map": round3(ncc),
        "pose_error_deg": round3(pose_error_deg),
    }
    return coarse_total + precise_total, detail


def score_L8_resolution_physics(
    recon_vol: np.ndarray,
    true_vol: np.ndarray,
    pixel_size: float,
    declared_res_ang: float,
    cfg: dict[str, Any],
    h_mod,
) -> tuple[float, dict[str, Any]]:
    if recon_vol.shape != true_vol.shape:
        return 0.0, {"reason": "shape_mismatch"}
    box = recon_vol.shape[0]
    k_declared = 1.0 / max(declared_res_ang, 1e-6)
    freq_cutoff_pix = k_declared * box * pixel_size
    freq_cutoff_pix = max(1.0, min(float(box) / 2.0 - 1.0, freq_cutoff_pix))
    try:
        randomized = h_mod.phase_randomize_beyond(recon_vol, freq_cutoff_pix)
        _, fsc_rand = h_mod.fourier_shell_correlation(randomized, true_vol)
    except Exception as exc:
        return 0.0, {"reason": f"phase_randomize_failed: {exc}"}

    beyond_bins = np.arange(int(freq_cutoff_pix) + 1, len(fsc_rand))
    if len(beyond_bins) == 0:
        beyond_fsc = 0.0
    else:
        beyond_fsc = float(np.mean(np.abs(fsc_rand[beyond_bins])))
    threshold = cfg.get("L8_phase_random_threshold", 0.10)

    F_recon = np.fft.fftshift(np.fft.fftn(recon_vol.astype(np.float64)))
    center = box // 2
    coords = np.arange(box) - center
    Xr, Yr, Zr = np.meshgrid(coords, coords, coords, indexing="ij")
    r_arr = np.sqrt(Xr * Xr + Yr * Yr + Zr * Zr)
    beyond_mask = r_arr > freq_cutoff_pix
    inside_mask = (r_arr > 0) & (r_arr <= freq_cutoff_pix)
    beyond_power = float(np.mean(np.abs(F_recon[beyond_mask]) ** 2)) if beyond_mask.any() else 0.0
    inside_power = float(np.mean(np.abs(F_recon[inside_mask]) ** 2)) if inside_mask.any() else 1.0
    power_ratio = beyond_power / max(inside_power, 1e-12)
    signal_present = power_ratio > 0.02

    gate_ok = (beyond_fsc <= threshold) and signal_present
    detail = {
        "declared_resolution_ang": float(declared_res_ang),
        "freq_cutoff_pix": float(freq_cutoff_pix),
        "phase_random_fsc_beyond": round3(beyond_fsc),
        "phase_random_threshold": threshold,
        "beyond_over_inside_power_ratio": round3(power_ratio),
        "signal_present_beyond_cutoff": bool(signal_present),
        "gate_ok": bool(gate_ok),
    }
    if not gate_ok:
        return 0.0, detail

    try:
        oct_split = box // 4
        variances = []
        for ox in (0, box - oct_split):
            for oy in (0, box - oct_split):
                for oz in (0, box - oct_split):
                    patch = recon_vol[ox:ox + oct_split, oy:oy + oct_split, oz:oz + oct_split]
                    variances.append(float(np.var(patch)))
        v = np.array(variances)
        rel_var = float(np.std(v) / max(np.mean(v), 1e-8))
    except Exception:
        rel_var = 0.0
    denom = cfg.get("L8_local_variance_denominator", 0.05)
    consistency = max(0.0, 1.0 - rel_var / max(denom, 1e-8))
    consistency = min(1.0, consistency)
    detail["local_variance_relative"] = round3(rel_var)
    detail["local_consistency"] = round3(consistency)
    return 15.0 * consistency, detail


def evaluate(submission_dir: Path, case_dir: Path, scoring_dir: Path, output: Path) -> dict[str, Any]:
    sys.path.insert(0, str(scoring_dir))
    import hidden_forward_model as h_mod

    cfg = load_json(scoring_dir / "hidden_eval_config.json")

    detail: dict[str, Any] = {
        "total_score": 0.0,
        "raw_total": 0.0,
        "L1_format": 0.0,
        "L2_bounds": 0.0,
        "L3_public_sanity": 0.0,
        "L4_handedness": 0.0,
        "L5_symmetry": 0.0,
        "L6_method_workflow": 0.0,
        "L7_reconstruction": 0.0,
        "L8_resolution_physics": 0.0,
        "structural_gate_ok": False,
        "structural_gate_reason": "",
        "canary_leaks": [],
        "answer_summary": {},
        "lane_details": {},
        "warnings": [],
        "errors": [],
    }

    answer: dict[str, Any] | None = None
    answer_path = submission_dir / "answer.json"
    if answer_path.exists():
        try:
            answer = load_json(answer_path)
        except Exception as exc:
            detail["errors"].append(f"answer.json parse failed: {exc}")
    else:
        detail["errors"].append("answer.json not found")

    tokens = cfg.get("canary_tokens", []) + cfg.get("canary_tokens_short", [])
    leaks = scan_canary_leaks(submission_dir, tokens)
    detail["canary_leaks"] = leaks
    if leaks:
        detail["errors"].append(f"RL4 canary leak: {leaks[:5]}")
        _finalize(detail, output, gate_zero=True, reason="canary_leak")
        return detail

    gate_ok, gate_reason = structural_gate(submission_dir, answer)
    detail["structural_gate_ok"] = gate_ok
    detail["structural_gate_reason"] = gate_reason
    if not gate_ok or answer is None:
        _finalize(detail, output, gate_zero=True, reason=f"structural_gate: {gate_reason}")
        return detail

    detail["answer_summary"] = {
        "method_length": len(str(answer.get("method", ""))),
        "declared_symmetry": answer.get("declared_symmetry"),
        "declared_handedness": answer.get("declared_handedness"),
        "box_size_px": answer.get("box_size_px"),
        "pixel_size_ang": answer.get("pixel_size_ang"),
        "declared_resolution_ang": answer.get("declared_resolution_ang"),
    }

    sym_vocab = cfg.get("symmetry_vocabulary", ["C1", "C2", "C4", "D2", "D4", "O", "I"])
    hand_vocab = cfg.get("handedness_vocabulary", ["right", "left"])
    l1, l1_detail = score_L1_format(answer, sym_vocab, hand_vocab)
    l2, l2_detail = score_L2_bounds(answer, cfg)
    detail["L1_format"] = round3(l1)
    detail["L2_bounds"] = round3(l2)
    detail["lane_details"]["L1"] = l1_detail
    detail["lane_details"]["L2"] = l2_detail

    recon_path = submission_dir / str(answer.get("reconstruction_path", "reconstruction.mrc"))
    recon_vol = load_mrc_data(recon_path)
    true_vol = load_mrc_data(scoring_dir / "hidden_true_volume.mrc")

    pixel_size = safe_float(answer.get("pixel_size_ang"), cfg.get("pixel_size_ang", 2.5))
    if recon_vol is None or true_vol is None:
        detail["errors"].append("Failed to load recon or truth volume for scoring")
        _finalize(detail, output)
        return detail

    metrics = compute_reconstruction_metrics(recon_vol, true_vol, pixel_size, h_mod)
    detail["lane_details"]["recon_metrics"] = {k: round3(v) if isinstance(v, (int, float)) else v for k, v in metrics.items()}

    l3, l3_detail = score_L3_public_sanity(metrics, cfg)
    detail["L3_public_sanity"] = round3(l3)
    detail["lane_details"]["L3"] = l3_detail

    l4, l4_detail = score_L4_handedness(
        recon_vol, true_vol,
        str(answer.get("declared_handedness", "")),
        cfg.get("true_handedness", "right"),
        h_mod,
    )
    detail["L4_handedness"] = round3(l4)
    detail["lane_details"]["L4"] = l4_detail

    l5, l5_detail = score_L5_symmetry(
        str(answer.get("declared_symmetry", "")),
        cfg.get("true_symmetry", "C1"),
        h_mod,
    )
    detail["L5_symmetry"] = round3(l5)
    detail["lane_details"]["L5"] = l5_detail

    l6, l6_detail = score_L6_method_workflow(answer, submission_dir)
    detail["L6_method_workflow"] = round3(l6)
    detail["lane_details"]["L6"] = l6_detail

    pose_error_deg = 999.0
    pose_detail: dict[str, Any] = {}
    try:
        pose_path = submission_dir / str(answer.get("pose_file_path", "poses.star"))
        star = h_mod.read_star_poses(pose_path)
        true_pub = h_mod.read_star_poses(scoring_dir / "hidden_public_true_poses.star")
        n_compare = min(star["n"], true_pub["n"])
        if n_compare > 0:
            errs = h_mod.angular_error_deg(true_pub["poses_zyz_deg"][:n_compare], star["poses_zyz_deg"][:n_compare])
            pose_error_deg = float(np.mean(errs))
            pose_detail = {
                "n_compared": int(n_compare),
                "mean_deg": round3(pose_error_deg),
                "median_deg": round3(float(np.median(errs))),
                "p90_deg": round3(float(np.percentile(errs, 90))),
            }
        else:
            pose_detail = {"reason": "no_particles_to_compare"}
    except Exception as exc:
        pose_detail = {"reason": f"pose_scoring_failed: {exc}"}
        detail["warnings"].append(f"Pose scoring failed: {exc}")
    detail["lane_details"]["pose_error"] = pose_detail

    l7, l7_detail = score_L7_reconstruction(metrics, pose_error_deg, cfg)
    detail["L7_reconstruction"] = round3(l7)
    detail["lane_details"]["L7"] = l7_detail

    l5_declared_order = l5_detail.get("declared_order", 1)
    l5_truth_order = l5_detail.get("truth_order", 1)
    if l5_declared_order > l5_truth_order:
        cap_factor = cfg.get("RL3_symmetry_abuse_cap_factor", 0.5)
        precise_before = l7_detail["precise_total"]
        precise_after = precise_before * cap_factor
        detail["L7_reconstruction"] = round3((l7 - precise_before) + precise_after)
        detail["lane_details"]["L7"]["RL3_precise_cap_applied"] = True
        detail["lane_details"]["L7"]["RL3_cap_factor"] = cap_factor
        l7 = detail["L7_reconstruction"]

    l7_gate = cfg.get("L7_gate_for_L8", 10.0)
    if l7 >= l7_gate:
        declared_res = safe_float(answer.get("declared_resolution_ang"), 999.0)
        if not math.isfinite(declared_res) or declared_res <= 0:
            declared_res = 20.0
        l8, l8_detail = score_L8_resolution_physics(
            recon_vol, true_vol, pixel_size, declared_res, cfg, h_mod
        )
    else:
        l8 = 0.0
        l8_detail = {"gated_by_L7_below": l7_gate, "L7_score": l7}
    detail["L8_resolution_physics"] = round3(l8)
    detail["lane_details"]["L8"] = l8_detail

    raw_total = l1 + l2 + l3 + l4 + l5 + l6 + l7 + l8
    detail["raw_total"] = round3(raw_total)
    detail["total_score"] = round3(min(max(raw_total, 0.0), 100.0))

    _finalize(detail, output)
    return detail


def _finalize(detail: dict[str, Any], output: Path, gate_zero: bool = False, reason: str = "") -> None:
    if gate_zero:
        detail["total_score"] = 0.0
        detail["raw_total"] = 0.0
        if reason:
            detail["gate_reason"] = reason
    save_json(detail, output)
    total = float(detail["total_score"])
    print(f"CASE {TASK_NAME} OK score={total:.3f}")
    print(f"CASE {TASK_NAME} OK score={total:.3f}")
    print(f"RAW_TOTAL_SCORE {float(detail.get('raw_total', total)):.3f}")
    print(f"TOTAL_SCORE {total:.3f}")
    print("SCORE_BREAKDOWN", json.dumps({
        "raw_total": detail.get("raw_total"),
        "L1_format": detail.get("L1_format"),
        "L2_bounds": detail.get("L2_bounds"),
        "L3_public_sanity": detail.get("L3_public_sanity"),
        "L4_handedness": detail.get("L4_handedness"),
        "L5_symmetry": detail.get("L5_symmetry"),
        "L6_method_workflow": detail.get("L6_method_workflow"),
        "L7_reconstruction": detail.get("L7_reconstruction"),
        "L8_resolution_physics": detail.get("L8_resolution_physics"),
        "structural_gate_ok": detail.get("structural_gate_ok"),
        "structural_gate_reason": detail.get("structural_gate_reason"),
        "canary_leaks": detail.get("canary_leaks"),
        "gate_reason": detail.get("gate_reason", ""),
    }, ensure_ascii=False))
    print("ANSWER_SUMMARY", json.dumps(detail.get("answer_summary", {}), ensure_ascii=False))
    print("LANE_DETAILS", json.dumps(detail.get("lane_details", {}), ensure_ascii=False, default=str))

    l7_detail = detail.get("lane_details", {}).get("L7", {})
    structured_result = {
        "valid": True,
        "score": float(total),
        "pass_rate": 1.0 if total >= 30.0 else 0.0,
        "summary": (
            f"TOTAL_SCORE={total:.3f}; "
            f"L7_reconstruction={detail.get('L7_reconstruction', 0):.3f}; "
            f"resolution_ang={l7_detail.get('resolution_ang', 999)}; "
            f"ncc_map={l7_detail.get('ncc_map', 0)}; "
            f"pose_error_deg={l7_detail.get('pose_error_deg', 999)}; "
            f"structural_gate={detail.get('structural_gate_ok')}; "
            f"canary_leaks={len(detail.get('canary_leaks', []))}"
        ),
        "metrics": {
            "total_score": float(total),
            "raw_total": float(detail.get("raw_total", total)),
            "L1_format": detail.get("L1_format"),
            "L2_bounds": detail.get("L2_bounds"),
            "L3_public_sanity": detail.get("L3_public_sanity"),
            "L4_handedness": detail.get("L4_handedness"),
            "L5_symmetry": detail.get("L5_symmetry"),
            "L6_method_workflow": detail.get("L6_method_workflow"),
            "L7_reconstruction": detail.get("L7_reconstruction"),
            "L8_resolution_physics": detail.get("L8_resolution_physics"),
            "fsc_143_resolution_ang": l7_detail.get("resolution_ang"),
            "ncc_map": l7_detail.get("ncc_map"),
            "pose_error_deg": l7_detail.get("pose_error_deg"),
        },
        "details": [
            {"name": "L1_format", "status": "PASSED" if float(detail.get("L1_format", 0)) > 0 else "FAILED",
             "score": detail.get("L1_format"), "weight": 3, "message": "answer.json schema fields"},
            {"name": "L2_bounds", "status": "PASSED" if float(detail.get("L2_bounds", 0)) > 0 else "FAILED",
             "score": detail.get("L2_bounds"), "weight": 2, "message": "box/pixel/symmetry within ranges"},
            {"name": "L3_public_sanity", "status": "PASSED" if float(detail.get("L3_public_sanity", 0)) >= 5 else "FAILED",
             "score": detail.get("L3_public_sanity"), "weight": 10,
             "message": f"resolution {l7_detail.get('resolution_ang', 999)} A"},
            {"name": "L4_handedness", "status": "PASSED" if float(detail.get("L4_handedness", 0)) >= 5 else "FAILED",
             "score": detail.get("L4_handedness"), "weight": 5, "message": "chirality declaration vs truth"},
            {"name": "L5_symmetry", "status": "PASSED" if float(detail.get("L5_symmetry", 0)) >= 5 else "FAILED",
             "score": detail.get("L5_symmetry"), "weight": 5, "message": "point-group declaration"},
            {"name": "L6_method_workflow", "status": "PASSED" if float(detail.get("L6_method_workflow", 0)) >= 4 else "FAILED",
             "score": detail.get("L6_method_workflow"), "weight": 5, "message": "method text + workflow code"},
            {"name": "L7_reconstruction", "status": "PASSED" if float(detail.get("L7_reconstruction", 0)) >= 30 else "FAILED",
             "score": detail.get("L7_reconstruction"), "weight": 55,
             "message": f"FSC-0.143 res={l7_detail.get('resolution_ang', 999)}A NCC={l7_detail.get('ncc_map', 0)} pose={l7_detail.get('pose_error_deg', 999)}deg"},
            {"name": "L8_resolution_physics", "status": "PASSED" if float(detail.get("L8_resolution_physics", 0)) >= 10 else "FAILED",
             "score": detail.get("L8_resolution_physics"), "weight": 15, "message": "phase-random + local consistency gate"},
        ],
    }
    print(">>>>> Start Structured Result")
    print(json.dumps(structured_result, ensure_ascii=False))
    print(">>>>> End Structured Result")

    if detail.get("warnings"):
        print("WARNINGS", json.dumps(detail["warnings"], ensure_ascii=False))
    if detail.get("errors"):
        print("ERRORS", json.dumps(detail["errors"], ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission_dir", required=True)
    parser.add_argument("--case_dir", required=True)
    parser.add_argument("--scoring_dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    evaluate(
        submission_dir=Path(args.submission_dir),
        case_dir=Path(args.case_dir),
        scoring_dir=Path(args.scoring_dir),
        output=Path(args.output),
    )


if __name__ == "__main__":
    main()
