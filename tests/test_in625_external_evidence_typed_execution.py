from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_authorization import (
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.in625_execution_verifier import (
    In625ExecutionVerifierError,
    verify_in625_execution_handoff,
)
from materials_data_analyzer.research_loop.kernel import (
    initialize_research_loop,
    load_research_state,
)
from materials_data_analyzer.research_loop.planning_adapter import plan_research_next_action


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _registry() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "registry_id": "in625-external-evidence-typed-actions-v1",
        "domain": "in625_external_empirical_evidence",
        "actions": [
            {
                "action_type": "external_evidence_search",
                "version": "1.0",
                "availability": "available",
                "category": "external_evidence_search",
                "scientific_purpose": "Register one real checksum-verified IN625 external source without scientific promotion.",
                "target_blockers": ["empirical_evidence_not_acquired"],
                "preconditions": [
                    "active_research_run_with_budget",
                    "explicit_external_acquisition_authorization",
                    "exact_archive_checksum_bound",
                ],
                "required_inputs": [
                    {
                        "name": "source_config",
                        "kind": "json_file",
                        "required": True,
                        "description": "Pinned source identity.",
                    },
                    {
                        "name": "archive_path",
                        "kind": "binary_archive",
                        "required": True,
                        "description": "Real external archive bytes.",
                    },
                ],
                "expected_outputs": [
                    {
                        "path": "action_result.json",
                        "kind": "json_report",
                        "required": True,
                        "description": "Typed action report.",
                    },
                    {
                        "path": "reports/verified_external_evidence.json",
                        "kind": "json_report",
                        "required": True,
                        "description": "Verified source evidence report.",
                    },
                ],
                "cost_units": 2,
                "binding": {
                    "kind": "source_script",
                    "name": None,
                    "path": "scripts/run_in625_external_evidence_action.py",
                    "platform": "cross_platform",
                },
                "verifier_checks": [
                    "exact_execution_request_bytes_pinned",
                    "full_external_archive_sha256_reverified",
                ],
                "allowed_outcomes": ["verified_external_source_archive_registered"],
                "prohibited_effects": [
                    "synthetic_empirical_measurement_creation",
                    "sample_identity_inference",
                    "measurement_semantics_inference",
                    "replicate_independence_inference",
                    "direct_nist_condition_comparability_claim",
                    "empirical_model_validation_claim",
                    "hypothesis_truth_claim",
                    "positive_scientific_closeout",
                    "physical_experiment_execution",
                    "automatic_scientific_evidence_promotion",
                    "engineering_decision",
                ],
            }
        ],
    }


def _build_fixture(tmp_path: Path) -> dict[str, Path | str]:
    root = tmp_path / "repository"
    root.mkdir()
    script = root / "scripts" / "run_in625_external_evidence_action.py"
    script.parent.mkdir(parents=True)
    script.write_text("# typed test binding\n", encoding="utf-8")

    archive = root / "inputs" / "Dataset.zip"
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("Dataset/Tribological testing/Friction/CM_1.dat", "distance\tcof\n0\t0.20\n1\t0.22\n")
        handle.writestr("Dataset/README.txt", "synthetic fixture only; not scientific evidence\n")
    archive_bytes = archive.read_bytes()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    archive_md5 = hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest()
    readme = b"fixture\n"

    source_config = root / "configs" / "research" / "in625_zenodo_20503603_verified_source.v1.json"
    config = {
        "schema_version": "1.1",
        "source_id": "zenodo-20503603-in625-lpbf-publication-supplement",
        "source_family": "zenodo_publication_supplement",
        "zenodo": {
            "record_id": 20503603,
            "version_doi": "10.5281/zenodo.20503603",
            "expected_title": "test fixture only",
            "publication_date": "2026-06-02",
            "license_id": "cc-by-4.0",
            "related_article_doi": "10.1016/j.jmrt.2026.05.163",
            "related_article_relation": "isSupplementTo",
            "selected_files": ["README - Dataset description.txt", "Dataset.zip"],
            "readme_file": "README - Dataset description.txt",
            "archive_file": "Dataset.zip",
            "files": {
                "README - Dataset description.txt": {
                    "size_bytes": len(readme),
                    "provider_checksum_algorithm": "md5",
                    "provider_checksum_digest": hashlib.md5(readme, usedforsecurity=False).hexdigest(),
                    "verified_sha256": hashlib.sha256(readme).hexdigest(),
                },
                "Dataset.zip": {
                    "size_bytes": len(archive_bytes),
                    "provider_checksum_algorithm": "md5",
                    "provider_checksum_digest": archive_md5,
                    "verified_sha256": archive_sha,
                },
            },
            "archive_policy": {
                "max_members": 100,
                "max_total_uncompressed_bytes": 1_000_000,
                "max_member_uncompressed_bytes": 500_000,
                "max_selected_tabular_bytes": 500_000,
                "selected_extensions": [".dat"],
                "reject_symlinks": True,
                "reject_path_traversal": True,
            },
        },
        "scientific_boundaries": {
            "authority_class": "source_artifact_only",
            "issue_76_eligible": False,
            "automatic_scientific_promotion": False,
            "source_acquisition_establishes_direct_nist_comparability": False,
            "source_acquisition_establishes_hypothesis_truth": False,
            "source_acquisition_establishes_positive_scientific_closeout": False,
        },
    }
    _write_json(source_config, config)

    registry_path = root / "configs" / "research" / "in625_external_evidence_action_registry.v1.json"
    _write_json(registry_path, _registry())
    registry = load_action_registry(registry_path, repository_root=root)

    objective_path = root / "objective.json"
    _write_json(
        objective_path,
        {
            "schema_version": "1.0",
            "research_id": "in625-external-evidence-test",
            "question": "Can one real external IN625 source be registered with exact provenance?",
            "metrics": {"primary": "source provenance", "secondary": ["byte integrity"]},
            "constraints": ["no scientific promotion"],
            "budget": {"maximum_actions": 2, "maximum_cost_units": 4},
            "stop_rules": ["stop after source registration"],
        },
    )
    run = root / "runs" / "case"
    initialize_research_loop(objective_path, run)

    request_path = root / "request.json"
    request = {
        "schema_version": "1.0",
        "action_id": "register-real-in625-source",
        "action_type": "external_evidence_search",
        "action_version": "1.0",
        "research_run": str(run),
        "source_config": str(source_config),
        "expected_source_config_sha256": _sha256(source_config),
        "archive_path": str(archive),
        "expected_archive_sha256": archive_sha,
        "registry": str(registry_path),
        "repository_root": str(root),
        "expected_registry_sha256": registry["registry_sha256"],
    }
    _write_json(request_path, request)
    return {
        "root": root,
        "run": run,
        "archive": archive,
        "source_config": source_config,
        "registry": registry_path,
        "request": request_path,
        "archive_sha": archive_sha,
    }


def test_planning_and_authorization_expose_real_external_evidence_candidate(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    plan = plan_research_next_action(
        "in625-external-evidence",
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
    )
    assert plan["selection_status"] == "ready_to_execute"
    assert plan["selected_action"]["action_type"] == "external_evidence_search"
    assert plan["selected_action"]["availability"] == "available"
    assert plan["selected_action"]["expected_archive_sha256"] == fixture["archive_sha"]
    assert plan["network_access_performed"] is False
    assert plan["scientific_evidence_upgraded"] is False

    authorization = assess_current_action_authorization(
        "in625-external-evidence",
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
    )
    assert authorization["authorization_status"] == "ready_for_explicit_execution_request"
    assert authorization["execution_contract"]["category"] == "external_evidence_search"
    assert authorization["action_executed"] is False
    assert authorization["scientific_evidence_upgraded"] is False


def test_independent_handoff_rejects_request_or_archive_drift(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    verified = verify_in625_execution_handoff(
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
        request_path=fixture["request"],
    )
    assert verified["archive_sha256"] == fixture["archive_sha"]
    assert verified["numerical_candidate_count"] == 1
    assert verified["direct_condition_comparability_established"] is False

    original_request = json.loads(Path(fixture["request"]).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(original_request)
    mutated["expected_archive_sha256"] = "0" * 64
    _write_json(Path(fixture["request"]), mutated)
    with pytest.raises(In625ExecutionVerifierError, match="archive SHA"):
        verify_in625_execution_handoff(
            repository_root=fixture["root"],
            research_run=fixture["run"],
            action_registry_path=fixture["registry"],
            request_path=fixture["request"],
        )

    _write_json(Path(fixture["request"]), original_request)
    Path(fixture["archive"]).write_bytes(Path(fixture["archive"]).read_bytes() + b"tamper")
    with pytest.raises(In625ExecutionVerifierError, match="archive differs"):
        verify_in625_execution_handoff(
            repository_root=fixture["root"],
            research_run=fixture["run"],
            action_registry_path=fixture["registry"],
            request_path=fixture["request"],
        )


def test_public_typed_execution_appends_exactly_one_nonpromoting_action(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    verified = verify_in625_execution_handoff(
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
        request_path=fixture["request"],
    )
    result = execute_authorized_action(
        "in625-external-evidence",
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
        request_path=fixture["request"],
        expected_action_type=verified["action_type"],
        expected_request_sha256=verified["request_sha256"],
        expected_research_ledger_sha256=verified["research_ledger_sha256"],
    )
    assert result["action_executed"] is True
    assert result["actions_before"] == 0
    assert result["actions_after"] == 1
    assert result["real_external_archive_consumed"] is True
    assert result["network_access_initiated_by_typed_action"] is False
    assert result["direct_condition_comparability_established"] is False
    assert result["empirical_model_validation_established"] is False
    assert result["scientific_evidence_upgraded_by_orchestrator"] is False
    assert result["verified_report"]["source_provenance_verified"] is True
    assert result["verified_report"]["archive_sha256"] == fixture["archive_sha"]

    state = load_research_state(fixture["run"])
    assert len(state["actions"]) == 1
    assert state["actions"][0]["action_type"] == "external_evidence_search"
    assert state["actions"][0]["status"] == "completed"
    assert len(state["actions"][0]["artifacts"]) == 2

    repeat_plan = plan_research_next_action(
        "in625-external-evidence",
        repository_root=fixture["root"],
        research_run=fixture["run"],
        action_registry_path=fixture["registry"],
    )
    assert repeat_plan["selected_action"] is None
    assert repeat_plan["selection_status"] == "no_positive_value_action"


def test_router_rejects_cross_adapter_and_missing_sha_pins(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    with pytest.raises(AuthorizedExecutionError, match="cannot be routed through the NASA adapter"):
        execute_authorized_action(
            "nasa-battery",
            repository_root=fixture["root"],
            research_run=fixture["run"],
            action_registry_path=fixture["registry"],
            request_path=fixture["request"],
            expected_action_type="external_evidence_search",
        )
    with pytest.raises(AuthorizedExecutionError, match="requires exact request and research-ledger SHA pins"):
        execute_authorized_action(
            "in625-external-evidence",
            repository_root=fixture["root"],
            research_run=fixture["run"],
            action_registry_path=fixture["registry"],
            request_path=fixture["request"],
            expected_action_type="external_evidence_search",
        )
