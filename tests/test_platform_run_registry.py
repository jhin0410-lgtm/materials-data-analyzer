import json
from pathlib import Path

import pytest

from src.platform_core.artifact_resolver import calculate_sha256
from src.platform_core.run_registry import (
    RegistryConflictError,
    RegistryPathError,
    compare_runs,
    export_registry_snapshot,
    get_lineage,
    get_run,
    get_schema_version,
    ingest_manifest,
    initialize_registry,
    list_artifact_records,
    list_runs,
    reproducibility_status,
    resolve_registry_path,
    validate_registry,
)


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return calculate_sha256(path)


def _run_manifest(tmp_path: Path, *, run_id: str = "run-a", config_sha: str = "a" * 64, code_commit: str = "b" * 40):
    input_path = tmp_path / "data" / "processed" / "reliability_v1_5_classification_metrics.csv"
    output_path = tmp_path / "data" / "processed" / "reliability_v1_5_trust_summary.csv"
    input_sha = _write(input_path, "metric,value\naverage_precision,0.1\n")
    output_sha = _write(output_path, "field,value\nrepresentative_model,none_selected\n")
    manifest = {
        "run_id": run_id,
        "pipeline_id": "reliability-trust",
        "plugin_id": "reliability",
        "adapter_id": "reliability_trust_closeout",
        "stage": "trust",
        "config_sha256": config_sha,
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
        "code_commit": code_commit,
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
        "input_checksums": {"reliability_v1_5_classification_metrics": input_sha},
        "produced_artifacts": ["data/processed/reliability_v1_5_trust_summary.csv"],
        "output_checksums": {"data/processed/reliability_v1_5_trust_summary.csv": output_sha},
        "side_effect_status": "allowed_outputs_only",
        "local_only_outputs": [],
        "tracked_outputs": [],
        "output_directory": "outputs/platform_runs/run-a",
    }
    manifest_path = tmp_path / "outputs" / "platform_runs" / run_id / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path, manifest


def test_registry_initialization_and_schema_version(tmp_path):
    path = initialize_registry(tmp_path)

    assert path.exists()
    assert path.as_posix().endswith("outputs/platform_registry/platform_registry.sqlite3")
    assert get_schema_version(tmp_path) == 4


def test_registry_rejects_absolute_and_traversal_paths(tmp_path):
    with pytest.raises(RegistryPathError):
        resolve_registry_path(tmp_path, "C:/tmp/platform_registry.sqlite3")
    with pytest.raises(RegistryPathError, match="path traversal"):
        resolve_registry_path(tmp_path, "../platform_registry.sqlite3")
    with pytest.raises(RegistryPathError):
        resolve_registry_path(tmp_path, "data/platform_registry.sqlite3")


def test_manifest_ingest_is_idempotent_and_records_lineage(tmp_path):
    manifest_path, manifest = _run_manifest(tmp_path)

    first = ingest_manifest(manifest_path, repo_root=tmp_path)
    second = ingest_manifest(manifest_path, repo_root=tmp_path)

    assert first.status == "ingested"
    assert second.status == "idempotent"
    runs = list_runs(repo_root=tmp_path)
    assert [run["run_id"] for run in runs] == [manifest["run_id"]]
    artifacts = list_artifact_records(run_id=manifest["run_id"], repo_root=tmp_path)
    assert {artifact["role"] for artifact in artifacts} == {"input", "output"}
    output = next(artifact for artifact in artifacts if artifact["role"] == "output")
    lineage = get_lineage(output["artifact_record_id"], repo_root=tmp_path)
    assert len(lineage["parents"]) == 1
    assert validate_registry(repo_root=tmp_path)["valid"] is True


def test_conflicting_duplicate_manifest_rolls_back(tmp_path):
    manifest_path, manifest = _run_manifest(tmp_path)
    ingest_manifest(manifest_path, repo_root=tmp_path)
    manifest["config_sha256"] = "c" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RegistryConflictError):
        ingest_manifest(manifest_path, repo_root=tmp_path)

    assert len(list_runs(repo_root=tmp_path)) == 1


def test_reproducibility_verified_partial_and_checksum_mismatch(tmp_path):
    manifest_path, _ = _run_manifest(tmp_path)
    ingest_manifest(manifest_path, repo_root=tmp_path)
    assert reproducibility_status("run-a", repo_root=tmp_path)["status"] == "reproducible_verified"

    metrics = tmp_path / "data" / "processed" / "reliability_v1_5_classification_metrics.csv"
    metrics.write_text("metric,value\naverage_precision,0.2\n", encoding="utf-8")
    assert reproducibility_status("run-a", repo_root=tmp_path)["status"] == "unverifiable_checksum_mismatch"

    partial_path, manifest = _run_manifest(tmp_path, run_id="run-partial")
    manifest["output_checksums"] = {}
    partial_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ingest_manifest(partial_path, repo_root=tmp_path)
    assert reproducibility_status("run-partial", repo_root=tmp_path)["status"] == "reproducible_partial"


def test_run_comparison_statuses(tmp_path):
    path_a, _ = _run_manifest(tmp_path, run_id="run-a")
    path_b, _ = _run_manifest(tmp_path, run_id="run-b")
    path_c, _ = _run_manifest(tmp_path, run_id="run-c", config_sha="d" * 64)
    ingest_manifest(path_a, repo_root=tmp_path)
    ingest_manifest(path_b, repo_root=tmp_path)
    ingest_manifest(path_c, repo_root=tmp_path)

    assert compare_runs("run-a", "run-a", repo_root=tmp_path)["status"] == "identical_metadata"
    assert compare_runs("run-a", "run-b", repo_root=tmp_path)["status"] == "reproducible_equivalent"
    assert compare_runs("run-a", "run-c", repo_root=tmp_path)["status"] == "configuration_changed"


def test_registry_export_is_local_only_and_parseable(tmp_path):
    manifest_path, _ = _run_manifest(tmp_path)
    ingest_manifest(manifest_path, repo_root=tmp_path)

    result = export_registry_snapshot(repo_root=tmp_path)

    assert result["status"] == "exported"
    exported = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    assert exported["runs"][0]["run_id"] == "run-a"
    assert "C:/" not in json.dumps(exported)


def test_report_manifest_ingestion(tmp_path):
    source = tmp_path / "data" / "processed" / "reliability_v1_5_trust_summary.csv"
    report = tmp_path / "outputs" / "platform_reports" / "demo" / "platform_report.json"
    source_sha = _write(source, "field,value\nrepresentative_model,none_selected\n")
    report_sha = _write(report, "{\"ok\": true}\n")
    manifest = {
        "report_id": "demo",
        "report_schema_version": "2.0",
        "platform_version": "2.1.2-dev",
        "code_commit": "b" * 40,
        "generated_formats": ["json"],
        "source_registry_snapshot": {"plugin_count": 1},
        "source_artifacts": ["data/processed/reliability_v1_5_trust_summary.csv"],
        "source_artifact_checksums": {"data/processed/reliability_v1_5_trust_summary.csv": source_sha},
        "case_study_ids": ["reliability"],
        "warnings": [],
        "errors": [],
        "output_files": ["outputs/platform_reports/demo/platform_report.json"],
        "output_checksums": {"outputs/platform_reports/demo/platform_report.json": report_sha},
        "generation_status": "completed",
        "local_only": True,
        "scientific_recomputation_performed": False,
    }
    manifest_path = tmp_path / "outputs" / "platform_reports" / "demo" / "report_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = ingest_manifest(manifest_path, repo_root=tmp_path)

    assert result.run_id == "report-demo"
    assert get_run("report-demo", repo_root=tmp_path)["run"]["stage"] == "report"
