"""Compiled rubric tests. GENERATED SECTION. DO NOT HAND-EDIT.

Source: solution/grounding.yaml through solution/recompute.py.
"""

import json
import pathlib

import pytest

REPORT = pathlib.Path("/logs/verifier/report.json")


@pytest.fixture(scope='module')
def report():
    if not REPORT.exists():
        pytest.skip('verifier report absent')
    return json.loads(REPORT.read_text())


def _full(report, lane):
    maxima = report.get('lane_maxima', {})
    points = report.get('points', {})
    if lane not in maxima:
        return False
    return abs(points.get(lane, 0.0) - maxima[lane]) < 1e-6


def _gate(report, lane):
    entry = report.get('lanes', {}).get(lane)
    if not isinstance(entry, dict) or 'passed' not in entry:
        return False
    return bool(entry['passed'])


def test_r01(report):
    assert _full(report, 'L4_hidden_shifted')

def test_r02(report):
    assert _full(report, 'L3_hidden_typical')

def test_r03(report):
    assert _full(report, 'L2_corpus_reproduction')

def test_r04(report):
    assert _full(report, 'L5_boundary_seams')

def test_r05(report):
    assert _full(report, 'L6_block_choice')

def test_r06(report):
    assert _full(report, 'L7_size_fidelity')

def test_r07(report):
    assert _gate(report, 'L1_container_conformance')

def test_r08(report):
    assert _gate(report, 'L8_anti_fabrication')

def test_r09(report):
    assert _full(report, 'L9_calibration')

def test_r10(report):
    assert _full(report, 'B1_unseen_magnitude')

def test_r11(report):
    assert not report.get('red_line')
