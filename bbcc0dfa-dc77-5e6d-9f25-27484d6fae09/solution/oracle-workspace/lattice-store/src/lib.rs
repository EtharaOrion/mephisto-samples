//! lattice-store: store orchestration over the sibling crates.
//!
//! On-disk layout under a store root: `lattice.meta` (fixed 64 bytes: magic
//! b"LATSTORE", version u16 LE, chunk_min u32 LE, chunk_max u32 LE,
//! mask_bits u32 LE, zero padding through byte 59, CRC32 of bytes 0..60 LE);
//! `objects/pack-000000.lpk` (header 16 bytes: magic b"LPK\x01", pack index
//! u32 LE, 8 reserved zero bytes; then records [varint len][raw chunk
//! bytes]); `manifests/<object-hex>.lmf` (magic b"LMF\x01", varint object
//! size, varint chunk count, per chunk [32-byte hash][varint len], CRC32 of
//! all preceding bytes LE); `index/index.lix` (lattice-index format);
//! `journal.llg` (lattice-log format, first record after init is
//! CHECKPOINT).
//!
//! Commit ordering for put: append chunk bytes to the pack with matching
//! CHUNK_APPENDED journal records after a BEGIN_PUT, then write the
//! manifest, then rewrite the index, then append COMMIT_PUT carrying the
//! committed pack length and the index trailer CRC32. Recovery on open:
//! replay the journal, truncate it to the durable prefix, truncate the pack
//! to the last committed pack length, and remove every manifest file whose
//! object id lacks a durable COMMIT_PUT record (manifests are swept against
//! the committed set, so a manifest orphaned by a crash before its
//! BEGIN_PUT became durable is still removed). Manifest files are visited
//! in sorted filename order. The object id is the SHA-256 of the complete
//! object content. Repeated put of an already stored object changes
//! nothing on disk.

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

pub const PACK_MAGIC: &[u8; 4] = b"LPK\x01";
pub const MANIFEST_MAGIC: &[u8; 4] = b"LMF\x01";
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
    /// Dedup ratio logical/unique with exactly four decimals, computed in
    /// integer arithmetic (truncating): "0.0000" when unique_bytes is 0.
    pub fn dedup_ratio_string(&self) -> String {
        if self.unique_bytes == 0 {
            return "0.0000".to_string();
        }
        let q = self.logical_bytes.saturating_mul(10_000) / self.unique_bytes;
        format!("{}.{:04}", q / 10_000, q % 10_000)
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
        let mut out = Vec::new();
        out.extend_from_slice(MANIFEST_MAGIC);
        write_varint(&mut out, self.size);
        write_varint(&mut out, self.chunks.len() as u64);
        for (id, len) in &self.chunks {
            out.extend_from_slice(&id.0);
            write_varint(&mut out, *len);
        }
        let crc = crc32(&out);
        out.extend_from_slice(&crc.to_le_bytes());
        out
    }

    pub fn from_bytes(data: &[u8], location: &str) -> Result<Self, LatticeError> {
        if data.len() < MANIFEST_MAGIC.len() + 4 {
            return Err(LatticeError::Truncated);
        }
        if &data[..MANIFEST_MAGIC.len()] != MANIFEST_MAGIC {
            return Err(LatticeError::Malformed(format!(
                "bad manifest magic at {}",
                location
            )));
        }
        let body_end = data.len() - 4;
        let stored_crc = u32::from_le_bytes([
            data[body_end],
            data[body_end + 1],
            data[body_end + 2],
            data[body_end + 3],
        ]);
        if stored_crc != crc32(&data[..body_end]) {
            return Err(LatticeError::ChecksumMismatch {
                what: "manifest".to_string(),
                location: location.to_string(),
            });
        }
        let body = &data[..body_end];
        let (size, pos) = read_varint(body, MANIFEST_MAGIC.len())?;
        let (count, mut pos) = read_varint(body, pos)?;
        let mut chunks = Vec::new();
        for _ in 0..count {
            if pos + HASH_LEN > body.len() {
                return Err(LatticeError::Truncated);
            }
            let mut hash = [0u8; HASH_LEN];
            hash.copy_from_slice(&body[pos..pos + HASH_LEN]);
            pos += HASH_LEN;
            let (len, next) = read_varint(body, pos)?;
            pos = next;
            chunks.push((ChunkId(hash), len));
        }
        if pos != body.len() {
            return Err(LatticeError::Malformed(format!(
                "trailing bytes in manifest at {}",
                location
            )));
        }
        Ok(Self { size, chunks })
    }
}

fn meta_bytes() -> [u8; META_LEN] {
    let mut meta = [0u8; META_LEN];
    meta[..8].copy_from_slice(META_MAGIC);
    meta[8..10].copy_from_slice(&META_VERSION.to_le_bytes());
    meta[10..14].copy_from_slice(&CHUNK_MIN.to_le_bytes());
    meta[14..18].copy_from_slice(&CHUNK_MAX.to_le_bytes());
    meta[18..22].copy_from_slice(&CHUNK_MASK_BITS.to_le_bytes());
    let crc = crc32(&meta[..60]);
    meta[60..64].copy_from_slice(&crc.to_le_bytes());
    meta
}

fn io_err(e: std::io::Error) -> LatticeError {
    LatticeError::Io(e.to_string())
}

impl Store {
    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn init(root: &Path) -> Result<Store, LatticeError> {
        if root.exists() {
            let mut entries = fs::read_dir(root).map_err(io_err)?;
            if entries.next().is_some() {
                return Err(LatticeError::Malformed(
                    "refusing to initialize non-empty directory".to_string(),
                ));
            }
        } else {
            fs::create_dir_all(root).map_err(io_err)?;
        }
        fs::create_dir_all(root.join(PACK_DIR)).map_err(io_err)?;
        fs::create_dir_all(root.join(MANIFEST_DIR)).map_err(io_err)?;
        fs::create_dir_all(root.join("index")).map_err(io_err)?;
        fs::write(root.join(META_FILE), meta_bytes()).map_err(io_err)?;
        let mut pack = Vec::with_capacity(PACK_HEADER_LEN as usize);
        pack.extend_from_slice(PACK_MAGIC);
        pack.extend_from_slice(&0u32.to_le_bytes());
        pack.extend_from_slice(&[0u8; 8]);
        fs::write(root.join(PACK_FILE), &pack).map_err(io_err)?;
        fs::write(root.join(INDEX_FILE), ChunkIndex::new().to_bytes()).map_err(io_err)?;
        fs::write(root.join(JOURNAL_FILE), JournalRecord::Checkpoint.to_bytes())
            .map_err(io_err)?;
        Ok(Store {
            root: root.to_path_buf(),
        })
    }

    pub fn open(root: &Path) -> Result<(Store, RecoveryReport), LatticeError> {
        let meta = fs::read(root.join(META_FILE))
            .map_err(|_| LatticeError::Malformed("not a lattice store".to_string()))?;
        if meta.len() != META_LEN || meta[..8] != *META_MAGIC {
            return Err(LatticeError::Malformed("not a lattice store".to_string()));
        }
        let stored_crc = u32::from_le_bytes([meta[60], meta[61], meta[62], meta[63]]);
        if stored_crc != crc32(&meta[..60]) {
            return Err(LatticeError::ChecksumMismatch {
                what: "meta".to_string(),
                location: META_FILE.to_string(),
            });
        }
        let store = Store {
            root: root.to_path_buf(),
        };
        let report = store.recover()?;
        Ok((store, report))
    }

    fn recover(&self) -> Result<RecoveryReport, LatticeError> {
        let journal_path = self.root.join(JOURNAL_FILE);
        let journal = fs::read(&journal_path).map_err(io_err)?;
        let outcome = replay(&journal);
        let mut report = RecoveryReport {
            journal_truncated: false,
            pack_truncated: false,
            manifests_removed: 0,
        };
        if outcome.tail_discarded {
            fs::write(&journal_path, &journal[..outcome.durable_len as usize])
                .map_err(io_err)?;
            report.journal_truncated = true;
        }
        let mut committed_pack_len = PACK_HEADER_LEN;
        let mut committed: std::collections::BTreeSet<ObjectId> =
            std::collections::BTreeSet::new();
        for rec in &outcome.records {
            if let JournalRecord::CommitPut { object, pack_len, .. } = rec {
                committed.insert(*object);
                committed_pack_len = *pack_len;
            }
        }
        let manifest_dir = self.root.join(MANIFEST_DIR);
        let mut entries: Vec<PathBuf> = fs::read_dir(&manifest_dir)
            .map_err(io_err)?
            .filter_map(|e| e.ok().map(|e| e.path()))
            .collect();
        entries.sort();
        for path in entries {
            let stem = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or_default()
                .to_string();
            let keep = ObjectId::from_hex(&stem)
                .map(|id| committed.contains(&id))
                .unwrap_or(false);
            if !keep {
                fs::remove_file(&path).map_err(io_err)?;
                report.manifests_removed += 1;
            }
        }
        let pack_path = self.root.join(PACK_FILE);
        let pack_len = fs::metadata(&pack_path).map_err(io_err)?.len();
        if pack_len > committed_pack_len {
            let pack = fs::read(&pack_path).map_err(io_err)?;
            fs::write(&pack_path, &pack[..committed_pack_len as usize]).map_err(io_err)?;
            report.pack_truncated = true;
        }
        Ok(report)
    }

    fn manifest_path(&self, object: &ObjectId) -> PathBuf {
        self.root.join(MANIFEST_DIR).join(format!("{}.lmf", object))
    }

    fn load_index(&self) -> Result<ChunkIndex, LatticeError> {
        let bytes = fs::read(self.root.join(INDEX_FILE)).map_err(io_err)?;
        ChunkIndex::from_bytes(&bytes)
    }

    pub fn put_bytes(&self, content: &[u8]) -> Result<PutOutcome, LatticeError> {
        let object = ObjectId(sha256(content));
        let manifest_path = self.manifest_path(&object);
        if manifest_path.exists() {
            let manifest_bytes = fs::read(&manifest_path).map_err(io_err)?;
            let manifest =
                Manifest::from_bytes(&manifest_bytes, manifest_path.to_string_lossy().as_ref())?;
            return Ok(PutOutcome {
                object,
                n_chunks: manifest.chunks.len() as u64,
                n_new_chunks: 0,
                size: content.len() as u64,
            });
        }
        let gear = gear_table();
        let spans = chunk_spans(content, &gear);
        let mut index = self.load_index()?;
        let journal_path = self.root.join(JOURNAL_FILE);
        let pack_path = self.root.join(PACK_FILE);
        let mut journal = fs::read(&journal_path).map_err(io_err)?;
        let mut pack = fs::read(&pack_path).map_err(io_err)?;
        journal.extend_from_slice(&JournalRecord::BeginPut { object }.to_bytes());
        let mut manifest_chunks: Vec<(ChunkId, u64)> = Vec::with_capacity(spans.len());
        let mut n_new: u64 = 0;
        for span in &spans {
            let chunk_bytes = &content[span.offset..span.offset + span.len];
            let chunk = ChunkId(sha256(chunk_bytes));
            manifest_chunks.push((chunk, span.len as u64));
            if index.get(&chunk).is_some() {
                continue;
            }
            let mut record = Vec::new();
            write_varint(&mut record, span.len as u64);
            let offset = pack.len() as u64 + record.len() as u64;
            record.extend_from_slice(chunk_bytes);
            pack.extend_from_slice(&record);
            index.insert(
                chunk,
                IndexEntry {
                    pack_id: 0,
                    offset,
                    len: span.len as u64,
                    refcount: 0,
                },
            );
            journal.extend_from_slice(
                &JournalRecord::ChunkAppended {
                    chunk,
                    pack_id: 0,
                    offset,
                    len: span.len as u64,
                }
                .to_bytes(),
            );
            n_new += 1;
        }
        for (chunk, _) in &manifest_chunks {
            index.increment_refcount(chunk)?;
        }
        let manifest = Manifest {
            size: content.len() as u64,
            chunks: manifest_chunks.clone(),
        };
        let index_bytes = index.to_bytes();
        let index_crc = u32::from_le_bytes([
            index_bytes[index_bytes.len() - 4],
            index_bytes[index_bytes.len() - 3],
            index_bytes[index_bytes.len() - 2],
            index_bytes[index_bytes.len() - 1],
        ]);
        journal.extend_from_slice(
            &JournalRecord::CommitPut {
                object,
                pack_len: pack.len() as u64,
                index_crc,
            }
            .to_bytes(),
        );
        fs::write(&pack_path, &pack).map_err(io_err)?;
        fs::write(&manifest_path, manifest.to_bytes()).map_err(io_err)?;
        fs::write(self.root.join(INDEX_FILE), &index_bytes).map_err(io_err)?;
        fs::write(&journal_path, &journal).map_err(io_err)?;
        Ok(PutOutcome {
            object,
            n_chunks: spans.len() as u64,
            n_new_chunks: n_new,
            size: content.len() as u64,
        })
    }

    pub fn get(&self, object: &ObjectId) -> Result<Vec<u8>, LatticeError> {
        let manifest_path = self.manifest_path(object);
        if !manifest_path.exists() {
            return Err(LatticeError::UnknownObject(object.to_string()));
        }
        let manifest_bytes = fs::read(&manifest_path).map_err(io_err)?;
        let manifest =
            Manifest::from_bytes(&manifest_bytes, manifest_path.to_string_lossy().as_ref())?;
        let index = self.load_index()?;
        let pack = fs::read(self.root.join(PACK_FILE)).map_err(io_err)?;
        let mut content = Vec::with_capacity(manifest.size as usize);
        for (chunk, len) in &manifest.chunks {
            let entry = index.get(chunk).ok_or_else(|| {
                LatticeError::Malformed(format!("manifest references absent chunk {}", chunk))
            })?;
            let start = entry.offset as usize;
            let end = start + entry.len as usize;
            if entry.len != *len || end > pack.len() {
                return Err(LatticeError::ChecksumMismatch {
                    what: "chunk".to_string(),
                    location: format!("pack offset {}", entry.offset),
                });
            }
            content.extend_from_slice(&pack[start..end]);
        }
        if ObjectId(sha256(&content)) != *object || content.len() as u64 != manifest.size {
            return Err(LatticeError::ChecksumMismatch {
                what: "object".to_string(),
                location: object.to_string(),
            });
        }
        Ok(content)
    }

    pub fn verify(&self) -> Result<VerifyReport, LatticeError> {
        let pack_path = self.root.join(PACK_FILE);
        let pack = fs::read(&pack_path).map_err(io_err)?;
        if pack.len() < PACK_HEADER_LEN as usize || pack[..4] != *PACK_MAGIC {
            return Err(LatticeError::ChecksumMismatch {
                what: "pack".to_string(),
                location: "pack-000000.lpk header".to_string(),
            });
        }
        let index = self.load_index()?;
        for (chunk, entry) in index.iter() {
            let start = entry.offset as usize;
            let end = start.saturating_add(entry.len as usize);
            if entry.pack_id != 0 || start < PACK_HEADER_LEN as usize || end > pack.len() {
                return Err(LatticeError::ChecksumMismatch {
                    what: "index".to_string(),
                    location: format!("entry {}", chunk),
                });
            }
            if ChunkId(sha256(&pack[start..end])) != *chunk {
                return Err(LatticeError::ChecksumMismatch {
                    what: "chunk".to_string(),
                    location: format!("pack offset {}", entry.offset),
                });
            }
        }
        let mut objects: u64 = 0;
        let mut manifest_names: Vec<String> = Vec::new();
        for entry in fs::read_dir(self.root.join(MANIFEST_DIR)).map_err(io_err)? {
            let entry = entry.map_err(io_err)?;
            manifest_names.push(entry.file_name().to_string_lossy().to_string());
        }
        manifest_names.sort();
        for name in manifest_names {
            let path = self.root.join(MANIFEST_DIR).join(&name);
            let bytes = fs::read(&path).map_err(io_err)?;
            let manifest = Manifest::from_bytes(&bytes, &format!("manifests/{}", name))?;
            let mut total: u64 = 0;
            for (chunk, len) in &manifest.chunks {
                let entry = index.get(chunk).ok_or_else(|| {
                    LatticeError::ChecksumMismatch {
                        what: "manifest".to_string(),
                        location: format!("manifests/{} chunk {}", name, chunk),
                    }
                })?;
                if entry.len != *len {
                    return Err(LatticeError::ChecksumMismatch {
                        what: "manifest".to_string(),
                        location: format!("manifests/{} chunk {}", name, chunk),
                    });
                }
                total += len;
            }
            if total != manifest.size {
                return Err(LatticeError::ChecksumMismatch {
                    what: "manifest".to_string(),
                    location: format!("manifests/{}", name),
                });
            }
            objects += 1;
        }
        let journal = fs::read(self.root.join(JOURNAL_FILE)).map_err(io_err)?;
        let outcome = replay(&journal);
        if outcome.tail_discarded {
            return Err(LatticeError::ChecksumMismatch {
                what: "journal".to_string(),
                location: format!("record at byte {}", outcome.durable_len),
            });
        }
        Ok(VerifyReport {
            packs: 1,
            chunks: index.len() as u64,
            objects,
        })
    }

    pub fn stats(&self) -> Result<StatsReport, LatticeError> {
        let index = self.load_index()?;
        let mut unique_bytes: u64 = 0;
        for (_, entry) in index.iter() {
            unique_bytes += entry.len;
        }
        let mut objects: u64 = 0;
        let mut logical_bytes: u64 = 0;
        let mut names: Vec<String> = Vec::new();
        for entry in fs::read_dir(self.root.join(MANIFEST_DIR)).map_err(io_err)? {
            let entry = entry.map_err(io_err)?;
            names.push(entry.file_name().to_string_lossy().to_string());
        }
        names.sort();
        for name in names {
            let path = self.root.join(MANIFEST_DIR).join(&name);
            let bytes = fs::read(&path).map_err(io_err)?;
            let manifest = Manifest::from_bytes(&bytes, &format!("manifests/{}", name))?;
            logical_bytes += manifest.size;
            objects += 1;
        }
        let pack_bytes = fs::metadata(self.root.join(PACK_FILE)).map_err(io_err)?.len();
        Ok(StatsReport {
            objects,
            chunks: index.len() as u64,
            unique_bytes,
            logical_bytes,
            pack_bytes,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tempdir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "lattice-store-test-{}-{}",
            tag,
            std::process::id()
        ));
        if dir.exists() {
            fs::remove_dir_all(&dir).unwrap();
        }
        dir
    }

    fn corpus(len: usize, phase: u8) -> Vec<u8> {
        (0..len)
            .map(|i| {
                let mut z = (i as u64)
                    .wrapping_add(0x9E3779B97F4A7C15u64.wrapping_mul(phase as u64 + 1));
                z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
                z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
                (z ^ (z >> 31)) as u8
            })
            .collect()
    }

    #[test]
    fn init_put_get_roundtrip() {
        let root = tempdir("roundtrip");
        let store = Store::init(&root).unwrap();
        let content = corpus(300_000, 1);
        let outcome = store.put_bytes(&content).unwrap();
        assert_eq!(outcome.size, content.len() as u64);
        assert!(outcome.n_chunks >= 2);
        assert_eq!(outcome.n_new_chunks, outcome.n_chunks);
        let fetched = store.get(&outcome.object).unwrap();
        assert_eq!(fetched, content);
        let report = store.verify().unwrap();
        assert_eq!(report.objects, 1);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn duplicate_put_is_noop() {
        let root = tempdir("dup");
        let store = Store::init(&root).unwrap();
        let content = corpus(150_000, 2);
        let first = store.put_bytes(&content).unwrap();
        let pack_before = fs::read(root.join(PACK_FILE)).unwrap();
        let second = store.put_bytes(&content).unwrap();
        assert_eq!(second.n_new_chunks, 0);
        assert_eq!(second.object, first.object);
        assert_eq!(fs::read(root.join(PACK_FILE)).unwrap(), pack_before);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn shared_chunks_dedupe() {
        let root = tempdir("dedupe");
        let store = Store::init(&root).unwrap();
        let base = corpus(200_000, 3);
        let mut variant = base.clone();
        variant.extend_from_slice(&corpus(50_000, 4));
        let a = store.put_bytes(&base).unwrap();
        let b = store.put_bytes(&variant).unwrap();
        assert!(b.n_new_chunks < b.n_chunks);
        assert_ne!(a.object, b.object);
        assert_eq!(store.get(&b.object).unwrap(), variant);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn init_refuses_non_empty() {
        let root = tempdir("nonempty");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("existing"), b"x").unwrap();
        assert!(Store::init(&root).is_err());
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn get_unknown_object_fails() {
        let root = tempdir("unknown");
        let store = Store::init(&root).unwrap();
        let missing = ObjectId([9u8; HASH_LEN]);
        assert!(matches!(
            store.get(&missing),
            Err(LatticeError::UnknownObject(_))
        ));
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn corrupt_pack_detected_by_verify() {
        let root = tempdir("corrupt");
        let store = Store::init(&root).unwrap();
        store.put_bytes(&corpus(100_000, 5)).unwrap();
        let pack_path = root.join(PACK_FILE);
        let mut pack = fs::read(&pack_path).unwrap();
        let mid = pack.len() / 2;
        pack[mid] ^= 0x40;
        fs::write(&pack_path, &pack).unwrap();
        assert!(matches!(
            store.verify(),
            Err(LatticeError::ChecksumMismatch { .. })
        ));
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn crash_recovery_rolls_back_uncommitted_put() {
        let root = tempdir("recovery");
        let store = Store::init(&root).unwrap();
        let first = store.put_bytes(&corpus(120_000, 6)).unwrap();
        let journal_committed = fs::read(root.join(JOURNAL_FILE)).unwrap();
        let pack_committed = fs::read(root.join(PACK_FILE)).unwrap();
        let index_committed = fs::read(root.join(INDEX_FILE)).unwrap();
        store.put_bytes(&corpus(90_000, 7)).unwrap();
        let journal_full = fs::read(root.join(JOURNAL_FILE)).unwrap();
        fs::write(
            root.join(JOURNAL_FILE),
            &journal_full[..journal_committed.len() + 10],
        )
        .unwrap();
        fs::write(root.join(INDEX_FILE), &index_committed).unwrap();
        let second_obj = ObjectId(sha256(&corpus(90_000, 7)));
        let (recovered, report) = Store::open(&root).unwrap();
        assert!(report.journal_truncated);
        assert!(report.pack_truncated);
        assert_eq!(report.manifests_removed, 1);
        assert_eq!(fs::read(root.join(PACK_FILE)).unwrap(), pack_committed);
        assert_eq!(fs::read(root.join(JOURNAL_FILE)).unwrap(), journal_committed);
        assert_eq!(recovered.get(&first.object).unwrap(), corpus(120_000, 6));
        assert!(recovered.get(&second_obj).is_err());
        recovered.verify().unwrap();
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn stats_report_dedup_ratio_format() {
        let report = StatsReport {
            objects: 2,
            chunks: 3,
            unique_bytes: 3000,
            logical_bytes: 4500,
            pack_bytes: 3100,
        };
        assert_eq!(report.dedup_ratio_string(), "1.5000");
        let zero = StatsReport {
            objects: 0,
            chunks: 0,
            unique_bytes: 0,
            logical_bytes: 0,
            pack_bytes: 16,
        };
        assert_eq!(zero.dedup_ratio_string(), "0.0000");
    }
}
