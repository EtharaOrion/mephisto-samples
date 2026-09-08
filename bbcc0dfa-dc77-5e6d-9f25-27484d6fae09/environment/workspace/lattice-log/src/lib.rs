












#![forbid(unsafe_code)]

use lattice_codec::{crc32, read_varint, write_varint};
use lattice_types::{ChunkId, LatticeError, ObjectId, HASH_LEN};

pub const REC_BEGIN_PUT: u8 = 0;
pub const REC_CHUNK_APPENDED: u8 = 0;
pub const REC_COMMIT_PUT: u8 = 0;
pub const REC_CHECKPOINT: u8 = 0;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JournalRecord {
    BeginPut {
        object: ObjectId,
    },
    ChunkAppended {
        chunk: ChunkId,
        pack_id: u64,
        offset: u64,
        len: u64,
    },
    CommitPut {
        object: ObjectId,
        pack_len: u64,
        index_crc: u32,
    },
    Checkpoint,
}

impl JournalRecord {
    fn type_byte(&self) -> u8 {
    todo!()
}

    fn payload(&self) -> Vec<u8> {
    todo!()
}

    
    pub fn to_bytes(&self) -> Vec<u8> {
    todo!()
}
}

fn take_hash(payload: &[u8], pos: usize) -> Result<([u8; HASH_LEN], usize), LatticeError> {
    todo!()
}

fn decode_payload(rec_type: u8, payload: &[u8]) -> Result<JournalRecord, LatticeError> {
    todo!()
}


#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayOutcome {
    
    pub records: Vec<JournalRecord>,
    
    
    pub durable_len: u64,
    
    pub tail_discarded: bool,
}


pub fn replay(data: &[u8]) -> ReplayOutcome {
    todo!()
}

fn parse_record(data: &[u8], pos: usize) -> Result<(JournalRecord, usize), LatticeError> {
    todo!()
}


