from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from platform_core.battery_intelligence import import_nasa_pcoe_battery


def _write_battery_with_nonpositive_capacity(
    path: Path,
    *,
    capacity_value: float,
) -> None:
    operations: list[dict[str, object]] = []
    for cycle in range(1, 6):
        elapsed = np.linspace(0.0, 3600.0, 11)
        capacity = 2.0 - 0.05 * cycle
        if cycle == 3:
            capacity = capacity_value
        operations.append(
            {
                "type": "discharge",
                "ambient_temperature": 25.0,
                "time": np.array([2026, 1, cycle, 0, 0, 0], dtype=float),
                "data": {
                    "Voltage_measured": np.linspace(4.2, 3.0, 11),
                    "Current_measured": np.full(11, -1.0),
                    "Temperature_measured": np.linspace(25.0, 28.0, 11),
                    "Time": elapsed,
                    "Capacity": capacity,
                },
            }
        )
    savemat(path, {"B0042": {"cycle": np.array(operations, dtype=object)}})


@pytest.mark.parametrize("capacity_value", [0.0, -0.25])
def test_nonpositive_capacity_is_quarantined_without_renumbering(
    tmp_path: Path,
    capacity_value: float,
) -> None:
    source = tmp_path / "B0042.mat"
    _write_battery_with_nonpositive_capacity(
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
    assert manifest["nonpositive_capacity_operation_count"] == 1

    row = inventory.iloc[0]
    assert int(row["discharge_operation_count"]) == 5
    assert int(row["imported_discharge_operation_count"]) == 4
    assert int(row["excluded_discharge_operation_count"]) == 1
    assert int(row["nonpositive_capacity_operation_count"]) == 1

    warning = warnings[
        warnings["code"] == "nonpositive_discharge_capacity_excluded"
    ].iloc[0]
    assert warning["battery_id"] == "B0042"
    assert int(warning["cycle_index"]) == 3
    assert float(warning["observed_value"]) == pytest.approx(capacity_value)
    assert "No value was imputed or clipped" in warning["message"]

    policy = provenance["transformation"]["nonpositive_capacity_policy"]
    assert "excluded from canonical cycle-summary and raw-signal tables" in policy
    assert provenance["transformation"][
        "excluded_nonpositive_capacity_operation_count"
    ] == 1
