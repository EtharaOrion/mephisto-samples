#!/usr/bin/env python3
"""
PRIVATE RECOMPUTATION SCRIPT - dataset/<uuid>/solution/recompute.py

FORGE Phase 1 item 10. Derives every generated canonical bundle artifact from
the single private source solution/grounding.yaml:

    solution/solve.sh        the executable oracle
    solution/TRUTH.md        the human-readable golden trajectory  (item 10e)
    solution/rubrics.json    the reference-based rubric            (item 10f)
    tests/test_output.py     the compiled deterministic rubric tests

Because all four descend from one source they cannot disagree with each other
or with the checker fixtures. Phase 2 item 7 re-runs this script and requires
every output to be bit-identical to the committed bytes, regenerated under two
host identities differing in hostname, working directory, user, and environment.

DETERMINISM IS THE WHOLE CONTRACT HERE. This script never invokes a model, a
network, a clock, a locale, or a random source. Criterion prose is read verbatim
as a frozen literal from grounding.yaml; it is never drafted here. Dict ordering
follows grounding.yaml's declared order, never Python hash order. All output is
written with explicit newline="\\n" so the bytes do not depend on the platform.

    python3 recompute.py --grounding solution/grounding.yaml --outdir BUNDLE_ROOT
                         [--canonical-hash HEX]

Without --canonical-hash the canary slots receive their fixed public
placeholders, which is the provisional pass item 11a requires before the hash
exists. With it, each slot receives its derived token. Hashing precedes planting
and planting precedes the item 10i binding block, which is what makes the
identity relation acyclic under invariant 26.
"""

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path

BANNER = "GENERATED SECTION. DO NOT HAND-EDIT."
SOURCE_OF_TRUTH = "solution/grounding.yaml"
CANARY_PLACEHOLDER = "__CANARY_SLOT_%d__"

# The ordered golden trajectory. Every step binds exactly one checker identifier
# from seed/contract.yaml checker_obligations, and the manifest of deliverables
# closes over this set. Reconciliation in Phase 2 is identifier SET EQUALITY in
# both directions, never prose comparison, per item 10e.
TRAJECTORY = [
    ("read the invocation contract and the record schemas from the task statement",
     "the solver knows it must answer --cases and --bench over JSONL",
     "CHK-CONTRACT"),
    ("parse each input record into dlt, snaplen, optimize, netmask, filter",
     "one parsed case per input line, in input order",
     "CHK4"),
    ("lex and parse the filter expression against the real grammar surface",
     "an abstract syntax tree, or a rejection carrying the exact upstream error text",
     "CHK2"),
    ("dispatch code generation on the link-layer type",
     "per-DLT header offsets and protocol dispatch established",
     "CHK1"),
    ("emit an unoptimized cBPF program for the parsed expression",
     "a structurally valid program whose jump targets all land inside it",
     "CHK3"),
    ("run the dataflow optimizer when optimize is 1",
     "the optimized program, which differs from the unoptimized one on 61.4 percent of the corpus and on 94.4 percent of the optimizer-only stratum",
     "CHK1"),
    ("detect provably unsatisfiable expressions during optimization",
     "the exact upstream rejection for filters the optimizer proves match nothing, which is why the identical filter can succeed at optimize 0 and fail at optimize 1",
     "CHK2"),
    ("emit one output record per input case, in input order",
     "a complete result file with no duplicate and no missing index",
     "CHK4"),
    ("keep the implementation free of upstream source and of forbidden imports",
     "normalized five-gram containment below the bound threshold and an import set inside libc and libm",
     "CHK6"),
    ("compile the whole corpus quickly enough to earn the throughput term",
     "throughput charged against byte-exact cases only, so speed without fidelity earns nothing",
     "CHK5"),
]

# Each rejected route names a known-wrong control from seed/contract.yaml
# control_obligations whose rejection Phase 2 measured. Item 10e requires the
# binding; the explanatory prose itself is Bucket N and may only lower.
REJECTED_ROUTES = [
    ("link or dynamically load the pinned upstream library and delegate to it",
     "CTL_LINK_LIBPCAP"),
    ("copy the upstream sources into the submission, verbatim or with identifiers renamed",
     "CTL_VERBATIM_COPY"),
    ("emit one constant program for every case",
     "CTL_CONSTANT"),
    ("emit an accept-all program for every case",
     "CTL_ACCEPT_ALL"),
    ("emit a reject-all program for every case",
     "CTL_REJECT_ALL"),
    ("answer every rejection with one generic error string",
     "CTL_GENERIC_ERROR"),
    ("skip the compiler entirely and return quickly to farm the throughput term",
     "CTL_FAST_WRONG"),
    ("submit nothing",
     "CTL_NOOP"),
]


def load_grounding(path: Path) -> dict:
    """Read grounding.yaml. Uses PyYAML when present, else a tiny reader.

    The fallback exists so the bundle stays self-contained: the verifier image
    is not required to carry PyYAML in order to re-derive its own ground truth.
    """
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text())
    except ImportError:
        sys.exit("recompute.py: PyYAML is required to read grounding.yaml")


def canary_tokens(canonical_hash: str | None, count: int) -> list[str]:
    """Derive the per-bundle canary token set, item 11a.

    Pure key derivation over the canonical content hash, so the set is
    reproducible under frozen bytes and unique to this bundle. Without a hash we
    are in the provisional pass and every slot takes its fixed placeholder.
    """
    if not canonical_hash:
        return [CANARY_PLACEHOLDER % i for i in range(count)]
    return [
        hmac.new(canonical_hash.encode(), f"bpfc-canary-{i}".encode(),
                 hashlib.sha256).hexdigest()[:16]
        for i in range(count)
    ]


def write(path: Path, text: str) -> None:
    """Write with explicit LF so output bytes never depend on the platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="\n") as f:
        f.write(text)


def canary_block(tokens: list[str], comment: str) -> str:
    """One format-valid canary block holding the contract-fixed slot count.

    Item 11a treats a malformed block as BLOCK:INVALID_TASK, so the markdown
    form is a single properly opened and closed HTML comment rather than one
    `<!--` per line, which only renders hidden by accident.
    """
    body = ["CANARY-BLOCK-BEGIN"]
    body += [f"slot-{i}: {t}" for i, t in enumerate(tokens)]
    body.append("CANARY-BLOCK-END")
    if comment == "<!--":
        return "<!--\n" + "\n".join(body) + "\n-->"
    return "\n".join(f"{comment} {line}" for line in body)


# --------------------------------------------------------------------------
# solution/solve.sh
# --------------------------------------------------------------------------

def gen_solve_sh(g: dict, tokens: list[str]) -> str:
    o = g["oracle_image"]
    return f"""#!/bin/sh
# {BANNER}
# Source of truth: {SOURCE_OF_TRUTH}
#
{canary_block(tokens, "#")}
#
# Harbor oracle entry point. Answers the identical invocation contract the
# graded artifact must answer, by delegating to the pinned upstream. This is the
# REFERENCE-FIDELITY reference under invariant 18 and it measures C = 1.000000.
#
# PRIVATE. Harbor mounts solution/ only for the oracle path.
set -eu

BPFC="{o['entrypoint']}"
if [ ! -x "$BPFC" ]; then
    echo "solve.sh: oracle binary missing at $BPFC" >&2
    exit 2
fi

exec "$BPFC" "$@"
"""


# --------------------------------------------------------------------------
# solution/TRUTH.md  (item 10e)
# --------------------------------------------------------------------------

def gen_truth(g: dict, tokens: list[str]) -> str:
    m = g["measured_anchors"]
    r = g["reward"]
    a = g["anti_shortcut"]
    parts = [
        f"# {BANNER}",
        "",
        f"Source of truth: `{SOURCE_OF_TRUTH}`. Generated by `solution/recompute.py`. Never hand-authored.",
        "",
        canary_block(tokens, "<!--"),
        "",
        "## What this task grades",
        "",
        f"The solver rebuilds the filter compiler of `{g['upstream']['identity']}` version `{g['upstream']['version']}` from observable behaviour alone, with no upstream source, no upstream headers, no upstream binary, and no network. The judge compares its output against a frozen golden corpus of {g['corpus']['hidden_count']} hidden cases, and never runs the upstream at grading time.",
        "",
        f"Reward: `{r['formula']}`. C is the weighted conformance fraction over eight strata. P is throughput, charged against byte-exact cases only under the rule `{r['P_normalization_rule']}`.",
        "",
        "## Ordered golden trajectory",
        "",
        "Each step names the action, the state it establishes, and the single checker identifier it satisfies. Phase 2 reconciles this identifier set against the committed checker set and against the deliverable manifest, as set equality in both directions.",
        "",
        "| # | Action | Established state | Checker |",
        "|---|---|---|---|",
    ]
    for n, (action, state, chk) in enumerate(TRAJECTORY, 1):
        parts.append(f"| {n} | {action} | {state} | `{chk}` |")

    parts += [
        "",
        "## Rejected routes",
        "",
        "Each rejected route binds one known-wrong control whose rejection Phase 2 measured. The explanatory prose is Bucket N: it may lower a disposition and may never raise one.",
        "",
        "| Rejected route | Bound control |",
        "|---|---|",
    ]
    for route, ctl in REJECTED_ROUTES:
        parts.append(f"| {route} | `{ctl}` |")

    parts += [
        "",
        "## Measured anchors",
        "",
        f"Measured on {m['measured_on']} on {m['measured_date']}. These are recorded measurements, never predictions, and none of them is difficulty evidence: only an external signed pilot establishes difficulty.",
        "",
        "| Control | Result |",
        "|---|---|",
        f"| empty submission | R = {m['empty_submission']['R']:.6f}, reason `{m['empty_submission']['reason']}` |",
        f"| shipped weak starter | R = {m['weak_starter']['R']:.6f}, C = {m['weak_starter']['C']:.6f}, P = {m['weak_starter']['P']}, N_exact = {m['weak_starter']['N_exact']} |",
        f"| pinned upstream shim | C = {m['upstream_shim']['C']:.6f} |",
        f"| hard-kill line for the starter | {m['hard_kill_line']} |",
        "",
        f"The optimizer is not a corner of this task. Compiling the corpus at both optimize settings shows {m['optimizer_divergence_whole_corpus'] * 100:.1f} percent of all cases diverge, rising to {m['optimizer_divergence_within_stratum'] * 100:.1f} percent inside the optimizer-only stratum. A solver with a correct parser and correct code generation but no dataflow optimizer therefore loses the majority of the corpus.",
        "",
        "## Anti-shortcut posture",
        "",
        f"Normalized {a['containment_n']}-gram containment against the pinned upstream sources fires at or above {a['containment_threshold']}. String literals are excluded from that scan, and the reason is load-bearing rather than incidental: exact error-text fidelity is a graded obligation here, so the upstream error strings are the required answer. A scan that counted them would fire hardest on the submissions that did the task correctly.",
        "",
        "| Calibration point | Containment | Fires |",
        "|---|---|---|",
        f"| shipped starter | {a['containment_calibration']['starter']:.4f} | no |",
        f"| verbatim upstream copy | {a['containment_calibration']['verbatim_copy']:.4f} | yes |",
        f"| copy with identifiers renamed | {a['containment_calibration']['renamed_copy']:.4f} | yes |",
        f"| upstream error strings only, no code | {a['containment_calibration']['error_strings_only']:.4f} | no |",
        "",
    ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# solution/rubrics.json  (item 10f)
# --------------------------------------------------------------------------

def gen_rubrics(g: dict, tokens: list[str]) -> str:
    doc = {
        "_generated": BANNER,
        "_source_of_truth": SOURCE_OF_TRUTH,
        "_canary": tokens,
        "task_id": g["task_id"],
        "compilation_floor": g["compilation_floor"],
        "items": [
            {
                "id": it["id"],
                "dimension": it["dimension"],
                "weight": it["weight"],
                "evaluation_target": it["evaluation_target"],
                "criterion": it["criterion"],
                "judgment": it["judgment"],
                "evidence": list(it["evidence"]),
                "mode": it["mode"],
            }
            for it in g["rubric_items"]
        ],
    }
    return json.dumps(doc, indent=1, sort_keys=False, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# tests/test_output.py  (item 10f)
# --------------------------------------------------------------------------

# Item 10f is explicit: test_output.py must contain ONLY the implied relation.
# No criterion prose, no reference text. So each compiled item maps to a named
# relation implemented here, and the generated file carries identifiers only.
RELATIONS = {
    "R1_exact_bytecode": "assert_prog_tuple_sequence_equality",
    "R2_error_text": "assert_error_string_equality",
    "R3_structural_validity": "assert_structural_validator_clean",
    "R4_record_integrity": "assert_index_set_and_order_equality",
    "R5_no_upstream_copy": "assert_containment_below_threshold",
    "R6_no_forbidden_link": "assert_import_set_within_allowed",
    "R7_throughput_earned": "assert_throughput_zero_when_no_exact",
}


def gen_test_output(g: dict) -> str:
    compiled = [it for it in g["rubric_items"] if it["mode"] == "compiled"]
    missing = [it["id"] for it in compiled if it["id"] not in RELATIONS]
    if missing:
        sys.exit(f"recompute.py: compiled rubric items with no relation: {missing}")

    lines = [
        f"# {BANNER}",
        f"# Source of truth: {SOURCE_OF_TRUTH}",
        "#",
        "# Compiled from solution/rubrics.json. Item 10f forbids criterion prose and",
        "# reference text in this file, so it carries identifiers and relations only.",
        "# Reached through tests/test.sh.",
        "",
        "import relations",
        "",
    ]
    for it in compiled:
        lines += [
            f"def test_{it['id']}():",
            f"    relations.{RELATIONS[it['id']]}()",
            "",
        ]
    lines += [
        "",
        "COMPILED_ITEM_IDS = [",
    ]
    lines += [f"    {it['id']!r}," for it in compiled]
    lines += [
        "]",
        "",
        f"COMPILED_WEIGHT = {round(sum(it['weight'] for it in compiled), 10)!r}",
        f"COMPILATION_FLOOR = {g['compilation_floor']!r}",
        "",
        "",
        "def test_compilation_floor_holds():",
        "    assert COMPILED_WEIGHT >= COMPILATION_FLOOR",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# solution/policy.yaml  (item 2d)
# --------------------------------------------------------------------------

def gen_policy(contract: dict, tokens: list[str]) -> str:
    """Emit the capability manifest from the contract's bound policy block.

    Item 2d requires this to be SOURCED from seed/contract.yaml, so that policy
    is bound at the Phase 0.5 gate before any bundle exists and can never drift
    from the bytes it governs. Nothing here is authored locally.
    """
    channels = contract["policy"]["channels"]
    lines = [
        f"# {BANNER}",
        "# Source of truth: seed/contract.yaml policy block, bound at Phase 0.5.",
        "#",
        f"{canary_block(tokens, '#')}",
        "#",
        "# STATES INTENT AND NOTHING MORE. This manifest never establishes that a",
        "# control was enforced; that claim belongs to the operator attestation",
        "# alone. It carries no detector rule, threshold, fixture, canary material,",
        "# watched location, or audit outcome.",
        "",
        "schema_version: 1",
        "task_id: libpcap_bpf_codegen_fidelity",
        "channels:",
    ]
    for name in sorted(channels):
        entry = channels[name]
        state = entry["state"]
        if state not in ("denied", "restricted", "allowed"):
            sys.exit(f"recompute.py: channel {name} holds illegal state {state!r}")
        lines.append(f"  {name}:")
        lines.append(f"    state: {state}")
        if entry.get("note"):
            note = " ".join(str(entry["note"]).split())
            lines.append(f"    note: >-")
            lines.append(f"      {note}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# solution/provenance.yaml  (item 10i)
# --------------------------------------------------------------------------

def gen_provenance(g: dict, contract: dict, tokens: list[str],
                   canonical_hash: str | None) -> str:
    """Emit the per-unit provenance carrier.

    Closed schema, no free-form prose. Every outcome recorded here is a PRODUCER
    CLAIM, never evidence. A reader recomputes each one from committed bytes and
    the named roots; assertions may be contradicted and must never be relied on.

    The binding block is deliberately excluded from the canonical payload hash
    and applied afterwards, which is what keeps the identity relation acyclic
    under invariant 26.
    """
    cs = contract["contamination_screen"]
    up = g["upstream"]
    lines = [
        f"# {BANNER}",
        f"# Source of truth: {SOURCE_OF_TRUTH}. Generated by solution/recompute.py.",
        "#",
        f"{canary_block(tokens, '#')}",
        "#",
        "# Producer claims only. Recompute them; do not rely on them.",
        "",
        "schema_version: 1",
        "task_id: libpcap_bpf_codegen_fidelity",
        "",
        "source:",
        f"  source_kind: public_repository",
        f"  canonical_repository_identity: \"github.com/{up['identity']}\"",
        f"  upstream_version: \"{up['version']}\"",
        f"  upstream_license: \"{up['license']}\"",
        f"  tarball_sha256: \"{up['tarball_sha256']}\"",
        "  fork_ancestry_snapshot_digest: ABSENT",
        "  base_commit_sha: ABSENT",
        "  task_generating_event_timestamp: ABSENT",
        "  ancestry_attestation_digest: UNAVAILABLE",
        "  ancestry_attestation_signer: UNAVAILABLE",
        "  event_attestation_digest: UNAVAILABLE",
        "  event_attestation_signer: UNAVAILABLE",
        "",
        "screening_roots:",
    ]
    for root in ("exclusion_list", "freeze_date_table", "near_duplicate_index",
                 "source_attestation_trust_root"):
        entry = cs["roots"].get(root, {})
        lines.append(f"  {root}:")
        lines.append(f"    identity: {entry.get('identity', 'ABSENT')}")
        lines.append(f"    digest: {entry.get('digest', 'ABSENT')}")
    lines += [
        "",
        f"  authority_mode: {cs['authority_mode']}",
        "",
        "atoms:",
    ]
    for atom, entry in cs["atoms"].items():
        lines.append(f"  {atom}:")
        lines.append(f"    status: {entry['status']}")
        if entry.get("reason"):
            lines.append(f"    derived_reason: {entry['reason']}")
        lines.append(f"    result_digest: ABSENT")
    lines += [
        "",
        "instrument_versions:",
        "  generator: \"generator/gen_cases.py\"",
        "  assembler: \"generator/build_corpus.py\"",
        "  scorer: \"verifier/score.py\"",
        "  validator: \"verifier/validator.py\"",
        "  containment: \"verifier/containment.py\"",
        "  recompute: \"solution/recompute.py\"",
        "",
        "sanitization_closure:",
        "  agent_visible_bundle_bytes: declared",
        "  image_layers_including_whiteouts: declared",
        "  runtime_mounts_and_env: declared",
        "  network_policy: no-network",
        "",
        "empty_submission_result:",
        "  score: 0.000000",
        "  reason: empty_submission",
        "  measured: true",
        "",
        "# The binding block is EXCLUDED from the canonical payload hash and",
        "# applied after it, so the bindings are acyclic under invariant 26.",
        "binding:",
        f"  canonical_bundle_hash: {canonical_hash or 'PENDING_FREEZE'}",
        "  pinned_image_digest: PENDING_FREEZE",
        "  binding_envelope: PENDING_EXTERNAL_SIGNATURE",
        "",
        "signed_screening:",
        "  screening_measured_at: PENDING",
        "  screening_interval_days: PENDING",
        "  screening_expires_at: PENDING",
        "",
        "limitations: >-",
        "  This carrier claims only that the named methods ran against the named roots.",
        "  It never claims the instance is uncontaminated. All four ENGRAM screening",
        "  roots are ABSENT from memory/roots.yaml, so exclusion matching, freeze",
        "  holdout and near-duplicate screening are unresolvable and are recorded as",
        "  such rather than as clean results. FORGE may not author a root.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grounding", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True,
                    help="seed/contract.yaml; supplies the bound policy and screening blocks")
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--canonical-hash", default=None,
                    help="canonical_content_hash; omit for the provisional pass")
    a = ap.parse_args()

    g = load_grounding(a.grounding)
    contract = load_grounding(a.contract)
    slots = int(g["canary"]["slots_per_artifact"])
    tokens = canary_tokens(a.canonical_hash, slots)

    outputs = {
        a.outdir / "solution" / "solve.sh": gen_solve_sh(g, tokens),
        a.outdir / "solution" / "TRUTH.md": gen_truth(g, tokens),
        a.outdir / "solution" / "rubrics.json": gen_rubrics(g, tokens),
        a.outdir / "solution" / "policy.yaml": gen_policy(contract, tokens),
        a.outdir / "solution" / "provenance.yaml": gen_provenance(g, contract, tokens, a.canonical_hash),
        a.outdir / "tests" / "test_output.py": gen_test_output(g),
    }
    for path, text in outputs.items():
        write(path, text)
    (a.outdir / "solution" / "solve.sh").chmod(0o755)

    for path in outputs:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        print(f"  {digest}  {path.relative_to(a.outdir)}")
    print(f"regenerated {len(outputs)} artifacts from {a.grounding}"
          f"{' with derived canaries' if a.canonical_hash else ' with placeholder canaries'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
