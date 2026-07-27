from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_representative_process_characterization_workflow.py"


def _module():
    spec = importlib.util.spec_from_file_location("representative_workflow", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cli_runs_verified_representative_workflow(tmp_path: Path) -> None:
    output = tmp_path / "representative"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "representative process-characterization workflow completed" in (
        completed.stdout.lower()
    )

    summary = json.loads(
        (output / "representative_workflow_summary.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (output / "representative_workflow_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["status"] == "completed"
    assert summary["evidence_level"] == "Diagnostic"
    assert summary["components"]["verified_case"]["trace_count"] == 10
    assert summary["components"]["verified_case"]["model_trained"] is False
    assert summary["components"]["process_design_audit"] == {
        "directory": "02_process_design_audit",
        "audit": "02_process_design_audit/process_design_audit.json",
        "manifest": (
            "02_process_design_audit/process_design_audit_manifest.json"
        ),
        "manifest_sha256": summary["components"]["process_design_audit"][
            "manifest_sha256"
        ],
        "unique_condition_count": 3,
        "factorial_coverage_fraction": 0.5,
        "readiness": "not_ready_for_predictive_or_causal_modeling",
        "model_trained": False,
        "optimization_performed": False,
    }
    plan = summary["components"]["minimum_design_plan"]
    assert plan["recommended_next_action"] == "execute_stage_1_only"
    assert plan["stage_1_new_conditions"] == 3
    assert plan["stage_1_new_traces"] == 9
    assert plan["stage_2_is_conditional"] is True
    assert plan["stage_2_candidate_midpoint_power_w"] == pytest.approx(158.55)
    assert plan["response_model_fitted"] is False
    assert plan["optimization_performed"] is False
    assert plan["machine_feasibility_assumed"] is False

    assert summary["software_validation"] == {
        "existing_component_workflows_reused": True,
        "new_scientific_analyzer_added": False,
        "response_model_fitted": False,
        "response_values_inferred": False,
        "optimization_performed": False,
        "machine_feasibility_assumed": False,
        "row_order_join_used": False,
    }

    assert manifest["generation_status"] == "completed"
    assert manifest["scientific_status"] == "Diagnostic"
    assert manifest["component_directories"] == [
        "01_verified_case",
        "02_process_design_audit",
        "03_minimum_design_plan",
    ]
    assert manifest["response_model_fitted"] is False
    assert manifest["optimization_performed"] is False
    assert manifest["machine_feasibility_assumed"] is False
    assert manifest["artifact_count"] == len(manifest["artifact_sha256"])

    for relative, expected_sha in manifest["artifact_sha256"].items():
        artifact = output / relative
        assert artifact.is_file()
        assert _sha256(artifact) == expected_sha

    assert (
        summary["components"]["verified_case"]["manifest_sha256"]
        == _sha256(
            output
            / "01_verified_case"
            / "ambench_integrated_workflow_manifest.json"
        )
    )
    assert (
        summary["components"]["process_design_audit"]["manifest_sha256"]
        == _sha256(
            output
            / "02_process_design_audit"
            / "process_design_audit_manifest.json"
        )
    )
    assert (
        summary["components"]["minimum_design_plan"]["manifest_sha256"]
        == _sha256(
            output
            / "03_minimum_design_plan"
            / "nist_design_augmentation_manifest.json"
        )
    )

    assert not list(output.rglob("*.pkl"))
    assert not [
        path
        for path in output.rglob("*")
        if path.is_file() and "trained_model" in path.name.lower()
    ]


def test_nonempty_output_is_preserved(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        module.run_representative_workflow(output)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_component_validation_rejects_relaxed_modeling_gate() -> None:
    module = _module()
    case_manifest = {
        "generation_status": "completed",
        "scientific_status": "diagnostic",
        "model_trained": True,
        "optimization_performed": False,
    }
    audit = {
        "status": "completed",
        "evidence_level": "Diagnostic",
        "readiness": {
            "overall": "not_ready_for_predictive_or_causal_modeling"
        },
        "software_validation": {"model_trained": False},
    }
    plan = {
        "status": "completed",
        "evidence_level": "Diagnostic",
        "decision": {"recommended_next_action": "execute_stage_1_only"},
        "software_validation": {
            "response_model_fitted": False,
            "optimization_performed": False,
        },
    }

    with pytest.raises(ValueError, match="unexpectedly reports model training"):
        module._validate_component_results(case_manifest, audit, plan)
