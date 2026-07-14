import json
import sqlite3
from pathlib import Path

import pytest

from src.platform_core.artifact_resolver import calculate_sha256
from src.platform_core.claim_diagnostics import evaluate_claim_id
from src.platform_core.diagnostic_rules import build_default_diagnostic_rules
from src.platform_core.diagnostic_service import (
    diagnose_run,
    diagnostics_validate,
    evaluate_claim,
    show_diagnostics,
)
from src.platform_core.evidence_graph import build_evidence_graph
from src.platform_core.run_registry import get_schema_version, ingest_manifest
from src.platform_core.trust_registry import build_default_trust_policy_registry


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return calculate_sha256(path)


def _run_manifest(tmp_path: Path, *, run_id: str = "run-a", include_input_checksum: bool = True) -> Path:
    input_path = tmp_path / "data" / "processed" / "reliability_v1_5_classification_metrics.csv"
    output_path = tmp_path / "data" / "processed" / "reliability_v1_5_trust_summary.csv"
    input_sha = _write(input_path, "metric,value\naverage_precision,0.0998\n")
    output_sha = _write(output_path, "field,value\nrepresentative_model,none_selected\n")
    input_checksums = {"reliability_v1_5_classification_metrics": input_sha} if include_input_checksum else {}
    manifest = {
        "run_id": run_id,
        "pipeline_id": "reliability-trust",
        "plugin_id": "reliability",
        "adapter_id": "reliability_trust_closeout",
        "stage": "trust",
        "config_sha256": "a" * 64,
        "source_artifacts": [
            {
                "artifact_id": "reliability_v1_5_classification_metrics",
                "relative_path": "data/processed/reliability_v1_5_classification_metrics.csv",
                "tracked_policy": "generated_compact",
                "local_only": False,
            }
        ],
        "output_artifacts": [
            {
                "artifact_id": "reliability_v1_5_trust_summary",
                "relative_path": "data/processed/reliability_v1_5_trust_summary.csv",
                "tracked_policy": "generated_compact",
                "local_only": False,
            }
        ],
        "code_commit": "b" * 40,
        "started_at": "2026-07-14T00:00:00Z",
        "completed_at": "2026-07-14T00:00:01Z",
        "duration_seconds": 1.0,
        "status": "verification_completed",
        "dry_run": False,
        "test_mode": False,
        "execution_mode": "verify",
        "environment": {"python_implementation": "cpython"},
        "python_version": "3.11.0",
        "dependency_summary": {"external_execution_dependency": "none"},
        "random_state": None,
        "warnings": [],
        "errors": [],
        "claim_boundary": {
            "trust_policy_id": "reliability_asset_time_aware",
            "production_claim_allowed": False,
        },
        "execution_boundary": {"execution_allowed": True},
        "input_checksums": input_checksums,
        "produced_artifacts": ["data/processed/reliability_v1_5_trust_summary.csv"],
        "output_checksums": {"data/processed/reliability_v1_5_trust_summary.csv": output_sha},
        "side_effect_status": "allowed_outputs_only",
        "local_only_outputs": [],
        "tracked_outputs": [],
        "output_directory": f"outputs/platform_runs/{run_id}",
    }
    manifest_path = tmp_path / "outputs" / "platform_runs" / run_id / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def test_diagnostic_rules_are_static_and_production_ready_absent():
    rules = build_default_diagnostic_rules()

    assert [rule.rule_id for rule in rules] == [rule.rule_id for rule in build_default_diagnostic_rules()]
    assert all(rule.evaluator.__module__.endswith("diagnostic_rules") for rule in rules)
    policies = build_default_trust_policy_registry().snapshot()
    assert all("production_ready" not in policy["allowed_statuses"] for policy in policies)


def test_diagnose_run_persists_policy_findings_claims_and_evidence_graph(tmp_path):
    manifest_path = _run_manifest(tmp_path)
    ingest_manifest(manifest_path, repo_root=tmp_path)

    report = diagnose_run("run-a", repo_root=tmp_path)
    stored = show_diagnostics("run-a", repo_root=tmp_path)

    assert report.overall_status == "passed"
    assert report.promotion_status == "diagnostic_only"
    assert stored["evaluation"]["evaluation_id"] == report.evaluation_id
    assert all(finding.status == "satisfied" for finding in report.findings)
    claim_status = {claim.claim_id: claim.status for claim in report.claim_evaluations}
    assert claim_status["retrospective_diagnostic"] == "supported"
    assert claim_status["production_deployment"] == "prohibited"
    assert claim_status["calibrated_probability"] == "prohibited"
    assert any(node["node_type"] == "trust_status" for node in report.evidence_graph["nodes"])
    assert diagnostics_validate(repo_root=tmp_path)["valid"] is True


def test_missing_checksum_creates_evidence_gap_without_hiding_logic(tmp_path):
    manifest_path = _run_manifest(tmp_path, include_input_checksum=False)
    ingest_manifest(manifest_path, repo_root=tmp_path)

    report = diagnose_run("run-a", repo_root=tmp_path)

    assert report.overall_status == "warning"
    assert report.promotion_status == "missing_evidence"
    assert any(gap.gap_code == "rule:provenance.input_checksums_present" for gap in report.evidence_gaps)
    assert any(finding.status == "unavailable" for finding in report.findings)


def test_claim_diagnostics_are_machine_readable_and_registered_only(tmp_path):
    manifest_path = _run_manifest(tmp_path)
    ingest_manifest(manifest_path, repo_root=tmp_path)
    diagnose_run("run-a", repo_root=tmp_path)

    claim = evaluate_claim("run-a", "rul_prediction", repo_root=tmp_path)

    assert claim["status"] == "prohibited"
    with pytest.raises(KeyError):
        evaluate_claim("run-a", "free_text_unregistered_claim", repo_root=tmp_path)
    direct = evaluate_claim_id(
        "external_population_generalization",
        allowed_claims=(),
        prohibited_claims=(),
        available_evidence=(),
    )
    assert direct.status == "unsupported"
    assert direct.reason_code == "missing_external_holdout"


def test_evidence_graph_contains_run_policy_artifact_and_claim_nodes():
    graph = build_evidence_graph(
        run={"run_id": "run-a", "stage": "trust", "status": "completed", "code_commit": "b" * 40},
        artifacts=[
            {
                "artifact_record_id": "artifact-record",
                "artifact_id": "reliability_v1_5_trust_summary",
                "role": "output",
            }
        ],
        validation_policy_id="asset_time_combined_classification",
        trust_policy_id="reliability_asset_time_aware",
        claim_ids=("retrospective_diagnostic",),
    )

    node_types = {node["node_type"] for node in graph["nodes"]}
    assert {"run", "code_commit", "artifact", "validation", "trust_status", "claim"} <= node_types
    assert graph["edges"] == sorted(graph["edges"], key=lambda edge: (edge["source"], edge["target"], edge["edge_type"]))


def test_registry_schema_migrates_v1_database_to_diagnostic_schema(tmp_path):
    db_path = tmp_path / "outputs" / "platform_registry" / "legacy.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE registry_metadata (metadata_id INTEGER PRIMARY KEY CHECK (metadata_id = 1), schema_version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO registry_metadata(metadata_id, schema_version, created_at, updated_at) VALUES (1, 1, '2026-07-14T00:00:00Z', '2026-07-14T00:00:00Z')"
        )

    version = get_schema_version(tmp_path, "outputs/platform_registry/legacy.sqlite3")

    assert version == 2
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"diagnostic_evaluations", "diagnostic_findings", "evidence_gaps", "claim_evaluations"} <= tables
