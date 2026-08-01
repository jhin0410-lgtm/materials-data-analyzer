from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import savemat

from platform_core.battery_intelligence import import_nasa_pcoe_battery


def test_nasa_source_timestamp_does_not_invent_timezone(tmp_path: Path) -> None:
    source = tmp_path / "B0005.mat"
    elapsed = np.array([0.0, 10.0, 20.0])
    savemat(
        source,
        {
            "B0005": {
                "cycle": np.array(
                    [
                        {
                            "type": "discharge",
                            "ambient_temperature": 24.0,
                            "time": np.array([2008, 4, 1, 12, 30, 0], dtype=float),
                            "data": {
                                "Voltage_measured": np.array([4.2, 4.0, 3.8]),
                                "Current_measured": np.array([-1.0, -1.0, -1.0]),
                                "Temperature_measured": np.array([24.0, 25.0, 26.0]),
                                "Time": elapsed,
                                "Capacity": 1.9,
                            },
                        }
                    ],
                    dtype=object,
                )
            }
        },
    )
    output = tmp_path / "output"
    import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    cycle_summary = pd.read_csv(output / "nasa_pcoe_cycle_summary.csv")
    assert "operation_started_at_source_time" in cycle_summary.columns
    assert "operation_started_at_utc" not in cycle_summary.columns
    timestamp = cycle_summary.loc[0, "operation_started_at_source_time"]
    assert "+00:00" not in timestamp
    assert not timestamp.endswith("Z")

    provenance = json.loads(
        (output / "nasa_pcoe_raw_signal_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    derivation = provenance["transformation"]["global_time_s_derivation"]
    assert "Source timezone is not asserted" in derivation
