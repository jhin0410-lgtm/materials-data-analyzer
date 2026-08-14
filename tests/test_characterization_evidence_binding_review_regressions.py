from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_evidence_binding import (
    validate_required_evidence_identity_binding,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS


CASE_ID = "review-regression-case"
SOURCE_DIGEST = "a" * 64


def _feature_row(*, value: float = 1.0) -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": None,
        "value": value,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "producer-local/source.csv",
        "source_sha256": SOURCE_DIGEST,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _feature_table() -> pd.DataFrame:
    return pd.DataFrame([_feature_row()], columns=REQUIRED_COLUMNS)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_comparability(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "modality": "xrd",
                "comparability_status": "not_established",
            }
        ]
    ).to_csv(path, index=False)
    return path


def _required_manifest(contract: object | None = None) -> dict[str, object]:
    if contract is None:
        contract = {"schema_version": "1.0", "required": True}
    return {
        "case_id": CASE_ID,
        "evidence_identity_binding_contract": contract,
    }


def _valid_analysis_payload() -> dict[str, object]:
    return {
        "analysis_count": 1,
        "analyses": [
            {
                "schema_version": "1.0",
                "software_version": "review-regression",
                "features": [_feature_row()],
            }
        ],
    }


def test_present_null_evidence_binding_contract_fails_closed() -> None:
    manifest = {
        "case_id": CASE_ID,
        "evidence_identity_binding_contract": None,
    }

    with pytest.raises(
        ValueError,
        match="evidence_identity_binding_contract must be an object",
    ):
        validate_required_evidence_identity_binding(
            manifest=manifest,
            feature_table=_feature_table(),
            evidence_paths={},
        )


def test_boolean_analysis_feature_value_cannot_replay_as_numeric(
    tmp_path: Path,
) -> None:
    analysis = _valid_analysis_payload()
    analysis["analyses"][0]["features"][0]["value"] = True  # type: ignore[index]

    evidence_paths = {
        "analysis_manifest": _write_json(tmp_path / "analysis.json", analysis),
        "source_manifest": _write_json(
            tmp_path / "source.json",
            {
                "case_id": CASE_ID,
                "sources": [{"source_sha256": SOURCE_DIGEST}],
            },
        ),
        "comparability_matrix": _write_comparability(tmp_path / "comparability.csv"),
    }

    with pytest.raises(ValueError, match="feature value must be a finite JSON number"):
        validate_required_evidence_identity_binding(
            manifest=_required_manifest(),
            feature_table=_feature_table(),
            evidence_paths=evidence_paths,
        )


def test_unrelated_generic_checksum_cannot_satisfy_source_binding(
    tmp_path: Path,
) -> None:
    evidence_paths = {
        "analysis_manifest": _write_json(
            tmp_path / "analysis.json",
            _valid_analysis_payload(),
        ),
        "source_manifest": _write_json(
            tmp_path / "source.json",
            {
                "case_id": CASE_ID,
                "audit": {"sha256": SOURCE_DIGEST},
            },
        ),
        "comparability_matrix": _write_comparability(tmp_path / "comparability.csv"),
    }

    with pytest.raises(ValueError, match="source manifest does not bind every feature"):
        validate_required_evidence_identity_binding(
            manifest=_required_manifest(),
            feature_table=_feature_table(),
            evidence_paths=evidence_paths,
        )
