"""Cross-language wire for packed/aligned raw_storage (MaD Sample shape).

Vectors use **raw** scaled integers (mN). C and Rust memory models match that
after the packed raw_storage fix. TypeScript (A2) stays physical; render.py
divides by scale when emitting TS literals so wire steps still agree.
"""

from __future__ import annotations

import os

import pytest
from _harness import (
    assert_language_coverage,
    assert_matches_goldens,
    pivot_by_label,
    run_all,
)

SCHEMA = os.path.join(os.path.dirname(__file__), "schemas", "raw_storage.yaml")
PREFIX = "RawDemo"

# Values are raw mN / µm (C/RS). force=12345 mN → physical 12.345 N for TS.
VECTORS = [
    ("sample_zero", "Sample", {"force": 0, "position": 0}),
    ("sample_mid", "Sample", {"force": 12345, "position": -50000}),
    ("sample_max", "Sample", {"force": 100000, "position": 200000}),
    ("sample_min", "Sample", {"force": -100000, "position": -200000}),
    ("aligned_zero", "AlignedRaw", {"force": 0}),
    ("aligned_mid", "AlignedRaw", {"force": 12345}),
    ("aligned_max", "AlignedRaw", {"force": 100000}),
]


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    work = str(tmp_path_factory.mktemp("raw_storage_conf"))
    return run_all(SCHEMA, PREFIX, VECTORS, work)


def test_at_least_two_languages_available(outputs):
    assert_language_coverage(outputs)


def test_no_roundtrip_mismatch(outputs):
    for lang, lines in outputs.items():
        bad = [ln for ln in lines if ln.endswith("ROUNDTRIP_MISMATCH")]
        assert not bad, f"{lang} round-trip failures: {bad}"


def test_every_vector_emitted(outputs):
    labels = {lbl for lbl, _s, _v in VECTORS}
    for lang, lines in outputs.items():
        got = {ln.split(" ", 1)[0] for ln in lines}
        assert got == labels, f"{lang} emitted {got ^ labels} unexpectedly"


def test_wire_is_byte_identical_across_languages(outputs):
    langs = sorted(outputs)
    mismatches = []
    for label, per_lang in sorted(pivot_by_label(outputs).items()):
        if len(set(per_lang.values())) != 1:
            mismatches.append(
                f"{label}: "
                + ", ".join(f"{lg}={per_lang[lg]}" for lg in langs if lg in per_lang)
            )
    assert not mismatches, "wire divergence:\n" + "\n".join(mismatches)


def test_wire_matches_goldens(outputs):
    assert_matches_goldens(outputs, "raw_storage")
