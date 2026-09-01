# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
"""Cycle accurate machine model for edgebench/vliw_kernel_optimization.

The simulator is the sole authority for what a schedule costs and for whether it
is legal. The bundle at index k issues at cycle k, every result lands at the
issue cycle plus the opcode latency, and no hardware interlock exists, so a
consumer packed one cycle before its producer retires reads a stale value rather
than stalling. Cycle counts are simulated, never timed, so the measurement is
exactly reproducible.
"""

from __future__ import annotations

MASK64 = (1 << 64) - 1

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

REGISTER_WAW_CLASS = "register_waw"


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


def mem_read(op: dict):
    return op["addr"] if op["op"] == "load" else None


def mem_write(op: dict):
    return op["addr"] if op["op"] == "store" else None


def latency_of(model: dict, op: dict) -> int:
    return int(model["latencies"][op["op"]])


def dependences(kernel: dict) -> dict:
    """Program order hazard pairs. Every edge runs from a lower identifier to a
    higher one, which is what lets a forward pass decide readiness."""
    ops = kernel["ops"]
    last_reg_write: dict = {}
    open_reg_reads: dict = {}
    last_mem_write: dict = {}
    open_mem_reads: dict = {}
    edges = {"raw": [], "war": [], "waw": [], "mem_raw": [], "mem_war": [], "mem_waw": []}

    for index, op in enumerate(ops):
        for register in reg_reads(op):
            if register in last_reg_write:
                edges["raw"].append((last_reg_write[register], index, register))
            open_reg_reads.setdefault(register, []).append(index)
        address = mem_read(op)
        if address is not None:
            if address in last_mem_write:
                edges["mem_raw"].append((last_mem_write[address], index, address))
            open_mem_reads.setdefault(address, []).append(index)

        written = reg_write(op)
        if written is not None:
            for reader in open_reg_reads.get(written, []):
                if reader != index:
                    edges["war"].append((reader, index, written))
            if written in last_reg_write:
                edges["waw"].append((last_reg_write[written], index, written))
            last_reg_write[written] = index
            open_reg_reads[written] = []
        stored = mem_write(op)
        if stored is not None:
            for reader in open_mem_reads.get(stored, []):
                edges["mem_war"].append((reader, index, stored))
            if stored in last_mem_write:
                edges["mem_waw"].append((last_mem_write[stored], index, stored))
            last_mem_write[stored] = index
            open_mem_reads[stored] = []
    return edges


def earliest_after(edge_class: str, producer_cycle: int, producer_latency: int, consumer_latency: int) -> int:
    """Minimum issue cycle for the later member of a hazard pair. RAW waits for the
    producer to retire, WAR only has to read before the later write lands, and WAW
    has to land strictly after the earlier write lands."""
    if edge_class in ("raw", "mem_raw"):
        return producer_cycle + producer_latency
    if edge_class in ("war", "mem_war"):
        return producer_cycle - consumer_latency + 1
    return producer_cycle + producer_latency - consumer_latency + 1


def predecessors(kernel: dict, model: dict) -> list:
    ops = kernel["ops"]
    table = [[] for _ in ops]
    for edge_class, pairs in dependences(kernel).items():
        for producer, consumer, resource in pairs:
            table[consumer].append((edge_class, producer, resource))
    return table


def _resource_violations(kernel: dict, model: dict, issue: dict) -> list:
    ops = kernel["ops"]
    violations = []
    for opcode, occupancy in sorted(model.get("unit_occupancy", {}).items()):
        cycles = sorted(issue[op["id"]] for op in ops if op["op"] == opcode and op["id"] in issue)
        for position in range(1, len(cycles)):
            if cycles[position] - cycles[position - 1] < int(occupancy):
                violations.append(
                    {
                        "violation_class": "unit_occupancy",
                        "reason": "unpipelined_unit_reissued_too_soon",
                        "opcode": opcode,
                        "earlier_cycle": cycles[position - 1],
                        "later_cycle": cycles[position],
                        "required_distance": int(occupancy),
                    }
                )
                break
    return violations


def replay(kernel: dict, model: dict, bundles) -> dict:
    """Recomputes issue cycles, hazard legality and the cycle count from the emitted
    bundles alone. Register write after write findings are reported separately from
    every other hazard class."""
    ops = kernel["ops"]
    op_by_id = {op["id"]: op for op in ops}
    outcome = {
        "structural_ok": False,
        "violations": [],
        "waw_violations": [],
        "cycles": None,
        "bundle_count": 0,
        "issue": {},
    }

    if not isinstance(bundles, list):
        outcome["violations"].append({"violation_class": "structure", "reason": "bundles_not_a_list"})
        return outcome

    outcome["bundle_count"] = len(bundles)
    issue: dict = {}
    for cycle, bundle in enumerate(bundles):
        if not isinstance(bundle, list):
            outcome["violations"].append(
                {"violation_class": "structure", "reason": "bundle_not_a_list", "cycle": cycle}
            )
            return outcome
        if len(bundle) > int(model["issue_width"]):
            outcome["violations"].append(
                {
                    "violation_class": "issue_width",
                    "reason": "issue_width_exceeded",
                    "cycle": cycle,
                    "packed": len(bundle),
                    "issue_width": int(model["issue_width"]),
                }
            )
            return outcome
        occupied: dict = {}
        for entry in bundle:
            if not isinstance(entry, int) or entry not in op_by_id:
                outcome["violations"].append(
                    {"violation_class": "structure", "reason": "unknown_operation_identifier", "cycle": cycle, "entry": entry}
                )
                return outcome
            if entry in issue:
                outcome["violations"].append(
                    {"violation_class": "structure", "reason": "operation_issued_twice", "operation": entry, "cycle": cycle}
                )
                return outcome
            issue[entry] = cycle
            port = OP_PORT[op_by_id[entry]["op"]]
            occupied[port] = occupied.get(port, 0) + 1
        for port, used in sorted(occupied.items()):
            capacity = int(model["port_capacity"].get(port, 0))
            if used > capacity:
                outcome["violations"].append(
                    {
                        "violation_class": "port",
                        "reason": "port_oversubscribed",
                        "cycle": cycle,
                        "port": port,
                        "used": used,
                        "capacity": capacity,
                    }
                )
                return outcome

    missing = sorted(op_by_id.keys() - issue.keys())
    if missing:
        outcome["violations"].append(
            {"violation_class": "structure", "reason": "operation_dropped_from_schedule", "operations": missing[:8]}
        )
        return outcome

    outcome["structural_ok"] = True
    outcome["issue"] = issue
    outcome["violations"].extend(_resource_violations(kernel, model, issue))

    for edge_class, pairs in sorted(dependences(kernel).items()):
        for producer, consumer, resource in pairs:
            producer_latency = latency_of(model, op_by_id[producer])
            consumer_latency = latency_of(model, op_by_id[consumer])
            required = earliest_after(edge_class, issue[producer], producer_latency, consumer_latency)
            if issue[consumer] < required:
                record = {
                    "violation_class": edge_class,
                    "reason": f"{edge_class}_hazard_violated",
                    "producer": producer,
                    "consumer": consumer,
                    "resource": resource,
                    "producer_cycle": issue[producer],
                    "consumer_cycle": issue[consumer],
                    "required_cycle": required,
                }
                if edge_class == "waw":
                    record["violation_class"] = REGISTER_WAW_CLASS
                    record["reason"] = "register_write_after_write_conflict"
                    outcome["waw_violations"].append(record)
                else:
                    outcome["violations"].append(record)

    retire = max((issue[op["id"]] + latency_of(model, op) for op in ops), default=0)
    outcome["cycles"] = max(len(bundles), retire)
    return outcome


def lower_bound(kernel: dict, model: dict) -> int:
    ops = kernel["ops"]
    op_by_id = {op["id"]: op for op in ops}
    edges = dependences(kernel)
    earliest = {op["id"]: 0 for op in ops}
    for edge_class in ("raw", "mem_raw"):
        for producer, consumer, _resource in edges[edge_class]:
            candidate = earliest[producer] + latency_of(model, op_by_id[producer])
            if candidate > earliest[consumer]:
                earliest[consumer] = candidate
    critical_path = max((earliest[op["id"]] + latency_of(model, op) for op in ops), default=1)

    bounds = [critical_path]
    width = int(model["issue_width"])
    bounds.append((len(ops) + width - 1) // width)
    port_counts: dict = {}
    for op in ops:
        port = OP_PORT[op["op"]]
        port_counts[port] = port_counts.get(port, 0) + 1
    for port, count in sorted(port_counts.items()):
        capacity = int(model["port_capacity"].get(port, 1)) or 1
        bounds.append((count + capacity - 1) // capacity)
    for opcode, occupancy in sorted(model.get("unit_occupancy", {}).items()):
        count = sum(1 for op in ops if op["op"] == opcode)
        if count:
            bounds.append((count - 1) * int(occupancy) + int(model["latencies"][opcode]))
    return max(1, max(bounds))


def execute_sequential(kernel: dict, memory: list) -> dict:
    registers = [0] * int(kernel["register_count"])
    words = list(memory)
    for op in kernel["ops"]:
        _apply(op, registers, words, registers, words)
    return {"registers": registers, "memory": words}


def _apply(op: dict, read_registers: list, read_memory: list, write_registers: list, write_memory: list):
    opcode = op["op"]
    if opcode == "load":
        write_registers[op["rd"]] = read_memory[op["addr"]]
        return None
    if opcode == "store":
        write_memory[op["addr"]] = read_registers[op["ra"]]
        return None
    if opcode == "add":
        value = (read_registers[op["ra"]] + read_registers[op["rb"]]) & MASK64
    elif opcode == "sub":
        value = (read_registers[op["ra"]] - read_registers[op["rb"]]) & MASK64
    elif opcode == "xor":
        value = read_registers[op["ra"]] ^ read_registers[op["rb"]]
    elif opcode == "shl":
        value = (read_registers[op["ra"]] << op["imm"]) & MASK64
    elif opcode == "mul":
        value = (read_registers[op["ra"]] * read_registers[op["rb"]]) & MASK64
    else:
        value = (read_registers[op["rd"]] + read_registers[op["ra"]] * read_registers[op["rb"]]) & MASK64
    write_registers[op["rd"]] = value
    return None


def execute_scheduled(kernel: dict, model: dict, bundles: list, memory: list, cycles: int) -> dict:
    op_by_id = {op["id"]: op for op in kernel["ops"]}
    registers = [0] * int(kernel["register_count"])
    words = list(memory)
    pending: dict = {}
    sequence = 0

    for cycle in range(cycles + 1):
        for _order, kind, target, value in sorted(pending.pop(cycle, [])):
            if kind == "r":
                registers[target] = value
            else:
                words[target] = value
        if cycle < len(bundles):
            for entry in bundles[cycle]:
                op = op_by_id[entry]
                landing = cycle + latency_of(model, op)
                staged_registers = list(registers)
                staged_memory = list(words)
                _apply(op, registers, words, staged_registers, staged_memory)
                sequence += 1
                if op["op"] == "store":
                    pending.setdefault(landing, []).append((sequence, "m", op["addr"], staged_memory[op["addr"]]))
                else:
                    pending.setdefault(landing, []).append((sequence, "r", op["rd"], staged_registers[op["rd"]]))
    for cycle in sorted(pending):
        for _order, kind, target, value in sorted(pending[cycle]):
            if kind == "r":
                registers[target] = value
            else:
                words[target] = value
    return {"registers": registers, "memory": words}
