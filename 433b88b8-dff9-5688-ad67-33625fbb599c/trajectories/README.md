# Trajectories — p6zeta_zero_one_ip_solver_from_scratch_v2

Agent rollouts against this bundle. Both cohorts ran with `--agent openhands`,
`--timeout 43200`, `--disable-internet`, `--max-submissions 60`,
`--submission-cooldown 900`, `--eval-interval 1800`, judge workers pinned to
disjoint cpusets so the two runs could not contend.

## Results

| Model | Best | Lanes at best | Runtime | Provenance |
|---|---|---|---|---|
| `claude-opus-5[1m]` | **0.9321** | l1 10.00 · l2 26.56 · l3 21.88 · l4 19.78 · l5 15.00 | 12.00 h | native, uninterrupted |
| `gpt-5.6-sol` | **0.8384** | l1 9.89 · l2 26.79 · l3 12.50 · l4 19.71 · l5 14.95 | 12.28 h | **merged, 2 parts** |

Neither run tripped the KILL band (`kill=[]` on every graded round).

## `opus-5/`

One clean 12.00 h run (`runtime_seconds=43200.1`, `timed_out=true`,
`resume_count=0`), 42 rounds (19 agent + 23 auto). Best `agent-16`. All summary
files written by the harness itself; nothing reconstructed. This is the
reference measurement for the bundle.

## `gpt-5.6-sol/`

66 rounds, 12.28 h, best `agent-41` (0.8384). **This is a merged record, not one
continuous session.** Every file carries `merged: true`, and every round keeps
its original id under `merged_from`. Its `parts` block records the two segments
it was built from by `scripts/merge_runs.py`:

- **part 1** — 11.08 h, 60 rounds, best 0.7153. Ended early: the upstream Codex
  backend returned a single `server_error`, the bridge surfaced it as a 502, and
  the driver exited cleanly at 08:11 UTC. Not a timeout (`timed_out=false`) and
  not the submission cap (38 of 60 agent submissions used). 1698 successful
  calls preceded it.
- **part 2** — 1.20 h, 6 rounds, best 0.8384. Relaunched 08:30 UTC with
  `--seed-archive` from part 1's `final_archive.tar.gz`. Killed deliberately at
  09:42; summary files rebuilt by `scripts/recover_run.py` from the per-round
  `report.json` files (each carries a `reconstructed` block).

The part directories are not published here — only the merged record is. They
are retained outside the bundle under
`trajectories/openhands/codex/runs/p6zeta-v2-gpt56sol-{openhands-20260905-2106,20260906-seeded}`.

### What the merged run is and is not

It is a **task-level** record: the score curve across the whole effort, total
graded rounds, total agent time. Between the parts the container, the installed
state and the model's context were all fresh; `--seed-archive` restored only
`build.sh`, `solve` and `src/`; and any work part 1 did after its last
submission is absent. `runtime_seconds` is the sum of the parts' agent time and
excludes the 19 minutes of wall clock between them.

For a strict like-for-like comparison against the Opus run, use **part 1's
0.7153 over 11.08 h** — that is the single-run measurement. The merged 0.8384 is
the "what can this model reach on this task" number.

### Lane 3 is the whole story

`gpt-5.6-sol` scored **0.00 on lane 3 in all 60 rounds of part 1**. It never
wrote `l3_ranking.json`. The seeded relaunch — a fresh agent re-reading the spec
with part 1's working solver already in the workspace — attempted the lane within
40 minutes. Part 2's rounds, in order:

```
71.55   l3= 0.00    seed baseline, confirms the archive restored intact
77.64   l3= 6.25    first non-zero lane 3 for this model on this task
83.84   l3=12.50    peak
77.58   l3= 6.25
71.46   l3= 0.00    regression
71.41   l3= 0.00    regression confirmed
```

The gain was **not stable** — the last two rounds fell back to zero. 0.8384 is a
real graded peak, not a plateau.

The 93.21 − 83.84 spread is therefore mostly one lane: Opus reached 21.88 on
lane 3, gpt-5.6-sol peaked at 12.50 and did not hold it. On every other lane the
two models are within ~0.3 points.

## Known bundle issue these runs surfaced

`instruction.md` / `task_instruction.md` still carry v1's submission economics —
*"at most 300 submissions with a 120 second cooldown"* — while the harness
enforces 60 and 900 s. Both figures reach the agent in the same prompt. Part 1's
agent believed the 120 s number and ran a `sleep 121; sforge-submit` loop,
producing 48 cooldown rejections. Fixing the text requires a work-image rebuild.
