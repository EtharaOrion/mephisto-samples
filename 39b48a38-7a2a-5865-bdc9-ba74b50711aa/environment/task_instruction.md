Read the complete task instructions in `/home/workspace/task_instruction.md`, and complete the task according to those requirements. The final deliverables must be written to the file paths specified in `task_instruction.md`.

---

# chronopack: reconstruct an encoder from its output

A production system emits columnar integer data in a container called chronopack. The container format is documented and the documentation is complete. The encoder that produces it is not documented at all, and the team that wrote it is gone.

You have 560 columns of real output: the input values, and the exact bytes the encoder produced for them. Your job is to write an encoder that produces the same bytes that encoder would, on data it has never seen.

## What you have

| Path | What it is |
|---|---|
| `spec/FORMAT.md` | the container format, specified completely |
| `spec/API.md` | the names the grader calls and the modules you may use |
| `corpus/corpus.json` | 560 columns with the exact bytes the reference produced, and the encoding it chose for every block |
| `verify_local.py` | replays your codec over that corpus and reports what differs |

## What you must build

`/home/workspace/submission/codec.py`, exposing the names in `spec/API.md`.

It must encode a column of int64 values to chronopack bytes, decode chronopack bytes back to values, and report, for each block of a column, how likely it believes each of the six encodings is to be the one the reference would choose. That last part is a statement about your own uncertainty and it is read as one.

## What makes this hard

Every one of the six encodings can represent any block, so on almost every block several outputs are legal and only one is the one the reference produces. The choice is made by a policy that appears in no file you have. So is the way the encoder normalises the fields it stores, the way it derives a bit width before writing it, and the four byte value it appends to every column.

The corpus is a sample of that encoder's behaviour. It is not a specification of it. It exercises every structural class the policy turns on, so nothing is hidden from you, but it does not enumerate the policy and the data you are graded on is not drawn from the same distribution as the data you were given.

Work out what the encoder does. Then work out how confident you are, and say so honestly, because a confident wrong answer is treated differently from an uncertain one.

## Deliverable

`submission/codec.py`. Nothing else is read.
