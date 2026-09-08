








#![forbid(unsafe_code)]

use std::collections::BTreeMap;

use lattice_codec::{crc32, read_varint, write_varint};
use lattice_types::{ChunkId, LatticeError, HASH_LEN};

pub const INDEX_MAGIC: &[u8; 4] = &[0u8; 4];


#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IndexEntry {
    pub pack_id: u64,
    pub offset: u64,
    pub len: u64,
    pub refcount: u64,
}


#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct ChunkIndex {
    entries: BTreeMap<ChunkId, IndexEntry>,
}

impl ChunkIndex {
    pub fn new() -> Self {
    todo!()
}

    pub fn len(&self) -> usize {
    todo!()
}

    pub fn is_empty(&self) -> bool {
    todo!()
}

    pub fn get(&self, id: &ChunkId) -> Option<&IndexEntry> {
    todo!()
}

    pub fn insert(&mut self, id: ChunkId, entry: IndexEntry) {
    todo!()
}

    pub fn increment_refcount(&mut self, id: &ChunkId) -> Result<(), LatticeError> {
    todo!()
}

    pub fn iter(&self) -> impl Iterator<Item = (&ChunkId, &IndexEntry)> {
        self.entries.iter()
    }

    
    pub fn to_bytes(&self) -> Vec<u8> {
    todo!()
}

    
    
    
    pub fn from_bytes(data: &[u8]) -> Result<Self, LatticeError> {
    todo!()
}
}


