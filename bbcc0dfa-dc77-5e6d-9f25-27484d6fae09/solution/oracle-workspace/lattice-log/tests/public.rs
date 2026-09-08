//! Public test subset for lattice-log. Necessary but not sufficient: the
//! hidden evaluator additionally checks exact record bytes, every record
//! type, and corrupt-tail byte positions.

use lattice_log::{replay, JournalRecord};
use lattice_types::ObjectId;

#[test]
fn checkpoint_roundtrip() {
    let bytes = JournalRecord::Checkpoint.to_bytes();
    let outcome = replay(&bytes);
    assert!(!outcome.tail_discarded);
    assert_eq!(outcome.durable_len as usize, bytes.len());
    assert_eq!(outcome.records.len(), 1);
}

#[test]
fn truncated_tail_is_discarded() {
    let mut bytes = JournalRecord::Checkpoint.to_bytes();
    let full = JournalRecord::BeginPut {
        object: ObjectId([5u8; 32]),
    }
    .to_bytes();
    let checkpoint_len = bytes.len();
    bytes.extend_from_slice(&full[..full.len() - 3]);
    let outcome = replay(&bytes);
    assert!(outcome.tail_discarded);
    assert_eq!(outcome.durable_len as usize, checkpoint_len);
    assert_eq!(outcome.records.len(), 1);
}

#[test]
fn empty_journal_replays_clean() {
    let outcome = replay(&[]);
    assert!(!outcome.tail_discarded);
    assert_eq!(outcome.durable_len, 0);
    assert!(outcome.records.is_empty());
}
