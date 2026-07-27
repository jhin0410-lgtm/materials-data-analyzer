from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_bundle import (
    BUNDLE_TYPE,
    MANIFEST_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS, sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "scripts" / "consume_characterization_handoff_bundle.py"


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _write_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for instrument, feature_name, unit in (
        ("raman", "candidate_count", "count"),
        ("ftir", "band_candidate_count", "count"),
        ("xps", "peak_candidate_count", "count"),
        ("tga", "retained_mass_percent", "percent"),
    ):
        rows.append(
            {
                "sample_id": "public-dwcnt",
                "measurement_id": f"public-dwcnt-{instrument}-public",
                "instrument": instrument,
                "feature_name": feature_name,
                "feature_label": None,
                "value": 2.0 if unit == "count" else 12.5,
                "unit": unit,
                "method": f"{instrument}_diagnostic_method",
                "source_file": f"producer-local/{instrument}.tab",
                "source_sha256": (instrument[0] * 64),
                "preprocessing_id": f"{instrument}-preprocessing-v1",
                "quality_flag": "review_required",
            }
        )
    feature_path = root / "characterization_features_long.csv"
    pd.DataFrame(rows, columns=REQUIRED_COLUMNS).to_csv(feature_path, index=False)

    context_path = root / "sample_context.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "public-dwcnt",
                "source_label": "DWCNT",
                "material_class": "double-walled carbon nanotubes",
                "dataset_persistent_id": "doi:10.57745/7KA2UG",
                "identical_physical_aliquot_confirmed": False,
            }
        ]
    ).to_csv(context_path, index=False)

    source_manifest = root / "case_source_manifest.json"
    source_manifest.write_text('{"source": "public"}\n', encoding="utf-8")
    analysis_manifest = root / "case_analysis_manifest.json"
    analysis_manifest.write_text('{"analysis_count": 4}\n', encoding="utf-8")
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {
            "modality": ["raman", "ftir", "xps", "tga"],
            "comparability_status": ["conditionally_comparable"] * 4,
        }
    ).to_csv(comparability, index=False)

    manifest = {
        "schema_version": "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": "public-carbon-dwcnt-multimodal-v1",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["0.8.3"],
            "analysis_result_schema_versions": ["1.0"],
        },
        "join_contract": {
            "join_key": "sample_id",
            "row_order_join_allowed": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
        },
        "feature_table": {
            **_record(feature_path),
            "columns": REQUIRED_COLUMNS,
            "row_count": 4,
            "sample_count": 1,
            "measurement_count": 4,
            "instruments": ["ftir", "raman", "tga", "xps"],
            "quality_flag_counts": {"review_required": 4},
            "source_sha256_record_count": 4,
            "preprocessing_id_record_count": 4,
        },
        "sample_context": {
            **_record(context_path),
            "columns": pd.read_csv(context_path).columns.tolist(),
            "row_count": 1,
        },
        "evidence_references": {
            "source_manifest": _record(source_manifest),
            "analysis_manifest": _record(analysis_manifest),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "result": "real_public_multimodal_features_exported",
            "strongest_evidence": "All feature rows retain source hashes and stable IDs.",
            "primary_limitation": "Identical physical aliquots are not confirmed.",
            "suitable_for": [
                "cross-repository contract validation",
                "descriptive multimodal feature integration",
            ],
            "unsuitable_for": [
                "process-response modeling",
                "causal attribution",
                "engineering release decisions",
            ],
        },
    }
    manifest_path = root / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_consumer_validates_bundle_and_builds_integrated_sample_table(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"

    paths = consume_characterization_bundle(bundle_manifest, output)

    expected = {
        "characterization_features_validated_long.csv",
        "characterization_feature_dictionary.csv",
        "characterization_features_wide.csv",
        "characterization_handoff_manifest.json",
        "integrated_sample_table.csv",
        "sample_join_audit.csv",
        SUMMARY_NAME,
        REPORT_NAME,
        MANIFEST_NAME,
    }
    assert expected.issubset({path.name for path in output.iterdir()})
    assert paths["cross_repository_manifest"].name == MANIFEST_NAME

    audit = pd.read_csv(output / "sample_join_audit.csv")
    assert audit.to_dict("records") == [
        {"sample_id": "public-dwcnt", "join_status": "matched"}
    ]
    integrated = pd.read_csv(output / "integrated_sample_table.csv")
    assert len(integrated) == 1
    assert integrated.loc[0, "source_label"] == "DWCNT"
    assert {
        "char__raman__candidate_count__count",
        "char__ftir__band_candidate_count__count",
        "char__xps__peak_candidate_count__count",
        "char__tga__retained_mass_percent__percent",
    }.issubset(integrated.columns)

    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["status"] == "verified"
    assert summary["join_summary"] == {
        "matched": 1,
        "process_only": 0,
        "characterization_only": 0,
    }
    assert summary["scientific_closeout"]["evidence_level"] == "Diagnostic"
    assert summary["software_validation"]["model_trained"] is False
    assert summary["software_validation"]["scientific_metrics_recomputed"] is False

    consumer_manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    for name, filename in consumer_manifest["outputs"].items():
        assert consumer_manifest["output_sha256"][name] == sha256_file(output / filename)
    assert not list(output.glob("*.pkl"))
    assert not list(output.glob("*model*"))


def test_consumer_cli_runs_end_to_end(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--bundle-manifest",
            str(bundle_manifest),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "handoff completed" in completed.stdout.lower()
    assert (output / SUMMARY_NAME).is_file()


def test_bundle_validation_rejects_feature_checksum_tampering(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    feature_path = bundle_manifest.parent / "characterization_features_long.csv"
    feature_path.write_text(feature_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="feature_table checksum mismatch"):
        validate_characterization_bundle(bundle_manifest)


def test_bundle_validation_rejects_path_traversal(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    manifest["feature_table"]["path"] = "../characterization_features_long.csv"
    bundle_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="relative sibling filename"):
        validate_characterization_bundle(bundle_manifest)


def test_consumer_rejects_nonempty_output_without_deleting_files(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        consume_characterization_bundle(bundle_manifest, output)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
