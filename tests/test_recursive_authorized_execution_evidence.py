from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_controller as controller
import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence
from materials_data_analyzer.research_loop.recursive_authorized_execution_evidence import (
    RecursiveAuthorizedExecutionEvidenceError,
    build_authenticated_recursive_execution_record,
)


def test_raw_recursive_checkpoint_constructor_is_not_public() -> None:
    assert "build_recursive_research_cycle_checkpoint" not in controller.__all__
    assert "validate_recursive_research_cycle_checkpoint" not in controller.__all__
    assert not hasattr(controller, "build_recursive_research_cycle_checkpoint")
    assert not hasattr(controller, "validate_recursive_research_cycle_checkpoint")


def test_public_progression_requires_reconstructed_planning_and_execution() -> None:
    parameters = inspect.signature(
        evidence.advance_recursive_cycle_after_verified_transition
    ).parameters
    assert "validated_planning_artifact" in parameters
    assert "planning_handoff" in parameters
    assert "source_discrepancy_report" in parameters
    assert "source_evaluated_graph" in parameters
    assert "planner_program_state" in parameters
    assert "execution_adapter_id" in parameters
    assert "request_path" in parameters
    assert "action_report_path" in parameters
    assert "authorization_checkpoint" not in parameters
    assert "verified_execution_record" not in parameters


def test_recursive_execution_evidence_rejects_unpinned_adapter_before_filesystem_use(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        RecursiveAuthorizedExecutionEvidenceError,
        match="supports only independently pinned heat/NIST adapters",
    ):
        build_authenticated_recursive_execution_record(
            source_checkpoint_sha256="a" * 64,
            expected_candidate_action_id="planner:simulation",
            expected_candidate_action_class="simulation",
            adapter_id="generic-command",
            repository_root=tmp_path,
            research_run=tmp_path,
            action_registry_path=tmp_path / "missing-registry.json",
            request_path=tmp_path / "missing-request.json",
            action_report_path=tmp_path / "missing-report.json",
        )


def test_recursive_execution_evidence_rejects_noncanonical_checkpoint_sha(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        RecursiveAuthorizedExecutionEvidenceError,
        match="source_checkpoint_sha256 must be lowercase SHA-256",
    ):
        build_authenticated_recursive_execution_record(
            source_checkpoint_sha256="NOT-A-SHA",
            expected_candidate_action_id="planner:simulation",
            expected_candidate_action_class="simulation",
            adapter_id="reference-heat-conduction",
            repository_root=tmp_path,
            research_run=tmp_path,
            action_registry_path=tmp_path / "missing-registry.json",
            request_path=tmp_path / "missing-request.json",
            action_report_path=tmp_path / "missing-report.json",
        )
