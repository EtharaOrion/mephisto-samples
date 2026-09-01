#!/usr/bin/env python3
# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
"""Reference bundle scheduler.

Slack based list scheduling over the full hazard graph. Priority is the longest
remaining latency weighted path to a sink, so an operation on the critical chain
wins a scarce port over an operation whose delay is absorbed by its own slack.
Several priority variants are tried and the variant with the fewest simulated
cycles is emitted, which is deterministic because the variant set is fixed.
"""

from __future__ import annotations

import argparse
import json
import pathlib

OP_PORT = {
    "load": "mem",
    "store": "mem",
    "add": "alu",
    "sub": "alu",
    "xor": "alu",
    "shl": "alu",
    "mul": "mul",
    "mac": "mul",
}


def reg_reads(op: dict) -> tuple:
    opcode = op["op"]
    if opcode == "load":
        return ()
    if opcode == "store":
        return (op["ra"],)
    if opcode == "shl":
        return (op["ra"],)
    if opcode == "mac":
        return (op["rd"], op["ra"], op["rb"])
    return (op["ra"], op["rb"])


def reg_write(op: dict):
    return None if op["op"] == "store" else op["rd"]


def edges_of(kernel: dict) -> list:
    ops = kernel["ops"]
    last_reg_write: dict = {}
    open_reg_reads: dict = {}
    last_mem_write: dict = {}
    open_mem_reads: dict = {}
    edges = []
    for index, op in enumerate(ops):
        for register in reg_reads(op):
            if register in last_reg_write:
                edges.append(("raw", last_reg_write[register], index))
            open_reg_reads.setdefault(register, []).append(index)
        if op["op"] == "load":
            if op["addr"] in last_mem_write:
                edges.append(("raw", last_mem_write[op["addr"]], index))
            open_mem_reads.setdefault(op["addr"], []).append(index)
        written = reg_write(op)
        if written is not None:
            for reader in open_reg_reads.get(written, []):
                if reader != index:
                    edges.append(("war", reader, index))
            if written in last_reg_write:
                edges.append(("waw", last_reg_write[written], index))
            last_reg_write[written] = index
            open_reg_reads[written] = []
        if op["op"] == "store":
            for reader in open_mem_reads.get(op["addr"], []):
                edges.append(("war", reader, index))
            if op["addr"] in last_mem_write:
                edges.append(("waw", last_mem_write[op["addr"]], index))
            last_mem_write[op["addr"]] = index
            open_mem_reads[op["addr"]] = []
    return edges


def required_cycle(kind: str, producer_cycle: int, producer_latency: int, consumer_latency: int) -> int:
    if kind == "raw":
        return producer_cycle + producer_latency
    if kind == "war":
        return producer_cycle - consumer_latency + 1
    return producer_cycle + producer_latency - consumer_latency + 1


def heights(kernel: dict, latencies: dict, edges: list) -> list:
    ops = kernel["ops"]
    successors = [[] for _ in ops]
    for kind, producer, consumer in edges:
        if kind == "raw":
            successors[producer].append(consumer)
    height = [0] * len(ops)
    for index in range(len(ops) - 1, -1, -1):
        best = 0
        for successor in successors[index]:
            if height[successor] > best:
                best = height[successor]
        height[index] = best + int(latencies[ops[index]["op"]])
    return height


def schedule_with(kernel: dict, model: dict, priority: list) -> list:
    ops = kernel["ops"]
    latencies = model["latencies"]
    width = int(model["issue_width"])
    capacity = model["port_capacity"]
    occupancy = model.get("unit_occupancy", {})
    strict_war = model.get("war_rule") == "issue_ordered_strict"

    predecessors = [[] for _ in ops]
    remaining = [0] * len(ops)
    for kind, producer, consumer in edges_of(kernel):
        predecessors[consumer].append((kind, producer))
        remaining[consumer] += 1

    successors_of = [[] for _ in ops]
    for consumer, entries in enumerate(predecessors):
        for kind, producer in entries:
            successors_of[producer].append((kind, consumer))

    issue: dict = {}
    earliest = [0] * len(ops)
    ready = sorted((index for index in range(len(ops)) if remaining[index] == 0))
    pending = set(ready)
    last_unit_cycle: dict = {}
    bundles: list = []
    cycle = 0
    placed = 0

    while placed < len(ops):
        available = sorted(
            (index for index in pending if earliest[index] <= cycle),
            key=lambda index: (-priority[index], index),
        )
        bundle: list = []
        used: dict = {}
        for index in available:
            if len(bundle) >= width:
                break
            op = ops[index]
            port = OP_PORT[op["op"]]
            if used.get(port, 0) >= int(capacity.get(port, 0)):
                continue
            gap = occupancy.get(op["op"])
            if gap is not None and cycle - last_unit_cycle.get(op["op"], -(10 ** 9)) < int(gap):
                continue
            bundle.append(index)
            used[port] = used.get(port, 0) + 1
            if gap is not None:
                last_unit_cycle[op["op"]] = cycle

        for index in bundle:
            issue[index] = cycle
            pending.discard(index)
            placed += 1
        for index in bundle:
            consumer_latency_source = int(latencies[ops[index]["op"]])
            for kind, consumer in successors_of[index]:
                bound = required_cycle(kind, cycle, consumer_latency_source, int(latencies[ops[consumer]["op"]]))
                if kind == "war" and strict_war:
                    bound = cycle + 1
                if bound > earliest[consumer]:
                    earliest[consumer] = bound
                remaining[consumer] -= 1
                if remaining[consumer] == 0:
                    pending.add(consumer)
        bundles.append(bundle)
        cycle += 1

    while bundles and not bundles[-1]:
        bundles.pop()
    return bundles


def cycles_of(kernel: dict, model: dict, bundles: list) -> int:
    issue = {entry: cycle for cycle, bundle in enumerate(bundles) for entry in bundle}
    retire = max(issue[op["id"]] + int(model["latencies"][op["op"]]) for op in kernel["ops"])
    return max(len(bundles), retire)


def best_schedule(kernel: dict, model: dict) -> list:
    latencies = model["latencies"]
    edges = edges_of(kernel)
    height = heights(kernel, latencies, edges)
    variants = [
        height,
        [value * 4 + (4 if OP_PORT[op["op"]] == "mem" else 0) for value, op in zip(height, kernel["ops"])],
        [value * 4 + (4 if op["op"] == "mac" else 0) for value, op in zip(height, kernel["ops"])],
        [value * 4 - op["id"] % 3 for value, op in zip(height, kernel["ops"])],
    ]
    best = None
    best_cycles = None
    for priority in variants:
        bundles = schedule_with(kernel, model, priority)
        total = cycles_of(kernel, model, bundles)
        if best_cycles is None or total < best_cycles:
            best_cycles = total
            best = bundles
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--machine-model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args()

    kernel = json.loads(pathlib.Path(args.kernel).read_text())
    model = json.loads(pathlib.Path(args.machine_model).read_text())
    bundles = best_schedule(kernel, model)
    pathlib.Path(args.out).write_text(
        json.dumps(
            {
                "kernel_id": kernel["kernel_id"],
                "bundle_count": len(bundles),
                "bundles": bundles,
                "claimed_cycles": cycles_of(kernel, model, bundles),
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
