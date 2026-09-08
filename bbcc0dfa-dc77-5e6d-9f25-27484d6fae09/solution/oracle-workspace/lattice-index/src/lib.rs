//! lattice-index: the on-disk chunk index `index/index.lix`.
//!
//! Layout (all integers LEB128 varints unless noted):
//! header = magic b"LIX\x01" then varint entry_count; body = entries sorted
//! ascending by chunk hash bytes, each entry [32-byte hash][varint pack_id]
//! [varint offset][varint len][varint refcount]; trailer = CRC32 (IEEE) of
//! every preceding byte, little-endian u32. Serialization is deterministic:
//! equal maps produce equal bytes.

#![forbid(unsafe_code)]

use std::collections::BTreeMap;

use lattice_codec::{crc32, read_varint, write_varint};
use lattice_types::{ChunkId, LatticeError, HASH_LEN};

pub const INDEX_MAGIC: &[u8; 4] = b"LIX\x01";

/// Where a chunk's bytes live and how many manifests reference it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IndexEntry {
    pub pack_id: u64,
    pub offset: u64,
    pub len: u64,
    pub refcount: u64,
}

/// In-memory chunk index, keyed by chunk hash, sorted by construction.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct ChunkIndex {
    entries: BTreeMap<ChunkId, IndexEntry>,
}

impl ChunkIndex {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn get(&self, id: &ChunkId) -> Option<&IndexEntry> {
        self.entries.get(id)
    }

    pub fn insert(&mut self, id: ChunkId, entry: IndexEntry) {
        self.entries.insert(id, entry);
    }

    pub fn increment_refcount(&mut self, id: &ChunkId) -> Result<(), LatticeError> {
        match self.entries.get_mut(id) {
            Some(e) => {
                e.refcount += 1;
                Ok(())
            }
            None => Err(LatticeError::Malformed(format!(
                "refcount increment for absent chunk {}",
                id
            ))),
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = (&ChunkId, &IndexEntry)> {
        self.entries.iter()
    }

    /// Serialize to the normative `index.lix` byte layout.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(INDEX_MAGIC);
        write_varint(&mut out, self.entries.len() as u64);
        for (id, entry) in &self.entries {
            out.extend_from_slice(&id.0);
            write_varint(&mut out, entry.pack_id);
            write_varint(&mut out, entry.offset);
            write_varint(&mut out, entry.len);
            write_varint(&mut out, entry.refcount);
        }
        let crc = crc32(&out);
        out.extend_from_slice(&crc.to_le_bytes());
        out
    }

    /// Parse and validate an `index.lix` byte image. Rejects bad magic,
    /// truncation, unsorted or duplicate hashes, trailing garbage, and CRC
    /// mismatch (reported as ChecksumMismatch with what "index").
    pub fn from_bytes(data: &[u8]) -> Result<Self, LatticeError> {
        if data.len() < INDEX_MAGIC.len() + 4 {
            return Err(LatticeError::Truncated);
        }
        if &data[..INDEX_MAGIC.len()] != INDEX_MAGIC {
            return Err(LatticeError::Malformed("bad index magic".to_string()));
        }
        let body_end = data.len() - 4;
        let stored_crc = u32::from_le_bytes([
            data[body_end],
            data[body_end + 1],
            data[body_end + 2],
            data[body_end + 3],
        ]);
        let actual_crc = crc32(&data[..body_end]);
        if stored_crc != actual_crc {
            return Err(LatticeError::ChecksumMismatch {
                what: "index".to_string(),
                location: "index.lix trailer".to_string(),
            });
        }
        let body = &data[..body_end];
        let (count, mut pos) = read_varint(body, INDEX_MAGIC.len())?;
        let mut entries = BTreeMap::new();
        let mut prev: Option<ChunkId> = None;
        for _ in 0..count {
            if pos + HASH_LEN > body.len() {
                return Err(LatticeError::Truncated);
            }
            let mut hash = [0u8; HASH_LEN];
            hash.copy_from_slice(&body[pos..pos + HASH_LEN]);
            let id = ChunkId(hash);
            pos += HASH_LEN;
            let (pack_id, p1) = read_varint(body, pos)?;
            let (offset, p2) = read_varint(body, p1)?;
            let (len, p3) = read_varint(body, p2)?;
            let (refcount, p4) = read_varint(body, p3)?;
            pos = p4;
            if let Some(ref prev_id) = prev {
                if *prev_id >= id {
                    return Err(LatticeError::Malformed(
                        "index entries not strictly ascending".to_string(),
                    ));
                }
            }
            prev = Some(id);
            entries.insert(
                id,
                IndexEntry {
                    pack_id,
                    offset,
                    len,
                    refcount,
                },
            );
        }
        if pos != body.len() {
            return Err(LatticeError::Malformed(
                "trailing bytes after index entries".to_string(),
            ));
        }
        Ok(Self { entries })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ChunkIndex {
        let mut idx = ChunkIndex::new();
        for i in 0..5u8 {
            let mut hash = [0u8; HASH_LEN];
            hash[0] = i * 7 + 1;
            hash[31] = i;
            idx.insert(
                ChunkId(hash),
                IndexEntry {
                    pack_id: 0,
                    offset: u64::from(i) * 1000,
                    len: 512 + u64::from(i),
                    refcount: 1 + u64::from(i % 2),
                },
            );
        }
        idx
    }

    #[test]
    fn roundtrip_preserves_entries() {
        let idx = sample();
        let bytes = idx.to_bytes();
        let parsed = ChunkIndex::from_bytes(&bytes).unwrap();
        assert_eq!(parsed, idx);
    }

    #[test]
    fn serialization_is_deterministic() {
        assert_eq!(sample().to_bytes(), sample().to_bytes());
    }

    #[test]
    fn crc_flip_detected() {
        let mut bytes = sample().to_bytes();
        let mid = bytes.len() / 2;
        bytes[mid] ^= 0x01;
        match ChunkIndex::from_bytes(&bytes) {
            Err(LatticeError::ChecksumMismatch { what, .. }) => assert_eq!(what, "index"),
            other => panic!("expected checksum mismatch, got {:?}", other),
        }
    }

    #[test]
    fn bad_magic_rejected() {
        let mut bytes = sample().to_bytes();
        bytes[0] = b'X';
        assert!(matches!(
            ChunkIndex::from_bytes(&bytes),
            Err(LatticeError::Malformed(_))
        ));
    }

    #[test]
    fn empty_index_roundtrip() {
        let idx = ChunkIndex::new();
        let parsed = ChunkIndex::from_bytes(&idx.to_bytes()).unwrap();
        assert!(parsed.is_empty());
    }

    #[test]
    fn refcount_increment() {
        let mut idx = sample();
        let id = *idx.iter().next().unwrap().0;
        let before = idx.get(&id).unwrap().refcount;
        idx.increment_refcount(&id).unwrap();
        assert_eq!(idx.get(&id).unwrap().refcount, before + 1);
        let missing = ChunkId([0xFF; HASH_LEN]);
        assert!(idx.increment_refcount(&missing).is_err());
    }
}
