
# chronopack: reconstruct an encoder from its output

A production system emits columnar integer data in a container called chronopack. The container format is documented and the documentation is complete. The encoder that produces it is not documented at all, and the team that wrote it is gone.

You have 300 columns of real output: the input values, and the exact bytes the encoder produced for them. Your job is to write an encoder that produces the same bytes that encoder would, on data it has never seen.

## What you have

| Path | What it is |
|---|---|
| `spec/FORMAT.md` | the container format, specified completely |
| `spec/API.md` | the names the grader calls and the modules you may use |
| `corpus/corpus.json` | 300 columns with the exact bytes the reference produced, and the encoding it chose for every block |
| `verify_local.py` | replays your codec over that corpus and reports what differs |

## What you must build

`/home/workspace/submission/codec.py`, exposing the names in `spec/API.md`.

It must encode a column of int64 values to chronopack bytes, decode chronopack bytes back to values, and report, for each block of a column, how likely it believes each of the six encodings is to be the one the reference would choose. That last part is a statement about your own uncertainty and it is read as one.


## Deliverable

`submission/codec.py`. Nothing else is read.
