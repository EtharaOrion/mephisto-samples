

























#![forbid(unsafe_code)]

use std::fs;
use std::path::{Path, PathBuf};

use lattice_chunk::{chunk_spans, gear_table};
use lattice_codec::{crc32, read_varint, write_varint};
use lattice_index::{ChunkIndex, IndexEntry};
use lattice_log::{replay, JournalRecord};
use lattice_types::{
    sha256, ChunkId, LatticeError, ObjectId, CHUNK_MASK_BITS, CHUNK_MAX, CHUNK_MIN, HASH_LEN,
    INDEX_FILE, JOURNAL_FILE, MANIFEST_DIR, META_FILE, META_MAGIC, META_VERSION, PACK_DIR,
};

pub const PACK_MAGIC: &[u8; 4] = &[0u8; 4];
pub const MANIFEST_MAGIC: &[u8; 4] = &[0u8; 4];
pub const PACK_HEADER_LEN: u64 = 16;
pub const META_LEN: usize = 64;
pub const PACK_FILE: &str = "objects/pack-000000.lpk";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PutOutcome {
    pub object: ObjectId,
    pub n_chunks: u64,
    pub n_new_chunks: u64,
    pub size: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VerifyReport {
    pub packs: u64,
    pub chunks: u64,
    pub objects: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatsReport {
    pub objects: u64,
    pub chunks: u64,
    pub unique_bytes: u64,
    pub logical_bytes: u64,
    pub pack_bytes: u64,
}

impl StatsReport {
    
    
    pub fn dedup_ratio_string(&self) -> String {
    todo!()
}
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RecoveryReport {
    pub journal_truncated: bool,
    pub pack_truncated: bool,
    pub manifests_removed: u64,
}

pub struct Store {
    root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Manifest {
    pub size: u64,
    pub chunks: Vec<(ChunkId, u64)>,
}

impl Manifest {
    pub fn to_bytes(&self) -> Vec<u8> {
    todo!()
}

    pub fn from_bytes(data: &[u8], location: &str) -> Result<Self, LatticeError> {
    todo!()
}
}

fn meta_bytes() -> [u8; META_LEN] {
    todo!()
}

fn io_err(e: std::io::Error) -> LatticeError {
    todo!()
}

impl Store {
    pub fn root(&self) -> &Path {
    todo!()
}

    pub fn init(root: &Path) -> Result<Store, LatticeError> {
    todo!()
}

    pub fn open(root: &Path) -> Result<(Store, RecoveryReport), LatticeError> {
    todo!()
}

    fn recover(&self) -> Result<RecoveryReport, LatticeError> {
    todo!()
}

    fn manifest_path(&self, object: &ObjectId) -> PathBuf {
    todo!()
}

    fn load_index(&self) -> Result<ChunkIndex, LatticeError> {
    todo!()
}

    pub fn put_bytes(&self, content: &[u8]) -> Result<PutOutcome, LatticeError> {
    todo!()
}

    pub fn get(&self, object: &ObjectId) -> Result<Vec<u8>, LatticeError> {
    todo!()
}

    pub fn verify(&self) -> Result<VerifyReport, LatticeError> {
    todo!()
}

    pub fn stats(&self) -> Result<StatsReport, LatticeError> {
    todo!()
}
}


