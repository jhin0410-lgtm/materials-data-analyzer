"""Tests for the complete NIST AM-Bench integrated closeout workflow."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_nist_ambench_2018_02_workflow.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "nist_ambench_integrated_workflow",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_integrated_workflow_runs_end_to_end_and_closes_out(tmp_path: Path) -> None:
    output_dir = tmp_path / "ambench_integrated"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--output",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "integrated workflow completed" in completed.stdout.lower()

    expected_files = {
        "ambench_case_study_manifest.json",
        "characterization_handoff_manifest.json",
        "ambench_case_summary.csv",
        "integrated_sample_table.csv",
        "sample_join_audit.csv",
        "melt_pool_width_by_linear_energy.png",
        "melt_pool_depth_by_linear_energy.png",
        "ambench_integrated_summary.json",
        "ambench_integrated_report.md",
        "ambench_integrated_workflow_manifest.json",
    }
    assert expected_files.issubset({path.name for path in output_dir.iterdir()})

    summary = json.loads(
        (output_dir / "ambench_integrated_summary.json").read_text(encoding="utf-8")
    )
    assert summary["result"] == {
        "integrity_status": "verified",
        "interpretation": (
            "Within the three source-defined AMMT conditions, higher line "
            "energy coincides with larger mean melt-pool width and depth. "
            "This is descriptive and does not isolate a causal process variable."
        ),
        "scientific_status": "diagnostic",
    }
    assert summary["software_validation"]["integrity_verification"] == {
        "status": "verified",
        "case_study_id": "nist_ambench_2018_02_process_characterization",
        "checksummed_artifact_count": 11,
        "feature_record_count": 40,
        "sample_count": 10,
        "measurement_count": 10,
        "matched_sample_count": 10,
        "scientific_status": "diagnostic",
    }
    assert [row["case_id"] for row in summary["case_summary"]] == ["A", "B", "C"]
    assert summary["report_boundary"] == {
        "existing_case_summary_reformatted": True,
        "missing_metadata_inferred": False,
        "new_scientific_metrics_computed": False,
        "predictive_model_added": False,
    }
    assert summary["scientific_closeout"]["decision_use"] == {
        "exploration": True,
        "portfolio_demonstration": True,
        "engineering_decision": False,
        "causal_scientific_claim": False,
    }

    report = (output_dir / "ambench_integrated_report.md").read_text(
        encoding="utf-8"
    )
    assert "Scientific status: **Diagnostic**" in report
    assert "Integrity status: **Verified**" in report
    assert "Matched samples: **10 / 10**" in report
    assert "does not isolate power or speed" in report
    assert "new predictive evidence" in report

    workflow_manifest = json.loads(
        (output_dir / "ambench_integrated_workflow_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert workflow_manifest["generation_status"] == "completed"
    assert workflow_manifest["scientific_status"] == "diagnostic"
    assert workflow_manifest["model_trained"] is False
    assert workflow_manifest["optimization_performed"] is False
    assert workflow_manifest["network_access_performed"] is False
    assert "ambench_integrated_workflow_manifest.json" not in workflow_manifest[
        "artifact_checksums"
    ]
    for filename, expected_sha in workflow_manifest["artifact_checksums"].items():
        assert _sha256(output_dir / filename) == expected_sha

    assert not list(output_dir.glob("*.pkl"))
    assert not list(output_dir.glob("*model*"))


def test_integrated_summary_and_report_are_output_path_independent(
    tmp_path: Path,
) -> None:
    module = _load_module()
    first = module.run_integrated_workflow(tmp_path / "first")
    second = module.run_integrated_workflow(tmp_path / "second")

    for key in ("integrated_summary", "integrated_report"):
        assert first[key].read_bytes() == second[key].read_bytes()


def test_integrated_workflow_rejects_nonempty_output_directory(
    tmp_path: Path,
) -> None:
    module = _load_module()
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("user file", encoding="utf-8")

    with pytest.raises(FileExistsError, match="must be new or empty"):
        module.run_integrated_workflow(output_dir)

    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "user file"
