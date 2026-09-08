from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import affine_transform
from scipy.spatial.transform import Rotation as R


VOLTAGE_KV = 300.0
CS_MM = 2.7
AMPLITUDE_CONTRAST = 0.07


def electron_wavelength_ang(voltage_kv: float = VOLTAGE_KV) -> float:
    V = voltage_kv * 1000.0
    return 12.2643247 / math.sqrt(V * (1.0 + 0.978466e-6 * V))


def procedural_d2_volume(box: int = 64, pixel_size: float = 2.5, seed: int = 42) -> np.ndarray:
    seeds_ang = np.array(
        [
            [30.0, 12.0, 8.0],
            [8.0, 28.0, 16.0],
            [22.0, 4.0, 22.0],
        ],
        dtype=np.float64,
    )
    sigma_ang = 7.0
    vol = np.zeros((box, box, box), dtype=np.float32)
    coords = (np.arange(box) - box / 2.0) * pixel_size
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    for x0, y0, z0 in seeds_ang:
        orbit = [
            (x0, y0, z0),
            (x0, -y0, -z0),
            (-x0, y0, -z0),
            (-x0, -y0, z0),
        ]
        for px, py, pz in orbit:
            g = np.exp(-((X - px) ** 2 + (Y - py) ** 2 + (Z - pz) ** 2) / (2.0 * sigma_ang * sigma_ang))
            vol += g.astype(np.float32)
    return vol


def spherical_initial_model(box: int = 64, pixel_size: float = 2.5, radius_ang: float = 45.0) -> np.ndarray:
    coords = (np.arange(box) - box / 2.0) * pixel_size
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    r = np.sqrt(X * X + Y * Y + Z * Z)
    vol = np.exp(-((r / radius_ang) ** 6)).astype(np.float32)
    return vol


def rotation_matrix_from_zyz(alpha_deg: float, beta_deg: float, gamma_deg: float) -> np.ndarray:
    return R.from_euler("ZYZ", [alpha_deg, beta_deg, gamma_deg], degrees=True).as_matrix().astype(np.float32)


def rotate_volume(vol: np.ndarray, matrix: np.ndarray, order: int = 1) -> np.ndarray:
    box = vol.shape[0]
    center = np.array([(box - 1) / 2.0] * 3, dtype=np.float32)
    offset = center - matrix @ center
    return affine_transform(vol, matrix, offset=offset, order=order, mode="constant", cval=0.0)


def project_volume(vol: np.ndarray, matrix: np.ndarray, translation_pix: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    rotated = rotate_volume(vol, matrix)
    proj = rotated.sum(axis=2).astype(np.float32)
    tx, ty = translation_pix
    if abs(tx) > 1e-6 or abs(ty) > 1e-6:
        F = np.fft.fft2(proj)
        kx = np.fft.fftfreq(proj.shape[1])
        ky = np.fft.fftfreq(proj.shape[0])
        KX, KY = np.meshgrid(kx, ky, indexing="xy")
        shift = np.exp(-2j * np.pi * (KX * tx + KY * ty))
        proj = np.real(np.fft.ifft2(F * shift)).astype(np.float32)
    return proj


def compute_ctf_2d(
    box: int,
    pixel_size_ang: float,
    defocus_ang: float,
    voltage_kv: float = VOLTAGE_KV,
    cs_mm: float = CS_MM,
    amplitude_contrast: float = AMPLITUDE_CONTRAST,
) -> np.ndarray:
    lam = electron_wavelength_ang(voltage_kv)
    cs_ang = cs_mm * 1e7
    freqs = np.fft.fftfreq(box, d=pixel_size_ang)
    kx, ky = np.meshgrid(freqs, freqs, indexing="ij")
    k2 = kx * kx + ky * ky
    gamma = np.pi * lam * defocus_ang * k2 - 0.5 * np.pi * cs_ang * (lam ** 3) * (k2 ** 2)
    w = amplitude_contrast
    ctf = -w * np.sin(gamma) - math.sqrt(1.0 - w * w) * np.cos(gamma)
    return ctf.astype(np.float32)


def apply_ctf(image: np.ndarray, ctf_2d: np.ndarray) -> np.ndarray:
    F = np.fft.fft2(image)
    return np.real(np.fft.ifft2(F * ctf_2d)).astype(np.float32)


def add_gaussian_noise(image: np.ndarray, snr: float, rng: np.random.Generator) -> np.ndarray:
    signal_power = float(np.var(image))
    if signal_power <= 0.0:
        return image
    noise_power = signal_power / max(snr, 1e-8)
    noise = rng.normal(0.0, math.sqrt(noise_power), image.shape).astype(np.float32)
    return image + noise


def generate_particles(
    vol: np.ndarray,
    n: int,
    pixel_size: float,
    snr: float,
    defocus_range_ang: tuple[float, float] = (8000.0, 20000.0),
    seed: int = 0,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    box = vol.shape[0]
    particles = np.zeros((n, box, box), dtype=np.float32)
    rot_obj = R.random(n, random_state=rng.integers(0, 2**31 - 1))
    poses = rot_obj.as_euler("ZYZ", degrees=True).astype(np.float32)
    trans_pix = rng.uniform(-3.0, 3.0, size=(n, 2)).astype(np.float32)
    defoci = rng.uniform(defocus_range_ang[0], defocus_range_ang[1], size=n).astype(np.float32)
    matrices = rot_obj.as_matrix().astype(np.float32)
    for i in range(n):
        proj = project_volume(vol, matrices[i], (trans_pix[i, 0], trans_pix[i, 1]))
        ctf = compute_ctf_2d(box, pixel_size, defoci[i])
        proj_ctf = apply_ctf(proj, ctf)
        particles[i] = add_gaussian_noise(proj_ctf, snr, rng)
    trans_ang = trans_pix * pixel_size
    return {
        "particles": particles,
        "poses_zyz_deg": poses,
        "translations_ang": trans_ang.astype(np.float32),
        "defoci_ang": defoci,
    }


def fourier_shell_correlation(vol1: np.ndarray, vol2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    box = vol1.shape[0]
    F1 = np.fft.fftshift(np.fft.fftn(vol1.astype(np.float64)))
    F2 = np.fft.fftshift(np.fft.fftn(vol2.astype(np.float64)))
    center = box // 2
    coords = np.arange(box) - center
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    r = np.sqrt(X * X + Y * Y + Z * Z).astype(np.int32)
    max_r = box // 2
    fsc_arr = np.zeros(max_r + 1, dtype=np.float64)
    for i in range(max_r + 1):
        shell = r == i
        if not shell.any():
            fsc_arr[i] = 0.0
            continue
        a = F1[shell]
        b = F2[shell]
        num = float(np.real(np.sum(a * np.conj(b))))
        den = math.sqrt(float(np.sum(np.abs(a) ** 2) * float(np.sum(np.abs(b) ** 2))))
        fsc_arr[i] = num / max(den, 1e-30)
    return np.arange(max_r + 1, dtype=np.int32), fsc_arr


def resolution_at_threshold(fsc_arr: np.ndarray, box: int, pixel_size_ang: float, threshold: float = 0.143) -> float:
    if len(fsc_arr) <= 1:
        return 1e6
    for i in range(1, len(fsc_arr)):
        if fsc_arr[i] < threshold:
            k = i / (box * pixel_size_ang)
            if k <= 0:
                return 1e6
            return 1.0 / k
    k = (len(fsc_arr) - 1) / (box * pixel_size_ang)
    return 1.0 / max(k, 1e-6)


def ncc_volumes(vol1: np.ndarray, vol2: np.ndarray) -> float:
    v1 = vol1.astype(np.float64).ravel()
    v2 = vol2.astype(np.float64).ravel()
    v1 -= v1.mean()
    v2 -= v2.mean()
    den = math.sqrt(float((v1 * v1).sum()) * float((v2 * v2).sum()))
    if den <= 0:
        return 0.0
    return float((v1 * v2).sum() / den)


def angular_error_deg(true_eulers: np.ndarray, pred_eulers: np.ndarray) -> np.ndarray:
    r_true = R.from_euler("ZYZ", true_eulers, degrees=True)
    r_pred = R.from_euler("ZYZ", pred_eulers, degrees=True)
    r_delta = r_true.inv() * r_pred
    rotvec = r_delta.as_rotvec()
    angles = np.linalg.norm(rotvec, axis=-1) * 180.0 / math.pi
    return np.minimum(angles, 360.0 - angles)


def symmetry_matrices(sym: str) -> list[np.ndarray]:
    sym = sym.upper().strip()
    I3 = np.eye(3, dtype=np.float32)
    Rx = R.from_rotvec([math.pi, 0, 0]).as_matrix().astype(np.float32)
    Ry = R.from_rotvec([0, math.pi, 0]).as_matrix().astype(np.float32)
    Rz = R.from_rotvec([0, 0, math.pi]).as_matrix().astype(np.float32)
    if sym == "C1":
        return [I3]
    if sym == "C2":
        return [I3, Rz]
    if sym == "C4":
        return [R.from_rotvec([0, 0, i * math.pi / 2]).as_matrix().astype(np.float32) for i in range(4)]
    if sym == "D2":
        return [I3, Rx, Ry, Rz]
    if sym == "D4":
        c4 = [R.from_rotvec([0, 0, i * math.pi / 2]).as_matrix().astype(np.float32) for i in range(4)]
        c4d = [Rx @ m for m in c4]
        return c4 + c4d
    if sym == "O":
        gen = R.create_group("O").as_matrix().astype(np.float32)
        return [gen[i] for i in range(gen.shape[0])]
    if sym == "I":
        gen = R.create_group("I").as_matrix().astype(np.float32)
        return [gen[i] for i in range(gen.shape[0])]
    return [I3]


def symmetry_order(sym: str) -> int:
    return len(symmetry_matrices(sym))


def symmetrize_volume(vol: np.ndarray, sym: str) -> np.ndarray:
    mats = symmetry_matrices(sym)
    if len(mats) == 1:
        return vol.copy()
    accum = np.zeros_like(vol, dtype=np.float64)
    for m in mats:
        accum += rotate_volume(vol.astype(np.float32), m.astype(np.float32)).astype(np.float64)
    return (accum / len(mats)).astype(np.float32)


def detect_symmetry(vol: np.ndarray, candidates: list[str]) -> tuple[str, dict[str, float]]:
    scores: dict[str, float] = {}
    for sym in candidates:
        sym_vol = symmetrize_volume(vol, sym)
        scores[sym] = ncc_volumes(vol, sym_vol)
    best = max(scores.items(), key=lambda kv: (kv[1], -symmetry_order(kv[0])))
    return best[0], scores


def flip_z(vol: np.ndarray) -> np.ndarray:
    return vol[:, :, ::-1].copy()


def write_star_poses(
    path: Path,
    poses_zyz_deg: np.ndarray,
    translations_ang: np.ndarray,
    optics_group: int = 1,
    pixel_size_ang: float = 2.5,
    voltage_kv: float = VOLTAGE_KV,
    cs_mm: float = CS_MM,
    amplitude_contrast: float = AMPLITUDE_CONTRAST,
    box_size: int = 64,
) -> None:
    n = poses_zyz_deg.shape[0]
    lines: list[str] = []
    lines.append("# RELION STAR 3.1")
    lines.append("")
    lines.append("data_optics")
    lines.append("")
    lines.append("loop_")
    lines.append("_rlnOpticsGroup #1")
    lines.append("_rlnVoltage #2")
    lines.append("_rlnSphericalAberration #3")
    lines.append("_rlnAmplitudeContrast #4")
    lines.append("_rlnImagePixelSize #5")
    lines.append("_rlnImageSize #6")
    lines.append(f"{optics_group} {voltage_kv:.2f} {cs_mm:.2f} {amplitude_contrast:.4f} {pixel_size_ang:.4f} {box_size}")
    lines.append("")
    lines.append("data_particles")
    lines.append("")
    lines.append("loop_")
    lines.append("_rlnImageId #1")
    lines.append("_rlnAngleRot #2")
    lines.append("_rlnAngleTilt #3")
    lines.append("_rlnAnglePsi #4")
    lines.append("_rlnOriginXAngst #5")
    lines.append("_rlnOriginYAngst #6")
    lines.append("_rlnOpticsGroup #7")
    for i in range(n):
        rot, tilt, psi = poses_zyz_deg[i]
        tx, ty = translations_ang[i]
        lines.append(f"{i} {float(rot):.4f} {float(tilt):.4f} {float(psi):.4f} {float(tx):.4f} {float(ty):.4f} {optics_group}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_star_poses(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for ln in lines:
        s = ln.strip()
        if s.startswith("data_"):
            current = s[len("data_"):]
            blocks[current] = []
        elif current is not None:
            blocks[current].append(ln)
    if "particles" not in blocks:
        raise ValueError("No data_particles block in STAR file")
    body = blocks["particles"]
    columns: list[str] = []
    rows: list[list[str]] = []
    in_loop = False
    for ln in body:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s == "loop_":
            in_loop = True
            columns = []
            continue
        if in_loop and s.startswith("_"):
            name = s.split()[0][1:]
            columns.append(name)
            continue
        if in_loop and columns:
            tokens = s.split()
            if len(tokens) < len(columns):
                continue
            rows.append(tokens[: len(columns)])
    if not columns or not rows:
        raise ValueError("STAR particles block has no rows")
    col_idx = {c: i for i, c in enumerate(columns)}
    required = ["rlnAngleRot", "rlnAngleTilt", "rlnAnglePsi", "rlnOriginXAngst", "rlnOriginYAngst"]
    for r in required:
        if r not in col_idx:
            raise ValueError(f"STAR file missing required column {r}")
    n = len(rows)
    poses = np.zeros((n, 3), dtype=np.float32)
    trans = np.zeros((n, 2), dtype=np.float32)
    for i, row in enumerate(rows):
        poses[i, 0] = float(row[col_idx["rlnAngleRot"]])
        poses[i, 1] = float(row[col_idx["rlnAngleTilt"]])
        poses[i, 2] = float(row[col_idx["rlnAnglePsi"]])
        trans[i, 0] = float(row[col_idx["rlnOriginXAngst"]])
        trans[i, 1] = float(row[col_idx["rlnOriginYAngst"]])
    return {"poses_zyz_deg": poses, "translations_ang": trans, "n": n}


def back_project(
    particles: np.ndarray,
    poses_zyz_deg: np.ndarray,
    translations_ang: np.ndarray | None,
    pixel_size_ang: float,
    defoci_ang: np.ndarray | None = None,
    apply_ctf_correction: bool = True,
    max_particles: int | None = None,
) -> np.ndarray:
    n_total = particles.shape[0]
    n = n_total if max_particles is None else min(n_total, max_particles)
    box = particles.shape[1]
    accum = np.zeros((box, box, box), dtype=np.complex128)
    weight = np.zeros((box, box, box), dtype=np.float64)
    kx = np.fft.fftfreq(box)
    ky = np.fft.fftfreq(box)
    KX, KY = np.meshgrid(kx, ky, indexing="ij")
    coords_2d = np.stack([KX.ravel(), KY.ravel(), np.zeros(box * box, dtype=np.float64)], axis=1)
    for i in range(n):
        img = particles[i].astype(np.float32)
        if translations_ang is not None:
            tx = float(translations_ang[i, 0]) / pixel_size_ang
            ty = float(translations_ang[i, 1]) / pixel_size_ang
            if abs(tx) > 1e-6 or abs(ty) > 1e-6:
                F_pre = np.fft.fft2(img)
                shift = np.exp(2j * np.pi * (KX * tx + KY * ty))
                img = np.real(np.fft.ifft2(F_pre * shift)).astype(np.float32)
        F = np.fft.fft2(np.fft.ifftshift(img))
        if apply_ctf_correction and defoci_ang is not None:
            ctf = compute_ctf_2d(box, pixel_size_ang, float(defoci_ang[i]))
            F = F * ctf
            w2d = ctf * ctf + 1e-3
        else:
            w2d = np.ones_like(F, dtype=np.float64)
        mat = rotation_matrix_from_zyz(*poses_zyz_deg[i]).astype(np.float64)
        rot_coords = mat @ coords_2d.T
        gx = (rot_coords[0] * box).reshape(box, box)
        gy = (rot_coords[1] * box).reshape(box, box)
        gz = (rot_coords[2] * box).reshape(box, box)
        fx = np.floor(gx); fy = np.floor(gy); fz = np.floor(gz)
        dx = gx - fx; dy = gy - fy; dz = gz - fz
        for ox in (0, 1):
            for oy in (0, 1):
                for oz in (0, 1):
                    ix = np.mod((fx + ox).astype(np.int64), box)
                    iy = np.mod((fy + oy).astype(np.int64), box)
                    iz = np.mod((fz + oz).astype(np.int64), box)
                    wx = dx if ox else (1.0 - dx)
                    wy = dy if oy else (1.0 - dy)
                    wz = dz if oz else (1.0 - dz)
                    w_lin = (wx * wy * wz).astype(np.float64)
                    np.add.at(accum, (ix, iy, iz), F * w_lin)
                    np.add.at(weight, (ix, iy, iz), w2d * w_lin)
    weight = np.where(weight <= 0, 1.0, weight)
    F3 = accum / weight
    vol_raw = np.real(np.fft.ifftn(F3)).astype(np.float32)
    return np.fft.fftshift(vol_raw)


def phase_randomize_beyond(vol: np.ndarray, freq_cutoff_pix: float) -> np.ndarray:
    box = vol.shape[0]
    F = np.fft.fftshift(np.fft.fftn(vol.astype(np.float64)))
    center = box // 2
    coords = np.arange(box) - center
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    r = np.sqrt(X * X + Y * Y + Z * Z)
    mask = r > freq_cutoff_pix
    rng = np.random.default_rng(12345)
    random_phase = rng.uniform(-math.pi, math.pi, size=vol.shape)
    magnitudes = np.abs(F)
    new_F = np.where(mask, magnitudes * np.exp(1j * random_phase), F)
    return np.real(np.fft.ifftn(np.fft.ifftshift(new_F))).astype(np.float32)
