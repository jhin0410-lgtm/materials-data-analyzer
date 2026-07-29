"""Tests for safe candidate-constraint evaluation and final ranking."""

from __future__ import annotations

import pandas as pd
import pytest

from analyzers.constrained_simulation import (
    _apply_eligibility_closeout,
    _build_final_ranking,
    evaluate_candidate_constraints,
    validate_constraint_config,
)


def _config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "constraints": [
            {
                "constraint_id": "temperature_window",
                "kind": "range",
                "feature": "process_temp_c",
                "minimum": 650.0,
                "maximum": 850.0,
            },
            {
                "constraint_id": "high_temp_pressure",
                "kind": "conditional_range",
                "if": {
                    "feature": "process_temp_c",
                    "operator": ">",
                    "value": 800.0,
                },
                "then": {
                    "feature": "pressure_mpa",
                    "minimum": 1.1,
                    "maximum": 1.5,
                },
            },
        ],
    }


def test_constraint_config_rejects_arbitrary_expression_kind() -> None:
    payload = {
        "schema_version": "1.0",
        "constraints": [
            {
                "constraint_id": "unsafe",
                "kind": "expression",
                "expression": "__import__('os')",
            }
        ],
    }

    with pytest.raises(ValueError, match="unsupported constraint kind"):
        validate_constraint_config(payload)


def test_candidate_constraints_record_pass_and_failure() -> None:
    candidates = pd.DataFrame(
        {
            "candidate_id": ["safe", "unsafe"],
            "process_temp_c": [780.0, 820.0],
            "pressure_mpa": [1.0, 0.9],
        }
    )

    audit = evaluate_candidate_constraints(candidates, _config())

    unsafe_rows = audit[audit["candidate_id"] == "unsafe"]
    assert len(audit) == 4
    assert int((~unsafe_rows["passed"]).sum()) == 1
    assert unsafe_rows.loc[
        unsafe_rows["constraint_id"] == "high_temp_pressure", "passed"
    ].iloc[0] is False or not bool(
        unsafe_rows.loc[
            unsafe_rows["constraint_id"] == "high_temp_pressure", "passed"
        ].iloc[0]
    )


def test_eligibility_closeout_excludes_constraint_violations_and_domain_warnings() -> None:
    predictions = pd.DataFrame(
        {
            "candidate_id": ["eligible", "domain_warning", "constraint_failure"],
            "predicted_target": [90.0, 99.0, 98.0],
            "target_name": ["yield_percent"] * 3,
            "model_type": ["RandomForest"] * 3,
            "validation_status": ["valid"] * 3,
            "validation_message": ["Predicted successfully."] * 3,
            "domain_warning_count": [0, 1, 0],
            "has_domain_warning": [False, True, False],
            "process_temp_c": [750.0, 900.0, 820.0],
        }
    )
    audit = pd.DataFrame(
        {
            "candidate_id": ["eligible", "domain_warning", "constraint_failure"],
            "constraint_id": ["temperature", "temperature", "pressure"],
            "constraint_kind": ["range", "range", "conditional_range"],
            "passed": [True, True, False],
            "message": ["ok", "ok", "failed"],
        }
    )

    final_predictions, summary = _apply_eligibility_closeout(predictions, audit)

    status = final_predictions.set_index("candidate_id")["eligibility_status"]
    assert status["eligible"] == "eligible"
    assert status["domain_warning"] == "not_eligible_outside_training_domain"
    assert status["constraint_failure"] == "excluded_constraint_violation"
    failed_prediction = final_predictions.set_index("candidate_id").loc[
        "constraint_failure", "predicted_target"
    ]
    assert pd.isna(failed_prediction)
    assert int(summary["candidate_count"].sum()) == 3


def test_final_ranking_includes_only_eligible_candidates() -> None:
    predictions = pd.DataFrame(
        {
            "candidate_id": ["eligible_low", "eligible_high", "not_eligible"],
            "predicted_target": [85.0, 92.0, 99.0],
            "target_name": ["yield_percent"] * 3,
            "model_type": ["RandomForest"] * 3,
            "validation_status": ["valid"] * 3,
            "eligibility_status": [
                "eligible",
                "eligible",
                "not_eligible_outside_training_domain",
            ],
            "process_temp_c": [700.0, 800.0, 900.0],
        }
    )

    ranking = _build_final_ranking(predictions, goal="maximize")

    assert ranking.loc[0, "candidate_id"] == "eligible_high"
    assert ranking.loc[1, "candidate_id"] == "eligible_low"
    not_eligible = ranking[ranking["candidate_id"] == "not_eligible"].iloc[0]
    assert pd.isna(not_eligible["rank"])
    assert not_eligible["ranking_status"] == "not_ranked"
