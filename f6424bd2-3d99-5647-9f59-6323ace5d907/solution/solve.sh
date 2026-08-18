#!/bin/bash
# Reference for ffmpeg_swscale_reimplementation (ARM64).
# The reference candidate is solution/reference_swscale_impl/ (the Rust scaffold that
# reached 30/30 correctness natively on arm64, reward ~0.71). It is the file tree the
# agent starts from at /home/workspace/swscale-impl/. Rebuild with `cargo build --release`;
# the judge (tests/) enforces the PSNR correctness gate then benchmarks speedup vs the
# static C baseline in /verifier-data/. The expert (fast SIMD) solution is the upstream
# touchstone's and is not re-implemented here.
echo "Reference: solution/reference_swscale_impl/ (Rust; 30/30 correctness on arm64)."
echo "Scoring: correctness gate (PSNR) then geometric-mean speedup vs the C baseline."
exit 0
