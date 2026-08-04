from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from platform_core.battery_intelligence.nasa_audit_diagnostics import (
    repair_staged_charge_semantics,
)


CHARGE_COLUMNS = (
    "charge_duration_s",
    "charge_cc_duration_s",
    "charge_cv_duration_s",
    "charge_throughput_ah",
    "charge_energy_wh",
    "coulombic_efficiency",
    "energy_efficiency",
    "cv_fraction_of_charge_time",
)


def _staging(tmp_path: Path, table: pd.DataFrame) -> Path:
    staging = tmp_path / "staging"
    (staging / "tables").mkdir(parents=True)
    (staging / "reports").mkdir(parents=True)
    table.to_csv(staging / "tables" / "signal_features.csv", index=False)
    return staging


def test_already_remediated_charge_semantics_report_recomputed_model(
    tmp_path: Path,
) -> None:
    table = pd.DataFrame(
        {
            **{column: [np.nan] for column in CHARGE_COLUMNS},
            "charge_signal_available": [False],
            "charge_feature_status": ["not_observed_in_raw_signal"],
        }
    )
    staging = _staging(tmp_path, table)

    summary = repair_staged_charge_semantics(staging)

    assert summary["changed_cell_count"] == 0
    assert summary["explicit_charge_semantics_present"] is True
    assert summary["staged_correction_applied"] is False
    assert summary["model_results_recomputed"] is True
    assert "No staged correction was required" in summary["note"]
    written = json.loads(
        (staging / "reports" / "charge_feature_semantics_remediation.json")
        .read_text(encoding="utf-8")
    )
    assert written == summary


def test_legacy_zero_charge_semantics_remain_not_recomputed(
    tmp_path: Path,
) -> None:
    table = pd.DataFrame({column: [0.0] for column in CHARGE_COLUMNS})
    staging = _staging(tmp_path, table)

    summary = repair_staged_charge_semantics(staging)

    assert summary["changed_cell_count"] == len(CHARGE_COLUMNS)
    assert summary["explicit_charge_semantics_present"] is False
    assert summary["staged_correction_applied"] is True
    assert summary["model_results_recomputed"] is False
    corrected = pd.read_csv(staging / "tables" / "signal_features.csv")
    assert corrected[list(CHARGE_COLUMNS)].isna().all().all()
    assert corrected["charge_signal_available"].eq(False).all()  # noqa: E712
    assert corrected["charge_feature_status"].eq(
        "not_observed_in_raw_signal"
    ).all()
