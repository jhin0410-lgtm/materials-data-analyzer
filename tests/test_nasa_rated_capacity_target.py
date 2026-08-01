from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from platform_core.battery_intelligence import import_nasa_pcoe_battery


def _write_partial_first_discharge(path: Path) -> None:
    capacities = [0.1, 2.0, 1.9, 1.8, 1.7, 1.6]
    operations: list[dict[str, object]] = []
    for cycle, capacity in enumerate(capacities, start=1):
        elapsed = np.linspace(0.0, 3600.0, 21)
        operations.append(
            {
                "type": "discharge",
                "ambient_temperature": 24.0,
                "time": np.array([2026, 1, cycle, 0, 0, 0], dtype=float),
                "data": {
                    "Voltage_measured": np.linspace(4.2, 3.0, 21),
                    "Current_measured": np.full(21, -1.0),
                    "Temperature_measured": np.linspace(24.0, 27.0, 21),
                    "Time": elapsed,
                    "Capacity": capacity,
                },
            }
        )
    savemat(path, {"B0033": {"cycle": np.array(operations, dtype=object)}})


def test_nasa_import_uses_documented_two_ah_rating_not_first_discharge(
    tmp_path: Path,
) -> None:
    source = tmp_path / "B0033.mat"
    _write_partial_first_discharge(source)
    output = tmp_path / "imported"

    manifest = import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    cycles = pd.read_csv(output / "nasa_pcoe_cycle_summary.csv")
    assert cycles["discharge_capacity_ah"].tolist() == pytest.approx(
        [0.1, 2.0, 1.9, 1.8, 1.7, 1.6]
    )
    assert cycles["reference_capacity_ah"].eq(2.0).all()
    assert cycles["reference_capacity_method"].eq(
        "source_rated_capacity_2_ah"
    ).all()
    assert cycles["capacity_retention_percent"].tolist() == pytest.approx(
        [5.0, 100.0, 95.0, 90.0, 85.0, 80.0]
    )
    assert manifest["target_reference"]["rated_capacity_ah"] == 2.0
    assert (
        manifest["target_reference"]["first_observed_capacity_used_as_reference"]
        is False
    )

    protocol = pd.read_csv(output / "nasa_pcoe_protocol_summary.csv")
    assert protocol.loc[0, "rated_capacity_ah"] == 2.0
    assert protocol.loc[0, "maximum_capacity_retention_percent"] == 100.0
    assert protocol.loc[0, "initial_discharge_capacity_fraction_of_rated"] == (
        pytest.approx(0.05)
    )

    provenance = json.loads(
        (output / "nasa_pcoe_raw_signal_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    transformation = provenance["transformation"]
    assert transformation["source_rated_capacity_ah"] == 2.0
    assert transformation["first_observed_capacity_used_as_reference"] is False
