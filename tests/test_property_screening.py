"""Tests for generic tabular property screening helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from analyzers.property_screening import (
    apply_screening_filters,
    build_screening_summary,
    rank_screening_candidates,
    validate_screening_inputs,
    validate_screening_spec,
)


def _screening_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "material_id": ["m1", "m2", "m3", "m4"],
            "formula": ["A", "B", "C", "D"],
            "quality_status": ["valid", "valid", "warning", "valid"],
            "gap": [1.0, 3.0, 2.0, None],
            "hull": [0.2, 0.0, 0.1, 0.4],
            "density": [5.0, 5.0, 5.0, 5.0],
        }
    )


def _spec(mode: str = "minimize", property_name: str = "hull") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_name": "screening_test",
        "screening_mode": "descriptive_observed_property_screening",
        "identifier_column": "material_id",
        "display_columns": ["formula"],
        "filters": [
            {"column": "quality_status", "operator": "in", "values": ["valid"]}
        ],
        "objectives": [
            {
                "property": property_name,
                "mode": mode,
                "weight": 1.0,
                "target": 2.0 if mode == "target_value" else None,
                "lower_bound": 0.5 if mode == "target_range" else None,
                "upper_bound": 1.5 if mode == "target_range" else None,
                "unit": "unknown",
                "rationale": "synthetic test",
            }
        ],
        "missing_value_policy": "exclude_from_ranking",
        "tie_policy": "min_rank",
        "top_n": 2,
        "provenance_status": "reconstructed",
        "limitations": ["synthetic fixture"],
        "notes": ["no credentials"],
    }


def test_validate_screening_spec_accepts_valid_spec() -> None:
    validate_screening_spec(_spec())


def test_validate_screening_inputs_rejects_unknown_objective_property() -> None:
    with pytest.raises(ValueError, match="Objective property not found"):
        validate_screening_inputs(_screening_df(), _spec(property_name="missing"))


def test_validate_screening_inputs_rejects_identifier_objective() -> None:
    with pytest.raises(ValueError, match="not a numeric screening property"):
        validate_screening_inputs(_screening_df(), _spec(property_name="material_id"))


def test_validate_screening_spec_rejects_invalid_mode_and_weight() -> None:
    invalid_mode = _spec()
    invalid_mode["objectives"][0]["mode"] = "optimize"
    with pytest.raises(ValueError, match="Unsupported objective mode"):
        validate_screening_spec(invalid_mode)

    invalid_weight = _spec()
    invalid_weight["objectives"][0]["weight"] = 0
    with pytest.raises(ValueError, match="positive"):
        validate_screening_spec(invalid_weight)


def test_validate_screening_spec_rejects_credentials_and_absolute_paths() -> None:
    credential_spec = _spec()
    credential_spec["api_key"] = "do-not-store"
    with pytest.raises(ValueError, match="credential"):
        validate_screening_spec(credential_spec)

    path_spec = _spec()
    path_spec["notes"] = ["C:\\private\\screening.json"]
    with pytest.raises(ValueError, match="absolute paths"):
        validate_screening_spec(path_spec)


def test_apply_screening_filters_preserves_failed_rows() -> None:
    filtered = apply_screening_filters(_screening_df(), _spec())

    assert len(filtered) == 4
    assert bool(filtered.loc[2, "passes_filters"]) is False
    assert filtered.loc[2, "filter_status"] == "fail"


def test_minimize_ranking_places_lowest_value_first() -> None:
    ranked = rank_screening_candidates(_screening_df(), _spec("minimize", "hull"))

    assert ranked.iloc[0]["material_id"] == "m2"
    assert ranked.iloc[0]["overall_rank"] == 1
    assert ranked[ranked["material_id"].eq("m3")].iloc[0]["screening_status"] == "filter_failed"


def test_maximize_ranking_places_highest_value_first() -> None:
    ranked = rank_screening_candidates(_screening_df(), _spec("maximize", "gap"))

    assert ranked.iloc[0]["material_id"] == "m2"
    assert ranked.iloc[0]["gap_objective_rank"] == 1


def test_target_value_and_target_range_ranking() -> None:
    target_value = rank_screening_candidates(_screening_df(), _spec("target_value", "gap"))
    target_range = rank_screening_candidates(_screening_df(), _spec("target_range", "gap"))

    assert target_value.iloc[0]["material_id"] == "m1"
    assert target_range.iloc[0]["material_id"] == "m1"
    assert target_range.iloc[0]["gap_objective_score"] == 1.0


def test_missing_value_policy_and_constant_property_handling() -> None:
    missing_spec = _spec("maximize", "gap")
    ranked = rank_screening_candidates(_screening_df(), missing_spec)
    assert ranked[ranked["material_id"].eq("m4")].iloc[0]["screening_status"] == "missing_objective"

    score_missing_spec = _spec("maximize", "gap")
    score_missing_spec["missing_value_policy"] = "score_as_missing"
    score_missing = rank_screening_candidates(_screening_df(), score_missing_spec)
    assert score_missing[score_missing["material_id"].eq("m4")].iloc[0]["screening_status"] == "ranked"

    constant = rank_screening_candidates(_screening_df(), _spec("maximize", "density"))
    assert constant.loc[constant["screening_status"].eq("ranked"), "density_objective_score"].eq(1.0).all()


def test_tied_rank_and_deterministic_summary() -> None:
    df = _screening_df()
    df.loc[0, "hull"] = 0.0
    ranked = rank_screening_candidates(df, _spec("minimize", "hull"))
    summary = build_screening_summary(ranked, _spec("minimize", "hull"))

    assert ranked.iloc[0]["overall_rank"] == 1
    assert ranked.iloc[1]["overall_rank"] == 1
    assert summary["material_id"].tolist() == ["m1", "m2"]
    assert "limitation_flag" in summary.columns


def test_original_properties_are_preserved() -> None:
    ranked = rank_screening_candidates(_screening_df(), _spec("minimize", "hull"))

    assert {"gap", "hull", "density"}.issubset(ranked.columns)
    assert "composite_score" in ranked.columns
    assert "overall_rank" in ranked.columns
