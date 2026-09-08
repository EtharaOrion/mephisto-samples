//! Public test subset for lattice-index. Necessary but not sufficient: the
//! hidden evaluator additionally checks the exact serialized bytes, the
//! strict ordering rule, and corruption rejection.

use lattice_index::{ChunkIndex, IndexEntry};
use lattice_types::ChunkId;

#[test]
fn empty_index_roundtrip() {
    let index = ChunkIndex::new();
    let bytes = index.to_bytes();
    let parsed = ChunkIndex::from_bytes(&bytes).unwrap();
    assert_eq!(parsed.len(), 0);
}

#[test]
fn insert_get_roundtrip() {
    let mut index = ChunkIndex::new();
    let id = ChunkId([3u8; 32]);
    index.insert(
        id,
        IndexEntry {
            pack_id: 0,
            offset: 16,
            len: 4096,
            refcount: 1,
        },
    );
    let bytes = index.to_bytes();
    let parsed = ChunkIndex::from_bytes(&bytes).unwrap();
    let entry = parsed.get(&id).unwrap();
    assert_eq!(entry.offset, 16);
    assert_eq!(entry.len, 4096);
    assert_eq!(entry.refcount, 1);
}

#[test]
fn refcount_increment() {
    let mut index = ChunkIndex::new();
    let id = ChunkId([7u8; 32]);
    index.insert(
        id,
        IndexEntry {
            pack_id: 0,
            offset: 16,
            len: 10,
            refcount: 0,
        },
    );
    index.increment_refcount(&id).unwrap();
    index.increment_refcount(&id).unwrap();
    assert_eq!(index.get(&id).unwrap().refcount, 2);
    assert!(index.increment_refcount(&ChunkId([8u8; 32])).is_err());
}
