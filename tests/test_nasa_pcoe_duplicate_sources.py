from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from platform_core.battery_intelligence import import_nasa_pcoe_battery


def _write_mat(path: Path, battery_id: str, *, capacity: float) -> None:
    elapsed = np.array([0.0, 10.0, 20.0])
    savemat(
        path,
        {
            battery_id: {
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
                                "Capacity": capacity,
                            },
                        }
                    ],
                    dtype=object,
                )
            }
        },
    )


def test_identical_repeated_battery_file_is_deduplicated_by_checksum(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    first = source / "bundle_a"
    second = source / "bundle_b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    _write_mat(first / "B0025.mat", "B0025", capacity=1.9)
    shutil.copyfile(first / "B0025.mat", second / "B0025.mat")

    output = tmp_path / "output"
    manifest = import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )

    assert manifest["battery_count"] == 1
    assert manifest["source_mat_file_count"] == 1
    assert manifest["identical_duplicate_copy_count"] == 1
    cycle_summary = pd.read_csv(output / "nasa_pcoe_cycle_summary.csv")
    assert len(cycle_summary) == 1
    inventory = pd.read_csv(output / "nasa_pcoe_source_inventory.csv")
    duplicate = inventory[
        inventory["skip_reason"] == "duplicate_identical_source_copy"
    ]
    assert len(duplicate) == 1


def test_same_battery_id_with_different_mat_bytes_fails_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    first = source / "bundle_a"
    second = source / "bundle_b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    _write_mat(first / "B0025.mat", "B0025", capacity=1.9)
    _write_mat(second / "B0025.mat", "B0025", capacity=1.8)

    with pytest.raises(ValueError, match="different MAT checksums"):
        import_nasa_pcoe_battery(
            input_path=source,
            output_dir=tmp_path / "output",
            retrieved_at="2026-08-01T00:00:00Z",
        )
