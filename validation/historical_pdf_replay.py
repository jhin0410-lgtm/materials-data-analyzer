"""Run explicitly, offline, with the installed baseline wheel (not current src).

These synthetic contract checks are not a reproduction of a retained research run.
The unchanged baseline verifier must still authenticate any real retained run.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import resource
import socket
from io import BytesIO
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round9 as round9,
)

CONTRACT = json.loads(Path(__file__).with_name("historical_pdf_contract.json").read_text())


def _report() -> dict:
    return {
        "pdf_extractor": {"package": "pypdf", "version": "6.18.1", "strict": False},
        "network_requests_performed": 8,
        "network_request_budget": 8,
        "source_bytes_persisted": True,
        "retained_source_bytes_count": 8,
        **{field: False for field in round9._NETWORK_FALSE_FIELDS},
    }


def _synthetic_pdf() -> bytes:
    # A small deterministic, text-only fixture; no downloaded or instrument data.
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (Historical replay contract) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


def test_baseline_parser_and_implementation_identity() -> None:
    assert importlib.metadata.version("pypdf") == CONTRACT["pypdf_version"]
    assert round9._EXPECTED_PYPDF_VERSION == CONTRACT["pypdf_version"]
    for filename, expected in CONTRACT["module_sha256"].items():
        module = importlib.import_module("materials_data_analyzer.research_loop." + filename[:-3])
        path = Path(module.__file__).resolve()
        assert "site-packages" in path.parts, "historical verification must use the baseline wheel"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_offline_read_only_sandbox() -> None:
    for name, limit in (
        (resource.RLIMIT_AS, 1610612736),
        (resource.RLIMIT_CPU, 90),
        (resource.RLIMIT_NOFILE, 256),
    ):
        soft, hard = resource.getrlimit(name)
        assert 0 < soft <= limit and 0 < hard <= limit
    # No DNS or external service is used: a network namespace has no external route.
    with pytest.raises(OSError):
        socket.create_connection(("192.0.2.1", 443), timeout=0.1)
    with pytest.raises(OSError):
        descriptor = os.open(round9.__file__, os.O_WRONLY)
        os.close(descriptor)


def test_real_historical_environment_accepts_exact_contract() -> None:
    round9._validate_multisource_report_boundaries(_report())


@pytest.mark.parametrize("field", round9._NETWORK_FALSE_FIELDS)
def test_real_historical_environment_rejects_network_promotion(field: str) -> None:
    report = _report()
    report[field] = True
    with pytest.raises(round9.AutonomousProductionFreshReviewRound9Error,
                       match="widened network/scientific execution boundary"):
        round9._validate_multisource_report_boundaries(report)


def test_real_historical_environment_rejects_report_parser_drift() -> None:
    report = _report()
    report["pdf_extractor"]["version"] = "6.21.4"
    with pytest.raises(round9.AutonomousProductionFreshReviewRound9Error,
                       match="PDF extractor environment drifted"):
        round9._validate_multisource_report_boundaries(report)


@pytest.mark.parametrize("name", [
    "in625_geometry_condition_source_acquisition",
    "nist_ammt_calibration_candidate_acquisition",
    "nist_mds2_2923_reference_chain_evidence",
    "in625_published_model_comparator",
])
def test_baseline_pdf_processing_on_synthetic_bytes(name: str) -> None:
    module = importlib.import_module("materials_data_analyzer.research_loop." + name)
    raw = _synthetic_pdf()
    if name == "in625_geometry_condition_source_acquisition":
        pages = module._pdf_pages(raw, source_id="synthetic", content_type="application/pdf")
    elif name == "nist_ammt_calibration_candidate_acquisition":
        pages = module._pdf_pages(raw, "application/pdf")
    elif name == "nist_mds2_2923_reference_chain_evidence":
        pages = module._pdf_views(raw)["plain"]
    else:
        pages = module._normalized_pdf_pages(raw)
    assert pages == ["Historical replay contract"]
