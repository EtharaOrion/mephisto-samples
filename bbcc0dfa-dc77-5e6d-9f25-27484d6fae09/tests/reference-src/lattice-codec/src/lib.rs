//! lattice-codec: LEB128 varints, zigzag, delta coding, and CRC32 (IEEE).
//!
//! Every multi-byte length or offset in LatticeStore's on-disk formats is a
//! LEB128 varint; every trailer checksum is CRC32 (IEEE, reflected,
//! polynomial 0xEDB88320, init 0xFFFFFFFF, final xor 0xFFFFFFFF). The exact
//! byte encodings here are normative for the store formats.

#![forbid(unsafe_code)]

use lattice_types::LatticeError;

/// Append `value` to `out` as an unsigned LEB128 varint (7 bits per byte,
/// low groups first, high bit set on continuation bytes).
pub fn write_varint(out: &mut Vec<u8>, mut value: u64) {
    loop {
        let byte = (value & 0x7F) as u8;
        value >>= 7;
        if value == 0 {
            out.push(byte);
            return;
        }
        out.push(byte | 0x80);
    }
}

/// Decode an unsigned LEB128 varint from `data[pos..]`, returning the value
/// and the new position. Rejects truncation and encodings longer than 10
/// bytes or overflowing 64 bits.
pub fn read_varint(data: &[u8], pos: usize) -> Result<(u64, usize), LatticeError> {
    let mut value: u64 = 0;
    let mut shift: u32 = 0;
    let mut i = pos;
    loop {
        if i >= data.len() {
            return Err(LatticeError::Truncated);
        }
        let byte = data[i];
        i += 1;
        if shift == 63 && (byte & 0x7E) != 0 {
            return Err(LatticeError::Malformed("varint overflow".to_string()));
        }
        value |= u64::from(byte & 0x7F) << shift;
        if byte & 0x80 == 0 {
            return Ok((value, i));
        }
        shift += 7;
        if shift > 63 {
            return Err(LatticeError::Malformed("varint too long".to_string()));
        }
    }
}

/// Map a signed value onto an unsigned one for varint coding:
/// 0, -1, 1, -2, ... become 0, 1, 2, 3, ...
pub fn zigzag_encode(value: i64) -> u64 {
    ((value << 1) ^ (value >> 63)) as u64
}

/// Inverse of [`zigzag_encode`].
pub fn zigzag_decode(value: u64) -> i64 {
    ((value >> 1) as i64) ^ -((value & 1) as i64)
}

/// Encode `values` as zigzag varint deltas from each previous value (first
/// delta is from 0).
pub fn delta_encode(out: &mut Vec<u8>, values: &[u64]) {
    let mut prev: u64 = 0;
    for &v in values {
        let delta = (v as i64).wrapping_sub(prev as i64);
        write_varint(out, zigzag_encode(delta));
        prev = v;
    }
}

/// Decode `count` values previously written by [`delta_encode`] from
/// `data[pos..]`, returning the values and the new position.
pub fn delta_decode(
    data: &[u8],
    pos: usize,
    count: usize,
) -> Result<(Vec<u64>, usize), LatticeError> {
    let mut values = Vec::with_capacity(count);
    let mut prev: u64 = 0;
    let mut i = pos;
    for _ in 0..count {
        let (raw, next) = read_varint(data, i)?;
        i = next;
        let v = (prev as i64).wrapping_add(zigzag_decode(raw)) as u64;
        values.push(v);
        prev = v;
    }
    Ok((values, i))
}

fn crc32_table() -> [u32; 256] {
    let mut table = [0u32; 256];
    for (i, slot) in table.iter_mut().enumerate() {
        let mut crc = i as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
        *slot = crc;
    }
    table
}

/// CRC32 (IEEE) over `data`.
pub fn crc32(data: &[u8]) -> u32 {
    let table = crc32_table();
    let mut crc: u32 = 0xFFFF_FFFF;
    for &b in data {
        crc = (crc >> 8) ^ table[((crc ^ u32::from(b)) & 0xFF) as usize];
    }
    crc ^ 0xFFFF_FFFF
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn varint_roundtrip() {
        let cases = [0u64, 1, 127, 128, 300, u32::MAX as u64, u64::MAX];
        for &v in &cases {
            let mut buf = Vec::new();
            write_varint(&mut buf, v);
            let (decoded, pos) = read_varint(&buf, 0).unwrap();
            assert_eq!(decoded, v);
            assert_eq!(pos, buf.len());
        }
    }

    #[test]
    fn varint_known_encodings() {
        let mut buf = Vec::new();
        write_varint(&mut buf, 300);
        assert_eq!(buf, vec![0xAC, 0x02]);
        buf.clear();
        write_varint(&mut buf, 0);
        assert_eq!(buf, vec![0x00]);
    }

    #[test]
    fn varint_rejects_truncation() {
        assert!(matches!(
            read_varint(&[0x80], 0),
            Err(LatticeError::Truncated)
        ));
    }

    #[test]
    fn zigzag_roundtrip() {
        for v in [-3i64, -1, 0, 1, 2, i64::MIN, i64::MAX] {
            assert_eq!(zigzag_decode(zigzag_encode(v)), v);
        }
        assert_eq!(zigzag_encode(0), 0);
        assert_eq!(zigzag_encode(-1), 1);
        assert_eq!(zigzag_encode(1), 2);
    }

    #[test]
    fn delta_roundtrip() {
        let values = [5u64, 5, 9, 3, 1_000_000, 0];
        let mut buf = Vec::new();
        delta_encode(&mut buf, &values);
        let (decoded, pos) = delta_decode(&buf, 0, values.len()).unwrap();
        assert_eq!(decoded, values);
        assert_eq!(pos, buf.len());
    }

    #[test]
    fn crc32_known_vector() {
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
        assert_eq!(crc32(b""), 0);
    }
}
