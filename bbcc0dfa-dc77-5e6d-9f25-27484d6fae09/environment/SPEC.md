# LatticeStore Specification

This document is normative about behavior and structure but deliberately withholds the exact on-disk encodings. It describes what the store does and the invariants it maintains. The precise byte layouts, magic markers, numeric constants, hashing parameters, and field orders are NOT stated here. A stripped reference binary named `lattice` is shipped at `/reference/lattice` and is the executable ground truth: you recover every exact encoding by running that binary and inspecting the bytes it reads and writes. Where a workspace doc comment and this document describe the same rule they agree, and the observable behavior of the reference binary is authoritative over both.

## 1. Workspace

The Cargo workspace has seven crates forming a dependency DAG. `lattice-types` provides the shared hash and id types, hex rendering, the error type, path and size constants, and a SHA-256 implementation. `lattice-chunk` depends on types. `lattice-codec` depends on types. `lattice-index` and `lattice-log` depend on types and codec. `lattice-store` depends on all of the above. `lattice-cli` (binary name `lattice`) depends on store and types. No third-party dependencies are permitted anywhere in the workspace; the build must succeed with `cargo build --release --offline` using only the standard library. Every crate ships with its public item signatures and type definitions intact and its function bodies replaced by `todo!()`; your task is to reconstruct the bodies so the workspace reproduces the reference binary's observable behavior byte for byte.

## 2. Common encodings

The store is fully deterministic: no timestamps, no randomness, and no absolute paths appear in any on-disk byte. Object ids and chunk ids are 32-byte SHA-256 digests rendered as lowercase hex, and hex parsing rejects uppercase and wrong lengths. The on-disk fixed-width integer order, the variable-length integer coding, the signed-integer and delta coding, and the block checksum are each a specific well-defined scheme, but their exact forms are not given here; recover them by encoding known inputs through the reference binary and reading back the bytes. Decoders are expected to reject malformed encodings such as truncation, overlong forms, and out-of-range values, exactly as the reference does.

## 3. Content-defined chunking

`lattice-chunk` splits object content into variable-length chunks with a gear-style rolling-hash content-defined chunker. The chunker has a minimum and a maximum chunk length and an average size controlled by a mask over a rolling hash; the empty object produces zero chunks, and any remainder shorter than the minimum is a single chunk. The exact rolling-hash function, its seeded gear table, the mask width, and the minimum and maximum lengths are determined by the reference binary and are not stated here. Recover the chunk boundaries by feeding crafted inputs to `lattice put` and observing the reported chunk counts and the resulting pack contents; a correct port reproduces the reference's chunk boundaries exactly on every input.

## 4. Store layout

A store root contains exactly a metadata file, a single pack file under an objects directory, a manifests directory holding one manifest per stored object named by the object id hex, an index file under an index directory, and a journal file. The exact file names are visible by listing a store that the reference binary creates. There is exactly one pack in this version and every index entry refers to it.

## 5. Metadata, pack, manifest, index

The metadata file is a small fixed-size record carrying a magic marker, a version, the chunker parameters, and a trailing checksum; a missing file, wrong length, or wrong magic means the directory is not a store, and a bad checksum is a corruption of the metadata. The pack file begins with a fixed header and then holds chunk records, each a length-prefixed blob, and index offsets point at the first content byte of a chunk. A manifest carries the object size, the ordered list of its chunk hashes and lengths, and a trailing checksum. The index is a table of unique chunk hashes sorted strictly ascending, each mapped to its pack location, length, and a refcount, with a trailing checksum; a chunk's refcount is the number of manifest chunk-list occurrences referencing it across all committed objects, counting repeats within one object once per occurrence. All of these exact byte layouts, magic markers, and field orders are recovered by hexdumping the files the reference binary writes.

## 6. Journal and durability

The journal is an append-only sequence of self-describing, checksummed records covering the lifecycle of each put (a begin, a per-chunk append, and a commit) and a checkpoint. Replay parses records sequentially, and the first truncated, corrupt, or unknown record ends replay at the durable prefix; everything after it is a discardable tail, which is a recovery condition rather than an error. The exact record framing, type tags, and payloads are recovered by inspecting the journal the reference binary writes across init and put operations.

## 7. Operations

- `init`: refuse a non-empty existing directory. Otherwise create the store's directories and files, with an empty pack, an empty index, and a journal containing exactly one checkpoint record.
- `put`: the object id is the SHA-256 of the full content. If the object's manifest already exists the put is a complete no-op on disk and reports the manifest's chunk count with zero new chunks. Otherwise chunk the content, and for each chunk in order deduplicate against the index, or else append the chunk to the pack and add an index entry with a refcount starting at zero; after the chunk pass, increment the refcount once for every occurrence in the new manifest's chunk list, new and deduplicated alike. The put is journaled as a begin, then the per-chunk appends, then a commit carrying the resulting pack length and index checksum, and the files are written in the order pack, manifest, index, journal.
- `get`: an object whose manifest is absent is unknown. Reassemble content in manifest order through index lookups into the pack; a manifest referencing an absent chunk, a length disagreement, out-of-range pack bounds, or a final digest or size mismatch is a corruption error.
- `verify`: check the pack header, check every index entry (correct pack, offsets inside the pack past the header, and the digest of the referenced bytes equal to the entry's hash), parse every manifest in sorted filename order requiring every referenced chunk to exist in the index with matching length and the chunk lengths to sum to the manifest size, and replay the journal treating any discardable tail as journal corruption.
- `stats`: objects is the number of manifests, chunks is the index entry count, unique_bytes is the sum of index entry lengths, logical_bytes is the sum of manifest sizes, and pack_bytes is the pack file size in bytes. The dedup ratio is logical_bytes over unique_bytes, printed with exactly four decimal digits using integer arithmetic that truncates toward zero, and exactly `0.0000` when unique_bytes is zero.
- Recovery on every store open: replay the journal; if a tail was discarded truncate the journal to the durable prefix; compute the committed set from the durable commit records and the committed pack length from the last durable commit, using the header length when there are none; remove every file in the manifests directory, visited in sorted filename order, whose stem does not parse as the hex of a committed object id; and truncate the pack to the committed pack length when it is longer.

## 8. CLI contract

The binary is `lattice`. Every literal below is exact, each printed line ends with one newline, and exit codes are part of the contract.

- `lattice init <dir>`: stdout `initialized lattice store`, exit 0. Non-empty target: stderr `error: refusing to initialize non-empty directory`, exit 2.
- `lattice put <store> <file>`: stdout `<object-id-hex> <n_chunks> <n_new_chunks> <file_size>`, exit 0. Unreadable input: stderr `error: cannot read input: <file-arg>`, exit 3.
- `lattice get <store> <object-id-hex> <out>`: writes the object to `<out>`, stdout `<object-id-hex> <size> OK`, exit 0. Unknown or malformed id: stderr `error: unknown object <id-arg>`, exit 4. Unwritable output: stderr `error: cannot write output: <out>`, exit 5.
- `lattice verify <store>`: stdout four lines `packs <n>`, `chunks <n>`, `objects <n>`, `verify OK`, exit 0. Corruption: stderr `error: corrupt <what> at <location>`, exit 5.
- `lattice stats <store>`: stdout six lines `objects <n>`, `chunks <n>`, `unique_bytes <n>`, `logical_bytes <n>`, `dedup_ratio <r>`, `pack_bytes <n>`, exit 0.
- Any other argument shape: stderr `usage: lattice <init|put|get|verify|stats> ...`, exit 2.
- Store-open failures on put, get, verify, and stats: checksum failures print stderr `error: corrupt <what> at <location>` and exit 5; other open failures print stderr `error: <message>` and exit 5, where a missing or non-store directory yields the message `not a lattice store`.

## 9. Corruption reporting vocabulary

The `<what>` and `<location>` values the reference produces are observable by running `lattice verify` and `lattice get` against deliberately corrupted stores. They name the metadata file, the pack header, the index (both a trailer checksum failure and a bad entry keyed by chunk hex), a chunk keyed by its pack offset, a manifest keyed by its path or name and optionally an offending chunk, an object keyed by its id hex, and the journal keyed by the byte offset of the discardable record. Their exact spellings are part of the contract and are recovered by observing the reference binary's output on the corresponding corruption.
