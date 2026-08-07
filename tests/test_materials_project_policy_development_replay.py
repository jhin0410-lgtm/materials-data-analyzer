from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.materials_project_policy_development_replay import (
    MaterialsProjectPolicyReplayError,
    _partition_frame,
    _partition_map,
    run_materials_project_policy_development_replay,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    benchmark = tmp_path / "benchmark"
    planner = benchmark / "planner"
    oracle = benchmark / "oracle"
    planner.mkdir(parents=True)
    oracle.mkdir(parents=True)

    rows = []
    for group_index in range(15):
        chemical = f"A{group_index}-B{group_index}"
        for member in range(2):
            rows.append(
                {
                    "material_id": f"m{group_index:02d}_{member}",
                    "chemical_system_group": chemical,
                    "reduced_formula_group": f"F{group_index}_{member}",
                    "f1": float(group_index + member / 10),
                    "f2": float((group_index % 4) - member / 10),
                    "energy_above_hull": float((group_index % 5) / 20 + member / 100),
                }
            )
    full = pd.DataFrame(rows)
    seed = full.iloc[:6].copy()
    acquisition = full.iloc[6:].copy()
    catalog = acquisition.drop(columns=["energy_above_hull"])
    labels = acquisition[["material_id", "energy_above_hull"]]

    seed_path = planner / "seed_evidence.csv"
    catalog_path = planner / "acquisition_catalog.csv"
    labels_path = oracle / "acquisition_labels.csv"
    _write_csv(seed_path, seed)
    _write_csv(catalog_path, catalog)
    _write_csv(labels_path, labels)

    # Intentionally do not create the locked-test file. The replay must not require it.
    manifest = {
        "benchmark_id": "fixture-benchmark",
        "outputs": {
            "seed_evidence": "planner/seed_evidence.csv",
            "acquisition_catalog": "planner/acquisition_catalog.csv",
            "acquisition_labels": "oracle/acquisition_labels.csv",
            "locked_test": "locked/DO_NOT_READ.csv",
        },
        "output_sha256": {
            "seed_evidence": _sha(seed_path),
            "acquisition_catalog": _sha(catalog_path),
            "acquisition_labels": _sha(labels_path),
            "locked_test": "0" * 64,
        },
    }
    (benchmark / "benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    benchmark_config = tmp_path / "benchmark_config.json"
    benchmark_config.write_text(
        json.dumps(
            {
                "benchmark_id": "fixture-benchmark",
                "identifier_column": "material_id",
                "target_column": "energy_above_hull",
                "partition_group_column": "chemical_system_group",
                "required_disjoint_group_columns": [
                    "chemical_system_group",
                    "reduced_formula_group",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    replay_config = tmp_path / "replay.json"
    replay_config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "replay_id": "fixture-replay",
                "source_benchmark_id": "fixture-benchmark",
                "development_source": {
                    "allowed_partitions": ["seed_evidence", "acquisition_pool"],
                    "expected_rows": 30,
                    "locked_test_read_authorized": False,
                },
                "partition_group_column": "chemical_system_group",
                "required_disjoint_group_columns": [
                    "chemical_system_group",
                    "reduced_formula_group",
                ],
                "partition_fractions": {
                    "development_seed": 0.2,
                    "development_pool": 0.6,
                    "development_validation": 0.2,
                },
                "replay_salts": ["fixture-a", "fixture-b"],
                "max_label_cost": 4,
                "random_seeds": [1, 2],
                "fixed_strategy_seed": 42,
                "strategies": ["fixed_catalog", "random", "diversity", "uncertainty"],
                "evaluation_models": ["dummy_median", "ridge_raw"],
                "development_questions": ["Does policy behavior repeat?"],
                "scientific_boundary": [
                    "The benchmark-v1 locked-test file and targets must not be read by this replay."
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return benchmark, benchmark_config, replay_config


def test_replay_succeeds_without_locked_test_file(tmp_path: Path) -> None:
    benchmark, benchmark_config, replay_config = _fixture(tmp_path)
    output = tmp_path / "out"
    result = run_materials_project_policy_development_replay(
        benchmark_dir=benchmark,
        benchmark_config_path=benchmark_config,
        replay_config_path=replay_config,
        output_dir=output,
    )
    assert result["execution_status"] == "development_replay_completed"
    assert result["benchmark_v1_locked_test_read"] is False
    manifest = json.loads((output / "development_replay_manifest.json").read_text())
    assert manifest["development_source"]["locked_test_read"] is False
    assert manifest["development_source"]["locked_test_target_used"] is False
    results = pd.read_csv(output / "sequence_model_results.csv")
    # two replays * (fixed + diversity + uncertainty + two random seeds) * two models
    assert len(results) == 2 * 5 * 2
    assert set(results["strategy"]) == {"fixed_catalog", "random", "diversity", "uncertainty"}


def test_partition_is_target_blind_and_group_disjoint(tmp_path: Path) -> None:
    benchmark, _, _ = _fixture(tmp_path)
    seed = pd.read_csv(benchmark / "planner" / "seed_evidence.csv")
    catalog = pd.read_csv(benchmark / "planner" / "acquisition_catalog.csv")
    labels = pd.read_csv(benchmark / "oracle" / "acquisition_labels.csv")
    development = pd.concat(
        [seed, catalog.merge(labels, on="material_id", validate="one_to_one")],
        ignore_index=True,
    )
    fractions = {
        "development_seed": 0.2,
        "development_pool": 0.6,
        "development_validation": 0.2,
    }
    assignment_a = _partition_map(
        development,
        group_column="chemical_system_group",
        fractions=fractions,
        salt="same-salt",
    )
    changed_target = development.copy()
    changed_target["energy_above_hull"] = changed_target["energy_above_hull"] * 1000 + 17
    assignment_b = _partition_map(
        changed_target,
        group_column="chemical_system_group",
        fractions=fractions,
        salt="same-salt",
    )
    assert assignment_a == assignment_b
    partitions = _partition_frame(
        development,
        assignment=assignment_a,
        group_column="chemical_system_group",
        required_groups=["chemical_system_group", "reduced_formula_group"],
    )
    observed = {}
    for name, frame in partitions.items():
        for group in frame["chemical_system_group"].astype(str).unique():
            observed.setdefault(group, set()).add(name)
    assert all(len(names) == 1 for names in observed.values())


def test_locked_test_authorization_is_rejected(tmp_path: Path) -> None:
    benchmark, benchmark_config, replay_config = _fixture(tmp_path)
    payload = json.loads(replay_config.read_text())
    payload["development_source"]["locked_test_read_authorized"] = True
    replay_config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(MaterialsProjectPolicyReplayError, match="locked-test access"):
        run_materials_project_policy_development_replay(
            benchmark_dir=benchmark,
            benchmark_config_path=benchmark_config,
            replay_config_path=replay_config,
            output_dir=tmp_path / "out",
        )
