from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    append_action,
    initialize_research_loop,
    load_research_state,
    nasa_external_data_requirement_action as action,
)
from materials_data_analyzer.research_loop.action_registry import (
    load_action_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "configs/research/nasa_external_data_requirement_action_registry.v1.json"
)


def _write_protocol_report(
    tmp_path: Path,
    rows: str,
    *,
    missing_evaluated_metadata: int = 0,
    exact_group_count: int = 3,
) -> Path:
    metrics = tmp_path / "protocol_group_metrics.csv"
    metrics.write_text(
        "ambient_temperature_median_c,evaluated_battery_count\n" + rows,
        encoding="utf-8",
    )
    report = tmp_path / "action_result.json"
    report.write_text(
        json.dumps(
            {
                "summary": {
                    "minimum_evaluated_batteries_per_group": 5,
                    "missing_evaluated_protocol_metadata_battery_count": (
                        missing_evaluated_metadata
                    ),
                    "exact_protocol_group_count": exact_group_count,
                },
                "outputs": [
                    {
                        "relative_path": (
                            "protocol_stratification/protocol_group_metrics.csv"
                        ),
                        "path": str(metrics),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return report


def test_protocol_requirement_reports_exact_group_deficits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _write_protocol_report(tmp_path, "24.0,3\n43.0,5\n4.0,1\n")
    monkeypatch.setattr(
        action,
        "verify_nasa_protocol_stratification_report",
        lambda _: {"outcome": "protocol_groups_too_small"},
    )

    result = action._protocol_requirement(report)

    assert result is not None
    requirement, inputs = result
    group_contract = requirement["minimum_group_contract"]
    assert group_contract["minimum_evaluated_batteries_per_exact_group"] == 5
    assert group_contract["minimum_total_additional_evaluated_batteries"] == 6
    assert group_contract["eligibility_threshold_is_not_power_analysis"] is True
    assert [
        item["ambient_temperature_median_c"]
        for item in group_contract["group_requirements"]
    ] == [4.0, 24.0, 43.0]
    assert [
        item["minimum_additional_evaluated_batteries"]
        for item in group_contract["group_requirements"]
    ] == [4, 2, 0]
    assert requirement["current_evidence_level"] == "Unsupported"
    assert inputs[0] == report


def test_missing_protocol_metadata_requires_authoritative_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _write_protocol_report(
        tmp_path,
        "25.0,3\n",
        missing_evaluated_metadata=2,
        exact_group_count=1,
    )
    monkeypatch.setattr(
        action,
        "verify_nasa_protocol_stratification_report",
        lambda _: {"outcome": "protocol_metadata_insufficient"},
    )

    result = action._protocol_requirement(report)

    assert result is not None
    requirement, inputs = result
    assert requirement["outcome"] == "current_blocker_not_resolvable_by_more_data"
    assert requirement["blocker"] == "protocol_metadata_insufficient"
    assert requirement["required_evidence_route"] == (
        "authoritative_metadata_recovery"
    )
    assert requirement["fallback_cohort_role"] == (
        "independent_external_or_predeclared_calibration"
    )
    metadata = requirement["required_metadata"][0]
    assert metadata["field"] == "ambient_temperature_median_c"
    assert metadata["unit"] == "degree_Celsius"
    assert metadata["missing_evaluated_battery_count"] == 2
    assert "imputation_without_authoritative_source_evidence" in requirement[
        "prohibited_substitutions"
    ]
    assert "minimum_group_contract" not in requirement
    assert inputs[0] == report


def test_single_exact_group_requires_a_new_source_recorded_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _write_protocol_report(
        tmp_path,
        "25.0,5\n",
        missing_evaluated_metadata=0,
        exact_group_count=1,
    )
    monkeypatch.setattr(
        action,
        "verify_nasa_protocol_stratification_report",
        lambda _: {"outcome": "protocol_metadata_insufficient"},
    )

    result = action._protocol_requirement(report)

    assert result is not None
    requirement, _ = result
    contract = requirement["minimum_group_contract"]
    assert requirement["outcome"] == "minimum_external_cohort_contract_generated"
    assert requirement["required_cohort_role"] == (
        "independent_external_or_predeclared_calibration"
    )
    assert contract["current_exact_groups"] == 1
    assert contract["additional_distinct_exact_group_required"] is True
    assert contract["minimum_evaluated_batteries_per_exact_group"] == 5
    assert contract["new_temperature_value_must_not_be_guessed"] is True


def test_target_requirement_requires_reference_metadata_recovery_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "action_result.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        action,
        "verify_nasa_target_reference_report",
        lambda _: {"outcome": "required_reference_metadata_missing"},
    )

    result = action._target_requirement(report)

    assert result is not None
    requirement, _ = result
    metadata = requirement["required_metadata"][0]
    assert requirement["outcome"] == "current_blocker_not_resolvable_by_more_data"
    assert requirement["required_evidence_route"] == (
        "authoritative_metadata_recovery"
    )
    assert requirement["fallback_cohort_role"] == (
        "independent_external_or_predeclared_calibration"
    )
    assert metadata["field"] == "reference_capacity_ah"
    assert metadata["unit"] == "ampere_hour"
    assert requirement["current_evidence_level"] == "Unsupported"


def _objective(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "external-data-requirement-test",
                "question": "What evidence is required after protocol support fails?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": [
                    "preserve_negative_results",
                    "do_not_relabel_existing_batteries_as_external",
                ],
                "budget": {"maximum_actions": 5, "maximum_cost_units": 20},
                "stop_rules": ["budget_exhausted", "external_evidence_required"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _execute_requirement_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], dict[Path, bytes]]:
    research = tmp_path / "research"
    initialize_research_loop(_objective(tmp_path / "objective.json"), research)

    protocol_dir = tmp_path / "protocol"
    protocol_dir.mkdir()
    protocol_report = _write_protocol_report(
        protocol_dir,
        "4.0,1\n24.0,3\n43.0,5\n",
    )
    metrics = protocol_dir / "protocol_group_metrics.csv"
    before = {
        protocol_report: protocol_report.read_bytes(),
        metrics: metrics.read_bytes(),
    }
    append_action(
        research,
        action_id="NASA-PROTOCOL-001",
        action_type="protocol_stratification",
        status="completed",
        summary="Exact-temperature groups are below the predeclared threshold.",
        cost_units=5,
        artifact_paths=[protocol_report],
    )

    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    request = tmp_path / "external_requirement_request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "NASA-EXTERNAL-001",
                "action_type": action.ACTION_TYPE,
                "research_run": str(research),
                "registry": str(REGISTRY),
                "repository_root": str(ROOT),
                "expected_registry_sha256": registry["registry_sha256"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        action,
        "verify_nasa_protocol_stratification_report",
        lambda _: {"valid": True, "outcome": "protocol_groups_too_small"},
    )
    return action.execute_nasa_external_data_requirement_action(request), before


def test_external_requirement_executes_reverifies_and_stops_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, before = _execute_requirement_case(tmp_path, monkeypatch)
    verified = action.verify_nasa_external_data_requirement_report(
        result["action_report"]
    )

    assert result["execution_status"] == "completed"
    assert result["outcome"] == "minimum_external_cohort_contract_generated"
    assert verified["valid"] is True
    assert verified["research_status"] == "stopped"
    assert verified["stop_reason"] == "external_evidence_required"
    assert all(path.read_bytes() == content for path, content in before.items())

    requirement = json.loads(
        Path(result["requirement_report"]).read_text(encoding="utf-8")
    )
    assert requirement["minimum_group_contract"][
        "minimum_total_additional_evaluated_batteries"
    ] == 6
    assert requirement["current_evidence_level"] == "Unsupported"

    state = load_research_state(result["research_state"]["research_id"])
    del state
    research_state = result["research_state"]
    assert research_state["status"] == "stopped"
    assert research_state["stop"]["reason_code"] == "external_evidence_required"
    assert research_state["actions"][-1]["action_type"] == action.ACTION_TYPE
    assert research_state["actions"][-1]["status"] == "completed"


def test_verifier_rejects_tampered_report_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _execute_requirement_case(tmp_path, monkeypatch)
    report_path = Path(result["action_report"])
    original = json.loads(report_path.read_text(encoding="utf-8"))
    mutations = (
        ("immutable_inputs", [], "immutable input bindings"),
        ("verification", {}, "verification flags"),
        ("outcome", "tampered_outcome", "outcome"),
        ("registry", {}, "registry binding"),
    )

    for field, replacement, expected_message in mutations:
        tampered = dict(original)
        tampered[field] = replacement
        report_path.write_text(
            json.dumps(tampered, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(
            action.NasaExternalDataRequirementActionError,
            match=expected_message,
        ):
            action.verify_nasa_external_data_requirement_report(report_path)

    report_path.write_text(
        json.dumps(original, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_external_action_registry_is_executable() -> None:
    registry = load_action_registry(REGISTRY, repository_root=ROOT)

    contract = registry["actions"][0]
    assert contract["action_type"] == action.ACTION_TYPE
    assert contract["availability"] == "available"
    assert contract["cost_units"] == 2
    assert contract["binding"]["kind"] == "source_script"
    assert (
        "evidence_route_is_metadata_recovery_or_external_calibration"
        in contract["verifier_checks"]
    )
