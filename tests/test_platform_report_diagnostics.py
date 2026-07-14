import json
from pathlib import Path

from src.platform_core.artifact_resolver import calculate_sha256
from src.platform_core.diagnostic_service import diagnose_run
from src.platform_core.report_generator import build_platform_report, render_report_markdown
from src.platform_core.run_registry import ingest_manifest


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return calculate_sha256(path)


def _manifest(tmp_path: Path) -> Path:
    source = tmp_path / "data" / "processed" / "reliability_v1_5_classification_metrics.csv"
    output = tmp_path / "data" / "processed" / "reliability_v1_5_trust_summary.csv"
    source_sha = _write(source, "metric,value\naverage_precision,0.0998\n")
    output_sha = _write(output, "field,value\nrepresentative_model,none_selected\n")
    manifest = {
        "run_id": "report-diagnostic-run",
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
        "input_checksums": {"reliability_v1_5_classification_metrics": source_sha},
        "produced_artifacts": ["data/processed/reliability_v1_5_trust_summary.csv"],
        "output_checksums": {"data/processed/reliability_v1_5_trust_summary.csv": output_sha},
        "side_effect_status": "allowed_outputs_only",
        "local_only_outputs": [],
        "tracked_outputs": [],
        "output_directory": "outputs/platform_runs/report-diagnostic-run",
    }
    path = tmp_path / "outputs" / "platform_runs" / "report-diagnostic-run" / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_report_can_include_registry_diagnostic_summary_without_running_diagnostics(tmp_path):
    registry_path = "outputs/platform_registry/report_diagnostics.sqlite3"
    ingest_manifest(_manifest(tmp_path), repo_root=tmp_path, registry_path=registry_path)
    diagnose_run("report-diagnostic-run", repo_root=tmp_path, registry_path=registry_path)

    report = build_platform_report(
        {
            "schema_version": "2.0",
            "report_id": "diagnostic_report",
            "formats": ["json", "markdown"],
            "selected_case_studies": ["reliability"],
            "output_dir": "outputs/platform_reports/diagnostic_report",
            "include_registry_diagnostics": True,
            "registry_path": registry_path,
        },
        repo_root=tmp_path,
    )

    assert report.registry_diagnostics_summary["status"] == "available"
    assert report.registry_diagnostics_summary["evaluation_count"] == 1
    markdown = render_report_markdown(report)
    assert "Registry Diagnostics Summary" in markdown
    assert "scientific" not in json.dumps(report.registry_diagnostics_summary).lower()


def test_report_diagnostics_are_opt_in_by_default():
    report = build_platform_report(
        {
            "schema_version": "2.0",
            "report_id": "diagnostic_report_default",
            "formats": ["json"],
            "selected_case_studies": ["reliability"],
            "output_dir": "outputs/platform_reports/diagnostic_report_default",
        }
    )

    assert report.registry_diagnostics_summary == {"status": "not_requested"}
