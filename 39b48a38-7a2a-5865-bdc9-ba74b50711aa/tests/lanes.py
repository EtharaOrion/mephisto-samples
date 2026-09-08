"""The chronopack lane system. Never agent visible.

Ten lanes over a denominator of 120, so a hundred points is not the ceiling and the last ten
are a bonus a submission reaches only by generalising past everything it was shown.

The lane weights are not published in any agent-visible byte. An earlier version of this task
printed the whole table in `instruction.md`, which told a solver exactly where the points were
and let it allocate effort instead of solving. The calibration library's hardest instance
publishes nothing, and its scoring lives judge side.

Two lanes exist here that pure byte comparison cannot express.

`L8_anti_fabrication` asks whether the encoder is a function of its input at all. An encoder
that replays memorised bytes, or that ignores part of the column, produces the right answer
for the wrong reason, and every graded outcome it earns is an accident.

`L9_calibration` reads the probability the submission assigns to each encoding and scores it
by log loss against what the reference actually did. A submission that is certain and wrong
scores worse than one that admits it does not know, and a submission that hedges everything
uniformly scores nothing. Confidence has to be earned before it pays.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END
"""

from __future__ import annotations

import math

ENCODINGS = 6
UNIFORM_LOSS = math.log(ENCODINGS)
LOSS_CLIP = 8.0


def integrity_red_line(columns: list[dict], results: dict, reference) -> list[dict]:
    """RL1. Bytes the submission emitted that are not chronopack at all.

    A submission may fail to reproduce the reference encoder and still be an encoder. What it
    may not do is emit a blob that does not decode, under the published container rules, back
    to the exact column it was handed. That is not a wrong encoding, it is data loss wearing
    the shape of one, and a codec that silently destroys the column it was given has failed at
    something the format documents completely and grades nowhere else.

    The gate is deliberately generous: it uses the reference decoder, which follows only the
    published framing, so any legal chronopack blob passes whatever policy produced it.
    """
    by_id = {item["id"]: item for item in results.get("results", [])}
    violations = []
    for column in columns:
        blob = by_id.get(column["id"], {}).get("encoded_hex")
        if not blob:
            continue  # failing to encode is a lane loss, not a corruption
        try:
            # Recoverability, not digest validity. An earlier version of this gate called the
            # verifying decoder, so a submission that reproduced every frame byte for byte and
            # got only the undocumented trailer wrong scored zero on every lane instead of
            # losing the exactness lanes. Four of six solvers in the first Phase 3 probe were
            # zeroed that way, for a defect this red line was never meant to name.
            recovered = reference.decode(bytes.fromhex(blob), verify_digest=False)
        except Exception as exc:  # noqa: BLE001
            violations.append({"column": column["id"], "reason": f"emitted blob does not decode: {type(exc).__name__}"})
            continue
        if list(recovered) != list(column["values"]):
            violations.append({"column": column["id"], "reason": "emitted blob decodes to a different column"})
    return violations


def exactness(columns: list[dict], results: dict, reference) -> tuple[int, int, list[dict]]:
    """Columns whose bytes match the reference exactly."""
    by_id = {item["id"]: item for item in results.get("results", [])}
    exact = 0
    detail = []
    for column in columns:
        got = by_id.get(column["id"], {})
        want = reference.encode(column["values"]).hex()
        ok = got.get("encoded_hex") == want
        exact += ok
        if not ok and len(detail) < 8:
            detail.append({"column": column["id"], "reason": got.get("encode_error") or "bytes differ"})
    return exact, len(columns), detail


def block_choice(columns: list[dict], results: dict, reference, walk) -> tuple[int, int]:
    by_id = {item["id"]: item for item in results.get("results", [])}
    match = total = 0
    for column in columns:
        want = reference.block_choices(column["values"])
        total += len(want)
        blob = by_id.get(column["id"], {}).get("encoded_hex")
        if not blob:
            continue
        try:
            got = walk(bytes.fromhex(blob))
        except Exception:  # noqa: BLE001
            continue
        match += sum(1 for a, b in zip(want, got) if a == b)
    return match, total


def size_fidelity(columns: list[dict], results: dict, reference) -> tuple[float, list[dict]]:
    """How close the encoder's output size is to the reference's, column by column.

    A policy that is approximately right produces approximately the right size even where the
    bytes differ, so this lane pays for understanding that byte comparison throws away. It
    pays nothing for an encoder that simply picks the smallest encoding, because the reference
    does not, and it pays nothing for one that cannot encode at all.
    """
    by_id = {item["id"]: item for item in results.get("results", [])}
    scores = []
    worst = []
    for column in columns:
        want = len(reference.encode(column["values"]))
        blob = by_id.get(column["id"], {}).get("encoded_hex")
        if not blob:
            scores.append(0.0)
            continue
        got = len(bytes.fromhex(blob)) if blob else 0
        drift = abs(got - want) / max(1, want)
        # Full credit inside one percent, nothing beyond twenty five percent.
        value = 0.0 if drift >= 0.25 else (1.0 if drift <= 0.01 else 1.0 - (drift - 0.01) / 0.24)
        scores.append(value)
        if value < 1.0 and len(worst) < 6:
            worst.append({"column": column["id"], "size": got, "reference": want, "drift": round(drift, 4)})
    return (sum(scores) / len(scores) if scores else 0.0), worst


def anti_fabrication(probe_columns: list[dict], run, reference) -> tuple[float, list[str]]:
    """Is the encoder a function of the column it was handed?

    Three checks, each of which a memorising or partially blind encoder fails. Every one of
    them is satisfied trivially by an honest encoder, so the lane costs a real submission
    nothing and costs a fabricated one everything.
    """
    findings: list[str] = []
    passed = 0
    total = 0

    # One: perturbing any single value must change the bytes. An encoder that ignores part of
    # its input, or replays a memorised blob, fails here.
    total += 1
    payload = []
    for index, column in enumerate(probe_columns[:12]):
        values = list(column["values"])
        if not values:
            continue
        mutated = list(values)
        mutated[len(mutated) // 2] = mutated[len(mutated) // 2] ^ 0x5A5A5A5A
        payload.append({"id": f"af_base_{index}", "values": values})
        payload.append({"id": f"af_mut_{index}", "values": mutated})
    response = run(payload)
    by_id = {item["id"]: item for item in response.get("results", [])}
    blind = [
        index
        for index in range(len(payload) // 2)
        if by_id.get(f"af_base_{index}", {}).get("encoded_hex")
        == by_id.get(f"af_mut_{index}", {}).get("encoded_hex")
    ]
    if blind:
        findings.append(f"encoder output did not change when a value changed on {len(blind)} column(s)")
    else:
        passed += 1

    # Two: the encoder must not be order blind. Reversing a column that is not a palindrome
    # must change the bytes, because the format stores values in order.
    total += 1
    payload = []
    kept = []
    for index, column in enumerate(probe_columns[:12]):
        values = list(column["values"])
        if len(values) < 3 or values == values[::-1]:
            continue
        kept.append(index)
        payload.append({"id": f"or_fwd_{index}", "values": values})
        payload.append({"id": f"or_rev_{index}", "values": values[::-1]})
    if payload:
        response = run(payload)
        by_id = {item["id"]: item for item in response.get("results", [])}
        same = [
            index
            for index in kept
            if by_id.get(f"or_fwd_{index}", {}).get("encoded_hex")
            == by_id.get(f"or_rev_{index}", {}).get("encoded_hex")
        ]
        if same:
            findings.append(f"encoder output was order blind on {len(same)} column(s)")
        else:
            passed += 1
    else:
        passed += 1

    # Three: the encoder must round-trip through its own decoder. An encoder that emits bytes
    # it cannot itself read is emitting something other than an encoding of the column.
    total += 1
    payload = [{"id": f"sf_{i}", "values": list(c["values"])} for i, c in enumerate(probe_columns[:12])]
    response = run(payload, echo_self=True)
    by_id = {item["id"]: item for item in response.get("results", [])}
    broken = [
        item["id"]
        for item in payload
        if by_id.get(item["id"], {}).get("self_decoded") != item["values"]
    ]
    if broken:
        findings.append(f"encoder output did not survive the submission's own decoder on {len(broken)} column(s)")
    else:
        passed += 1

    return (passed / total if total else 0.0), findings


def calibration(columns: list[dict], results: dict, reference) -> tuple[float, dict]:
    """Log loss of the submission's own probabilities against what the reference chose.

    Scaled so that a uniform hedge scores zero and a perfect confident prediction scores one.
    A confident wrong prediction scores below zero and is clipped there, which is the point:
    a submission that does not know and says it does is worse than one that says it does not.
    """
    by_id = {item["id"]: item for item in results.get("results", [])}
    losses = []
    malformed = 0
    for column in columns:
        want = reference.block_choices(column["values"])
        prediction = by_id.get(column["id"], {}).get("prediction")
        if not isinstance(prediction, list) or len(prediction) != len(want):
            malformed += 1
            losses.extend([LOSS_CLIP] * len(want))
            continue
        for truth, row in zip(want, prediction):
            if not isinstance(row, list) or len(row) != ENCODINGS:
                losses.append(LOSS_CLIP)
                continue
            try:
                weights = [max(0.0, float(x)) for x in row]
            except Exception:  # noqa: BLE001
                losses.append(LOSS_CLIP)
                continue
            mass = sum(weights)
            if mass <= 0:
                losses.append(LOSS_CLIP)
                continue
            probability = weights[truth] / mass
            losses.append(min(LOSS_CLIP, -math.log(max(probability, 1e-12))))
    if not losses:
        return 0.0, {"mean_log_loss": None, "malformed_columns": malformed}
    mean = sum(losses) / len(losses)
    score = max(0.0, 1.0 - mean / UNIFORM_LOSS)
    return score, {
        "mean_log_loss": round(mean, 4),
        "uniform_log_loss": round(UNIFORM_LOSS, 4),
        "malformed_columns": malformed,
        "blocks_scored": len(losses),
    }
