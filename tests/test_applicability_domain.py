"""Tests for generic applicability-domain diagnostics."""

from __future__ import annotations

import pandas as pd
import pytest

from analyzers.applicability_domain import (
    ApplicabilityConfig,
    build_applicability_diagnostics,
    fit_applicability_reference,
    summarize_distance_error_relationship,
    summarize_error_by_stratum,
)


def _train_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "material_id": ["a", "b", "c", "d"],
            "x1": [0.0, 0.0, 1.0, 1.0],
            "x2": [0.0, 1.0, 0.0, 1.0],
            "target": [0.0, 100.0, 200.0, 300.0],
        }
    )


def test_reference_excludes_self_neighbor_and_uses_fixed_percentiles() -> None:
    config = ApplicabilityConfig(["x1", "x2"], "material_id", k_neighbors=2)

    reference = fit_applicability_reference(_train_df(), config)

    assert reference.train_nn_distance_count == 4
    assert all(distance > 0 for distance in reference.train_nn_distances)
    assert reference.in_domain_threshold <= reference.out_of_domain_threshold


def test_domain_status_is_target_independent() -> None:
    config = ApplicabilityConfig(["x1", "x2"], "material_id", k_neighbors=2)
    test = pd.DataFrame(
        {
            "material_id": ["same", "far"],
            "x1": [0.0, 9.0],
            "x2": [0.0, 9.0],
            "target": [999.0, -999.0],
        }
    )

    first, _ = build_applicability_diagnostics(_train_df(), test, config)
    test["target"] = [-999.0, 999.0]
    second, _ = build_applicability_diagnostics(_train_df(), test, config)

    assert first["applicability_status"].tolist() == second["applicability_status"].tolist()
    assert first.loc[first["material_id"].eq("same"), "descriptor_seen_in_train"].item() is True
    assert first.loc[first["material_id"].eq("far"), "applicability_status"].item() == "out_of_domain"


def test_small_train_reference_is_unclassified_not_crashing() -> None:
    config = ApplicabilityConfig(["x1"], "material_id", k_neighbors=5)
    train = pd.DataFrame({"material_id": ["a"], "x1": [1.0]})
    test = pd.DataFrame({"material_id": ["b"], "x1": [2.0]})

    diagnostics, reference = build_applicability_diagnostics(train, test, config)

    assert reference["train_nn_distance_count"] == 0
    assert diagnostics["applicability_status"].tolist() == ["unclassified_small_train"]


def test_error_and_distance_summaries_handle_strata() -> None:
    df = pd.DataFrame(
        {
            "split_strategy": ["random", "random", "random"],
            "model_variant": ["ridge", "ridge", "ridge"],
            "applicability_status": ["in_domain", "boundary", "out_of_domain"],
            "actual_target": [0.0, 1.0, 2.0],
            "prediction": [0.1, 1.2, 3.0],
            "absolute_error": [0.1, 0.2, 1.0],
            "nearest_train_distance": [0.2, 0.5, 1.5],
            "negative_prediction": [False, False, False],
        }
    )

    error = summarize_error_by_stratum(
        df,
        stratum_type="domain_distance",
        stratum_column="applicability_status",
    )
    relationship = summarize_distance_error_relationship(df)

    assert set(error["stratum_value"]) == {"in_domain", "boundary", "out_of_domain"}
    assert "nearest_distance_absolute_error_spearman" in relationship.columns
    assert relationship["interpretation"].notna().all()


def test_missing_feature_column_raises_clear_error() -> None:
    config = ApplicabilityConfig(["missing"], "material_id")

    with pytest.raises(ValueError, match="Missing feature"):
        fit_applicability_reference(_train_df(), config)
