# TRUTH — cryoem_single_particle_reconstruction (private oracle)

## Do not ship to agent

This file is oracle-only. It documents the hidden ground-truth structure,
canary bindings, and reproduction instructions.

## Canary tokens (RL4)

```
CRYOEM_CANARY_APOFERRITIN_K7X3M9Q2
CRYOEM_CANARY_ALDOLASE_R5V1B8N4
CRYOEM_CANARY_PDB_LOOKUP_L9P6T2W3
```

Also blocked as short substrings: `7A6A`, `6ALD`, `EMD-12358`, `EMD-7551`.

If any of these appear in agent-visible bytes under
`/home/workspace/cryoem_reconstruction/`, evaluate.py sets total_score=0.

The three long tokens are ONLY present in:
- `solution/TRUTH.md` (this file)
- `tests/scoring/hidden_eval_config.json` (judge internals)
- `solution/rubrics.json` (oracle rubric)
- `solution/grounding.yaml` (oracle provenance)

They are NEVER in the agent workspace image.

## Ground-truth density (NOT PDB-derived)

- **Source**: procedural three-Gaussian mixture, D2-symmetrized.
- **Rationale**: contract explicitly forbids any PDB lift. Using a purely
  synthetic density means the RL4 canary gate is meaningful — no adversarial
  PDB lookup can hit the target.
- **Gaussian seeds (Å)**: `(30,12,8)`, `(8,28,16)`, `(22,4,22)`.
- **Gaussian sigma**: 7 Å.
- **D2 orbit**: each seed spawns 4 mates: `(x,y,z)`, `(x,-y,-z)`, `(-x,y,-z)`,
  `(-x,-y,z)`. Total = 12 Gaussian centers.
- **Box**: 64³ voxels, pixel size 2.5 Å.
- **File**: `tests/scoring/hidden_true_volume.mrc`.

## Public dataset (agent-visible)

- 500 particles, SNR=0.1, seed=111.
- Random SO(3) poses, translations ±3 pixels, defoci 8000-20000 Å.
- **Poses ARE visible** in the npz under `poses_zyz_deg`. Agents may use
  them directly. The reference solver does exactly this.
- File: `environment/public_micrographs.npz`.

## Hidden dataset (judge-only)

- 5000 particles, SNR=0.1, seed=222.
- Not accessed at scoring time (retained for future robustness sampling and
  documentation of full-scale simulator behavior).
- File: `tests/scoring/hidden_micrographs.npz`.

## Reference solver behavior

`python solution/reference_solver.py --workspace <task_root>`

Uses public poses + Wiener CTF-corrected Fourier back-projection + D2
symmetrization. Adds 25° RMS pose noise by default to simulate the accuracy
of common-lines pose estimation. Result: ~50 pts (mid-band of contract's
[30, 55] target).

Alternative configurations:
- `--pose_noise_deg 0 --symmetry D2` → ~77 pts (near-oracle upper bound)
- `--pose_noise_deg 25 --symmetry C1` → ~37 pts (no sym detection)
- `--n_particles 200 --pose_noise_deg 25` → ~45 pts (data-limited)

## Reproducing bundle from scratch

```
cd seed/build/cryoem_single_particle_reconstruction
python _generate_data.py        # regenerates volumes + micrographs + STAR
python solution/recompute.py    # regenerates rubrics.json from grounding.yaml
```

## Judge verification loop

```
# baseline
python environment/baseline_solver.py    # in a copy of environment/
python tests/scoring/evaluate.py --submission_dir <workspace> \
       --case_dir <workspace> \
       --scoring_dir tests/scoring \
       --output <workspace>/score.json
# expects: TOTAL_SCORE 10 (± calibration drift)

# reference
python solution/reference_solver.py --workspace <workspace>
python tests/scoring/evaluate.py ... (same as above)
# expects: TOTAL_SCORE ~50
```

## Known deviations from contract (see FIXES_APPLIED.md)

1. NCC scoring uses masked + Gaussian-filtered volumes (contract used raw NCC).
2. Baseline uniform-sphere lands at ~10 pts (contract said ~5); this is closer
   to reality after honest tuning.
3. Reference uses provided public poses; contract described "aspire common-lines"
   which is heavyweight for CPU-only 12h and unnecessary since public poses are
   visible to the agent by contract design.
4. L8 gate added a "signal_present_beyond_cutoff" secondary check so a smooth
   sphere cannot exploit the phase-randomization test trivially.
