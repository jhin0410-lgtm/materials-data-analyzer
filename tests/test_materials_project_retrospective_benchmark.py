from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.materials_project_retrospective_benchmark import (
    MaterialsProjectBenchmarkError,
    build_materials_project_retrospective_benchmark,
    verify_materials_project_retrospective_benchmark,
)


def _source() -> pd.DataFrame:
    rows = []
    for group_index in range(8):
        chemical_system = f"Fe-Si-X{group_index}"
        for replicate in range(2):
            rows.append(
                {
                    "material_id": f"mp-{group_index:02d}-{replicate}",
                    "energy_above_hull": 0.01 * (group_index + replicate),
                    "chemical_system_group": chemical_system,
                    "reduced_formula_group": f"F{group_index}_{replicate}",
                    "feature_a": float(group_index),
                    "feature_b": float(replicate + 1),
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


def _config(row_count: int = 16) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "benchmark_id": "test-materials-project-retrospective-v1",
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
        "partition_salt": "fixture-stage4-v1",
        "expected_source": {
            "row_count": row_count,
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


def _write_inputs(
    tmp_path: Path,
    *,
    source: pd.DataFrame | None = None,
) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_path = tmp_path / "source.csv"
    inventory_path = tmp_path / "inventory.csv"
    config_path = tmp_path / "config.json"
    (source if source is not None else _source()).to_csv(source_path, index=False)
    _inventory().to_csv(inventory_path, index=False)
    config_path.write_text(json.dumps(_config(), indent=2) + "\n", encoding="utf-8")
    return source_path, inventory_path, config_path


def test_build_and_verify_keep_oracle_and_locked_targets_out_of_planner(
    tmp_path: Path,
) -> None:
    source_path, inventory_path, config_path = _write_inputs(tmp_path)
    output = tmp_path / "benchmark"

    manifest = build_materials_project_retrospective_benchmark(
        input_path=source_path,
        inventory_path=inventory_path,
        config_path=config_path,
        output_dir=output,
    )
    verified = verify_materials_project_retrospective_benchmark(
        benchmark_dir=output,
        input_path=source_path,
        inventory_path=inventory_path,
        config_path=config_path,
    )

    acquisition = pd.read_csv(output / "planner" / "acquisition_catalog.csv")
    seed = pd.read_csv(output / "planner" / "seed_evidence.csv")
    locked = pd.read_csv(output / "locked" / "locked_test.csv")
    membership = pd.read_csv(output / "oracle" / "partition_membership.csv")

    assert manifest["execution_status"] == "partition_locked"
    assert manifest["scientific_evidence_created"] is False
    assert verified["valid"] is True
    assert "energy_above_hull" not in acquisition.columns
    assert "energy_above_hull" in seed.columns
    assert "energy_above_hull" in locked.columns
    assert set(membership["benchmark_partition"]) == {
        "seed_evidence",
        "acquisition_pool",
        "locked_test",
    }
    chemical_overlap = membership.groupby("chemical_system_group")[
        "benchmark_partition"
    ].nunique()
    formula_overlap = membership.groupby("reduced_formula_group")[
        "benchmark_partition"
    ].nunique()
    assert chemical_overlap.max() == 1
    assert formula_overlap.max() == 1


def test_partition_membership_is_target_blind(tmp_path: Path) -> None:
    original = _source()
    changed = original.copy()
    changed["energy_above_hull"] = list(reversed(range(len(changed))))

    source_a, inventory_a, config_a = _write_inputs(tmp_path / "a", source=original)
    source_b, inventory_b, config_b = _write_inputs(tmp_path / "b", source=changed)
    output_a = tmp_path / "benchmark-a"
    output_b = tmp_path / "benchmark-b"

    build_materials_project_retrospective_benchmark(
        input_path=source_a,
        inventory_path=inventory_a,
        config_path=config_a,
        output_dir=output_a,
    )
    build_materials_project_retrospective_benchmark(
        input_path=source_b,
        inventory_path=inventory_b,
        config_path=config_b,
        output_dir=output_b,
    )

    membership_a = pd.read_csv(output_a / "oracle" / "partition_membership.csv")
    membership_b = pd.read_csv(output_b / "oracle" / "partition_membership.csv")
    pd.testing.assert_frame_equal(membership_a, membership_b)


def test_duplicate_material_id_fails_closed(tmp_path: Path) -> None:
    source = _source()
    source.loc[1, "material_id"] = source.loc[0, "material_id"]
    source_path, inventory_path, config_path = _write_inputs(tmp_path, source=source)

    with pytest.raises(MaterialsProjectBenchmarkError, match="identifiers must be unique"):
        build_materials_project_retrospective_benchmark(
            input_path=source_path,
            inventory_path=inventory_path,
            config_path=config_path,
            output_dir=tmp_path / "benchmark",
        )


def test_primary_target_feature_fails_closed(tmp_path: Path) -> None:
    source_path, inventory_path, config_path = _write_inputs(tmp_path)
    inventory = pd.read_csv(inventory_path)
    inventory.loc[
        inventory["column_name"].eq("energy_above_hull"), "primary_feature"
    ] = True
    inventory.to_csv(inventory_path, index=False)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["expected_source"]["primary_feature_count"] = 3
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(MaterialsProjectBenchmarkError, match="marked as primary feature"):
        build_materials_project_retrospective_benchmark(
            input_path=source_path,
            inventory_path=inventory_path,
            config_path=config_path,
            output_dir=tmp_path / "benchmark",
        )


def test_verifier_rejects_tampered_planner_catalog(tmp_path: Path) -> None:
    source_path, inventory_path, config_path = _write_inputs(tmp_path)
    output = tmp_path / "benchmark"
    build_materials_project_retrospective_benchmark(
        input_path=source_path,
        inventory_path=inventory_path,
        config_path=config_path,
        output_dir=output,
    )
    catalog = output / "planner" / "acquisition_catalog.csv"
    catalog.write_text(
        catalog.read_text(encoding="utf-8") + "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(MaterialsProjectBenchmarkError, match="checksum mismatch"):
        verify_materials_project_retrospective_benchmark(
            benchmark_dir=output,
            input_path=source_path,
            inventory_path=inventory_path,
            config_path=config_path,
        )
