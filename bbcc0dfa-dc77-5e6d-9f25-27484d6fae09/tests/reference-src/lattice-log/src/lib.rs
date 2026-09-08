//! lattice-log: the crash-consistent journal `journal.llg`.
//!
//! The journal is a flat sequence of records. Each record is
//! [1-byte type][varint payload_len][payload bytes][CRC32 little-endian u32]
//! where the CRC covers the type byte, the encoded payload_len varint, and
//! the payload. Record types: 1 = BEGIN_PUT (payload: 32-byte object id),
//! 2 = CHUNK_APPENDED (payload: 32-byte chunk hash, varint pack_id, varint
//! offset, varint len), 3 = COMMIT_PUT (payload: 32-byte object id, varint
//! committed pack length, varint index crc32), 4 = CHECKPOINT (empty
//! payload). Replay stops cleanly at end of file; a truncated or corrupt
//! tail record is not an error, it marks the recovery point: every record
//! before it is durable, everything at and after it is discarded.

#![forbid(unsafe_code)]

use lattice_codec::{crc32, read_varint, write_varint};
use lattice_types::{ChunkId, LatticeError, ObjectId, HASH_LEN};

pub const REC_BEGIN_PUT: u8 = 1;
pub const REC_CHUNK_APPENDED: u8 = 2;
pub const REC_COMMIT_PUT: u8 = 3;
pub const REC_CHECKPOINT: u8 = 4;

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
        match self {
            JournalRecord::BeginPut { .. } => REC_BEGIN_PUT,
            JournalRecord::ChunkAppended { .. } => REC_CHUNK_APPENDED,
            JournalRecord::CommitPut { .. } => REC_COMMIT_PUT,
            JournalRecord::Checkpoint => REC_CHECKPOINT,
        }
    }

    fn payload(&self) -> Vec<u8> {
        let mut p = Vec::new();
        match self {
            JournalRecord::BeginPut { object } => p.extend_from_slice(&object.0),
            JournalRecord::ChunkAppended {
                chunk,
                pack_id,
                offset,
                len,
            } => {
                p.extend_from_slice(&chunk.0);
                write_varint(&mut p, *pack_id);
                write_varint(&mut p, *offset);
                write_varint(&mut p, *len);
            }
            JournalRecord::CommitPut {
                object,
                pack_len,
                index_crc,
            } => {
                p.extend_from_slice(&object.0);
                write_varint(&mut p, *pack_len);
                write_varint(&mut p, u64::from(*index_crc));
            }
            JournalRecord::Checkpoint => {}
        }
        p
    }

    /// Encode this record to the normative journal byte layout.
    pub fn to_bytes(&self) -> Vec<u8> {
        let payload = self.payload();
        let mut body = vec![self.type_byte()];
        write_varint(&mut body, payload.len() as u64);
        body.extend_from_slice(&payload);
        let crc = crc32(&body);
        body.extend_from_slice(&crc.to_le_bytes());
        body
    }
}

fn take_hash(payload: &[u8], pos: usize) -> Result<([u8; HASH_LEN], usize), LatticeError> {
    if pos + HASH_LEN > payload.len() {
        return Err(LatticeError::Truncated);
    }
    let mut hash = [0u8; HASH_LEN];
    hash.copy_from_slice(&payload[pos..pos + HASH_LEN]);
    Ok((hash, pos + HASH_LEN))
}

fn decode_payload(rec_type: u8, payload: &[u8]) -> Result<JournalRecord, LatticeError> {
    match rec_type {
        REC_BEGIN_PUT => {
            let (hash, pos) = take_hash(payload, 0)?;
            if pos != payload.len() {
                return Err(LatticeError::Malformed("begin_put payload size".to_string()));
            }
            Ok(JournalRecord::BeginPut {
                object: ObjectId(hash),
            })
        }
        REC_CHUNK_APPENDED => {
            let (hash, pos) = take_hash(payload, 0)?;
            let (pack_id, p1) = read_varint(payload, pos)?;
            let (offset, p2) = read_varint(payload, p1)?;
            let (len, p3) = read_varint(payload, p2)?;
            if p3 != payload.len() {
                return Err(LatticeError::Malformed(
                    "chunk_appended payload size".to_string(),
                ));
            }
            Ok(JournalRecord::ChunkAppended {
                chunk: ChunkId(hash),
                pack_id,
                offset,
                len,
            })
        }
        REC_COMMIT_PUT => {
            let (hash, pos) = take_hash(payload, 0)?;
            let (pack_len, p1) = read_varint(payload, pos)?;
            let (index_crc, p2) = read_varint(payload, p1)?;
            if p2 != payload.len() {
                return Err(LatticeError::Malformed(
                    "commit_put payload size".to_string(),
                ));
            }
            let index_crc = u32::try_from(index_crc)
                .map_err(|_| LatticeError::Malformed("commit_put crc range".to_string()))?;
            Ok(JournalRecord::CommitPut {
                object: ObjectId(hash),
                pack_len,
                index_crc,
            })
        }
        REC_CHECKPOINT => {
            if !payload.is_empty() {
                return Err(LatticeError::Malformed(
                    "checkpoint payload size".to_string(),
                ));
            }
            Ok(JournalRecord::Checkpoint)
        }
        other => Err(LatticeError::Malformed(format!(
            "unknown journal record type {}",
            other
        ))),
    }
}

/// Result of replaying a journal image.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayOutcome {
    /// Records recovered in order, up to but excluding any corrupt tail.
    pub records: Vec<JournalRecord>,
    /// Byte offset of the first non-durable byte: the journal should be
    /// truncated to this length during recovery.
    pub durable_len: u64,
    /// True when a truncated or corrupt tail record was discarded.
    pub tail_discarded: bool,
}

/// Replay a journal byte image, applying the tail-recovery rule.
pub fn replay(data: &[u8]) -> ReplayOutcome {
    let mut records = Vec::new();
    let mut pos = 0usize;
    loop {
        if pos == data.len() {
            return ReplayOutcome {
                records,
                durable_len: pos as u64,
                tail_discarded: false,
            };
        }
        match parse_record(data, pos) {
            Ok((rec, next)) => {
                records.push(rec);
                pos = next;
            }
            Err(_) => {
                return ReplayOutcome {
                    records,
                    durable_len: pos as u64,
                    tail_discarded: true,
                };
            }
        }
    }
}

fn parse_record(data: &[u8], pos: usize) -> Result<(JournalRecord, usize), LatticeError> {
    if pos >= data.len() {
        return Err(LatticeError::Truncated);
    }
    let rec_type = data[pos];
    let (payload_len, payload_start) = read_varint(data, pos + 1)?;
    let payload_len = usize::try_from(payload_len)
        .map_err(|_| LatticeError::Malformed("payload length range".to_string()))?;
    let payload_end = payload_start
        .checked_add(payload_len)
        .ok_or(LatticeError::Truncated)?;
    let crc_end = payload_end.checked_add(4).ok_or(LatticeError::Truncated)?;
    if crc_end > data.len() {
        return Err(LatticeError::Truncated);
    }
    let stored_crc = u32::from_le_bytes([
        data[payload_end],
        data[payload_end + 1],
        data[payload_end + 2],
        data[payload_end + 3],
    ]);
    let actual_crc = crc32(&data[pos..payload_end]);
    if stored_crc != actual_crc {
        return Err(LatticeError::ChecksumMismatch {
            what: "journal".to_string(),
            location: format!("record at byte {}", pos),
        });
    }
    let rec = decode_payload(rec_type, &data[payload_start..payload_end])?;
    Ok((rec, crc_end))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_records() -> Vec<JournalRecord> {
        vec![
            JournalRecord::BeginPut {
                object: ObjectId([1u8; HASH_LEN]),
            },
            JournalRecord::ChunkAppended {
                chunk: ChunkId([2u8; HASH_LEN]),
                pack_id: 0,
                offset: 16,
                len: 4096,
            },
            JournalRecord::CommitPut {
                object: ObjectId([1u8; HASH_LEN]),
                pack_len: 4120,
                index_crc: 0xDEADBEEF,
            },
            JournalRecord::Checkpoint,
        ]
    }

    fn encode_all(records: &[JournalRecord]) -> Vec<u8> {
        let mut out = Vec::new();
        for r in records {
            out.extend_from_slice(&r.to_bytes());
        }
        out
    }

    #[test]
    fn clean_replay_recovers_all() {
        let records = sample_records();
        let bytes = encode_all(&records);
        let outcome = replay(&bytes);
        assert_eq!(outcome.records, records);
        assert_eq!(outcome.durable_len, bytes.len() as u64);
        assert!(!outcome.tail_discarded);
    }

    #[test]
    fn truncated_tail_discarded() {
        let records = sample_records();
        let mut bytes = encode_all(&records);
        let full = bytes.len();
        bytes.truncate(full - 3);
        let outcome = replay(&bytes);
        assert_eq!(outcome.records.len(), records.len() - 1);
        assert!(outcome.tail_discarded);
        let prefix = encode_all(&records[..records.len() - 1]);
        assert_eq!(outcome.durable_len, prefix.len() as u64);
    }

    #[test]
    fn corrupt_tail_discarded() {
        let records = sample_records();
        let mut bytes = encode_all(&records);
        let last = bytes.len() - 1;
        bytes[last] ^= 0xFF;
        let outcome = replay(&bytes);
        assert_eq!(outcome.records.len(), records.len() - 1);
        assert!(outcome.tail_discarded);
    }

    #[test]
    fn empty_journal_is_clean() {
        let outcome = replay(&[]);
        assert!(outcome.records.is_empty());
        assert_eq!(outcome.durable_len, 0);
        assert!(!outcome.tail_discarded);
    }

    #[test]
    fn unknown_type_stops_replay() {
        let mut bytes = encode_all(&sample_records()[..1]);
        let mut bad = vec![9u8];
        write_varint(&mut bad, 0);
        let crc = crc32(&bad);
        bad.extend_from_slice(&crc.to_le_bytes());
        bytes.extend_from_slice(&bad);
        let outcome = replay(&bytes);
        assert_eq!(outcome.records.len(), 1);
        assert!(outcome.tail_discarded);
    }
}
