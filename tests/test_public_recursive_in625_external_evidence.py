from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import materials_data_analyzer.research_loop.public_recursive_api as api
from tests.test_public_recursive_real_evidence_replay import replay  # noqa: F401


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry_payload() -> dict:
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
                "scientific_purpose": "Register one real checksum-bound external IN625 source without promoting a scientific claim.",
                "target_blockers": ["empirical_evidence_not_acquired"],
                "preconditions": ["explicit authorization", "exact archive SHA"],
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
                        "description": "Source-provenance report.",
                    },
                ],
                "cost_units": 2,
                "binding": {
                    "kind": "source_script",
                    "name": None,
                    "path": "scripts/run_in625_external_evidence_action.py",
                    "platform": "cross_platform",
                },
                "verifier_checks": ["request SHA", "archive SHA"],
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


def _prepare_external_source(root: Path) -> tuple[Path, Path, Path, Path]:
    script = root / "scripts" / "run_in625_external_evidence_action.py"
    script.write_text("# typed IN625 external-evidence test entrypoint\n", encoding="utf-8")
    archive = root / "external" / "Dataset.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("Dataset/Tribological testing/Friction/CM_1.dat", "distance\tcof\n0\t0.20\n1\t0.22\n")
    archive_bytes = archive.read_bytes()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    readme = b"fixture only\n"
    source_config = root / "configs" / "research" / "in625_zenodo_20503603_verified_source.v1.json"
    _write_json(
        source_config,
        {
            "schema_version": "1.1",
            "source_id": "zenodo-20503603-in625-lpbf-publication-supplement",
            "source_family": "zenodo_publication_supplement",
            "zenodo": {
                "record_id": 20503603,
                "version_doi": "10.5281/zenodo.20503603",
                "expected_title": "fixture only",
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
                        "provider_checksum_digest": hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest(),
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
        },
    )
    registry = root / "configs" / "research" / "in625_external_evidence_action_registry.v1.json"
    _write_json(registry, _registry_payload())
    registry_value = api.load_action_registry(registry, repository_root=root)

    objective = root / "external-objective.json"
    _write_json(
        objective,
        {
            "schema_version": "1.0",
            "research_id": "public-recursive-real-external-evidence",
            "question": "Can real external IN625 source evidence be registered after the verified empirical gap?",
            "metrics": {"primary": "source provenance", "secondary": []},
            "constraints": ["No direct comparability or hypothesis-truth claim"],
            "budget": {"maximum_actions": 2, "maximum_cost_units": 4},
            "stop_rules": ["Stop after bounded source registration"],
        },
    )
    run = root / "run-in625"
    api.initialize_research_loop(objective, run)
    request = root / "request-in625.json"
    _write_json(
        request,
        {
            "schema_version": "1.0",
            "action_id": "in625-external-source-001",
            "action_type": "external_evidence_search",
            "action_version": "1.0",
            "research_run": str(run),
            "source_config": str(source_config),
            "expected_source_config_sha256": _sha(source_config),
            "archive_path": str(archive),
            "expected_archive_sha256": archive_sha,
            "registry": str(registry),
            "repository_root": str(root),
            "expected_registry_sha256": registry_value["registry_sha256"],
        },
    )
    return run, registry, request, archive


def test_cycle2_real_in625_candidate_replaces_prior_registry_bounded_stop(replay: dict) -> None:
    root = replay["root"]
    run, registry, request, _archive = _prepare_external_source(root)
    program = api.build_external_evidence_recursive_planner_program_state(
        planning_handoff=replay["handoff2"],
        discrepancy_report=replay["report2"],
        evaluated_graph=replay["graph2"],
        previous_discrepancy_report=replay["report1"],
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
    )
    binding = program["public_recursive_planner_binding"]
    assert binding["repository_authorized_external_candidate_available"] is True
    assert binding["available_external_evidence_action_count"] == 1
    assert binding["synthetic_candidate_created"] is False
    assert binding["execution_handoff"]["archive_sha256"] == json.loads(
        request.read_text(encoding="utf-8")
    )["expected_archive_sha256"]

    plan = api.build_autonomous_inquiry_plan(program)
    assert plan["selected_next_action"]["action_id"] == "in625-external-source-001"
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["execution_mode"] == "explicit_authorization_required"
    assert plan["stop_decision"]["stop"] is False
    match = api.build_public_candidate_match_record(
        planning_handoff=replay["handoff2"],
        fresh_plan=plan,
    )
    planning = api.build_validated_recursive_planning_checkpoint(
        planning_handoff=replay["handoff2"],
        source_discrepancy_report=replay["report2"],
        source_evaluated_graph=replay["graph2"],
        fresh_plan=plan,
        planner_program_state=program,
        previous_discrepancy_report=replay["report1"],
        candidate_match=match,
        previous_validated_planning_context=replay["context1"],
        recursive_limits=replay["limits"],
    )
    assert planning["recursive_checkpoint"]["cycle_index"] == 2
    assert planning["recursive_checkpoint"]["checkpoint_status"] == "explicit_authorization_required"
    assert planning["recursive_checkpoint"]["persistent_research_state"]["blockers"][
        "external_or_authorization_required_objective_ids"
    ]
    assert planning["autonomy_boundary"]["authorization_granted"] is False
    assert planning["autonomy_boundary"]["execution_performed"] is False
    assert planning["autonomy_boundary"]["scientific_status_changed"] is False
