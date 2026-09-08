# chronopack container format, revision 1

This document specifies the container completely. Every field, every width, every byte order. A decoder written from this document alone will read any chronopack blob correctly.

It does not specify how the encoder chooses. That is deliberate and it is the task.

## The column

```
column := u32le block_count | block* | u32le digest
```

The trailing digest is four bytes, little endian, and it is the last four bytes of the blob. Its algorithm is not specified here. Like the encoder's choices, it is part of the policy you recover from the corpus.

A column of N values is split into blocks of exactly 128 values, in order. The final block holds the remainder and may be shorter. An empty column encodes as a `block_count` of zero followed by its digest.

## The block

```
block := u8 encoding_id | u16le value_count | payload
```

`value_count` is the number of values in this block, never the payload length. The payload layout depends on the encoding.

| Id | Name | Payload |
|---|---|---|
| 0 | RAW | `value_count` x i64le |
| 1 | CONST | one i64le, the value every entry holds |
| 2 | FOR_BITPACK | i64le minimum, u8 width, then `value_count` packed offsets |
| 3 | DELTA_BITPACK | i64le first value, i64le minimum delta, u8 width, then `value_count - 1` packed offsets |
| 4 | RLE | u16le run_count, then run_count x (i64le value, u16le length) |
| 5 | DICT | u8 table_size, table_size x i64le in ascending order, u8 width, then `value_count` packed indices |

## Bit packing

Offsets are packed least significant bit first into a byte stream. A value of width `w` occupies `w` consecutive bits, values follow one another with no padding between them, and the final byte is zero filled. A packed run of `n` values at width `w` occupies exactly `ceil(n * w / 8)` bytes.

For FOR_BITPACK the packed offsets are `value - minimum`. For DELTA_BITPACK they are `delta - minimum_delta`, where `delta[i] = value[i+1] - value[i]`. For DICT they are indices into the table.

The `width` byte is part of the frame, so a decoder always knows the width and never has to derive it. An encoder does have to derive it, and the rule it uses is not stated here.

## Run length

Runs are maximal runs of equal adjacent values, in order, and a run is capped at 65535 entries. A run longer than that continues as a further run of the same value.

## Dictionary

The table holds every distinct value in the block, sorted ascending as signed integers, and the indices are positions in that table.

## What is not specified here

The encoder chooses one encoding per block. Every encoding above can represent any block, so on almost every block several choices are legal and only one of them is the one this format's encoder makes. The rule it applies is not in this document, not in the schema, and not in any file in this container.

The same is true of the trailing digest, and of the width an encoder derives before writing the `width` byte. A decoder reads the width; an encoder must produce the one the reference produces.

`corpus/corpus.json` holds 300 columns with the bytes the reference produced for each, and the per block encoding ids it chose. That corpus is a sample of the encoder's behaviour. It is not a specification of it, it does not enumerate the policy, and the columns you are graded on are drawn from a wider distribution than the columns you were given.
