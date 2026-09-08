//! lattice: the LatticeStore command-line interface.
//!
//! Subcommands and their exact observable contract (stdout literals, stderr
//! literals, exit codes) are normative:
//!
//! `lattice init <dir>`: create a store; stdout "initialized lattice store"
//! newline, exit 0; a non-empty target directory prints stderr "error:
//! refusing to initialize non-empty directory" newline, exit 2.
//!
//! `lattice put <store> <file>`: store a file; stdout "<object-id-hex>
//! <n_chunks> <n_new_chunks> <file_size>" newline, exit 0; unreadable input
//! prints stderr "error: cannot read input: <file-arg>" newline, exit 3.
//!
//! `lattice get <store> <object-id-hex> <out>`: materialize an object;
//! stdout "<object-id-hex> <size> OK" newline, exit 0; an unknown or
//! malformed id prints stderr "error: unknown object <id-arg>" newline,
//! exit 4.
//!
//! `lattice verify <store>`: full integrity scan; stdout four lines "packs
//! <n>", "chunks <n>", "objects <n>", "verify OK", exit 0; corruption
//! prints stderr "error: corrupt <what> at <location>" newline, exit 5.
//!
//! `lattice stats <store>`: stdout six lines "objects <n>", "chunks <n>",
//! "unique_bytes <n>", "logical_bytes <n>", "dedup_ratio <r>" (four
//! decimals), "pack_bytes <n>", exit 0.
//!
//! Any other invocation prints stderr "usage: lattice
//! <init|put|get|verify|stats> ..." newline, exit 2. Store-open failures
//! (missing or corrupt store files) print stderr "error: corrupt <what> at
//! <location>" (checksum) or "error: <message>" (other), exit 5.

use std::path::Path;
use std::process::ExitCode;

use lattice_store::Store;
use lattice_types::{LatticeError, ObjectId};

const USAGE: &str = "usage: lattice <init|put|get|verify|stats> ...";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = run(&args);
    ExitCode::from(code)
}

fn run(args: &[String]) -> u8 {
    match args.first().map(String::as_str) {
        Some("init") if args.len() == 2 => cmd_init(&args[1]),
        Some("put") if args.len() == 3 => cmd_put(&args[1], &args[2]),
        Some("get") if args.len() == 4 => cmd_get(&args[1], &args[2], &args[3]),
        Some("verify") if args.len() == 2 => cmd_verify(&args[1]),
        Some("stats") if args.len() == 2 => cmd_stats(&args[1]),
        _ => {
            eprintln!("{}", USAGE);
            2
        }
    }
}

fn store_error(err: &LatticeError) -> u8 {
    match err {
        LatticeError::ChecksumMismatch { what, location } => {
            eprintln!("error: corrupt {} at {}", what, location);
            5
        }
        other => {
            eprintln!("error: {}", other);
            5
        }
    }
}

fn cmd_init(dir: &str) -> u8 {
    match Store::init(Path::new(dir)) {
        Ok(_) => {
            println!("initialized lattice store");
            0
        }
        Err(LatticeError::Malformed(msg))
            if msg == "refusing to initialize non-empty directory" =>
        {
            eprintln!("error: refusing to initialize non-empty directory");
            2
        }
        Err(err) => store_error(&err),
    }
}

fn cmd_put(store_dir: &str, file: &str) -> u8 {
    let content = match std::fs::read(file) {
        Ok(c) => c,
        Err(_) => {
            eprintln!("error: cannot read input: {}", file);
            return 3;
        }
    };
    let (store, _) = match Store::open(Path::new(store_dir)) {
        Ok(s) => s,
        Err(err) => return store_error(&err),
    };
    match store.put_bytes(&content) {
        Ok(outcome) => {
            println!(
                "{} {} {} {}",
                outcome.object, outcome.n_chunks, outcome.n_new_chunks, outcome.size
            );
            0
        }
        Err(err) => store_error(&err),
    }
}

fn cmd_get(store_dir: &str, id_arg: &str, out: &str) -> u8 {
    let (store, _) = match Store::open(Path::new(store_dir)) {
        Ok(s) => s,
        Err(err) => return store_error(&err),
    };
    let object = match ObjectId::from_hex(id_arg) {
        Ok(o) => o,
        Err(_) => {
            eprintln!("error: unknown object {}", id_arg);
            return 4;
        }
    };
    match store.get(&object) {
        Ok(content) => {
            if std::fs::write(out, &content).is_err() {
                eprintln!("error: cannot write output: {}", out);
                return 5;
            }
            println!("{} {} OK", object, content.len());
            0
        }
        Err(LatticeError::UnknownObject(_)) => {
            eprintln!("error: unknown object {}", id_arg);
            4
        }
        Err(err) => store_error(&err),
    }
}

fn cmd_verify(store_dir: &str) -> u8 {
    let (store, _) = match Store::open(Path::new(store_dir)) {
        Ok(s) => s,
        Err(err) => return store_error(&err),
    };
    match store.verify() {
        Ok(report) => {
            println!("packs {}", report.packs);
            println!("chunks {}", report.chunks);
            println!("objects {}", report.objects);
            println!("verify OK");
            0
        }
        Err(err) => store_error(&err),
    }
}

fn cmd_stats(store_dir: &str) -> u8 {
    let (store, _) = match Store::open(Path::new(store_dir)) {
        Ok(s) => s,
        Err(err) => return store_error(&err),
    };
    match store.stats() {
        Ok(report) => {
            println!("objects {}", report.objects);
            println!("chunks {}", report.chunks);
            println!("unique_bytes {}", report.unique_bytes);
            println!("logical_bytes {}", report.logical_bytes);
            println!("dedup_ratio {}", report.dedup_ratio_string());
            println!("pack_bytes {}", report.pack_bytes);
            0
        }
        Err(err) => store_error(&err),
    }
}
