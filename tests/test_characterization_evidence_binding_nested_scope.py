from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_evidence_binding import (
    validate_required_evidence_identity_binding,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS


SOURCE_DIGEST = "a" * 64
CASE_ID = "nested-source-scope"


def _feature() -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": None,
        "value": 1.0,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "source.xlsx",
        "source_sha256": SOURCE_DIGEST,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "review_required",
    }


def test_nested_audit_digest_inside_source_record_cannot_bind_feature(tmp_path: Path) -> None:
    feature = _feature()
    feature_table = pd.DataFrame([feature], columns=REQUIRED_COLUMNS)

    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": CASE_ID,
                "sources": [
                    {
                        "path": "source.xlsx",
                        "audit": {"source_sha256": SOURCE_DIGEST},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "nested-source-scope-regression",
                        "features": [feature],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    comparability_path = tmp_path / "comparability.csv"
    pd.DataFrame(
        [{"sample_id": "sample-a", "modality": "xrd"}]
    ).to_csv(comparability_path, index=False)

    with pytest.raises(ValueError, match="source manifest does not bind every feature"):
        validate_required_evidence_identity_binding(
            manifest={
                "case_id": CASE_ID,
                "evidence_identity_binding_contract": {
                    "schema_version": "1.0",
                    "required": True,
                },
            },
            feature_table=feature_table,
            evidence_paths={
                "analysis_manifest": analysis_path,
                "source_manifest": source_path,
                "comparability_matrix": comparability_path,
            },
        )
