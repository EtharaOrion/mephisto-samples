





#![forbid(unsafe_code)]

use std::fmt;


pub const HASH_LEN: usize = 32;


pub const META_FILE: &str = "lattice.meta";


pub const INDEX_FILE: &str = "index/index.lix";


pub const JOURNAL_FILE: &str = "journal.llg";


pub const PACK_DIR: &str = "objects";


pub const MANIFEST_DIR: &str = "manifests";


pub const META_MAGIC: &[u8; 8] = &[0u8; 8];


pub const META_VERSION: u16 = 0;


pub const CHUNK_MIN: u32 = 2048;


pub const CHUNK_MAX: u32 = 65536;


pub const CHUNK_MASK_BITS: u32 = 13;


#[derive(Debug, PartialEq, Eq, Clone)]
pub enum LatticeError {
    
    Truncated,
    
    Malformed(String),
    
    ChecksumMismatch { what: String, location: String },
    
    UnknownObject(String),
    
    Io(String),
}

impl fmt::Display for LatticeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    todo!()
}
}

impl std::error::Error for LatticeError {}


#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ObjectId(pub [u8; HASH_LEN]);


#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ChunkId(pub [u8; HASH_LEN]);

impl ObjectId {
    
    pub fn from_hex(s: &str) -> Result<Self, LatticeError> {
    todo!()
}

    
    pub fn to_hex(&self) -> String {
    todo!()
}
}

impl ChunkId {
    
    pub fn from_hex(s: &str) -> Result<Self, LatticeError> {
    todo!()
}

    
    pub fn to_hex(&self) -> String {
    todo!()
}
}

impl fmt::Display for ObjectId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    todo!()
}
}

impl fmt::Display for ChunkId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    todo!()
}
}


pub fn bytes_to_hex(bytes: &[u8]) -> String {
    todo!()
}




pub fn hex_to_bytes(s: &str) -> Result<[u8; HASH_LEN], LatticeError> {
    todo!()
}

fn hex_nibble(c: u8) -> Result<u8, LatticeError> {
    todo!()
}


#[derive(Clone)]
pub struct Sha256 {
    state: [u32; 8],
    buf: [u8; 64],
    buf_len: usize,
    total_len: u64,
}

const SHA256_K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

impl Default for Sha256 {
    fn default() -> Self {
    todo!()
}
}

impl Sha256 {
    pub fn new() -> Self {
    todo!()
}

    pub fn update(&mut self, mut data: &[u8]) {
    todo!()
}

    pub fn finalize(mut self) -> [u8; HASH_LEN] {
    todo!()
}

    fn compress(&mut self, block: &[u8; 64]) {
    todo!()
}
}


pub fn sha256(data: &[u8]) -> [u8; HASH_LEN] {
    todo!()
}


