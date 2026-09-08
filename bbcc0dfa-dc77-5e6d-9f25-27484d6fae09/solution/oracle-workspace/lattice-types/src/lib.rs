//! lattice-types: foundation types for the LatticeStore workspace.
//!
//! This crate is fully implemented in the agent-facing workspace. It is the
//! bottom layer of the dependency DAG and every other crate builds on it.
//! Nothing in this crate performs I/O.

#![forbid(unsafe_code)]

use std::fmt;

/// Number of bytes in a content hash (SHA-256).
pub const HASH_LEN: usize = 32;

/// Store metadata file name inside a store root.
pub const META_FILE: &str = "lattice.meta";

/// Index file path relative to a store root.
pub const INDEX_FILE: &str = "index/index.lix";

/// Journal file path relative to a store root.
pub const JOURNAL_FILE: &str = "journal.llg";

/// Pack directory relative to a store root.
pub const PACK_DIR: &str = "objects";

/// Manifest directory relative to a store root.
pub const MANIFEST_DIR: &str = "manifests";

/// Store format magic (first 8 bytes of `lattice.meta`).
pub const META_MAGIC: &[u8; 8] = b"LATSTORE";

/// Store format version stored in `lattice.meta`.
pub const META_VERSION: u16 = 1;

/// Minimum chunk length produced by the content-defined chunker.
pub const CHUNK_MIN: u32 = 2048;

/// Maximum chunk length produced by the content-defined chunker.
pub const CHUNK_MAX: u32 = 65536;

/// Number of low bits of the rolling hash tested at a cut point.
pub const CHUNK_MASK_BITS: u32 = 13;

/// Errors shared across the LatticeStore crates.
#[derive(Debug, PartialEq, Eq, Clone)]
pub enum LatticeError {
    /// Byte stream ended before a complete record could be decoded.
    Truncated,
    /// A structural rule of an on-disk format was violated.
    Malformed(String),
    /// A checksum did not match the recorded value.
    ChecksumMismatch { what: String, location: String },
    /// A referenced object does not exist.
    UnknownObject(String),
    /// Wrapper for I/O failures raised by higher layers.
    Io(String),
}

impl fmt::Display for LatticeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LatticeError::Truncated => write!(f, "truncated input"),
            LatticeError::Malformed(m) => write!(f, "malformed: {m}"),
            LatticeError::ChecksumMismatch { what, location } => {
                write!(f, "checksum mismatch in {what} at {location}")
            }
            LatticeError::UnknownObject(id) => write!(f, "unknown object {id}"),
            LatticeError::Io(m) => write!(f, "io error: {m}"),
        }
    }
}

impl std::error::Error for LatticeError {}

/// 32-byte identifier of a stored object (SHA-256 of the full content).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ObjectId(pub [u8; HASH_LEN]);

/// 32-byte identifier of a chunk (SHA-256 of the chunk bytes).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ChunkId(pub [u8; HASH_LEN]);

impl ObjectId {
    /// Parse a 64-character lowercase hex string.
    pub fn from_hex(s: &str) -> Result<Self, LatticeError> {
        Ok(ObjectId(hex_to_bytes(s)?))
    }

    /// Render as 64-character lowercase hex.
    pub fn to_hex(&self) -> String {
        bytes_to_hex(&self.0)
    }
}

impl ChunkId {
    /// Parse a 64-character lowercase hex string.
    pub fn from_hex(s: &str) -> Result<Self, LatticeError> {
        Ok(ChunkId(hex_to_bytes(s)?))
    }

    /// Render as 64-character lowercase hex.
    pub fn to_hex(&self) -> String {
        bytes_to_hex(&self.0)
    }
}

impl fmt::Display for ObjectId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_hex())
    }
}

impl fmt::Display for ChunkId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_hex())
    }
}

/// Encode bytes as lowercase hex.
pub fn bytes_to_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

/// Decode a 64-character lowercase hex string into 32 bytes.
///
/// Uppercase digits are rejected: identifiers are canonical lowercase.
pub fn hex_to_bytes(s: &str) -> Result<[u8; HASH_LEN], LatticeError> {
    let raw = s.as_bytes();
    if raw.len() != HASH_LEN * 2 {
        return Err(LatticeError::Malformed(format!(
            "hex string must be {} characters, got {}",
            HASH_LEN * 2,
            raw.len()
        )));
    }
    let mut out = [0u8; HASH_LEN];
    for i in 0..HASH_LEN {
        let hi = hex_nibble(raw[2 * i])?;
        let lo = hex_nibble(raw[2 * i + 1])?;
        out[i] = (hi << 4) | lo;
    }
    Ok(out)
}

fn hex_nibble(c: u8) -> Result<u8, LatticeError> {
    match c {
        b'0'..=b'9' => Ok(c - b'0'),
        b'a'..=b'f' => Ok(c - b'a' + 10),
        _ => Err(LatticeError::Malformed(format!(
            "invalid hex character {:?}",
            c as char
        ))),
    }
}

/// Streaming SHA-256 (FIPS 180-4), pure Rust, no dependencies.
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
        Self::new()
    }
}

impl Sha256 {
    pub fn new() -> Self {
        Sha256 {
            state: [
                0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
                0x5be0cd19,
            ],
            buf: [0u8; 64],
            buf_len: 0,
            total_len: 0,
        }
    }

    pub fn update(&mut self, mut data: &[u8]) {
        self.total_len = self.total_len.wrapping_add(data.len() as u64);
        if self.buf_len > 0 {
            let need = 64 - self.buf_len;
            let take = need.min(data.len());
            self.buf[self.buf_len..self.buf_len + take].copy_from_slice(&data[..take]);
            self.buf_len += take;
            data = &data[take..];
            if self.buf_len == 64 {
                let block = self.buf;
                self.compress(&block);
                self.buf_len = 0;
            }
        }
        while data.len() >= 64 {
            let mut block = [0u8; 64];
            block.copy_from_slice(&data[..64]);
            self.compress(&block);
            data = &data[64..];
        }
        if !data.is_empty() {
            self.buf[..data.len()].copy_from_slice(data);
            self.buf_len = data.len();
        }
    }

    pub fn finalize(mut self) -> [u8; HASH_LEN] {
        let bit_len = self.total_len.wrapping_mul(8);
        self.update(&[0x80]);
        while self.buf_len != 56 {
            self.update(&[0x00]);
        }
        // Length update must not recount padding: total_len already advanced,
        // so append the length block directly to the buffer.
        self.buf[56..64].copy_from_slice(&bit_len.to_be_bytes());
        let block = self.buf;
        self.compress(&block);
        let mut out = [0u8; HASH_LEN];
        for (i, word) in self.state.iter().enumerate() {
            out[i * 4..i * 4 + 4].copy_from_slice(&word.to_be_bytes());
        }
        out
    }

    fn compress(&mut self, block: &[u8; 64]) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                block[i * 4],
                block[i * 4 + 1],
                block[i * 4 + 2],
                block[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = self.state;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = h
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(SHA256_K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        self.state[0] = self.state[0].wrapping_add(a);
        self.state[1] = self.state[1].wrapping_add(b);
        self.state[2] = self.state[2].wrapping_add(c);
        self.state[3] = self.state[3].wrapping_add(d);
        self.state[4] = self.state[4].wrapping_add(e);
        self.state[5] = self.state[5].wrapping_add(f);
        self.state[6] = self.state[6].wrapping_add(g);
        self.state[7] = self.state[7].wrapping_add(h);
    }
}

/// One-shot SHA-256 of a byte slice.
pub fn sha256(data: &[u8]) -> [u8; HASH_LEN] {
    let mut h = Sha256::new();
    h.update(data);
    h.finalize()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_empty_vector() {
        assert_eq!(
            bytes_to_hex(&sha256(b"")),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn sha256_abc_vector() {
        assert_eq!(
            bytes_to_hex(&sha256(b"abc")),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn sha256_multiblock_vector() {
        let msg = b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
        assert_eq!(
            bytes_to_hex(&sha256(msg)),
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
        );
    }

    #[test]
    fn sha256_streaming_matches_oneshot() {
        let data: Vec<u8> = (0u32..100_000).map(|i| (i % 251) as u8).collect();
        let mut h = Sha256::new();
        for part in data.chunks(977) {
            h.update(part);
        }
        assert_eq!(h.finalize(), sha256(&data));
    }

    #[test]
    fn hex_roundtrip() {
        let id = ObjectId(sha256(b"roundtrip"));
        let parsed = ObjectId::from_hex(&id.to_hex()).unwrap();
        assert_eq!(id, parsed);
    }

    #[test]
    fn hex_rejects_uppercase_and_bad_length() {
        assert!(ObjectId::from_hex("AB").is_err());
        let upper = "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855";
        assert!(ObjectId::from_hex(upper).is_err());
    }
}
