






#![forbid(unsafe_code)]

use lattice_types::{CHUNK_MASK_BITS, CHUNK_MAX, CHUNK_MIN};


pub const GEAR_SEED: u64 = 0;


pub const GEAR_MIX: u64 = 0;

const XORSHIFT_MULT: u64 = 0;


pub const CHUNK_MASK: u64 = (1u64 << CHUNK_MASK_BITS) - 1;


#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkSpan {
    pub offset: usize,
    pub len: usize,
}







pub fn gear_table() -> [u64; 256] {
    todo!()
}









pub fn next_boundary(data: &[u8], gear: &[u64; 256]) -> usize {
    todo!()
}


pub fn chunk_spans(data: &[u8], gear: &[u64; 256]) -> Vec<ChunkSpan> {
    todo!()
}


