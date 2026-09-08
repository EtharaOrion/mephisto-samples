# f6424bd2-3d99-5647-9f59-6323ace5d907

Re-implement FFmpeg's **libswscale** — image scaling and pixel-format conversion — in Rust
or Zig as a C-ABI shared library, matching FFmpeg's C scalar output and beating its speed
with portable SIMD. This is an ARM64-native rebuild of the upstream touchstone: it runs on
Graviton and Apple Silicon without emulation.

## The task

The agent works in `/app/swscale-impl/` (Zig and Rust scaffolds provided) and must produce
`libswscale_candidate.so` exporting three C-linkage functions:

```c
void *swscale_create(int src_w, int src_h, int src_fmt,
                     int dst_w, int dst_h, int dst_fmt, int algo);
int   swscale_process(void *ctx, const uint8_t *const src[4], const int src_stride[4],
                      uint8_t *const dst[4], const int dst_stride[4]);
void  swscale_destroy(void *ctx);
```

Coverage: conversions between any pair of ten pixel formats (planar YUV 420/422/444, NV12,
NV21, RGB24, BGR24, RGBA, BGRA, GRAY8) under three scaling algorithms (nearest, bilinear,
bicubic), with the same-size format-conversion fast path as the most common case. FFmpeg
source (libswscale + libavutil) ships in the image for study, alongside a full reference
`ffmpeg` binary for generating golden outputs during development — the reference is deleted
before scoring, so delegating to it is structurally impossible.

## Scoring

The judge rebuilds the submission from source, loads it through the C ABI, and grades it
against a statically linked C-only FFmpeg 7.1 baseline (`--disable-asm`) **on the same
machine**, so the speed comparison is emulation-free and host-fair:

```
C = per-plane PSNR over 30 hidden seed-generated workloads
    (>= 60 dB for same-size conversion, >= 40 dB when scaling; byte-exact = pass)
any workload below threshold -> reward 0, benchmark not run
S = geometric_mean(baseline_time / candidate_time)
R = clip(43 * ln(S) / ln(14.155), 0, 100) / 100
```

The correctness gate is absolute: one failing workload discards the entire speed result, so
a fast but slightly wrong kernel scores the same as no submission. Keeping every workload
correct *while* vectorized is the whole difficulty. The graded workloads are generated at
grade time from a fixed RNG seed, so there is no secret answer panel to leak. The
`log_anchor` mapping is monotonic — ranking and the raw speedup (retained in
`reward.json additional_data`) are preserved exactly.

## Measured anchors

Recorded on Apple Silicon arm64 (10 cores, native Docker), 2026-08-12:

| Control | Raw speedup S | Reward R |
|---|---|---|
| incorrect submission (gate fails) | not run | 0.000 |
| shipped reference scaffold, 30/30 correct | 0.71x | 0.000 |
| Opus 4.8, best of 14 pilot rollouts (90 min) | 2.38x | 0.141 |
| frontier-defeat floor | 8.13x | 0.340 |
| `log_anchor` calibration point | 14.155x | 0.430 |
| upstream expert reference | 21.47x | 0.498 |
| Opus 5, best 12 h run | 122.8x | 0.781 |

The spread shows real headroom in both directions: the scaffold is correct but floors at 0,
and strong runs separate cleanly across the log curve.

## Layout

```
task.toml                    task contract; arm64 images pinned by digest
instruction.md               agent-facing specification: API, formats, scoring, workflow
environment/                 work image: Dockerfile, scaffolds, FFmpeg source + reference
                             binary, public baseline library, dev correctness/bench tools
tests/                       judge image: Dockerfile, scoring/, test.sh
solution/                    private oracle tree: TRUTH.md, reference_swscale_impl,
                             rubrics.json, solve.sh
trajectory/                  two recorded runs: opus-5, gpt-5.6-sol
plots/opus-5.png             score trajectory for the opus-5 run
plots/gpt-5.6-sol.png        score trajectory for the gpt-5.6-sol run
inspect.html                 browsable bundle inspector
```

The graded truth lives in the judge image's seeded workload generator; `solution/TRUTH.md`
documents the golden trajectory step by step, from parsing the pixel-format descriptors
through exact FFmpeg rounding and chroma siting to portable-SIMD vectorization of the hot
loops.
