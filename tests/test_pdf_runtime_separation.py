from __future__ import annotations

import pytest

from materials_data_analyzer import pdf_runtime
from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round9 as round9,
)
from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition as geometry,
)
from materials_data_analyzer.research_loop import (
    in625_published_model_comparator as comparator,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_candidate_acquisition as calibration,
)
from materials_data_analyzer.research_loop import (
    nist_mds2_2923_reference_chain_evidence as reference,
)


@pytest.mark.parametrize("module", [geometry, comparator, calibration, reference])
@pytest.mark.parametrize("version", ["6.18.1", "6.18.0"])
def test_external_pdf_paths_reject_old_parser_before_reading(
    module, version: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_runtime.metadata, "version", lambda _name: version)

    def forbidden_reader(*args, **kwargs):
        pytest.fail("an unsupported parser must never receive external bytes")

    monkeypatch.setattr(pdf_runtime, "PdfReader", forbidden_reader)
    with pytest.raises(ValueError, match="external PDF processing requires pypdf==6.21.4"):
        if module is geometry:
            module._pdf_pages(b"%PDF-untrusted", source_id="test", content_type=None)
        elif module is calibration:
            module._pdf_pages(b"%PDF-untrusted", None)
        elif module is reference:
            module._pdf_views(b"%PDF-untrusted")
        else:
            module._normalized_pdf_pages(b"%PDF-untrusted")


def test_current_parser_environment_is_supported() -> None:
    pdf_runtime.require_current_pdf_parser()


def test_current_environment_cannot_claim_historical_replay() -> None:
    report = {"pdf_extractor": {"package": "pypdf", "version": "6.18.1", "strict": False}}
    with pytest.raises(round9.AutonomousProductionFreshReviewRound9Error,
                       match="PDF extractor environment drifted"):
        round9._validate_multisource_report_boundaries(report)


def test_current_environment_accepts_current_network_contract() -> None:
    report = {
        "pdf_extractor": {"package": "pypdf", "version": "6.21.4", "strict": False},
        "network_requests_performed": 8, "network_request_budget": 8,
        "source_bytes_persisted": True, "retained_source_bytes_count": 8,
        **{field: False for field in round9._NETWORK_FALSE_FIELDS},
    }
    round9._validate_multisource_report_boundaries(report)
