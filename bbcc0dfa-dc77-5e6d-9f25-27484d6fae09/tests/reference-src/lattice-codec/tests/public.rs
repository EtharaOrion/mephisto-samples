//! Public test subset for lattice-codec. Necessary but not sufficient: the
//! hidden evaluator checks additional encodings, rejection paths, and CRC
//! vectors.

use lattice_codec::{
    crc32, delta_decode, delta_encode, read_varint, write_varint, zigzag_decode, zigzag_encode,
};

#[test]
fn varint_known_encoding() {
    let mut out = Vec::new();
    write_varint(&mut out, 300);
    assert_eq!(out, vec![0xAC, 0x02]);
    let (value, pos) = read_varint(&out, 0).unwrap();
    assert_eq!(value, 300);
    assert_eq!(pos, 2);
}

#[test]
fn varint_rejects_truncation() {
    assert!(read_varint(&[0x80], 0).is_err());
}

#[test]
fn zigzag_roundtrip() {
    for v in [0i64, -1, 1, -2, i64::MIN, i64::MAX] {
        assert_eq!(zigzag_decode(zigzag_encode(v)), v);
    }
}

#[test]
fn delta_roundtrip() {
    let values = vec![5u64, 5, 9, 2, u64::MAX, 0];
    let mut out = Vec::new();
    delta_encode(&mut out, &values);
    let (decoded, end) = delta_decode(&out, 0, values.len()).unwrap();
    assert_eq!(decoded, values);
    assert_eq!(end, out.len());
}

#[test]
fn crc32_check_vector() {
    assert_eq!(crc32(b"123456789"), 0xCBF43926);
    assert_eq!(crc32(b""), 0);
}
