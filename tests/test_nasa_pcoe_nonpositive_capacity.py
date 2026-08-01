from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from platform_core.battery_intelligence import import_nasa_pcoe_battery


_MISSING = object()


def _write_battery_with_invalid_capacity(
    path: Path,
    *,
    capacity_value: Any,
) -> None:
    operations: list[dict[str, object]] = []
    for cycle in range(1, 6):
        elapsed = np.linspace(0.0, 3600.0, 11)
        data: dict[str, object] = {
            "Voltage_measured": np.linspace(4.2, 3.0, 11),
            "Current_measured": np.full(11, -1.0),
            "Temperature_measured": np.linspace(25.0, 28.0, 11),
            "Time": elapsed,
            "Capacity": 2.0 - 0.05 * cycle,
        }
        if cycle == 3:
            if capacity_value is _MISSING:
                data.pop("Capacity")
            else:
                data["Capacity"] = capacity_value
        operations.append(
            {
                "type": "discharge",
                "ambient_temperature": 25.0,
                "time": np.array([2026, 1, cycle, 0, 0, 0], dtype=float),
                "data": data,
            }
        )
    savemat(path, {"B0050": {"cycle": np.array(operations, dtype=object)}})


@pytest.mark.parametrize(
    ("capacity_value", "expected_issue"),
    [
        (0.0, "nonpositive"),
        (-0.25, "nonpositive"),
        (np.nan, "nonfinite"),
        (np.inf, "nonfinite"),
        (np.array([1.0, 2.0]), "nonscalar"),
        (1.0 + 2.0j, "complex"),
        ("not-a-number", "nonnumeric"),
        (_MISSING, "missing"),
    ],
)
def test_invalid_capacity_is_quarantined_without_renumbering(
    tmp_path: Path,
    capacity_value: Any,
    expected_issue: str,
) -> None:
    source = tmp_path / "B0050.mat"
    _write_battery_with_invalid_capacity(
        source,
        capacity_value=capacity_value,
    )
    output = tmp_path / "imported"

    manifest = import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    cycle_summary = pd.read_csv(output / "nasa_pcoe_cycle_summary.csv")
    raw_signal = pd.read_csv(output / "nasa_pcoe_raw_signal.csv")
    inventory = pd.read_csv(output / "nasa_pcoe_source_inventory.csv")
    warnings = pd.read_csv(output / "nasa_pcoe_import_warnings.csv")
    excluded = pd.read_csv(output / "nasa_pcoe_excluded_operations.csv")
    provenance = json.loads(
        (output / "nasa_pcoe_raw_signal_provenance.json").read_text(
            encoding="utf-8"
        )
    )

    assert cycle_summary["cycle_index"].tolist() == [1, 2, 4, 5]
    assert sorted(raw_signal["cycle_index"].unique().tolist()) == [1, 2, 4, 5]
    assert cycle_summary["discharge_capacity_ah"].gt(0).all()
    assert manifest["discharge_cycle_count"] == 4
    assert manifest["imported_discharge_operation_count"] == 4
    assert manifest["excluded_discharge_operation_count"] == 1
    assert manifest["invalid_capacity_operation_count"] == 1
    assert manifest[f"{expected_issue}_capacity_operation_count"] == 1
    assert manifest["excluded_operation_artifact_count"] == 1
    assert "excluded_operations" in manifest["outputs"]
    assert "excluded_operations" in manifest["output_sha256"]

    row = inventory.iloc[0]
    assert int(row["discharge_operation_count"]) == 5
    assert int(row["imported_discharge_operation_count"]) == 4
    assert int(row["excluded_discharge_operation_count"]) == 1
    assert int(row["invalid_capacity_operation_count"]) == 1
    assert int(row[f"{expected_issue}_capacity_operation_count"]) == 1

    warning = warnings[
        warnings["code"] == "invalid_discharge_capacity_excluded"
    ].iloc[0]
    assert warning["battery_id"] == "B0050"
    assert int(warning["cycle_index"]) == 3
    assert warning["capacity_issue"] == expected_issue
    assert expected_issue in str(warning["observed_value"])
    assert "No value was imputed" in warning["message"]

    excluded_row = excluded.iloc[0]
    assert excluded_row["battery_id"] == "B0050"
    assert int(excluded_row["cycle_index"]) == 3
    assert excluded_row["capacity_issue"] == expected_issue

    policy = provenance["transformation"]["invalid_capacity_policy"]
    assert (
        "missing, nonnumeric, non-scalar, complex-valued, non-finite, zero, or negative"
        in policy
    )
    assert provenance["transformation"][
        "excluded_invalid_capacity_operation_count"
    ] == 1
    assert provenance["transformation"]["invalid_capacity_counts_by_reason"][
        expected_issue
    ] == 1


def test_valid_capacity_import_has_empty_exclusion_artifact(tmp_path: Path) -> None:
    source = tmp_path / "B0050.mat"
    _write_battery_with_invalid_capacity(source, capacity_value=1.75)
    output = tmp_path / "imported"

    manifest = import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    excluded = pd.read_csv(output / "nasa_pcoe_excluded_operations.csv")
    assert excluded.empty
    assert manifest["invalid_capacity_operation_count"] == 0
    assert manifest["excluded_operation_artifact_count"] == 0


def test_identical_duplicate_source_does_not_duplicate_exclusion_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "B0050.mat"
    _write_battery_with_invalid_capacity(source, capacity_value=np.nan)
    archive_path = tmp_path / "duplicates.zip"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.write(source, arcname="bundle_a/B0050.mat")
        archive.write(source, arcname="bundle_b/B0050.mat")

    output = tmp_path / "imported"
    manifest = import_nasa_pcoe_battery(
        input_path=archive_path,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    excluded = pd.read_csv(output / "nasa_pcoe_excluded_operations.csv")
    inventory = pd.read_csv(output / "nasa_pcoe_source_inventory.csv")
    assert len(excluded) == 1
    assert manifest["invalid_capacity_operation_count"] == 1
    assert manifest["excluded_operation_artifact_count"] == 1
    assert manifest["identical_duplicate_copy_count"] == 1
    assert (
        inventory["skip_reason"].fillna("").eq(
            "duplicate_identical_source_copy"
        ).sum()
        == 1
    )


def _write_all_invalid_battery(
    path: Path,
    *,
    capacity_value: Any,
    current_a: float,
) -> None:
    operations: list[dict[str, object]] = []
    for cycle in range(1, 4):
        elapsed = np.linspace(0.0, 3600.0, 11)
        operations.append(
            {
                "type": "discharge",
                "ambient_temperature": 25.0,
                "time": np.array([2026, 1, cycle, 0, 0, 0], dtype=float),
                "data": {
                    "Voltage_measured": np.linspace(4.2, 3.0, 11),
                    "Current_measured": np.full(11, current_a),
                    "Temperature_measured": np.linspace(25.0, 28.0, 11),
                    "Time": elapsed,
                    "Capacity": capacity_value,
                },
            }
        )
    savemat(path, {"B0050": {"cycle": np.array(operations, dtype=object)}})


def test_all_invalid_source_still_participates_in_identity_conflict_check(
    tmp_path: Path,
) -> None:
    first = tmp_path / "a" / "B0050.mat"
    second = tmp_path / "b" / "B0050.mat"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_all_invalid_battery(first, capacity_value=np.nan, current_a=-1.0)
    _write_all_invalid_battery(second, capacity_value=np.inf, current_a=-1.1)

    with pytest.raises(ValueError, match="different MAT checksums"):
        import_nasa_pcoe_battery(
            input_path=tmp_path,
            output_dir=tmp_path / "imported",
            retrieved_at="2026-08-01T00:00:00Z",
        )
