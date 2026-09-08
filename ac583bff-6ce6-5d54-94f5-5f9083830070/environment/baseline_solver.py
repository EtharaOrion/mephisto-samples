import json
from pathlib import Path

import mrcfile
import numpy as np

CFG_PATH = Path("public_problem_config.json")
with open(CFG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

BOX = int(cfg["box_size_px"])
PIXEL = float(cfg["pixel_size_ang"])


def uniform_sphere(box: int, pixel: float, radius_ang: float = 60.0) -> np.ndarray:
    coords = (np.arange(box) - box / 2.0) * pixel
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    r = np.sqrt(X * X + Y * Y + Z * Z)
    return (r <= radius_ang).astype(np.float32)


vol = uniform_sphere(BOX, PIXEL)
with mrcfile.new("reconstruction.mrc", overwrite=True) as m:
    m.set_data(vol)
    m.voxel_size = PIXEL

npz = np.load("public_micrographs.npz")
n_particles = int(npz["particles"].shape[0])
n_cols = 5
star_lines = [
    "# RELION STAR 3.1",
    "",
    "data_optics",
    "",
    "loop_",
    "_rlnOpticsGroup #1",
    "_rlnVoltage #2",
    "_rlnSphericalAberration #3",
    "_rlnAmplitudeContrast #4",
    "_rlnImagePixelSize #5",
    "_rlnImageSize #6",
    f"1 300.0 2.7 0.07 {PIXEL:.4f} {BOX}",
    "",
    "data_particles",
    "",
    "loop_",
    "_rlnImageId #1",
    "_rlnAngleRot #2",
    "_rlnAngleTilt #3",
    "_rlnAnglePsi #4",
    "_rlnOriginXAngst #5",
    "_rlnOriginYAngst #6",
]
for i in range(n_particles):
    star_lines.append(f"{i} 0.0 0.0 0.0 0.0 0.0")
Path("poses.star").write_text("\n".join(star_lines) + "\n", encoding="utf-8")

answer = {
    "method": "baseline uniform-density sphere at expected particle radius; zero poses; NO refinement. Replace with real back-projection + iterative refinement pipeline.",
    "reconstruction_path": "reconstruction.mrc",
    "pose_file_path": "poses.star",
    "declared_symmetry": "C1",
    "declared_handedness": "right",
    "box_size_px": BOX,
    "pixel_size_ang": PIXEL,
    "declared_resolution_ang": 30.0
}
Path("answer.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
print(f"Baseline: wrote reconstruction.mrc (box {BOX}), poses.star ({n_particles} particles), answer.json")
