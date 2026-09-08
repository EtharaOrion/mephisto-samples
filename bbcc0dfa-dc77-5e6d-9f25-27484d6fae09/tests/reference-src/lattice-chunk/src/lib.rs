//! lattice-chunk: content-defined chunking, a bit-exact port of the frozen C
//! reference in `chunker-ref/` (chunker.h documents the normative algorithm).
//!
//! Every boundary this crate produces must equal the boundary the C reference
//! produces for the same bytes. The gear table, rolling-hash update, and cut
//! rules are implementation-defined numerics: reproduce them exactly.

#![forbid(unsafe_code)]

use lattice_types::{CHUNK_MASK_BITS, CHUNK_MAX, CHUNK_MIN};

/// Seed constant for gear table derivation, mirrors LATCHUNK_GEAR_SEED.
pub const GEAR_SEED: u64 = 0x14650FB0739D0383;

/// Per-index mix constant for gear table derivation, mirrors LATCHUNK_GEAR_MIX.
pub const GEAR_MIX: u64 = 0x9E3779B97F4A7C15;

const XORSHIFT_MULT: u64 = 0x2545F4914F6CDD1D;

/// Low-bit mask tested at candidate cut points: (1 << CHUNK_MASK_BITS) - 1.
pub const CHUNK_MASK: u64 = (1u64 << CHUNK_MASK_BITS) - 1;

/// A chunk boundary: byte offset and length within the source stream.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkSpan {
    pub offset: usize,
    pub len: usize,
}

/// Derive the 256-entry gear table.
///
/// For index i: state = GEAR_SEED ^ (i as u64).wrapping_mul(GEAR_MIX), then
/// three rounds of xorshift64* (state ^= state >> 12; state ^= state << 25;
/// state ^= state >> 27; state = state.wrapping_mul(XORSHIFT_MULT)). The
/// table value is the state after the third round. All arithmetic wraps.
pub fn gear_table() -> [u64; 256] {
    let mut table = [0u64; 256];
    for (i, slot) in table.iter_mut().enumerate() {
        let mut state = GEAR_SEED ^ (i as u64).wrapping_mul(GEAR_MIX);
        for _ in 0..3 {
            state ^= state >> 12;
            state ^= state << 25;
            state ^= state >> 27;
            state = state.wrapping_mul(XORSHIFT_MULT);
        }
        *slot = state;
    }
    table
}

/// Return the length of the first chunk starting at `data[0]`.
///
/// Rules, in order: empty input yields 0; input of at most CHUNK_MIN bytes is
/// one chunk of the full length; otherwise scan bytes with h starting at 0,
/// h = (h << 1).wrapping_add(gear[b]), and cut AFTER byte i (length i + 1)
/// when (i + 1) >= CHUNK_MIN and (h & CHUNK_MASK) == 0; a cut is forced at
/// CHUNK_MAX; if no cut fires before the data ends, the remainder is one
/// chunk.
pub fn next_boundary(data: &[u8], gear: &[u64; 256]) -> usize {
    if data.is_empty() {
        return 0;
    }
    let min = CHUNK_MIN as usize;
    let max = CHUNK_MAX as usize;
    if data.len() <= min {
        return data.len();
    }
    let limit = data.len().min(max);
    let mut h: u64 = 0;
    for (i, &b) in data[..limit].iter().enumerate() {
        h = (h << 1).wrapping_add(gear[b as usize]);
        if (i + 1) >= min && (h & CHUNK_MASK) == 0 {
            return i + 1;
        }
    }
    limit
}

/// Split a full buffer into consecutive chunk spans.
pub fn chunk_spans(data: &[u8], gear: &[u64; 256]) -> Vec<ChunkSpan> {
    let mut spans = Vec::new();
    let mut offset = 0usize;
    while offset < data.len() {
        let len = next_boundary(&data[offset..], gear);
        spans.push(ChunkSpan { offset, len });
        offset += len;
    }
    spans
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input_yields_no_spans() {
        let gear = gear_table();
        assert_eq!(next_boundary(&[], &gear), 0);
        assert!(chunk_spans(&[], &gear).is_empty());
    }

    #[test]
    fn short_input_is_single_chunk() {
        let gear = gear_table();
        let data = vec![7u8; CHUNK_MIN as usize];
        assert_eq!(next_boundary(&data, &gear), data.len());
    }

    #[test]
    fn spans_cover_input_exactly() {
        let gear = gear_table();
        let data: Vec<u8> = (0u32..200_000).map(|i| (i * 31 % 251) as u8).collect();
        let spans = chunk_spans(&data, &gear);
        let mut expect = 0usize;
        for s in &spans {
            assert_eq!(s.offset, expect);
            assert!(s.len >= 1);
            assert!(s.len <= CHUNK_MAX as usize);
            expect += s.len;
        }
        assert_eq!(expect, data.len());
    }

    #[test]
    fn gear_table_is_stable() {
        let gear = gear_table();
        assert_eq!(gear, gear_table());
        assert!(gear.iter().any(|&v| v != 0));
    }
}
