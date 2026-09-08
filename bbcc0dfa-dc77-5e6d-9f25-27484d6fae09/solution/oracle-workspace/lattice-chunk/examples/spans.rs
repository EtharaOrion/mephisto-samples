use lattice_chunk::{chunk_spans, gear_table};

fn main() {
    let path = std::env::args().nth(1).expect("usage: spans <file>");
    let data = std::fs::read(&path).expect("read input");
    let gear = gear_table();
    let spans = chunk_spans(&data, &gear);
    for s in &spans {
        println!("{} {}", s.offset, s.len);
    }
    println!("chunks {}", spans.len());
}
