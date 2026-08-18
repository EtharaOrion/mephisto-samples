
<!--
CANARY-BLOCK-BEGIN
none: derived/public-benchmark task; the graded workloads are generated at grade time
by compute_reward.py from a fixed RNG seed and compared against a same-machine C baseline,
so there is no synthesized per-task secret panel to leak.
CANARY-BLOCK-END
-->

## What this task grades

The solver re-implements FFmpeg's `libswscale` (image scaling and pixel-format conversion)
in Rust or Zig as a C-ABI shared library exporting `swscale_create`, `swscale_process`, and
`swscale_destroy`. The judge rebuilds the submission from source, loads it through that ABI,
and compares its output against a statically linked C-only FFmpeg baseline on the same
machine. No upstream SIMD path participates: the baseline is FFmpeg 7.1 built `--disable-asm`.

Reward: a hard correctness gate, then a speed ratio, then a fixed monotonic map into `[0,1]`.

    C = per-plane PSNR over 30 hidden workloads
        threshold 60 dB for same-size format conversion, 40 dB when scaling
        a byte-exact plane yields PSNR = infinity and passes any threshold
        any workload below threshold  ->  R = 0, benchmark not run
    S = geometric_mean(baseline_time / candidate_time) over the benchmark workloads
    R = clip(43 * ln(S) / ln(14.155), 0, 100) / 100

`S = 1.0` means the candidate matches the C scalar baseline. `R` is what `reward.json` emits
and what the harness reads; the raw `S` is retained in `additional_data.raw_speedup`.

## Ordered golden trajectory

Each step names the action, the state it establishes, and the graded subscore it serves. The
grader emits two subscores, `correctness` and `speedup`; this task has no per-step checker set.

| # | Action                                            | Established state                                                     | Subscore        |
| - | ------------------------------------------------- | --------------------------------------------------------------------- | --------------- |
| 1 | read`swscale_api.h` and the task statement      | the solver knows the three C-ABI entry points and the buffer contract | `correctness` |
| 2 | parse the pixel-format descriptors                | per-format plane count, subsampling, and stride layout established    | `correctness` |
| 3 | implement same-size format conversion             | YUV to RGB and RGB to YUV using FFmpeg's limited-range coefficients   | `correctness` |
| 4 | match FFmpeg's rounding and chroma siting exactly | per-plane PSNR at or above 60 dB on conversion workloads              | `correctness` |
| 5 | implement scaling with filter generation          | bilinear and nearest-neighbour resampling at arbitrary ratios         | `correctness` |
| 6 | hold fidelity under resampling                    | per-plane PSNR at or above 40 dB on scaling workloads                 | `correctness` |
| 7 | build as a`cdylib` exporting the C ABI          | the judge can load and call the candidate library                     | `correctness` |
| 8 | vectorize the hot loops with portable SIMD        | geometric-mean speedup above 1.0 against the C baseline               | `speedup`     |
| 9 | keep every workload correct while vectorized      | the gate still passes, so the speedup term is reachable at all        | both            |

Step 9 is the whole difficulty. The gate is absolute: one failing workload discards the entire
speed result, so a fast but slightly wrong kernel scores exactly the same as no submission.

## Rejected routes

These routes are named in `seed/contract.yaml` as control obligations. They are **declared, not
executable**: this bundle ships no runnable control fixtures, so the rejections below are
expectations recorded by the author, not measurements the gate reproduces.

| Rejected route                                                              | Why it fails                                                                                   | Bound control          |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------- |
| link or dynamically load the system FFmpeg`libswscale` and delegate to it | the grader deletes the system FFmpeg libraries before scoring, so the delegate disappears      | declared, no fixture   |
| copy upstream assembly or intrinsics from FFmpeg                            | the baseline is built`--disable-asm`; correctness is judged against C output, not asm output | declared, no fixture   |
| return the input buffer unchanged                                           | PSNR collapses on every conversion workload                                                    | `C_correctness_fail` |
| emit a constant or single-colour output                                     | PSNR collapses on every workload                                                               | `C_correctness_fail` |
| skip the work and return quickly to farm the speed term                     | the correctness gate runs first and zeroes the reward before the benchmark                     | `C_correctness_fail` |
| submit the untouched scaffold                                               | correct but slower than the baseline, so the map floors it to 0                                | `C_scaffold`         |
| submit nothing                                                              | no library to load; reward 0                                                                   | declared, no fixture   |

## Measured anchors

Measured on Apple Silicon arm64, 10 cores, 16 GiB, Docker native with no emulation, on
2026-08-12. These are recorded measurements, never predictions. None of them is difficulty
evidence: only the external signed pilot establishes difficulty.

| Control                                             | Raw speedup`S` | Reward`R` |
| --------------------------------------------------- | ---------------- | ----------- |
| incorrect submission (gate fails)                   | not run          | 0.000000    |
| shipped reference scaffold, 30/30 correctness       | 0.7101x          | 0.000000    |
| Opus 4.8, best of 14 pilot rollouts at 90 min       | 2.3833x          | 0.140921    |
| frontier-defeat floor                               | 8.13x            | 0.340000    |
| `log_anchor` calibration point                    | 14.155x          | 0.430000    |
| upstream expert reference                           | 21.472x          | 0.497611    |
| Opus 5, best of one 12 h run (supersedes the pilot) | 122.8x           | 0.780520    |

The reference scaffold is correct and still scores 0. It is slower than the C baseline, so the
map floors it. Correctness alone earns nothing on this task.

The signed pilot (`memory/proofs/pilot-ffmpeg_swscale_reimplementation-attempt1.yaml`) records
0 of 14 Opus 4.8 rollouts at or above the 0.34 floor, disposition `WATCH` under
`HOLD:UNDERPOWERED_PILOT` for single-cohort. The later Opus 5 run at 0.780520 clears that floor,
so the frontier-defeat claim holds against Opus 4.8 and not against the current frontier.

## Anti-shortcut posture

| Mechanism                                                                                                                  | Where it lives                              | Verifiable from committed bytes          |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------- |
| correctness zero-gate before any timing                                                                                    | `tests/scoring/compute_reward.py`         | yes                                      |
| workloads generated at grade time from a fixed seed (`0xDEADBEEF_CAFEBABE`), so every submission faces the identical set | `tests/scoring/compute_reward.py`         | yes                                      |
| baseline statically linked, survives deletion of system FFmpeg                                                             | `tests/Dockerfile`                        | yes                                      |
| baseline sha256 pinned to`/verifier-data/baseline_hash.txt`                                                              | written at image build,`tests/Dockerfile` | build step yes, enforcement no           |
| deletion of the reference FFmpeg and system libs before scoring                                                            | the image's inner`/opt/tests/test.sh`     | **no, that file is not committed** |
| hash check of the baseline before scoring                                                                                  | the image's inner`/opt/tests/test.sh`     | **no, that file is not committed** |

The last two rows are the honest limit of this bundle. `compute_reward.py` contains no
`baseline_hash` comparison and no deletion call, so those protections cannot be confirmed from
the bytes this repository ships. They may be implemented in `/opt/tests/test.sh` inside the
pinned judge image, which the bundle does not commit. Do not present them as established until
that file is committed or the enforcement is moved into `compute_reward.py`.

## Task identity

- task_id: `ffmpeg_swscale_reimplementation`
- bundle_uuid: `f6424bd2-3d99-5647-9f59-6323ace5d907`
- category: Systems and Software Engineering / SIMD / image scaling
- family: derived, EdgeBench touchstone (correctness-gated speedup), rebuilt for ARM64
- maturity: draft
- upstream: `ByteDance-Seed/EdgeBench :: ffmpeg_swscale_reimplementation` (CC-BY-4.0)
- work image: `edgebench.work.ffmpeg_swscale_reimplementation:arm64-20260812@sha256:bf652aea...c6502`
- judge image: `edgebench.judge.ffmpeg_swscale_reimplementation:arm64-20260812-fixed@sha256:936302e0...fb8ea`

The judge tag is `arm64-20260812-fixed`. The earlier `arm64-20260812` tag resolves to
`sha256:083943c0...43820`, which lacks the `/home/workspace/swscale-impl` exec workdir and
fails every submission with an archive-listing error. Do not pair that tag with this digest.

## ARM64 rebuild provenance

The upstream images are amd64-only, so running them on Graviton or Apple Silicon would emulate,
which invalidates a speed measurement. Both images were rebuilt natively for arm64 from source:

- FFmpeg 7.1 recompiled `--disable-asm`; the C paths are bit-identical to the asm paths, so
  correctness is preserved across architectures.
- The baseline `.so` is statically linked, so it survives the grade-time deletion of the system
  FFmpeg libraries.
- Rust (stable and nightly) and Zig arm64 toolchains, so the judge can rebuild the candidate.
- The python grader (`compute_reward.py`, `verify_correctness.py`, `pytest_shim.sh`) was carried
  over verbatim from the upstream amd64 judge and is architecture-independent.

Verified native: the scaffold builds, scores 30/30 correctness, and reaches a raw 0.7101x
speedup. The same scaffold reached 0.506x on x86. That difference is Intel SIMD against ARM
SIMD, which is why the native ARM rebuild was required.

## Open calibration item

The `log_anchor` map (`anchor_raw = 14.155`, `anchor_score = 43`) is inherited from the x86
touchstone and is not yet re-calibrated for ARM. The raw speedup `S` is valid on ARM because it
is a same-machine ratio. The `[0,1]` label derived from it is provisional until an ARM
reference or expert run re-fixes the anchor. The map is monotonic, so rankings and the
0.34 floor to 8.13x correspondence are preserved regardless.
