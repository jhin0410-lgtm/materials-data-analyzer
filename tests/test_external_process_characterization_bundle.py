from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_bundle import (
    BUNDLE_TYPE,
    EXTERNAL_PROCESS_INPUT_NAME,
    MANIFEST_NAME,
    SUMMARY_NAME,
    consume_characterization_bundle,
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


def _write_identity_bundle(root: Path) -> Path:
    root.mkdir(parents=True)
    features = pd.DataFrame(
        [
            {
                "sample_id": "trace-01",
                "measurement_id": "trace-01-xsection",
                "instrument": "optical_microscopy_metrology",
                "feature_name": "melt_pool_width_mean",
                "feature_label": None,
                "value": 100.0,
                "unit": "um",
                "method": "source_reported_table",
                "source_file": "measurements.csv",
                "source_sha256": "a" * 64,
                "preprocessing_id": "reported_table_v1",
                "quality_flag": "source_reported",
            },
            {
                "sample_id": "trace-02",
                "measurement_id": "trace-02-xsection",
                "instrument": "optical_microscopy_metrology",
                "feature_name": "melt_pool_width_mean",
                "feature_label": None,
                "value": 120.0,
                "unit": "um",
                "method": "source_reported_table",
                "source_file": "measurements.csv",
                "source_sha256": "a" * 64,
                "preprocessing_id": "reported_table_v1",
                "quality_flag": "source_reported",
            },
        ],
        columns=REQUIRED_COLUMNS,
    )
    feature_path = root / "characterization_features_long.csv"
    features.to_csv(feature_path, index=False)

    context = pd.DataFrame(
        [
            {
                "sample_id": "trace-01",
                "case_id": "A",
                "trace_number": 1,
                "material": "IN625",
                "system": "AMMT",
                "source_label": "NIST trace 1",
                "raw_image_parsed": False,
            },
            {
                "sample_id": "trace-02",
                "case_id": "B",
                "trace_number": 2,
                "material": "IN625",
                "system": "AMMT",
                "source_label": "NIST trace 2",
                "raw_image_parsed": False,
            },
        ]
    )
    context_path = root / "sample_context.csv"
    context.to_csv(context_path, index=False)

    source_manifest = root / "case_source_manifest.json"
    source_manifest.write_text('{"source":"test"}\n', encoding="utf-8")
    analysis_manifest = root / "case_analysis_manifest.json"
    analysis_manifest.write_text('{"analysis_count":2}\n', encoding="utf-8")
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        [
            {
                "instrument": "optical_microscopy_metrology",
                "comparability_status": "trace_mapping_confirmed",
            }
        ]
    ).to_csv(comparability, index=False)

    manifest = {
        "schema_version": "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": "test-process-characterization",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["0.8.5"],
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
            "row_count": 2,
            "sample_count": 2,
            "measurement_count": 2,
            "instruments": ["optical_microscopy_metrology"],
            "quality_flag_counts": {"source_reported": 2},
            "source_sha256_record_count": 2,
            "preprocessing_id_record_count": 2,
        },
        "sample_context": {
            **_record(context_path),
            "columns": context.columns.tolist(),
            "row_count": 2,
        },
        "evidence_references": {
            "source_manifest": _record(source_manifest),
            "analysis_manifest": _record(analysis_manifest),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "result": "test_identity_bundle",
            "strongest_evidence": "Explicit trace identities.",
            "primary_limitation": "Synthetic contract fixture.",
            "suitable_for": ["software validation"],
            "unsuitable_for": ["scientific claims"],
        },
    }
    manifest_path = root / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_matching_process_table(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "sample_id": "trace-02",
                "case_id": "B",
                "trace_number": 2,
                "material": "IN625",
                "system": "AMMT",
                "actual_laser_power_w": 180.0,
                "scan_speed_mm_s": 800.0,
            },
            {
                "sample_id": "trace-01",
                "case_id": "A",
                "trace_number": 1,
                "material": "IN625",
                "system": "AMMT",
                "actual_laser_power_w": 140.0,
                "scan_speed_mm_s": 400.0,
            },
        ]
    ).to_csv(path, index=False)
    return path


def test_external_process_table_is_identity_validated_and_joined_by_sample_id(
    tmp_path: Path,
) -> None:
    bundle = _write_identity_bundle(tmp_path / "producer")
    process = _write_matching_process_table(tmp_path / "process.csv")
    output = tmp_path / "consumer"

    paths = consume_characterization_bundle(
        bundle,
        output,
        process_table_path=process,
    )

    assert paths["validated_process_input"].name == EXTERNAL_PROCESS_INPUT_NAME
    validated_process = pd.read_csv(output / EXTERNAL_PROCESS_INPUT_NAME)
    assert validated_process["sample_id"].tolist() == ["trace-01", "trace-02"]
    assert {"source_label", "raw_image_parsed"}.issubset(validated_process.columns)

    integrated = pd.read_csv(output / "integrated_sample_table.csv").set_index(
        "sample_id"
    )
    assert integrated.loc["trace-01", "actual_laser_power_w"] == pytest.approx(140.0)
    assert integrated.loc["trace-01", "char__optical_microscopy_metrology__melt_pool_width_mean__um"] == pytest.approx(100.0)
    assert integrated.loc["trace-02", "scan_speed_mm_s"] == pytest.approx(800.0)
    assert integrated.loc["trace-02", "source_label"] == "NIST trace 2"

    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["process_input"]["mode"] == (
        "external_process_table_with_bundle_identity_validation"
    )
    assert summary["process_input"]["verified_identity_columns"] == [
        "case_id",
        "trace_number",
        "material",
        "system",
    ]
    assert summary["process_input"]["identity_mismatch_count"] == 0
    assert summary["join_summary"] == {
        "matched": 2,
        "process_only": 0,
        "characterization_only": 0,
    }
    assert summary["software_validation"]["external_process_table_used"] is True
    assert summary["software_validation"]["row_order_join_used"] is False
    assert summary["software_validation"]["scientific_metrics_recomputed"] is False

    consumer_manifest = json.loads(
        (output / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert consumer_manifest["process_input"]["sha256"] == sha256_file(process)
    for name, filename in consumer_manifest["outputs"].items():
        assert consumer_manifest["output_sha256"][name] == sha256_file(
            output / filename
        )


def test_external_process_identity_conflict_is_rejected_before_output_creation(
    tmp_path: Path,
) -> None:
    bundle = _write_identity_bundle(tmp_path / "producer")
    process = _write_matching_process_table(tmp_path / "process.csv")
    table = pd.read_csv(process)
    table.loc[table["sample_id"].eq("trace-02"), "material"] = "IN718"
    table.to_csv(process, index=False)
    output = tmp_path / "consumer"

    with pytest.raises(ValueError, match="trace-02:material"):
        consume_characterization_bundle(
            bundle,
            output,
            process_table_path=process,
        )

    assert not output.exists()


def test_external_process_sample_set_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle = _write_identity_bundle(tmp_path / "producer")
    process = _write_matching_process_table(tmp_path / "process.csv")
    table = pd.read_csv(process).iloc[:1]
    table.to_csv(process, index=False)

    with pytest.raises(ValueError, match="sample_id sets must match exactly"):
        consume_characterization_bundle(
            bundle,
            tmp_path / "consumer",
            process_table_path=process,
        )


def test_external_process_requires_shared_identity_beyond_sample_id(tmp_path: Path) -> None:
    bundle = _write_identity_bundle(tmp_path / "producer")
    process = tmp_path / "process.csv"
    pd.DataFrame(
        {
            "sample_id": ["trace-01", "trace-02"],
            "temperature_c": [100.0, 200.0],
        }
    ).to_csv(process, index=False)

    with pytest.raises(ValueError, match="share at least one identity column"):
        consume_characterization_bundle(
            bundle,
            tmp_path / "consumer",
            process_table_path=process,
        )


def test_cli_accepts_external_process_table(tmp_path: Path) -> None:
    bundle = _write_identity_bundle(tmp_path / "producer")
    process = _write_matching_process_table(tmp_path / "process.csv")
    output = tmp_path / "consumer"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--bundle-manifest",
            str(bundle),
            "--process-table",
            str(process),
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
    assert (output / EXTERNAL_PROCESS_INPUT_NAME).is_file()
