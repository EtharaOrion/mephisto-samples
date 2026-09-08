//! Public test subset for lattice-chunk. These tests are necessary but far
//! from sufficient: the hidden evaluator exercises the same public API on
//! additional inputs, including exact boundary positions cross-checked
//! against the C reference under chunker-ref/.

use lattice_chunk::{chunk_spans, gear_table, next_boundary};
use lattice_types::{CHUNK_MAX, CHUNK_MIN};

#[test]
fn empty_input_has_no_chunks() {
    let gear = gear_table();
    assert_eq!(next_boundary(&[], &gear), 0);
    assert!(chunk_spans(&[], &gear).is_empty());
}

#[test]
fn short_input_is_one_chunk() {
    let gear = gear_table();
    let data = vec![7u8; CHUNK_MIN as usize];
    assert_eq!(next_boundary(&data, &gear), data.len());
    let spans = chunk_spans(&data, &gear);
    assert_eq!(spans.len(), 1);
    assert_eq!(spans[0].offset, 0);
    assert_eq!(spans[0].len, data.len());
}

#[test]
fn spans_partition_the_input() {
    let gear = gear_table();
    let data: Vec<u8> = (0..300_000u64)
        .map(|i| {
            let mut z = i.wrapping_add(0x9E3779B97F4A7C15);
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
            (z ^ (z >> 31)) as u8
        })
        .collect();
    let spans = chunk_spans(&data, &gear);
    let mut cursor = 0usize;
    for span in &spans {
        assert_eq!(span.offset, cursor);
        assert!(span.len >= 1);
        assert!(span.len <= CHUNK_MAX as usize);
        cursor += span.len;
    }
    assert_eq!(cursor, data.len());
}

#[test]
fn gear_table_is_stable() {
    let a = gear_table();
    let b = gear_table();
    assert_eq!(a[..], b[..]);
    assert_ne!(a[0], a[1]);
}
