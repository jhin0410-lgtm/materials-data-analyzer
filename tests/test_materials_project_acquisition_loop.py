from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.materials_project_acquisition_loop import (
    MaterialsProjectAcquisitionError,
    compare_materials_project_acquisition_evaluations,
    evaluate_materials_project_acquisition_sequence,
    run_materials_project_acquisition_sequence,
)
from materials_data_analyzer.research_loop.materials_project_retrospective_benchmark import (
    build_materials_project_retrospective_benchmark,
)


def _source() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group_index in range(12):
        for replicate in range(3):
            rows.append(
                {
                    "material_id": f"mp-{group_index:02d}-{replicate}",
                    "energy_above_hull": 0.01 * group_index + 0.002 * replicate,
                    "chemical_system_group": f"Fe-Si-X{group_index:02d}",
                    "reduced_formula_group": f"F{group_index:02d}-{replicate}",
                    "feature_a": float(group_index),
                    "feature_b": float(replicate + group_index / 10),
                }
            )
    return pd.DataFrame(rows)


def _inventory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"column_name": "material_id", "primary_feature": False},
            {"column_name": "energy_above_hull", "primary_feature": False},
            {"column_name": "feature_a", "primary_feature": True},
            {"column_name": "feature_b", "primary_feature": True},
        ]
    )


def _benchmark_config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "benchmark_id": "fixture-materials-project-retrospective-v1",
        "dataset_version": "fixture-v1",
        "identifier_column": "material_id",
        "target_column": "energy_above_hull",
        "partition_group_column": "chemical_system_group",
        "required_disjoint_group_columns": [
            "chemical_system_group",
            "reduced_formula_group",
        ],
        "partition_fractions": {
            "seed_evidence": 0.25,
            "acquisition_pool": 0.5,
            "locked_test": 0.25,
        },
        "partition_salt": "fixture-stage4-acquisition-v1",
        "expected_source": {
            "row_count": 36,
            "primary_feature_count": 2,
        },
        "planner_visibility": {
            "seed_target_visible": True,
            "acquisition_target_visible": False,
            "locked_test_visible": False,
            "visible_columns": (
                "identifier + required disjoint groups + primary_feature=true columns"
            ),
        },
        "scientific_boundary": [
            "Target-blind partitioning only.",
            "Locked test is never planner-visible.",
        ],
    }


def _acquisition_config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "benchmark_id": "fixture-materials-project-retrospective-v1",
        "sequence_version": "1.0",
        "selection_unit": "chemical_system_group",
        "cost_definition": (
            "one cost unit per acquired material row; a selected chemical-system "
            "group reveals all rows in that group"
        ),
        "max_label_cost": 6,
        "random_seed": 42,
        "strategies": [
            "fixed_catalog",
            "random",
            "diversity",
            "uncertainty",
        ],
        "primary_evaluation_model": "ridge_raw",
        "evaluation_models": [
            "dummy_median",
            "ridge_raw",
            "ridge_log1p",
            "histogram_gradient_boosting_raw",
            "histogram_gradient_boosting_log1p",
        ],
        "acquisition_policy": {
            "whole_group_only": True,
            "target_visible_before_selection": False,
            "locked_test_visible_before_sequence_completion": False,
            "allow_budget_overshoot": False,
            "stop_when_no_remaining_group_fits_budget": True,
        },
        "strategy_contracts": {
            "fixed_catalog": "fixed",
            "random": "random",
            "diversity": "diversity",
            "uncertainty": "uncertainty",
        },
        "scientific_boundary": [
            "No acquisition target before selection.",
            "No locked test before sequence completion.",
        ],
    }


def _prepare(tmp_path: Path) -> dict[str, Path]:
    source_path = tmp_path / "source.csv"
    inventory_path = tmp_path / "inventory.csv"
    benchmark_config_path = tmp_path / "benchmark_config.json"
    acquisition_config_path = tmp_path / "acquisition_config.json"
    benchmark_dir = tmp_path / "benchmark"
    _source().to_csv(source_path, index=False)
    _inventory().to_csv(inventory_path, index=False)
    benchmark_config_path.write_text(
        json.dumps(_benchmark_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    acquisition_config_path.write_text(
        json.dumps(_acquisition_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = build_materials_project_retrospective_benchmark(
        input_path=source_path,
        inventory_path=inventory_path,
        config_path=benchmark_config_path,
        output_dir=benchmark_dir,
    )
    receipt = {
        "schema_version": "1.0",
        "benchmark_id": manifest["benchmark_id"],
        "dataset_version": manifest["dataset_version"],
        "source": manifest["source"],
        "descriptor_inventory": manifest["descriptor_inventory"],
        "benchmark_config": manifest["benchmark_config"],
        "partitions": {
            name: {
                "rows": values["rows"],
                "partition_group_count": values["partition_group_count"],
            }
            for name, values in manifest["partitions"].items()
        },
        "output_sha256": manifest["output_sha256"],
        "verified_execution": {
            "verification_result": "valid",
        },
        "scientific_boundary": ["fixture receipt"],
    }
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {
        "benchmark": benchmark_dir,
        "instance": instance_path,
        "benchmark_config": benchmark_config_path,
        "acquisition_config": acquisition_config_path,
    }


@pytest.mark.parametrize(
    "strategy",
    ["fixed_catalog", "random", "diversity", "uncertainty"],
)
def test_sequences_acquire_whole_groups_without_budget_overshoot(
    tmp_path: Path,
    strategy: str,
) -> None:
    paths = _prepare(tmp_path)
    output = tmp_path / strategy
    manifest = run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy=strategy,
        output_dir=output,
    )

    history = pd.read_csv(output / "acquisition_history.csv")
    training = pd.read_csv(output / "training_evidence.csv")
    seed = pd.read_csv(paths["benchmark"] / "planner" / "seed_evidence.csv")

    assert manifest["planner_boundary"]["locked_test_content_read"] is False
    assert manifest["counts"]["cost_used"] <= 6
    assert manifest["counts"]["acquired_rows"] == len(training) - len(seed)
    assert history["step_cost"].tolist() == [3, 3]
    assert history["cumulative_cost"].tolist() == [3, 6]
    acquired = training[~training["material_id"].isin(seed["material_id"])]
    assert acquired.groupby("chemical_system_group").size().tolist() == [3, 3]


def test_sequence_does_not_validate_or_read_locked_bytes(tmp_path: Path) -> None:
    paths = _prepare(tmp_path)
    locked = paths["benchmark"] / "locked" / "locked_test.csv"
    locked.write_text("deliberately tampered locked content\n", encoding="utf-8")

    manifest = run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy="fixed_catalog",
        output_dir=tmp_path / "sequence",
    )

    assert manifest["execution_status"] == "completed"
    assert manifest["planner_boundary"]["locked_test_content_read"] is False

    with pytest.raises(MaterialsProjectAcquisitionError, match="locked_test"):
        evaluate_materials_project_acquisition_sequence(
            benchmark_dir=paths["benchmark"],
            instance_path=paths["instance"],
            benchmark_config_path=paths["benchmark_config"],
            acquisition_config_path=paths["acquisition_config"],
            sequence_dir=tmp_path / "sequence",
            output_dir=tmp_path / "evaluation",
        )


def test_locked_evaluation_reports_seed_and_final_without_feedback(tmp_path: Path) -> None:
    paths = _prepare(tmp_path)
    sequence_dir = tmp_path / "sequence"
    evaluation_dir = tmp_path / "evaluation"
    run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy="diversity",
        output_dir=sequence_dir,
    )
    result = evaluate_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        sequence_dir=sequence_dir,
        output_dir=evaluation_dir,
    )

    metrics = pd.read_csv(evaluation_dir / "locked_metrics.csv")
    assert result["evaluation_status"] == "completed"
    assert result["locked_boundary"]["sequence_completed_before_locked_read"] is True
    assert result["locked_boundary"]["locked_metrics_not_available_to_sequence"] is True
    assert set(metrics["training_scope"]) == {"seed_only", "final_sequence"}
    assert set(metrics["model_variant"]) == set(_acquisition_config()["evaluation_models"])
    assert result["primary_model_result"]["model_variant"] == "ridge_raw"


def test_nonadaptive_history_is_independent_of_oracle_target_values(tmp_path: Path) -> None:
    paths = _prepare(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy="diversity",
        output_dir=first,
    )

    labels_path = paths["benchmark"] / "oracle" / "acquisition_labels.csv"
    labels = pd.read_csv(labels_path)
    labels["energy_above_hull"] = list(reversed(labels["energy_above_hull"].tolist()))
    labels.to_csv(labels_path, index=False)
    benchmark_manifest_path = paths["benchmark"] / "benchmark_manifest.json"
    benchmark_manifest = json.loads(benchmark_manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    benchmark_manifest["output_sha256"]["acquisition_labels"] = digest
    benchmark_manifest_path.write_text(
        json.dumps(benchmark_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = json.loads(paths["instance"].read_text(encoding="utf-8"))
    receipt["output_sha256"]["acquisition_labels"] = digest
    paths["instance"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy="diversity",
        output_dir=second,
    )

    first_history = pd.read_csv(first / "acquisition_history.csv")
    second_history = pd.read_csv(second / "acquisition_history.csv")
    assert first_history["selected_group"].tolist() == second_history["selected_group"].tolist()


def test_comparison_rejects_duplicate_strategy_evaluations(tmp_path: Path) -> None:
    paths = _prepare(tmp_path)
    sequence_dir = tmp_path / "sequence"
    evaluation_dir = tmp_path / "evaluation"
    run_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        strategy="random",
        output_dir=sequence_dir,
    )
    evaluate_materials_project_acquisition_sequence(
        benchmark_dir=paths["benchmark"],
        instance_path=paths["instance"],
        benchmark_config_path=paths["benchmark_config"],
        acquisition_config_path=paths["acquisition_config"],
        sequence_dir=sequence_dir,
        output_dir=evaluation_dir,
    )

    with pytest.raises(MaterialsProjectAcquisitionError, match="duplicate strategy"):
        compare_materials_project_acquisition_evaluations(
            evaluation_dirs=[evaluation_dir, evaluation_dir]
        )
