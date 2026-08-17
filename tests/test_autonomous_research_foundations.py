from __future__ import annotations

import hashlib

import pytest

from materials_data_analyzer.research_loop.evidence_federation import (
    EvidenceClass,
    EvidenceTrustVector,
    FederatedEvidenceCandidate,
    maximum_evidence_use,
)
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


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def test_federated_literature_claim_cannot_become_raw_measurement() -> None:
    candidate = FederatedEvidenceCandidate(
        provider="crossref",
        source_id="10.1234/example",
        title="Reported observation",
        evidence_class=EvidenceClass.E5_LITERATURE_CLAIM,
        trust=EvidenceTrustVector(
            source_authority="peer_reviewed",
            representation="narrative",
            sample_identity="unknown",
            acquisition_identity="unknown",
            calibration="unknown",
            independence="unresolved",
            comparability="adjacent",
            reuse="allowed",
            extraction="narrative",
        ),
        source_locator="doi:10.1234/example",
    )
    record = candidate.record()
    upper = maximum_evidence_use(candidate)
    assert record["evidence_class"] == "E5_literature_claim"
    assert record["scientific_status_changed"] is False
    assert upper["maximum_use"] == "qualitative_claim_only"
    assert upper["external_validation_eligible_before_scientific_intake"] is False


def test_exact_review_release_only_releases_exact_bytes_and_use() -> None:
    request = build_review_request(
        candidate_id="candidate:1",
        evidence_artifact_sha256=_sha("evidence"),
        semantic_contract_sha256=_sha("semantics"),
        lineage_sha256=_sha("lineage"),
        intake_artifact_sha256=_sha("intake"),
        requested_uses=["scientific_intake", "descriptive_analysis"],
    )
    decision = build_review_decision(
        request,
        reviewer_id="reviewer:alice",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=["descriptive_analysis"],
        review_notes="Exact bytes and declared lineage reviewed.",
    )
    release = verify_review_release(
        request=request,
        decision=decision,
        candidate_id="candidate:1",
        evidence_artifact_sha256=_sha("evidence"),
        semantic_contract_sha256=_sha("semantics"),
        lineage_sha256=_sha("lineage"),
        intake_artifact_sha256=_sha("intake"),
        downstream_use="scientific_intake",
    )
    assert release["human_review_blocker_released"] is True
    assert release["scientific_support_established"] is False
    with pytest.raises(ScientificReviewReleaseError):
        verify_review_release(
            request=request,
            decision=decision,
            candidate_id="candidate:1",
            evidence_artifact_sha256=_sha("tampered"),
            semantic_contract_sha256=_sha("semantics"),
            lineage_sha256=_sha("lineage"),
            intake_artifact_sha256=_sha("intake"),
            downstream_use="scientific_intake",
        )


def _lineage(
    *,
    source: str = "source-a",
    lab: str | None = "lab-a",
    lot: str | None = "lot-a",
    build: str | None = "build-a",
    specimen: str = "specimen-a",
    acquisition: str = "acq-a",
    measurement: str = "measurement-a",
) -> ObservationLineage:
    return ObservationLineage(
        source_id=source,
        lab_id=lab,
        material_lot_id=lot,
        build_or_synthesis_id=build,
        specimen_id=specimen,
        process_run_id=None,
        acquisition_id=acquisition,
        measurement_id=measurement,
    )


def test_lineage_prevents_pseudoreplication_and_requires_physical_independence() -> None:
    left = _lineage()
    repeated = _lineage(measurement="measurement-b")
    result = classify_observation_independence(left, repeated)
    assert result["independence_level"] == IndependenceLevel.SAME_ACQUISITION.value
    assert result["statistically_independent_for_naive_row_count"] is False

    external = _lineage(
        source="source-b",
        lab="lab-b",
        lot="lot-b",
        build="build-b",
        specimen="specimen-b",
        acquisition="acq-b",
        measurement="measurement-b",
    )
    result = classify_observation_independence(left, external)
    assert result["independence_level"] == IndependenceLevel.INDEPENDENT_SOURCE.value
    assert result["external_source_independence_established"] is True

    counts = effective_independent_unit([left, repeated])
    assert counts["row_count"] == 2
    assert counts["unique_acquisitions"] == 1
    assert counts["naive_row_count_is_independence_count"] is False
