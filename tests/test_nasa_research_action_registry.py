from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    ResearchLoopError,
    action_summaries,
    describe_action,
    load_action_registry,
    validate_action_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"
EXPECTED_ACTIONS = {
    "audit_existing_battery_run",
    "close_reviewed_nasa_audit",
    "external_data_requirement_generation",
    "feature_family_ablation",
    "hierarchical_state_space_baseline",
    "import_official_nasa_archive",
    "protocol_stratification",
    "run_fixed_battery_intelligence",
    "selective_prediction_abstention",
    "source_cohort_leave_one_out",
    "target_reference_sensitivity",
}
AVAILABLE_ACTIONS = {
    "audit_existing_battery_run",
    "close_reviewed_nasa_audit",
    "import_official_nasa_archive",
    "run_fixed_battery_intelligence",
}


def _raw_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _by_id() -> dict[str, dict]:
    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    return {action["action_type"]: action for action in registry["actions"]}


def test_nasa_action_registry_has_exact_bounded_inventory() -> None:
    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    by_id = {action["action_type"]: action for action in registry["actions"]}

    assert set(by_id) == EXPECTED_ACTIONS
    assert registry["registry_id"] == "nasa-research-actions-v1"
    assert registry["domain"] == "nasa_pcoe_battery_exact_horizon"
    assert registry["available_action_count"] == 4
    assert registry["planned_action_count"] == 7
    assert len(registry["registry_sha256"]) == 64
    assert {
        action_id
        for action_id, action in by_id.items()
        if action["availability"] == "available"
    } == AVAILABLE_ACTIONS


def test_available_actions_bind_only_to_real_declared_tools() -> None:
    by_id = _by_id()
    assert by_id["import_official_nasa_archive"]["binding"]["name"] == (
        "mda-nasa-battery-import"
    )
    assert by_id["run_fixed_battery_intelligence"]["binding"]["name"] == (
        "mda-battery-intelligence"
    )
    assert by_id["audit_existing_battery_run"]["binding"]["name"] == (
        "mda-battery-result-audit"
    )
    assert by_id["close_reviewed_nasa_audit"]["binding"] == {
        "kind": "source_script",
        "name": None,
        "path": "scripts/close_nasa_pcoe_audit.ps1",
        "platform": "windows_powershell",
    }


def test_available_output_markers_match_existing_implementations() -> None:
    by_id = _by_id()
    importer_source = "".join(
        (
            ROOT / "src/platform_core/battery_intelligence" / filename
        ).read_text(encoding="utf-8")
        for filename in ("nasa_pcoe_rated.py", "nasa_pcoe_resilient.py", "nasa_pcoe.py")
    )
    implementation_sources = {
        "import_official_nasa_archive": importer_source,
        "run_fixed_battery_intelligence": (
            ROOT / "src/platform_core/battery_intelligence/workflow.py"
        ).read_text(encoding="utf-8"),
        "audit_existing_battery_run": "".join(
            (
                ROOT / "src/platform_core/battery_intelligence" / filename
            ).read_text(encoding="utf-8")
            for filename in ("target_comparability.py", "influence_triage.py")
        ),
        "close_reviewed_nasa_audit": (
            ROOT / "scripts/close_nasa_pcoe_audit.ps1"
        ).read_text(encoding="utf-8"),
    }
    for action_id, source in implementation_sources.items():
        for output in by_id[action_id]["expected_outputs"]:
            assert Path(output["path"]).name in source


def test_planned_actions_have_no_execution_binding() -> None:
    for action in _by_id().values():
        if action["availability"] == "planned":
            assert action["binding"] is None
            assert action["version"].endswith("-planned")


def test_registry_is_deterministic_and_describable() -> None:
    first = load_action_registry(REGISTRY, repository_root=ROOT)
    second = load_action_registry(REGISTRY, repository_root=ROOT)
    summaries = action_summaries(first)
    detail = describe_action(first, "run_fixed_battery_intelligence")

    assert first["registry_sha256"] == second["registry_sha256"]
    assert [item["action_type"] for item in summaries] == sorted(EXPECTED_ACTIONS)
    assert detail["registry_sha256"] == first["registry_sha256"]
    assert detail["availability"] == "available"
    assert "random_row_split" in detail["prohibited_effects"]


def test_registry_rejects_unknown_action_and_duplicate_json_keys(tmp_path: Path) -> None:
    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    with pytest.raises(ResearchLoopError, match="unknown action_type"):
        describe_action(registry, "not_registered")

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8"
    )
    with pytest.raises(ResearchLoopError, match="duplicate JSON key"):
        load_action_registry(duplicate, repository_root=ROOT)


def test_registry_rejects_invalid_execution_bindings() -> None:
    undeclared = _raw_registry()
    next(
        item
        for item in undeclared["actions"]
        if item["action_type"] == "run_fixed_battery_intelligence"
    )["binding"]["name"] = "undeclared-command"
    with pytest.raises(ResearchLoopError, match="undeclared installed command"):
        validate_action_registry(undeclared, repository_root=ROOT)

    planned = _raw_registry()
    next(item for item in planned["actions"] if item["availability"] == "planned")[
        "binding"
    ] = {
        "kind": "installed_command",
        "name": "mda",
        "path": None,
        "platform": "cross_platform",
    }
    with pytest.raises(ResearchLoopError, match="planned action"):
        validate_action_registry(planned, repository_root=ROOT)

    escaped = _raw_registry()
    next(
        item
        for item in escaped["actions"]
        if item["action_type"] == "close_reviewed_nasa_audit"
    )["binding"]["path"] = "../unsafe.ps1"
    with pytest.raises(ResearchLoopError, match="repository-relative"):
        validate_action_registry(escaped, repository_root=ROOT)


def test_registry_rejects_duplicate_action_or_io_names() -> None:
    duplicate_action = _raw_registry()
    duplicate_action["actions"].append(copy.deepcopy(duplicate_action["actions"][0]))
    with pytest.raises(ResearchLoopError, match="duplicate action_type"):
        validate_action_registry(duplicate_action, repository_root=ROOT)

    duplicate_input = _raw_registry()
    action = duplicate_input["actions"][0]
    action["required_inputs"].append(copy.deepcopy(action["required_inputs"][0]))
    with pytest.raises(ResearchLoopError, match="duplicate name"):
        validate_action_registry(duplicate_input, repository_root=ROOT)


def test_available_actions_preserve_negative_results_and_claim_boundaries() -> None:
    by_id = _by_id()
    for action_id in AVAILABLE_ACTIONS:
        assert by_id[action_id]["verifier_checks"]

    assert "learned_model_unsupported" in by_id[
        "run_fixed_battery_intelligence"
    ]["allowed_outcomes"]
    assert {
        "target_repair",
        "silent_battery_exclusion",
        "external_generalization_claim",
    }.issubset(by_id["run_fixed_battery_intelligence"]["prohibited_effects"])
    assert {
        "battery_exclusion",
        "target_renormalization",
        "replacement_validation_score",
    }.issubset(by_id["audit_existing_battery_run"]["prohibited_effects"])
    assert {"model_refit", "target_repair", "external_validation_claim"}.issubset(
        by_id["close_reviewed_nasa_audit"]["prohibited_effects"]
    )
    assert {"signal_interpolation", "signal_smoothing", "timezone_inference"}.issubset(
        by_id["import_official_nasa_archive"]["prohibited_effects"]
    )
