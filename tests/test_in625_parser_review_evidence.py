from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_multisource_reviewed_witness as verifier,
)

ROOT = Path(__file__).resolve().parents[1]


def _records():
    witness_bytes = (ROOT / verifier._WITNESS_PATH).read_bytes()
    assert hashlib.sha256(witness_bytes).hexdigest() == verifier._EXPECTED_WITNESS_SHA256
    fixture = json.loads((ROOT / "tests/fixtures/lane_uncertainty_parser_spans.v1.json").read_text())
    return json.loads(witness_bytes), fixture


def test_old_span_is_bound_to_the_original_witness_not_a_replaced_hash() -> None:
    witness, fixture = _records()
    assert fixture["source_pdf_sha256"] == witness["sources"][4]["source_sha256"]
    receipt = witness["sources"][4]["claims"][4]["matches"][1]
    old = fixture["parser_spans"]["6.18.1"]
    assert hashlib.sha256(old["text"].encode()).hexdigest() == receipt["matched_text_sha256"]
    assert len(old["text"].encode()) == receipt["matched_text_utf8_bytes"] == 576


def test_reviewed_span_change_is_exactly_two_spaces_not_a_general_normalizer() -> None:
    _, fixture = _records()
    old = fixture["parser_spans"]["6.18.1"]["text"]
    new_record = fixture["parser_spans"]["6.21.4"]
    assert old[47] == old[72] == " "
    # Remove only the two observed positions in this fixture, never arbitrary whitespace.
    assert old[:47] + old[48:72] + old[73:] == new_record["text"]
    assert hashlib.sha256(new_record["text"].encode()).hexdigest() == new_record["sha256"]
    assert len(new_record["text"].encode()) == new_record["utf8_bytes"] == 574
    assert re.findall(r"\d+", old) == re.findall(r"\d+", new_record["text"])


def test_v1_still_rejects_the_current_parser_span_despite_limited_source_review() -> None:
    witness, fixture = _records()
    report = copy.deepcopy(witness)
    report["pdf_extractor"]["version"] = "6.21.4"
    new = fixture["parser_spans"]["6.21.4"]
    report["sources"][4]["claims"][4]["matches"][1].update(
        matched_text_sha256=new["sha256"], matched_text_utf8_bytes=new["utf8_bytes"],
    )
    with pytest.raises(verifier.AutonomousProductionMultisourceReviewedWitnessError,
                       match="authority projection drifted"):
        verifier._verify_historical_projection(report, witness)
