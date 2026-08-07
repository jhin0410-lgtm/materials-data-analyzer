from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.materials_project_acquisition_closeout_binding import (
    MaterialsProjectCloseoutBindingError,
    validate_strategy_comparison_binding,
)
from tests.test_materials_project_acquisition_closeout import _prepare


def test_comparison_is_bound_to_evaluation_manifests(tmp_path: Path) -> None:
    suite, _, _ = _prepare(tmp_path)
    result = validate_strategy_comparison_binding(suite)
    assert result["valid"] is True
    assert result["lowest_locked_mae_strategy"] == "random"
    assert result["comparison_bound_to_evaluation_manifests"] is True


def test_comparison_metric_tampering_is_rejected(tmp_path: Path) -> None:
    suite, _, _ = _prepare(tmp_path)
    path = suite / "strategy_comparison.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload["strategies"]:
        if row["strategy"] == "uncertainty":
            row["final_sequence_mae"] = 0.0001
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(MaterialsProjectCloseoutBindingError, match="final_sequence_mae drifted"):
        validate_strategy_comparison_binding(suite)
