from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer.research_loop import (
    nasa_external_data_requirement_action as action,
)
from materials_data_analyzer.research_loop.action_registry import (
    load_action_registry,
)


def _write_protocol_report(tmp_path: Path, rows: str) -> Path:
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
    tmp_path: Path, monkeypatch
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


def test_target_requirement_names_reference_capacity_metadata(
    tmp_path: Path, monkeypatch
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
    assert metadata["field"] == "reference_capacity_ah"
    assert metadata["unit"] == "ampere_hour"
    assert requirement["current_evidence_level"] == "Unsupported"


def test_external_action_registry_is_executable() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    registry = load_action_registry(
        repository_root
        / "configs/research/nasa_external_data_requirement_action_registry.v1.json",
        repository_root=repository_root,
    )

    contract = registry["actions"][0]
    assert contract["action_type"] == action.ACTION_TYPE
    assert contract["availability"] == "available"
    assert contract["cost_units"] == 2
    assert contract["binding"]["kind"] == "source_script"
