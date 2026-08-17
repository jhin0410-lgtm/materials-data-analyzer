from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.experimental_lineage import (
    IndependenceLevel,
    ObservationLineage,
    classify_observation_independence,
    effective_independent_unit,
)
from materials_data_analyzer.research_loop.scientific_review_release import (
    ScientificReviewReleaseError,
    build_review_decision,
    build_review_request,
    verify_review_release,
)


def _lineage(
    *,
    source: str = "source-a",
    lab: str | None = "lab-a",
    lot: str | None = "lot-a",
    build: str | None = "build-a",
    specimen: str = "specimen-a",
    acquisition: str = "acq-a",
    measurement: str = "m-a",
) -> ObservationLineage:
    return ObservationLineage(
        source_id=source,
        lab_id=lab,
        material_lot_id=lot,
        build_or_synthesis_id=build,
        specimen_id=specimen,
        process_run_id="process-a",
        acquisition_id=acquisition,
        measurement_id=measurement,
    )


def test_review_release_is_exact_byte_and_use_bound() -> None:
    request = build_review_request(
        candidate_id="federated-evidence:abc",
        evidence_artifact_sha256="a" * 64,
        semantic_contract_sha256="b" * 64,
        lineage_sha256="c" * 64,
        intake_artifact_sha256="d" * 64,
        requested_uses=["scientific_intake", "descriptive_analysis"],
    )
    decision = build_review_decision(
        request,
        reviewer_id="reviewer-1",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=["descriptive_analysis"],
        review_notes="Exact bytes and declared lineage reviewed.",
    )
    verified = verify_review_release(
        request=request,
        decision=decision,
        candidate_id="federated-evidence:abc",
        evidence_artifact_sha256="a" * 64,
        semantic_contract_sha256="b" * 64,
        lineage_sha256="c" * 64,
        intake_artifact_sha256="d" * 64,
        downstream_use="scientific_intake",
    )
    assert verified["human_review_blocker_released"] is True
    assert verified["scientific_support_established"] is False
    assert verified["scientific_status_changed"] is False


def test_review_release_invalidates_on_lineage_change() -> None:
    request = build_review_request(
        candidate_id="federated-evidence:abc",
        evidence_artifact_sha256="a" * 64,
        semantic_contract_sha256="b" * 64,
        lineage_sha256="c" * 64,
        intake_artifact_sha256=None,
        requested_uses=["scientific_intake"],
    )
    decision = build_review_decision(
        request,
        reviewer_id="reviewer-1",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Reviewed.",
    )
    with pytest.raises(ScientificReviewReleaseError, match="differ from reviewed request"):
        verify_review_release(
            request=request,
            decision=decision,
            candidate_id="federated-evidence:abc",
            evidence_artifact_sha256="a" * 64,
            semantic_contract_sha256="b" * 64,
            lineage_sha256="e" * 64,
            intake_artifact_sha256=None,
            downstream_use="scientific_intake",
        )


def test_rejected_review_cannot_allow_use() -> None:
    request = build_review_request(
        candidate_id="federated-evidence:abc",
        evidence_artifact_sha256="a" * 64,
        semantic_contract_sha256="b" * 64,
        lineage_sha256="c" * 64,
        intake_artifact_sha256=None,
        requested_uses=["scientific_intake"],
    )
    with pytest.raises(ScientificReviewReleaseError, match="rejected review"):
        build_review_decision(
            request,
            reviewer_id="reviewer-1",
            decision="rejected",
            allowed_uses=["scientific_intake"],
            excluded_uses=[],
            review_notes="Rejected.",
        )


def test_same_acquisition_is_not_independent_replication() -> None:
    left = _lineage(measurement="m-1")
    right = _lineage(measurement="m-2")
    result = classify_observation_independence(left, right)
    assert result["independence_level"] == IndependenceLevel.SAME_ACQUISITION.value
    assert result["statistically_independent_for_naive_row_count"] is False


def test_different_specimens_same_build_are_not_naive_independent_units() -> None:
    left = _lineage(specimen="s-1", acquisition="a-1", measurement="m-1")
    right = _lineage(specimen="s-2", acquisition="a-2", measurement="m-2")
    result = classify_observation_independence(left, right)
    assert result["independence_level"] == (
        IndependenceLevel.INDEPENDENT_SPECIMEN_SAME_BUILD.value
    )
    assert result["statistically_independent_for_naive_row_count"] is False


def test_independent_sources_require_distinct_labs_lots_and_builds() -> None:
    left = _lineage(
        source="source-a",
        lab="lab-a",
        lot="lot-a",
        build="build-a",
        specimen="s-a",
        acquisition="a-a",
        measurement="m-a",
    )
    right = _lineage(
        source="source-b",
        lab="lab-b",
        lot="lot-b",
        build="build-b",
        specimen="s-b",
        acquisition="a-b",
        measurement="m-b",
    )
    result = classify_observation_independence(left, right)
    assert result["independence_level"] == IndependenceLevel.INDEPENDENT_SOURCE.value
    assert result["external_source_independence_established"] is True


def test_missing_lineage_does_not_infer_independence() -> None:
    left = _lineage(lab=None, lot=None, build=None, specimen="s-1")
    right = _lineage(
        source="source-b",
        lab=None,
        lot=None,
        build=None,
        specimen="s-2",
        acquisition="a-2",
        measurement="m-2",
    )
    result = classify_observation_independence(left, right)
    assert result["independence_level"] == IndependenceLevel.UNRESOLVED.value


def test_effective_independent_unit_exposes_pseudoreplication() -> None:
    rows = [
        _lineage(measurement="m-1"),
        _lineage(measurement="m-2"),
        _lineage(measurement="m-3"),
    ]
    result = effective_independent_unit(rows)
    assert result["row_count"] == 3
    assert result["unique_measurements"] == 3
    assert result["unique_acquisitions"] == 1
    assert result["unique_specimens"] == 1
    assert result["naive_row_count_is_independence_count"] is False
