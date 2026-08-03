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


def _write_contract(path: Path, columns: dict[str, object]) -> Path:
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
    assert protected_columns(None) == set()


def test_decision_grade_requires_contract() -> None:
    with pytest.raises(ValueError, match="requires --dataset-contract"):
        audit_dataset_contract(
            None,
            pd.DataFrame({"sample_id": ["S1"], "yield": [90.0]}),
            mode="process",
            target_columns=["yield"],
            decision_grade=True,
        )

    audit = audit_dataset_contract(
        None,
        pd.DataFrame({"sample_id": ["S1"], "yield": [90.0]}),
        mode="process",
        target_columns=["yield"],
        decision_grade=False,
    )
    assert audit["status"] == "not_supplied"
    assert audit["limitations"]


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


def test_contract_loader_rejects_invalid_or_ambiguous_definitions(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_dataset_contract(tmp_path / "missing.json")

    scalar = tmp_path / "scalar.json"
    scalar.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        load_dataset_contract(scalar)

    wrong_version = tmp_path / "wrong-version.json"
    wrong_version.write_text(
        json.dumps({"schema_version": "2.0", "columns": {"x": {"role": "feature"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported.*schema_version"):
        load_dataset_contract(wrong_version)

    empty = tmp_path / "empty.json"
    empty.write_text(
        json.dumps({"schema_version": "1.0", "columns": {}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="non-empty columns"):
        load_dataset_contract(empty)

    collision = _write_contract(
        tmp_path / "collision.json",
        {"Sample ID": {"role": "identifier"}, "Sample-ID": {"role": "group"}},
    )
    with pytest.raises(ValueError, match="collide after normalization"):
        load_dataset_contract(collision)

    invalid_spec = _write_contract(tmp_path / "invalid-spec.json", {"x": "feature"})
    with pytest.raises(TypeError, match="spec must be an object"):
        load_dataset_contract(invalid_spec)

    invalid_role = _write_contract(
        tmp_path / "invalid-role.json", {"x": {"role": "unknown"}}
    )
    with pytest.raises(ValueError, match="unsupported role"):
        load_dataset_contract(invalid_role)


def test_non_decision_audit_reports_semantic_and_schema_issues(tmp_path: Path) -> None:
    contract = load_dataset_contract(
        _write_contract(
            tmp_path / "contract.json",
            {
                "sample_id": {"role": "identifier"},
                "missing_feature": {"role": "feature", "unit": "V"},
                "temperature_c": {"role": "feature"},
                "yield": {"role": "feature", "unit": "%"},
            },
        )
    )
    frame = pd.DataFrame(
        {
            "sample_id": ["S1"],
            "temperature_c": ["not-numeric"],
            "yield": [90.0],
            "undeclared": [1.0],
        }
    )

    audit = audit_dataset_contract(
        contract,
        frame,
        mode="process",
        target_columns=["yield", "not_declared"],
        decision_grade=False,
    )

    assert audit["status"] == "invalid"
    assert audit["undeclared_columns"] == ["undeclared"]
    codes = {issue["code"] for issue in audit["issues"]}
    assert {
        "declared_column_missing",
        "numeric_role_not_numeric",
        "physical_role_unit_missing",
        "target_role_mismatch",
        "target_not_declared",
    } <= codes
    assert "does not establish comparability" in audit["scientific_boundary"]


def test_decision_grade_mode_specific_roles_fail_closed(tmp_path: Path) -> None:
    no_identifier = load_dataset_contract(
        _write_contract(
            tmp_path / "no-id.json",
            {"yield": {"role": "target", "unit": "%"}},
        )
    )
    with pytest.raises(ValueError, match="identifier_role_missing"):
        audit_dataset_contract(
            no_identifier,
            pd.DataFrame({"yield": [90.0]}),
            mode="process",
            target_columns=["yield"],
            decision_grade=True,
        )

    reliability = load_dataset_contract(
        _write_contract(
            tmp_path / "reliability.json",
            {
                "sample_id": {"role": "identifier"},
                "time_h": {"role": "exposure", "unit": "h"},
                "failed": {"role": "outcome"},
            },
        )
    )
    with pytest.raises(ValueError, match="exposure_or_censoring_role_missing"):
        audit_dataset_contract(
            reliability,
            pd.DataFrame(
                {"sample_id": ["S1"], "time_h": [10.0], "failed": [1]}
            ),
            mode="reliability",
            target_columns=["failed"],
            decision_grade=True,
        )
