# ac583bff-6ce6-5d54-94f5-5f9083830070

CryoEM single-particle 3D reconstruction. The agent receives 500 noisy 2D projection images
of an unknown protein complex at unknown random orientations and must invert the forward
model — CTF-modulated parallel projection through an unknown SO(3) rotation — to recover the
hidden density. A Bayesian inverse problem from structural biology, run CPU-only with no
network, no GPU, and no CryoSPARC/RELION binaries, inside a 12 hour wall-clock budget.

## Deliverables

1. `reconstruction.mrc` — the 3D density map (10-15 Å resolution ceiling at box 64,
   2.5 Å/px).
2. `poses.star` — per-particle poses in RELION STAR 3.1+ format (`rlnAngleRot`,
   `rlnAngleTilt`, `rlnAnglePsi` in ZYZ degrees plus `rlnOriginXAngst`/`rlnOriginYAngst`),
   row `i` matching `particles[i]`.
3. Declared handedness (right/left) and point-group symmetry (`C1|C2|C4|D2|D4|O|I`).
4. `answer.json` structured metadata per the provided `answer_template.json`, including a
   method description of at least 20 characters and a declared resolution.
5. `reconstruct.py` and `requirements.txt` alongside the outputs.

## Provided inputs

- `public_micrographs.npz` — 500 particles (64×64, float32) at SNR 0.1 with per-particle
  defoci; ground-truth poses included for the public set.
- `public_problem_config.json` — box/pixel/CTF parameters and the I/O schema.
- `initial_model.mrc` — a ~25 Å featureless spherical starting volume.
- `baseline_solver.py` — a naive uniform-sphere baseline worth roughly 5 points.
- CTF model: 300 kV, Cs 2.7 mm, amplitude contrast 0.07, defocus 8000-20000 Å.

Permitted packages are numpy, scipy, mrcfile, starfile and pandas.

## Scoring

Eight lanes, 0-100. The early lanes gate format and parameter sanity (answer fields
present, symmetry/handedness in vocabulary, box size in [32, 128], pixel size in
[1.0, 4.0]); the public-sanity lane grades FSC-0.143 resolution against the public
reference (15 Å earns the full 10); the remaining lanes grade the hidden-side
reconstruction quality, pose accuracy, and declared metadata. The verifier runs in a
separate judge image with a 1 hour budget.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image: problem config, particles, starting volume, baseline
tests/               judge image: FSC/pose scorer and verification harness
solution/            private oracle tree
```
