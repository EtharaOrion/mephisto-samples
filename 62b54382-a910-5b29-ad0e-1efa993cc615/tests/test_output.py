# GENERATED SECTION. DO NOT HAND-EDIT.
# Generated artifact. Never hand-authored.
#
# Compiled from solution/rubrics.json. The rubric contract forbids criterion prose and
# reference text in this file, so it carries identifiers and relations only.
# Reached through tests/test.sh.

import relations

def test_R1_exact_bytecode():
    relations.assert_prog_tuple_sequence_equality()

def test_R2_error_text():
    relations.assert_error_string_equality()

def test_R3_structural_validity():
    relations.assert_structural_validator_clean()

def test_R4_record_integrity():
    relations.assert_index_set_and_order_equality()

def test_R5_no_upstream_copy():
    relations.assert_containment_below_threshold()

def test_R6_no_forbidden_link():
    relations.assert_import_set_within_allowed()

def test_R7_throughput_earned():
    relations.assert_throughput_zero_when_no_exact()


COMPILED_ITEM_IDS = [
    'R1_exact_bytecode',
    'R2_error_text',
    'R3_structural_validity',
    'R4_record_integrity',
    'R5_no_upstream_copy',
    'R6_no_forbidden_link',
    'R7_throughput_earned',
]

COMPILED_WEIGHT = 1.0
COMPILATION_FLOOR = 0.8


def test_compilation_floor_holds():
    assert COMPILED_WEIGHT >= COMPILATION_FLOOR
