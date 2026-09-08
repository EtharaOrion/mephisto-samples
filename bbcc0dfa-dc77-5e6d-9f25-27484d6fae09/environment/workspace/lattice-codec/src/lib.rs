






#![forbid(unsafe_code)]

use lattice_types::LatticeError;



pub fn write_varint(out: &mut Vec<u8>, mut value: u64) {
    todo!()
}




pub fn read_varint(data: &[u8], pos: usize) -> Result<(u64, usize), LatticeError> {
    todo!()
}



pub fn zigzag_encode(value: i64) -> u64 {
    todo!()
}


pub fn zigzag_decode(value: u64) -> i64 {
    todo!()
}



pub fn delta_encode(out: &mut Vec<u8>, values: &[u64]) {
    todo!()
}



pub fn delta_decode(
    data: &[u8],
    pos: usize,
    count: usize,
) -> Result<(Vec<u64>, usize), LatticeError> {
    todo!()
}

fn crc32_table() -> [u32; 256] {
    todo!()
}


pub fn crc32(data: &[u8]) -> u32 {
    todo!()
}


