






























use std::path::Path;
use std::process::ExitCode;

use lattice_store::Store;
use lattice_types::{LatticeError, ObjectId};

const USAGE: &str = "usage: lattice <init|put|get|verify|stats> ...";

fn main() -> ExitCode {
    todo!()
}

fn run(args: &[String]) -> u8 {
    todo!()
}

fn store_error(err: &LatticeError) -> u8 {
    todo!()
}

fn cmd_init(dir: &str) -> u8 {
    todo!()
}

fn cmd_put(store_dir: &str, file: &str) -> u8 {
    todo!()
}

fn cmd_get(store_dir: &str, id_arg: &str, out: &str) -> u8 {
    todo!()
}

fn cmd_verify(store_dir: &str) -> u8 {
    todo!()
}

fn cmd_stats(store_dir: &str) -> u8 {
    todo!()
}
