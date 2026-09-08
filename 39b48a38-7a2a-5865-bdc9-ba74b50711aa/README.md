# 39b48a38-7a2a-5865-bdc9-ba74b50711aa

Reconstruct an undocumented columnar block encoder from its recorded output. A production
system emits int64 columnar data in a container called chronopack. The container format is
fully specified; the encoder that produces it is documented nowhere, and the team that wrote
it is gone. From 300 columns of real output - input values plus the exact bytes the reference
encoder produced - the agent must write an encoder that reproduces those bytes exactly on
columns it has never seen, drawn from a wider distribution.

## What must be recovered

The reference encoder's behaviour has three undocumented layers:

- **selection policy** - which of the six block encodings the encoder chooses for a given block
- **field normalisations** - how values are transformed before encoding
- **trailer algorithm** - how the block trailer is computed

The corpus samples this behaviour rather than specifying it: `corpus/corpus.json` carries the
300 columns, the exact reference bytes, and the encoding chosen for every block. The grading
surface also asks the codec to report, per block, how likely it believes each of the six
encodings is to be the reference's choice - a calibrated statement of the codec's own
uncertainty, read as one.

## Working surface

| Path | What it is |
|---|---|
| `spec/FORMAT.md` | the container format, specified completely |
| `spec/API.md` | the names the grader calls and the modules allowed |
| `corpus/corpus.json` | 300 columns with exact reference bytes and per-block encoding choices |
| `verify_local.py` | replays the codec over the corpus and reports what differs |

## Deliverable

`/home/workspace/submission/codec.py`, exposing the names in `spec/API.md`. It must encode a
column of int64 values to chronopack bytes, decode chronopack bytes back to values, and report
per-block encoding likelihoods. Nothing else is read by the judge.

Both work and judge containers run with no network access. The agent has a 12-hour budget;
the verifier grades in a separate container.

## Layout

```
task.toml           task contract; work and judge images pinned by digest
instruction.md      agent-facing specification
environment/        work image: Dockerfile, format spec, API spec, corpus, local verifier
tests/              judge image: grading harness and held-out columns
solution/           private oracle tree: reference materials for the encoder
```
