# CONTRACT

This file is normative for the process boundary only. It defines how your binary is invoked, what it reads, and what it writes. It says nothing about how to produce the values, and nothing here should be read as a hint about them.

## Binary

The judge runs `make clean && make -j4` in the submission root and invokes the binary that build produced at `./bpfc`, relative to that root. The `Makefile` must produce that path with that name. One binary answers both invocation forms below.

## Invocation

```
./bpfc --cases <in.jsonl> --out <out.jsonl>
./bpfc --bench <in.jsonl> --reps N
```

Flags may appear in any order. `--cases` and `--out` are used together and name existing and to be created files respectively. `--bench` names an existing file and `--reps` gives a positive integer repetition count, defaulting to 1 when absent. An unrecognized flag, a flag missing its value, or `--cases` without `--out` is a usage error.

## Exit codes

Exit 0 when the requested work completed. Exit 2 on a usage error. Any non-zero exit on the `--cases` path is treated as a failed run and is graded as if no output had been produced. Diagnostics, if you emit any, go to stderr and are ignored; stdout is reserved.

## Input file

UTF-8 text, one JSON object per line, LF terminated. Empty lines are skipped. Line count is not bounded by anything smaller than the file. Each object has this shape:

```
{"i":INT,"dlt":INT,"snaplen":INT,"optimize":0|1,"netmask":UINT32|null,"filter":STRING}
```

| field | type | meaning |
|---|---|---|
| `i` | integer | case identifier, echoed verbatim in the output record for this line |
| `dlt` | integer | data link type number for this case |
| `snaplen` | integer | snapshot length in bytes |
| `optimize` | 0 or 1 | the optimize flag for this case |
| `netmask` | unsigned 32-bit integer, or JSON null | netmask for this case; `null` means the unknown netmask, numerically 0xffffffff |
| `filter` | string | the filter expression text, JSON escaped |

Every graded input line carries all six fields. For robustness, treat an absent `snaplen` as 262144, an absent `optimize` as 1, and an absent `netmask` as 0xffffffff. `i` values are not guaranteed to be contiguous, sorted, or zero based, and must never be used as an array index without checking.

`filter` is a JSON string and must be decoded before use. Decoding must handle `\"`, `\\`, `\/`, `\n`, `\t`, `\r`, `\b`, `\f`, and `\uXXXX` for code points below 0x80. Filter text may contain spaces, quotes, backslashes, parentheses, brackets, colons, and slashes, and may be empty.

## Output file

Written to the path given by `--out`, created or truncated. UTF-8 text, one JSON object per line, LF terminated, no leading or trailing content, no blank lines, no pretty printing, and nothing else on stdout. Emit exactly one record per input line, in input order. A missing record is graded as a failure for that case; a duplicated or reordered record makes the whole file non-conformant.

Success record:

```
{"i":INT,"ok":true,"prog":[[code,jt,jf,k],...]}
```

`prog` is an array of four element arrays, one per instruction, in program order. `code`, `jt`, and `jf` are unsigned integers and `k` is an unsigned long. All four are emitted as plain unsigned decimal, with no sign, no exponent, no hexadecimal, no leading zeros, and no quoting. An empty `prog` array is syntactically legal and is graded like any other sequence.

Failure record:

```
{"i":INT,"ok":false,"err":"EXACT ERROR STRING"}
```

`err` is emitted as a JSON string with standard escaping and is compared byte for byte after JSON decoding, so escaping style is free but the decoded bytes are not. Trailing whitespace, a trailing newline inside the string, and case differences all count as a mismatch.

The two record shapes are exclusive. A record carrying both `prog` and `err`, or neither, is non-conformant.

Schematic examples, values illustrative only:

```
{"i":41,"ok":true,"prog":[[6,0,0,0]]}
{"i":42,"ok":false,"err":"the exact error text for case 42"}
```

## Bench mode

`--bench <in.jsonl> --reps N` reads the same input file format, performs the same work the `--cases` path performs for each case, `N` times over the whole file, and prints exactly one line of JSON to stdout and nothing else:

```
{"elapsed_sec":FLOAT,"cases":N,"reps":R,"compiles":N*R,"sink":INT}
```

| field | type | meaning |
|---|---|---|
| `elapsed_sec` | float | wall time of the measured region, from a monotonic clock, in seconds |
| `cases` | integer | number of case records read from the input file |
| `reps` | integer | repetition count actually executed |
| `compiles` | integer | `cases * reps` |
| `sink` | integer | an accumulator fed by the real per case results, present so the work cannot be optimized away |

The measured region covers the repetition loop only, not input parsing and not process startup. No output file is written in this mode.

## Determinism

On the `--cases` path the process must not consult a clock, a locale, an environment variable, a random source, the network, or any file other than the input file, the output file, and the pinned tables under `etc/`. Two runs over the same input must produce byte identical output. The same requirement applies to `--bench` apart from its one clock reading.
