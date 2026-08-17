from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.evidence_federation import (
    EvidenceClass,
    EvidenceFederationError,
    EvidenceTrustVector,
    FederatedEvidenceCandidate,
    maximum_evidence_use,
)
from materials_data_analyzer.research_loop.research_episode import (
    ResearchEpisodeError,
    checkpoint_episode,
    create_research_episode,
    record_episode_iteration,
    resume_episode,
)


def _trust(**overrides: str) -> EvidenceTrustVector:
    values = {
        "source_authority": "authoritative",
        "representation": "raw",
        "sample_identity": "exact",
        "acquisition_identity": "exact",
        "calibration": "traceable",
        "independence": "independent",
        "comparability": "exact",
        "reuse": "allowed",
        "extraction": "native",
    }
    values.update(overrides)
    return EvidenceTrustVector(**values)


def test_federation_preserves_class_and_never_promotes_catalog_hit() -> None:
    candidate = FederatedEvidenceCandidate(
        provider="nist_pdr",
        source_id="mds2-demo",
        title="Raw measurement",
        evidence_class=EvidenceClass.E0_RAW_EXPERIMENTAL,
        trust=_trust(),
        source_locator="https://data.nist.gov/example",
        artifact_sha256="a" * 64,
    )
    record = candidate.record()
    assert record["evidence_class"] == "E0_raw_experimental"
    assert record["requires_scientific_intake"] is True
    assert record["scientific_status_changed"] is False
    assert record["search_or_catalog_hit_is_scientific_evidence"] is False
    use = maximum_evidence_use(candidate)
    assert use["external_validation_eligible_before_scientific_intake"] is False
    assert use["could_become_external_validation_eligible_after_intake"] is True


def test_figure_digitization_stays_diagnostic() -> None:
    candidate = FederatedEvidenceCandidate(
        provider="literature",
        source_id="doi:10.example/demo",
        title="Digitized figure",
        evidence_class=EvidenceClass.E4_FIGURE_DIGITIZED,
        trust=_trust(
            representation="digitized",
            sample_identity="partial",
            acquisition_identity="unknown",
            calibration="unknown",
            independence="unresolved",
            comparability="adjacent",
            extraction="digitized",
        ),
        source_locator="figure:5",
    )
    assert maximum_evidence_use(candidate)["maximum_use"] == "diagnostic_quantitative_only"


def test_unknown_reuse_blocks_stronger_use() -> None:
    candidate = FederatedEvidenceCandidate(
        provider="repository",
        source_id="dataset-x",
        title="Processed table",
        evidence_class=EvidenceClass.E1_PROCESSED_EXPERIMENTAL,
        trust=_trust(reuse="unknown"),
        source_locator="table.csv",
    )
    result = maximum_evidence_use(candidate)
    assert "reuse_not_explicitly_allowed" in result["blocker_codes"]
    assert result["could_become_external_validation_eligible_after_intake"] is False


def test_invalid_trust_vector_fails_closed() -> None:
    with pytest.raises(EvidenceFederationError):
        _trust(independence="probably_independent")


def test_episode_checkpoint_resume_and_iteration(tmp_path: Path) -> None:
    state = create_research_episode(
        episode_id="in625-evidence-federation",
        research_question="What IN625 evidence can resolve the current process-property gap?",
        mission_id="in625-autonomous-research",
        objectives=["find independent evidence", "preserve provenance"],
        max_iterations=5,
        cost_budget=10,
    )
    state = record_episode_iteration(
        state,
        planner_record={"selected_action": "external_evidence_search", "score": 1.0},
        artifact_refs=["discovery:sha256:" + "1" * 64],
        cost_units=1,
        evidence_refs=["federated-evidence:abc"],
        unresolved_gaps=["exact AMMT Stage 1 cells remain missing"],
        review_queue=["review:literature-table-1"],
        blockers=["external empirical dependency"],
        episode_status="blocked",
    )
    path = tmp_path / "episode.json"
    envelope = checkpoint_episode(path, state)
    resumed = resume_episode(path)
    assert resumed == state
    assert resumed["iteration"] == 1
    assert resumed["action_history"][0]["planner_record_sha256"]
    assert envelope["state_sha256"]


def test_episode_tamper_is_detected(tmp_path: Path) -> None:
    state = create_research_episode(
        episode_id="demo",
        research_question="question",
        mission_id="mission",
        objectives=["objective"],
        max_iterations=2,
        cost_budget=2,
    )
    path = tmp_path / "episode.json"
    checkpoint_episode(path, state)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state"]["research_question"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchEpisodeError, match="SHA-256 mismatch"):
        resume_episode(path)


def test_episode_budget_and_terminal_state_fail_closed() -> None:
    state = create_research_episode(
        episode_id="demo",
        research_question="question",
        mission_id="mission",
        objectives=["objective"],
        max_iterations=1,
        cost_budget=1,
    )
    with pytest.raises(ResearchEpisodeError, match="cost budget"):
        record_episode_iteration(state, planner_record={}, cost_units=2)
    terminal = record_episode_iteration(
        state,
        planner_record={"selected_action": "stop"},
        cost_units=0,
        episode_status="stopped",
    )
    with pytest.raises(ResearchEpisodeError, match="terminal episode"):
        record_episode_iteration(terminal, planner_record={})
