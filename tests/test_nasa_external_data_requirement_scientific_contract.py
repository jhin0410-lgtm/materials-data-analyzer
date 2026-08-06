from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    initialize_research_loop,
    nasa_external_data_requirement_action as action,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.kernel import load_research_state

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "configs/research/nasa_external_data_requirement_action_registry.v1.json"
)


def _protocol_report(
    tmp_path: Path,
    *,
    rows: str,
    outcome: str,
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


def test_sparse_group_contract_prohibits_cross_source_count_pooling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _protocol_report(
        tmp_path,
        rows="4.0,1\n24.0,3\n43.0,5\n",
        outcome="protocol_groups_too_small",
    )
    monkeypatch.setattr(
        action,
        "verify_nasa_protocol_stratification_report",
        lambda _: {"outcome": "protocol_groups_too_small"},
    )

    result = action._protocol_requirement(report)

    assert result is not None
    requirement, _ = result
    design = requirement["source_cohort_design"]
    assert design["existing_group_deficits_are_within_source_cohort_only"] is True
    assert design["unrelated_source_cohort_counts_may_not_be_pooled"] is True
    assert design[
        "same_source_top_up_requires_authoritative_shared_cohort_identity"
    ] is True
    assert design["new_source_cohort_minimum_exact_groups"] == 2
    assert design[
        "new_source_cohort_minimum_evaluated_batteries_per_exact_group"
    ] == 5
    assert design[
        "temperature_and_source_cohort_must_not_be_perfectly_confounded"
    ] is True
    assert design["source_cohort_aware_analysis_must_be_predeclared"] is True


def test_protocol_metadata_fallback_keeps_source_confounding_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _protocol_report(
        tmp_path,
        rows="25.0,3\n",
        outcome="protocol_metadata_insufficient",
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
    requirement, _ = result
    design = requirement["fallback_contract"]["source_cohort_design"]
    assert design["unrelated_source_cohort_counts_may_not_be_pooled"] is True
    assert design["new_source_cohort_minimum_exact_groups"] == 2
    assert "pooling_unrelated_source_cohorts_by_temperature" in requirement[
        "prohibited_substitutions"
    ]


def test_execution_rejects_unauthorized_terminal_reason_before_mutation(
    tmp_path: Path,
) -> None:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "missing-stop-rule-test",
                "question": "Can an unauthorized stop transition be recorded?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {"maximum_actions": 3, "maximum_cost_units": 10},
                "stop_rules": ["budget_exhausted"],
            }
        ),
        encoding="utf-8",
    )
    research = tmp_path / "research"
    initialize_research_loop(objective, research)

    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    request = tmp_path / "request.json"
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

    with pytest.raises(
        action.NasaExternalDataRequirementActionError,
        match="does not authorize stop rule",
    ):
        action.execute_nasa_external_data_requirement_action(request)

    state = load_research_state(research)
    assert state["status"] == "active"
    assert state["actions"] == []
    assert not (research / "actions" / "NASA-EXTERNAL-001").exists()
