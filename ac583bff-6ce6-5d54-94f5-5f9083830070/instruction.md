# CryoEM Single-Particle Reconstruction

## Task

You are given 500 noisy 2D cryoEM projection images of an unknown 3D protein
complex at unknown random orientations. Your task is to:

1. Reconstruct a 3D density map (`reconstruction.mrc`).
2. Estimate per-particle poses (`poses.star`).
3. Declare the handedness (right vs left) and point-group symmetry.
4. Produce structured metadata in `answer.json`.

This is a Bayesian inverse problem. A forward model (CTF-modulated projection
through unknown SO(3) rotation) generates the observed particles from a hidden
ground-truth density map. Your job is to invert that model.

## Compute budget

- **CPU-only**, 12 hours wall-clock.
- No network access. No GPU. No CryoSPARC/RELION binaries.
- Allowed: numpy, scipy, mrcfile, starfile, pandas.

## Provided files (in task root)

- `public_problem_config.json` — box/pixel/CTF parameters and I/O schema.
- `public_micrographs.npz` — 500 particles at SNR=0.1 with ground-truth poses.
  Keys: `particles` (500,64,64) float32, `poses_zyz_deg` (500,3), `defoci_ang`
  (500,) float32, `pixel_size_ang` float, `box_size_px` int.
- `initial_model.mrc` — ~25A featureless spherical starting volume at box 64.
- `answer_template.json` — required schema.
- `baseline_solver.py` — writes a naive uniform-sphere answer.json + reconstruction
  (~5 pts baseline).
- `requirements.txt` — permitted packages.

## Required output schema (`answer.json`)

```json
{
  "method": "at least 20 characters describing your pipeline",
  "reconstruction_path": "reconstruction.mrc",
  "pose_file_path": "poses.star",
  "declared_symmetry": "C1|C2|C4|D2|D4|O|I",
  "declared_handedness": "right|left",
  "box_size_px": 64,
  "pixel_size_ang": 2.5,
  "declared_resolution_ang": 25.0
}
```

## Pose file (`poses.star`)

RELION STAR 3.1+ format. Required columns:
- `rlnAngleRot` (alpha, ZYZ, degrees)
- `rlnAngleTilt` (beta, ZYZ, degrees)
- `rlnAnglePsi` (gamma, ZYZ, degrees)
- `rlnOriginXAngst` (x translation, Angstrom)
- `rlnOriginYAngst` (y translation, Angstrom)

Row `i` MUST correspond to `particles[i]` in `public_micrographs.npz`.

## Forward model

Parallel projection along +Z after rotating the volume by ZYZ Euler angles
`(alpha, beta, gamma)`. CTF applied in Fourier space with:

```
gamma(k) = pi * lambda * defocus * k^2 - 0.5 * pi * Cs * lambda^3 * k^4
CTF(k)   = -w * sin(gamma) - sqrt(1-w^2) * cos(gamma)
```

Parameters: voltage=300 kV, Cs=2.7 mm, amplitude_contrast (w) = 0.07,
defocus range = [8000, 20000] Å. See `public_problem_config.json`.

## Scoring lanes (100 pts total)

| Lane | Name | Points | Threshold / Rule |
|------|------|--------|------------------|
| L1 | Answer Format | 3 | All required fields present, method >= 20 chars, symmetry in vocab, handedness in vocab |
| L2 | Parameter Bounds | 2 | box_size_px in [32,128], pixel_size_ang in [1.0,4.0], declared_symmetry in vocab |
| L3 | Public Sanity | 10 | FSC-0.143 resolution on public reference. Good = 15A -> 10 pts; Bad = 30A -> 0 pts; smooth linear |
| L4 | Handedness Gate | 5 | Correct declaration -> 5; wrong but flippable -> 2; undetectable -> 0 |
| L5 | Symmetry Correctness | 5 | Exact match -> 5; lower declared than true -> 3; higher declared (abuse) -> 0 (RL3) |
| L6 | Method Workflow | 5 | method >= 20 chars AND >= 1 non-baseline .py file present AND text mentions recon primitives (fft/back-project/refine/projection/ctf) |
| L7 | Reconstruction (DOMINANT) | 55 | Coarse (25): FSC-0.143 coarse 10 (good=15A, bad=30A, gamma=1.4); NCC coarse 8 (good=0.30, bad=0.05); pose-angular coarse 7 (good=15deg, bad=45deg). Precise (30): FSC-0.143 precise 15 (good=10A, bad=18A, gamma=2.2); NCC precise 10 (good=0.60, bad=0.25); pose-angular precise 5 (good=5deg, bad=15deg) |
| L8 | Resolution Physics | 15 | Gated by L7 >= 10. Phase-randomized FSC beyond declared_resolution_ang must be <=0.10. Local resolution consistency reward |

## Red lines

- **RL2 (structural gate, catastrophic)**: missing reconstruction.mrc OR
  malformed answer.json OR poses.star fails STAR parse -> total = 0.
- **RL3 (symmetry abuse)**: declared symmetry ORDER > true order caps L7 precise
  at 0.5x and zeroes L5.
- **RL4 (PDB leak, catastrophic)**: known canary tokens in any agent-visible
  file -> total = 0.

## Baseline workflow (mandatory first step)

```bash
python baseline_solver.py
```

This writes a valid low-score `answer.json` + `reconstruction.mrc`. It gives
you a working schema to iterate on. Score will be small.

Then implement your reconstruction in a NEW file (e.g. `reconstruct.py`) and
overwrite `answer.json`, `reconstruction.mrc`, `poses.star` before submission.

## Rules

- Do not read or reference any hidden scoring files (they aren't accessible anyway).
- Do not hard-code the ground-truth density or poses.
- Do not modify judge files.
- The judge only reads `answer.json`, `reconstruction.mrc`, `poses.star`,
  and non-baseline `*.py` files in the task root.
- After every meaningful refinement iteration, overwrite `answer.json` and
  `reconstruction.mrc` — the judge only reads the final file state.

## Suggested approach

1. Run `python baseline_solver.py` to bootstrap a legal submission.
2. Load `public_micrographs.npz` and the known poses.
3. Implement direct Fourier back-projection: for each particle, insert its
   CTF-corrected Fourier transform into a 3D volume at the correct rotation.
4. Symmetrize if you can detect the point group.
5. Iterate: refine poses via projection matching, refine volume, repeat.
6. Update `answer.json` with your declared symmetry, handedness, and box/pixel.
