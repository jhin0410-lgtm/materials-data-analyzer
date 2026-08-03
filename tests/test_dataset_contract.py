"""Tests for versioned dataset semantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dataset_contract import (
    audit_dataset_contract,
    load_dataset_contract,
    protected_columns,
)


def _write_contract(path: Path, columns: dict[str, dict[str, str]]) -> Path:
    path.write_text(
        json.dumps({"schema_version": "1.0", "columns": columns}),
        encoding="utf-8",
    )
    return path


def test_contract_normalizes_roles_and_protects_custom_identifier(tmp_path: Path) -> None:
    contract = load_dataset_contract(
        _write_contract(
            tmp_path / "contract.json",
            {
                "Specimen Code": {"role": "identifier"},
                "Yield (%)": {"role": "target", "unit": "%"},
            },
        )
    )

    assert set(contract["columns"]) == {"specimen_code", "yield"}
    assert protected_columns(contract) == {"specimen_code"}


def test_decision_grade_requires_contract() -> None:
    with pytest.raises(ValueError, match="requires --dataset-contract"):
        audit_dataset_contract(
            None,
            pd.DataFrame({"sample_id": ["S1"], "yield": [90.0]}),
            mode="process",
            target_columns=["yield"],
            decision_grade=True,
        )


def test_valid_decision_grade_spc_contract_passes(tmp_path: Path) -> None:
    contract = load_dataset_contract(
        _write_contract(
            tmp_path / "contract.json",
            {
                "sample_id": {"role": "identifier"},
                "timestamp": {"role": "timestamp"},
                "temperature_c": {"role": "target", "unit": "degC"},
            },
        )
    )
    frame = pd.DataFrame(
        {
            "sample_id": ["S1", "S2"],
            "timestamp": ["2026-01-01", "2026-01-02"],
            "temperature_c": [700.0, 701.0],
        }
    )

    audit = audit_dataset_contract(
        contract,
        frame,
        mode="spc",
        target_columns=["temperature_c"],
        decision_grade=True,
    )

    assert audit["status"] == "valid"
    assert audit["decision_grade"] is True


def test_decision_grade_simulation_requires_group_role(tmp_path: Path) -> None:
    contract = load_dataset_contract(
        _write_contract(
            tmp_path / "contract.json",
            {
                "sample_id": {"role": "identifier"},
                "temperature_c": {"role": "feature", "unit": "degC"},
                "yield": {"role": "target", "unit": "%"},
            },
        )
    )

    with pytest.raises(ValueError, match="group_role_missing"):
        audit_dataset_contract(
            contract,
            pd.DataFrame(
                {"sample_id": ["S1"], "temperature_c": [700.0], "yield": [90.0]}
            ),
            mode="simulation",
            target_columns=["yield"],
            decision_grade=True,
        )
