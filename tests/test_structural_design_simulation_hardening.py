from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.design_simulation import (
    DesignSimulationError,
    simulate_design_structure,
    simulate_design_structure_file,
    validate_design_simulation_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"


def _tracked_config() -> dict[str, object]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_large_replicate_count_does_not_expand_one_row_per_replicate() -> None:
    config = _tracked_config()
    config["observed_cells"][0]["replicates"] = 1_000_000_000

    result = simulate_design_structure(config)

    expected_before = 1_000_000_000 + sum(
        int(cell["replicates"]) for cell in config["observed_cells"][1:]
    )
    assert result["before"]["grid"]["total_replicates"] == expected_before
    interaction = next(
        item for item in result["before"]["models"] if item["model"] == "interaction"
    )
    assert interaction["n_rows"] == expected_before
    assert interaction["matrix_rank"] == 3
    assert interaction["residual_degrees_of_freedom"] == expected_before - 3


def test_integer_outside_float_range_is_rejected_as_contract_error() -> None:
    config = _tracked_config()
    config["observed_cells"][0]["factor_values"]["actual_laser_power_w"] = 10**400

    with pytest.raises(DesignSimulationError, match="representable as a finite float"):
        validate_design_simulation_config(config)


def test_file_simulation_reads_spec_once_for_parse_and_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_bytes = CONFIG.read_bytes()
    expected_sha = hashlib.sha256(expected_bytes).hexdigest()
    real_read_bytes = Path.read_bytes
    reads = 0

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal reads
        if path.resolve() == CONFIG.resolve():
            reads += 1
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    result = simulate_design_structure_file(CONFIG)

    assert reads == 1
    assert result["simulation_spec_binding"]["sha256"] == expected_sha
