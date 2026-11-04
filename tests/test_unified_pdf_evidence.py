"""Real safe-parser contract tests on explicitly synthetic research evidence."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from materials_data_analyzer import pdf_runtime
from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition as acquisition,
)
from materials_data_analyzer.research_loop import pdf_evidence_reprocessing as evidence

ROOT = Path(__file__).resolve().parents[1]
TEXT = "Reviewed experiment: measured spot diameter 50 um on bare IN625; end observation."


def synthetic_pdf(text: str = TEXT) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=300)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })}),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 8 Tf 20 200 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


def fixture_contract(raw: bytes) -> tuple[dict, dict, dict]:
    claim = {"claim_id": "fixture-spot", "anchor_regex": "spot diameter.*IN625",
             "scope": "synthetic source-review test, not an experimental finding"}
    receipt = acquisition._claim_receipt(claim, [TEXT], is_pdf=True)
    source = {"source_id": "synthetic", "requested_url": "https://example.org/fixture.pdf",
              "media_type": "pdf", "source_size_bytes": len(raw),
              "source_sha256": hashlib.sha256(raw).hexdigest(), "claims": [receipt]}
    review = {"review_status": "reviewed", "review_reference": "synthetic-test-only",
              "claims": [{"claim_id": "fixture-spot", "scope": claim["scope"],
                          "page_index_zero_based": 0,
                          "context_regex": "Reviewed experiment: measured spot diameter.{0,80}?end observation",
                          "quantities": [{"name": "diameter", "pattern": r"diameter (?P<value>[+-]?[0-9.]+) (?P<unit>\w+)",
                                          "value": "50", "unit": "um"}]}]}
    contract = {"contract_id": "synthetic-test-only", "parser": {"package": "pypdf", "version": "6.21.4", "strict": False},
                "additional_sources": [], "source_reviews": {"synthetic": review}}
    return contract, {"sources": [source]}, {"sources": [{"source_id": "synthetic", "title": "Synthetic fixture, not research data", "claims_under_review": [claim]}]}


def install_fixture(monkeypatch: pytest.MonkeyPatch, raw: bytes):
    records = fixture_contract(raw)
    monkeypatch.setattr(evidence, "_load_contract", lambda: copy.deepcopy(records))
    return records


def test_reviewed_source_accepted_without_promoting_physical_validation(monkeypatch) -> None:
    raw = synthetic_pdf()
    records = install_fixture(monkeypatch, raw)
    before = copy.deepcopy(records)
    report = evidence.verify_reprocessed_sources({"synthetic": raw})
    assert report["sources"][0]["source_metadata"]["title"] == "Synthetic fixture, not research data"
    assert report["complete_source_review"] is True
    assert report["physical_or_model_validation_demonstrated"] is False
    assert report["network_requests_performed"] == 0
    assert report["sources"][0]["reviewed_claim_observations"][0]["quantities"] == [
        {"name": "diameter", "value": "50", "unit": "um"},
    ]
    assert report["sources"][0]["historical_comparison"] == [
        {"claim_id": "fixture-spot", "extraction_receipt_equal": True},
    ]
    assert records == before


def test_modified_source_rejected_before_parse(monkeypatch) -> None:
    raw = synthetic_pdf()
    install_fixture(monkeypatch, raw)
    monkeypatch.setattr(pdf_runtime, "PdfReader", lambda *_a, **_k: pytest.fail("changed source parsed"))
    with pytest.raises(evidence.EvidenceReprocessingError, match="source identity changed"):
        evidence.verify_reprocessed_sources({"synthetic": raw + b"changed"})


@pytest.mark.parametrize(("before", "after", "message"), [
    ("50 um", "51 um", "numeric value or unit changed"),
    ("50 um", "50 mm", "numeric value or unit changed"),
    ("Reviewed experiment", "Simulation output", "context is absent"),
    ("measured spot", "not measured spot", "context is absent"),
])
def test_rehashing_changed_source_does_not_bypass_quantity_unit_or_context(
    monkeypatch, before, after, message,
) -> None:
    raw = synthetic_pdf(TEXT.replace(before, after))
    # Even a reviewed byte-identity update alone cannot satisfy unchanged semantic rules.
    install_fixture(monkeypatch, raw)
    with pytest.raises(evidence.EvidenceReprocessingError, match=message):
        evidence.verify_reprocessed_sources({"synthetic": raw})


def test_missing_original_recorded_and_completion_rejected(monkeypatch) -> None:
    install_fixture(monkeypatch, synthetic_pdf())
    report = evidence.reprocess_retained_sources({})
    assert report["all_originals_present"] is False
    assert report["sources"][0]["status"] == "missing_original"
    with pytest.raises(evidence.EvidenceReprocessingError, match="source review incomplete"):
        evidence.verify_reprocessed_sources({})


@pytest.mark.parametrize("change", ["pending", "missing_reference", "missing_claim"])
def test_technical_success_does_not_complete_unreviewed_claims(monkeypatch, change) -> None:
    raw = synthetic_pdf()
    contract, _, _ = install_fixture(monkeypatch, raw)
    review = contract["source_reviews"]["synthetic"]
    if change == "pending":
        review["review_status"] = "pending_review"
    elif change == "missing_reference":
        review["review_reference"] = None
    else:
        review["claims"] = []
    report = evidence.reprocess_retained_sources({"synthetic": raw})
    assert report["sources"][0]["technical_checks_passed"] is True
    assert report["complete_source_review"] is False
    with pytest.raises(evidence.EvidenceReprocessingError, match="source review incomplete"):
        evidence.verify_reprocessed_sources({"synthetic": raw})


@pytest.mark.parametrize("version", ["6.18.1", "6.22.0"])
def test_parser_change_rejected_before_source_use(monkeypatch, version) -> None:
    monkeypatch.setattr(pdf_runtime.metadata, "version", lambda _name: version)
    monkeypatch.setattr(pdf_runtime, "PdfReader", lambda *_a, **_k: pytest.fail("unapproved parser used"))
    with pytest.raises(ValueError, match="requires pypdf==6.21.4"):
        evidence.reprocess_retained_sources({})


def test_checkout_contract_and_history_are_pinned_and_missing_is_not_success() -> None:
    contract, _, _ = evidence._load_contract()
    assert contract["additional_sources"][0]["doi"] == "10.1016/j.jmapro.2021.10.053"
    before = (ROOT / evidence.HISTORICAL_PATH).read_bytes()
    report = evidence.reprocess_retained_sources({})
    assert len(report["sources"]) == 9
    assert report["all_originals_present"] is False
    assert report["complete_source_review"] is False
    assert (ROOT / evidence.HISTORICAL_PATH).read_bytes() == before
    assert hashlib.sha256(before).hexdigest() == evidence.HISTORICAL_SHA256


def test_contract_hash_drift_rejected(monkeypatch) -> None:
    monkeypatch.setattr(evidence, "CONTRACT_SHA256", "0" * 64)
    with pytest.raises(evidence.EvidenceReprocessingError, match="identity drifted"):
        evidence.reprocess_retained_sources({})


def test_source_set_and_byte_budgets_are_closed(monkeypatch) -> None:
    raw = synthetic_pdf()
    install_fixture(monkeypatch, raw)
    with pytest.raises(evidence.EvidenceReprocessingError, match="unregistered"):
        evidence.reprocess_retained_sources({"unknown": raw})
    monkeypatch.setattr(evidence, "MAX_SOURCE_BYTES", len(raw) - 1)
    with pytest.raises(evidence.EvidenceReprocessingError, match="byte budget"):
        evidence.reprocess_retained_sources({"synthetic": raw})
    monkeypatch.setattr(evidence, "MAX_SOURCE_BYTES", len(raw))
    monkeypatch.setattr(evidence, "MAX_TOTAL_BYTES", len(raw) - 1)
    with pytest.raises(evidence.EvidenceReprocessingError, match="cumulative"):
        evidence.reprocess_retained_sources({"synthetic": raw})


def test_cli_writes_incomplete_report_without_overwriting_previous_result(tmp_path) -> None:
    target = tmp_path / "incomplete.json"
    command = [sys.executable, "-m", evidence.__name__, "--output", str(target)]
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    first = subprocess.run(command, check=False, cwd=ROOT, env=environment, capture_output=True, text=True)
    assert first.returncode == 2, first.stderr
    before = target.read_bytes()
    assert json.loads(before)["complete_source_review"] is False
    second = subprocess.run(command, check=False, cwd=ROOT, env=environment, capture_output=True, text=True)
    assert second.returncode == 2
    assert "output already exists" in second.stderr
    assert target.read_bytes() == before


def test_reconnaissance_also_rejects_old_runtime(monkeypatch) -> None:
    path = ROOT / "scripts/recon_in625_geometry_condition_sources.py"
    spec = importlib.util.spec_from_file_location("recon_unified_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(pdf_runtime.metadata, "version", lambda _name: "6.18.1")
    monkeypatch.setattr(pdf_runtime, "PdfReader", lambda *_a, **_k: pytest.fail("old parser called"))
    with pytest.raises(module.ReconError, match="requires pypdf==6.21.4"):
        module._pdf_pages(b"%PDF-untrusted", source_id="fixture", content_type=None)


def test_duplicate_evidence_keys_rejected() -> None:
    with pytest.raises(evidence.EvidenceReprocessingError, match="duplicate"):
        evidence._unique_object([("status", "pending"), ("status", "reviewed")])


@pytest.mark.parametrize("name", [
    "in625_geometry_condition_source_acquisition",
    "nist_ammt_calibration_candidate_acquisition",
    "nist_mds2_2923_reference_chain_evidence",
    "in625_published_model_comparator",
])
def test_all_existing_pdf_paths_process_real_safe_parser_fixture(name) -> None:
    import importlib

    module = importlib.import_module("materials_data_analyzer.research_loop." + name)
    raw = synthetic_pdf()
    if name == "in625_geometry_condition_source_acquisition":
        pages = module._pdf_pages(raw, source_id="synthetic", content_type="application/pdf")
    elif name == "nist_ammt_calibration_candidate_acquisition":
        pages = module._pdf_pages(raw, "application/pdf")
    elif name == "nist_mds2_2923_reference_chain_evidence":
        views = module._pdf_views(raw)
        assert views["plain"] == views["layout"]
        pages = views["plain"]
    else:
        pages = module._normalized_pdf_pages(raw)
    assert pages == [TEXT]


def test_no_production_pdf_import_bypasses_shared_runtime() -> None:
    permitted = ROOT / "src/materials_data_analyzer/pdf_runtime.py"
    for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]:
        if path == permitted:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(name.split(".")[0] in {"pypdf", "PyPDF2", "fitz", "pdfplumber", "pdfminer"}
                           for name in names), str(path)


@pytest.mark.parametrize(("name", "expected"), [
    ("historical_pdf_contract.json", "420735d5a70498c38acbff6fb721afba16db4a691148d9741d572fa3dc807649"),
    ("historical_pdf_replay.py.record", "6ae7c30ae98d5e8905afe326de66c65cbf1e781285f67b858aaf427878041aa0"),
    ("requirements-historical-replay.txt.record", "5e9173fbde81dede5c53087946dd59849b4d182dbaa11e71e9f9d662642b2b3f"),
])
def test_archived_runtime_records_remain_exact(name, expected) -> None:
    raw = (ROOT / "docs/history/pdf-replay" / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected


def test_ambiguous_quantity_is_rejected(monkeypatch) -> None:
    raw = synthetic_pdf(TEXT.replace("50 um", "50 um, diameter 50 um"))
    install_fixture(monkeypatch, raw)
    with pytest.raises(evidence.EvidenceReprocessingError, match="quantity is absent or ambiguous"):
        evidence.verify_reprocessed_sources({"synthetic": raw})


def test_historical_receipt_change_is_preserved_without_rewriting(monkeypatch) -> None:
    raw = synthetic_pdf()
    _, historical, _ = install_fixture(monkeypatch, raw)
    old_receipt = historical["sources"][0]["claims"][0]["matches"][0]
    old_receipt["matched_text_sha256"] = "0" * 64
    report = evidence.reprocess_retained_sources({"synthetic": raw})
    source = report["sources"][0]
    assert source["historical_comparison"][0]["extraction_receipt_equal"] is False
    assert source["historical_claim_receipts"][0]["matches"][0]["matched_text_sha256"] == "0" * 64
    assert source["reprocessed_claim_receipts"][0]["matches"][0]["matched_text_sha256"] != "0" * 64
    assert old_receipt["matched_text_sha256"] == "0" * 64
