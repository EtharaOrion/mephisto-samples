//! Public test subset for lattice-store. Necessary but far from sufficient:
//! the hidden evaluator grades exact on-disk bytes, crash recovery, and
//! corruption reporting through the CLI on regenerated workloads.

use std::fs;
use std::path::PathBuf;

use lattice_store::{Store, StatsReport, PACK_FILE};
use lattice_types::{INDEX_FILE, JOURNAL_FILE, META_FILE};

fn tempdir(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "lattice-public-test-{}-{}",
        tag,
        std::process::id()
    ));
    if dir.exists() {
        fs::remove_dir_all(&dir).unwrap();
    }
    dir
}

#[test]
fn init_creates_expected_layout() {
    let root = tempdir("layout");
    Store::init(&root).unwrap();
    assert_eq!(fs::read(root.join(META_FILE)).unwrap().len(), 64);
    assert_eq!(fs::read(root.join(PACK_FILE)).unwrap().len(), 16);
    assert!(root.join(INDEX_FILE).is_file());
    assert!(root.join(JOURNAL_FILE).is_file());
    assert!(root.join("manifests").is_dir());
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn init_refuses_non_empty_directory() {
    let root = tempdir("refuse");
    fs::create_dir_all(&root).unwrap();
    fs::write(root.join("existing"), b"x").unwrap();
    assert!(Store::init(&root).is_err());
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn put_get_roundtrip() {
    let root = tempdir("roundtrip");
    let store = Store::init(&root).unwrap();
    let content = b"hello lattice".to_vec();
    let outcome = store.put_bytes(&content).unwrap();
    assert_eq!(outcome.size, content.len() as u64);
    assert_eq!(outcome.n_chunks, 1);
    assert_eq!(store.get(&outcome.object).unwrap(), content);
    let report = store.verify().unwrap();
    assert_eq!(report.objects, 1);
    assert_eq!(report.packs, 1);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn dedup_ratio_formatting() {
    let report = StatsReport {
        objects: 0,
        chunks: 0,
        unique_bytes: 0,
        logical_bytes: 0,
        pack_bytes: 16,
    };
    assert_eq!(report.dedup_ratio_string(), "0.0000");
}
