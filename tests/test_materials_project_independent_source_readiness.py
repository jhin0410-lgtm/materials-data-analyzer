from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.materials_project_independent_source_readiness import (
    MaterialsProjectIndependentSourceReadinessError,
    run_materials_project_independent_source_readiness,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs/research/materials_project_independent_source_readiness.v1.json"
BENCHMARK_CONFIG_PATH = REPO_ROOT / "configs/research/materials_project_retrospective_benchmark.v1.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_benchmark(tmp_path: Path) -> Path:
    benchmark = tmp_path / "benchmark"
    membership_path = benchmark / "oracle/partition_membership.csv"
    membership_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    partition_sizes = {
        "seed_evidence": 168,
        "acquisition_pool": 503,
        "locked_test": 167,
    }
    index = 0
    for partition, count in partition_sizes.items():
        for _ in range(count):
            rows.append(
                {
                    "material_id": f"mp-old-{index:04d}",
                    "chemical_system_group": f"Fe-Si-X{index % 37}",
                    "reduced_formula_group": f"formula-{index:04d}",
                    "benchmark_partition": partition,
                }
            )
            index += 1
    membership = pd.DataFrame(rows)
    membership.to_csv(membership_path, index=False, lineterminator="\n")

    manifest = {
        "schema_version": "1.0",
        "benchmark_id": "materials-project-v1-3-retrospective-closed-loop-v1",
        "execution_status": "partition_locked",
        "benchmark_config": {
            "filename": BENCHMARK_CONFIG_PATH.name,
            "sha256": _sha256(BENCHMARK_CONFIG_PATH),
        },
        "outputs": {
            "seed_evidence": "planner/seed_evidence.csv",
            "acquisition_catalog": "planner/acquisition_catalog.csv",
            "acquisition_labels": "oracle/acquisition_labels.csv",
            "partition_membership": "oracle/partition_membership.csv",
            "locked_test": "locked/locked_test.csv",
        },
        "output_sha256": {
            "partition_membership": _sha256(membership_path),
        },
        "partitions": {
            name: {"rows": count}
            for name, count in partition_sizes.items()
        },
    }
    (benchmark / "benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Deliberately do not create locked/locked_test.csv. The readiness audit
    # must succeed without opening or resolving the locked file.
    return benchmark


class _Summary:
    def __init__(self, docs: list[dict[str, object]], calls: list[dict[str, object]]):
        self.docs = docs
        self.calls = calls

    def search(self, **kwargs):
        self.calls.append(dict(kwargs))
        return list(self.docs)


class _Client:
    def __init__(
        self,
        *,
        version: str,
        docs: list[dict[str, object]],
        calls: list[dict[str, object]],
    ):
        self.db_version = version
        self.materials = SimpleNamespace(summary=_Summary(docs, calls))
        self.closed = False

    def close(self):
        self.closed = True


def _docs() -> list[dict[str, object]]:
    return [
        {
            "material_id": "mp-old-0000",
            "formula_pretty": "FeSi",
            "chemsys": "Fe-Si",
            "elements": ["Fe", "Si"],
            "nelements": 2,
            "deprecated": False,
        },
        {
            "material_id": "mp-old-0001",
            "formula_pretty": "Fe2Si",
            "chemsys": "Fe-Si",
            "elements": ["Fe", "Si"],
            "nelements": 2,
            "deprecated": False,
        },
        {
            "material_id": "mp-new-0001",
            "formula_pretty": "FeSiO3",
            "chemsys": "Fe-O-Si",
            "elements": ["Fe", "Si", "O"],
            "nelements": 3,
            "deprecated": False,
        },
        {
            "material_id": "mp-new-0002",
            "formula_pretty": "FeSiAl",
            "chemsys": "Al-Fe-Si",
            "elements": ["Al", "Fe", "Si"],
            "nelements": 3,
            "deprecated": False,
        },
    ]


def _factory(versions: list[str], docs: list[dict[str, object]], calls: list[dict[str, object]]):
    queue = list(versions)

    def make_client():
        if not queue:
            raise AssertionError("unexpected extra Materials Project client creation")
        return _Client(version=queue.pop(0), docs=docs, calls=calls)

    return make_client


def test_readiness_uses_identity_only_and_excludes_original_ids(tmp_path: Path):
    benchmark = _write_benchmark(tmp_path)
    calls: list[dict[str, object]] = []
    output = tmp_path / "readiness"

    result = run_materials_project_independent_source_readiness(
        config_path=CONFIG_PATH,
        benchmark_dir=benchmark,
        output_dir=output,
        client_factory=_factory(["2026_08_01", "2026_08_01"], _docs(), calls),
        validate_signature=False,
    )

    assert result["execution_status"] == "same_source_identity_inventory_completed"
    assert result["source_outcome"] == "new_same_source_identity_cohort_available"
    assert result["materials_project_database_version"] == "2026_08_01"
    assert result["cohort_independence"]["same_source_system"] is True
    assert result["cohort_independence"]["material_id_disjoint_from_original_benchmark"] is True
    assert result["cohort_independence"]["source_independence_established"] is False
    assert result["cohort_independence"]["external_validation_ready"] is False
    assert result["original_benchmark"]["rows"] == 838
    assert result["original_benchmark"]["locked_test_file_read"] is False
    assert result["original_benchmark"]["locked_target_read"] is False
    assert result["current_identity_query"]["target_property_queried"] is False
    assert result["current_identity_query"]["policy_executed"] is False
    assert result["current_identity_query"]["model_fit"] is False
    assert result["overlap"]["original_ids_still_present"] == 2
    assert result["overlap"]["new_material_ids_after_original_exclusion"] == 2
    assert result["independent_candidate_inventory"]["rows"] == 2
    assert result["independent_candidate_inventory"]["meaning"] == (
        "ID-disjoint same-source candidate cohort"
    )
    assert result["policy_v2_freeze_authorized"] is False
    assert result["independent_benchmark_execution_authorized"] is False

    candidate = pd.read_csv(output / "independent_candidate_identity.csv")
    assert candidate["material_id"].tolist() == ["mp-new-0001", "mp-new-0002"]
    assert "energy_above_hull" not in candidate.columns
    assert len(calls) == 1
    assert calls[0]["elements"] == ["Fe", "Si"]
    assert tuple(calls[0]["num_elements"]) == (2, 5)
    assert calls[0]["deprecated"] is False
    assert calls[0]["include_gnome"] is False
    assert "energy_above_hull" not in calls[0]["fields"]
    assert "is_stable" not in calls[0]["fields"]


def test_readiness_fails_closed_on_database_version_drift(tmp_path: Path):
    benchmark = _write_benchmark(tmp_path)
    with pytest.raises(
        MaterialsProjectIndependentSourceReadinessError,
        match="database version changed",
    ):
        run_materials_project_independent_source_readiness(
            config_path=CONFIG_PATH,
            benchmark_dir=benchmark,
            output_dir=tmp_path / "readiness",
            client_factory=_factory(["2026_08_01", "2026_08_02"], _docs(), []),
            validate_signature=False,
        )
    assert not (tmp_path / "readiness").exists()


def test_target_field_cannot_be_authorized_for_identity_query(tmp_path: Path):
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["identity_fields"].append("energy_above_hull")
    bad_config = tmp_path / "bad_config.json"
    bad_config.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(
        MaterialsProjectIndependentSourceReadinessError,
        match="target or target-derived fields",
    ):
        run_materials_project_independent_source_readiness(
            config_path=bad_config,
            benchmark_dir=_write_benchmark(tmp_path),
            output_dir=tmp_path / "readiness",
            client_factory=_factory(["v", "v"], _docs(), []),
            validate_signature=False,
        )


def test_scope_drift_is_rejected_before_output(tmp_path: Path):
    benchmark = _write_benchmark(tmp_path)
    docs = _docs()
    docs[-1] = dict(docs[-1])
    docs[-1]["elements"] = ["Fe", "Al"]

    with pytest.raises(
        MaterialsProjectIndependentSourceReadinessError,
        match="outside Fe/Si scope",
    ):
        run_materials_project_independent_source_readiness(
            config_path=CONFIG_PATH,
            benchmark_dir=benchmark,
            output_dir=tmp_path / "readiness",
            client_factory=_factory(["v", "v"], docs, []),
            validate_signature=False,
        )
    assert not (tmp_path / "readiness").exists()
