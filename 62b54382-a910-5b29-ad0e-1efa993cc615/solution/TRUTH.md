## What this task grades

The solver rebuilds the filter compiler of `the-tcpdump-group/libpcap` version `1.10.6` from observable behaviour alone, with no upstream source, no upstream headers, no upstream binary, and no network. The judge compares its output against a frozen golden corpus of 12000 hidden cases, and never runs the upstream at grading time.

Reward: `R = clip(0.88*C + 0.12*P*min(1, C/0.25), 0, 1)`. C is the weighted conformance fraction over eight strata. P is throughput, charged against byte-exact cases only under the rule `r = (t_upstream / N_total) / (t_candidate / N_exact); N_exact counts compiled_exact and rejected_exact_err; N_exact = 0 yields r = 0`.

## Ordered golden trajectory

Each step names the action, the state it establishes, and the single checker identifier it satisfies. This identifier set reconciles against the committed checker set and against the deliverable manifest, as set equality in both directions.

| # | Action | Established state | Checker |
|---|---|---|---|
| 1 | read the invocation contract and the record schemas from the task statement | the solver knows it must answer --cases and --bench over JSONL | `CHK-CONTRACT` |
| 2 | parse each input record into dlt, snaplen, optimize, netmask, filter | one parsed case per input line, in input order | `CHK4` |
| 3 | lex and parse the filter expression against the real grammar surface | an abstract syntax tree, or a rejection carrying the exact upstream error text | `CHK2` |
| 4 | dispatch code generation on the link-layer type | per-DLT header offsets and protocol dispatch established | `CHK1` |
| 5 | emit an unoptimized cBPF program for the parsed expression | a structurally valid program whose jump targets all land inside it | `CHK3` |
| 6 | run the dataflow optimizer when optimize is 1 | the optimized program, which differs from the unoptimized one on 61.4 percent of the corpus and on 94.4 percent of the optimizer-only stratum | `CHK1` |
| 7 | detect provably unsatisfiable expressions during optimization | the exact upstream rejection for filters the optimizer proves match nothing, which is why the identical filter can succeed at optimize 0 and fail at optimize 1 | `CHK2` |
| 8 | emit one output record per input case, in input order | a complete result file with no duplicate and no missing index | `CHK4` |
| 9 | keep the implementation free of upstream source and of forbidden imports | normalized five-gram containment below the bound threshold and an import set inside libc and libm | `CHK6` |
| 10 | compile the whole corpus quickly enough to earn the throughput term | throughput charged against byte-exact cases only, so speed without fidelity earns nothing | `CHK5` |

## Rejected routes

Each rejected route binds one known-wrong control whose rejection was measured. The explanatory prose is advisory and grounds no score on its own.

| Rejected route | Bound control |
|---|---|
| link or dynamically load the pinned upstream library and delegate to it | `CTL_LINK_LIBPCAP` |
| copy the upstream sources into the submission, verbatim or with identifiers renamed | `CTL_VERBATIM_COPY` |
| emit one constant program for every case | `CTL_CONSTANT` |
| emit an accept-all program for every case | `CTL_ACCEPT_ALL` |
| emit a reject-all program for every case | `CTL_REJECT_ALL` |
| answer every rejection with one generic error string | `CTL_GENERIC_ERROR` |
| skip the compiler entirely and return quickly to farm the throughput term | `CTL_FAST_WRONG` |
| submit nothing | `CTL_NOOP` |

## Measured anchors

Measured on AMD Ryzen AI 9 365, x86_64 native, 20 threads, 22 GiB RAM on 2026-08-13. These are recorded measurements, never predictions.

| Control | Result |
|---|---|
| empty submission | R = 0.000000, reason `empty_submission` |
| shipped weak starter | R = 0.054229, C = 0.061624, P = 0.0, N_exact = 0 |
| pinned upstream shim | C = 1.000000 |
| hard-kill line for the starter | 0.12 |

The optimizer is not a corner of this task. Compiling the corpus at both optimize settings shows 61.4 percent of all cases diverge, rising to 94.4 percent inside the optimizer-only stratum. A solver with a correct parser and correct code generation but no dataflow optimizer therefore loses the majority of the corpus.

## Anti-shortcut posture

Normalized 5-gram containment against the pinned upstream sources fires at or above 0.15. String literals are excluded from that scan, and the reason is load-bearing rather than incidental: exact error-text fidelity is a graded obligation here, so the upstream error strings are the required answer. A scan that counted them would fire hardest on the submissions that did the task correctly.

| Calibration point | Containment | Fires |
|---|---|---|
| shipped starter | 0.0600 | no |
| verbatim upstream copy | 0.9481 | yes |
| copy with identifiers renamed | 0.7381 | yes |
| upstream error strings only, no code | 0.0976 | no |

