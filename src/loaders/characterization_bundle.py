"""Validate and consume versioned cross-repository characterization bundles."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .characterization_features import (
    REQUIRED_COLUMNS,
    run_characterization_handoff,
    sha256_file,
    validate_characterization_features,
)

BUNDLE_SCHEMA_VERSION = "1.0"
BUNDLE_TYPE = "materials_characterization_feature_handoff"
CONSUMER_SCHEMA_VERSION = "1.0"
SUMMARY_NAME = "cross_repository_handoff_summary.json"
REPORT_NAME = "cross_repository_handoff_report.md"
MANIFEST_NAME = "cross_repository_handoff_manifest.json"


@dataclass(frozen=True)
class ValidatedCharacterizationBundle:
    manifest_path: Path
    manifest: dict[str, Any]
    feature_path: Path
    sample_context_path: Path
    evidence_paths: dict[str, Path]
    feature_table: pd.DataFrame
    sample_context: pd.DataFrame


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def _as_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _resolve_sibling(bundle_root: Path, record: object, label: str) -> Path:
    metadata = _as_dict(record, label)
    recorded = metadata.get("path")
    if not isinstance(recorded, str) or not recorded.strip():
        raise ValueError(f"{label} path must be a non-empty string.")
    relative = Path(recorded)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != recorded:
        raise ValueError(f"{label} path must be one relative sibling filename.")
    target = bundle_root / relative
    if target.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link.")
    if not target.is_file():
        raise FileNotFoundError(f"{label} not found: {target}")
    expected_sha = metadata.get("sha256")
    actual_sha = sha256_file(target)
    if not isinstance(expected_sha, str) or expected_sha != actual_sha:
        raise ValueError(
            f"{label} checksum mismatch: expected {expected_sha}, actual {actual_sha}."
        )
    expected_size = metadata.get("size_bytes")
    if not isinstance(expected_size, int) or expected_size != target.stat().st_size:
        raise ValueError(f"{label} size_bytes does not match the referenced file.")
    return target


def validate_characterization_bundle(
    manifest_path: str | Path,
) -> ValidatedCharacterizationBundle:
    """Validate bundle schema, files, counts, IDs, provenance, and claim boundary."""
    manifest_path = Path(manifest_path)
    manifest = _read_json_object(manifest_path, "characterization bundle manifest")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported characterization bundle schema_version: {manifest.get('schema_version')}"
        )
    if manifest.get("bundle_type") != BUNDLE_TYPE:
        raise ValueError(f"Unsupported characterization bundle_type: {manifest.get('bundle_type')}")
    if not isinstance(manifest.get("case_id"), str) or not manifest["case_id"].strip():
        raise ValueError("characterization bundle case_id is required.")

    producer = _as_dict(manifest.get("producer"), "producer")
    if not isinstance(producer.get("repository"), str) or not producer["repository"].strip():
        raise ValueError("producer repository is required.")

    join_contract = _as_dict(manifest.get("join_contract"), "join_contract")
    expected_join_contract = {
        "join_key": "sample_id",
        "row_order_join_allowed": False,
        "aggregation_performed": False,
        "missing_metadata_inferred": False,
    }
    if join_contract != expected_join_contract:
        raise ValueError(f"Unsupported join contract: {join_contract!r}.")

    root = manifest_path.resolve().parent
    feature_record = _as_dict(manifest.get("feature_table"), "feature_table")
    context_record = _as_dict(manifest.get("sample_context"), "sample_context")
    feature_path = _resolve_sibling(root, feature_record, "feature_table")
    context_path = _resolve_sibling(root, context_record, "sample_context")

    evidence_records = _as_dict(manifest.get("evidence_references"), "evidence_references")
    required_evidence = {"source_manifest", "analysis_manifest", "comparability_matrix"}
    if set(evidence_records) != required_evidence:
        raise ValueError(
            "evidence_references must contain source_manifest, analysis_manifest, "
            "and comparability_matrix exactly."
        )
    evidence_paths = {
        name: _resolve_sibling(root, record, f"evidence reference {name}")
        for name, record in evidence_records.items()
    }

    raw_features = pd.read_csv(feature_path)
    if raw_features.columns.tolist() != REQUIRED_COLUMNS:
        raise ValueError(
            "Bundle feature columns must match the stable 12-column contract exactly."
        )
    features = validate_characterization_features(
        raw_features,
        source_name=str(feature_path),
    )
    if feature_record.get("columns") != REQUIRED_COLUMNS:
        raise ValueError("Bundle manifest feature columns do not match the consumer contract.")

    expected_feature_metadata = {
        "row_count": int(len(features)),
        "sample_count": int(features["sample_id"].nunique()),
        "measurement_count": int(features["measurement_id"].nunique()),
        "instruments": sorted(set(features["instrument"].astype(str))),
        "quality_flag_counts": dict(
            sorted(Counter(str(value) for value in features["quality_flag"]).items())
        ),
        "source_sha256_record_count": int(features["source_sha256"].notna().sum()),
        "preprocessing_id_record_count": int(features["preprocessing_id"].notna().sum()),
    }
    for key, actual in expected_feature_metadata.items():
        if feature_record.get(key) != actual:
            raise ValueError(
                f"Bundle feature metadata mismatch for {key}: "
                f"expected {actual!r}, recorded {feature_record.get(key)!r}."
            )
    if expected_feature_metadata["source_sha256_record_count"] != len(features):
        raise ValueError("Every cross-repository feature record must retain source_sha256.")
    if expected_feature_metadata["preprocessing_id_record_count"] != len(features):
        raise ValueError("Every cross-repository feature record must retain preprocessing_id.")

    context = pd.read_csv(context_path)
    recorded_context_columns = context_record.get("columns")
    if recorded_context_columns != context.columns.tolist():
        raise ValueError("Bundle sample-context columns do not match the manifest.")
    if context_record.get("row_count") != len(context):
        raise ValueError("Bundle sample-context row_count does not match the file.")
    if "sample_id" not in context.columns:
        raise ValueError("Bundle sample context requires sample_id.")
    context = context.copy()
    context["sample_id"] = context["sample_id"].astype("string").str.strip()
    if context["sample_id"].isna().any() or context["sample_id"].eq("").any():
        raise ValueError("Bundle sample context contains blank sample_id values.")
    if context["sample_id"].duplicated().any():
        raise ValueError("Bundle sample context sample_id values must be unique.")
    if set(context["sample_id"].astype(str)) != set(features["sample_id"].astype(str)):
        raise ValueError("Feature and sample-context sample_id sets must match exactly.")

    closeout = _as_dict(manifest.get("scientific_closeout"), "scientific_closeout")
    if not isinstance(closeout.get("evidence_level"), str):
        raise ValueError("scientific_closeout evidence_level is required.")
    for field in ("suitable_for", "unsuitable_for"):
        if not isinstance(closeout.get(field), list):
            raise ValueError(f"scientific_closeout {field} must be a list.")

    return ValidatedCharacterizationBundle(
        manifest_path=manifest_path,
        manifest=manifest,
        feature_path=feature_path,
        sample_context_path=context_path,
        evidence_paths=evidence_paths,
        feature_table=features,
        sample_context=context,
    )


def _ensure_empty_output(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def _build_report(summary: dict[str, Any]) -> str:
    instruments = ", ".join(summary["feature_summary"]["instruments"])
    suitable = "\n".join(f"- {item}" for item in summary["scientific_closeout"]["suitable_for"])
    unsuitable = "\n".join(
        f"- {item}" for item in summary["scientific_closeout"]["unsuitable_for"]
    )
    return f"""# Cross-Repository Characterization Handoff Report

## Result

Software handoff status: **Verified**.

Scientific evidence level: **{summary['scientific_closeout']['evidence_level']}**.

The consumer verified the producer bundle, all referenced SHA-256 values, the
stable 12-column feature contract, sample-context identity, provenance coverage,
and a one-to-one `sample_id` join. No row-order joining, silent aggregation,
metadata inference, model training, or scientific metric recomputation occurred.

## Producer

- Repository: `{summary['producer']['repository']}`
- Case ID: `{summary['case_id']}`
- Instruments: {instruments}
- Feature records: {summary['feature_summary']['row_count']}
- Measurements: {summary['feature_summary']['measurement_count']}
- Samples: {summary['feature_summary']['sample_count']}
- Matched samples: {summary['join_summary']['matched']}

## Strongest Evidence

{summary['scientific_closeout'].get('strongest_evidence', 'Not recorded by producer.')}

## Primary Limitation

{summary['scientific_closeout'].get('primary_limitation', 'Not recorded by producer.')}

## Suitable Use

{suitable}

## Unsupported Use

{unsuitable}

## Decision Boundary

This package validates software interoperability and provenance transfer. It
does not prove identical physical aliquots, process-response causality,
predictive generalization, phase or chemical-state assignments, or engineering
release readiness.
"""


def consume_characterization_bundle(
    manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Validate a producer bundle and generate consumer-side integrated artifacts."""
    bundle = validate_characterization_bundle(manifest_path)
    output = Path(output_dir)
    _ensure_empty_output(output)

    handoff_paths = run_characterization_handoff(
        [bundle.feature_path],
        output,
        process_table_path=bundle.sample_context_path,
    )
    audit = pd.read_csv(handoff_paths["join_audit"])
    join_summary = {
        status: int(audit["join_status"].eq(status).sum())
        for status in ("matched", "process_only", "characterization_only")
    }
    expected_matched = int(bundle.feature_table["sample_id"].nunique())
    if join_summary != {
        "matched": expected_matched,
        "process_only": 0,
        "characterization_only": 0,
    }:
        raise ValueError(f"Unexpected consumer join summary: {join_summary!r}.")

    feature_record = _as_dict(bundle.manifest["feature_table"], "feature_table")
    summary = {
        "schema_version": CONSUMER_SCHEMA_VERSION,
        "workflow": "cross_repository_characterization_handoff",
        "status": "verified",
        "case_id": bundle.manifest["case_id"],
        "producer": bundle.manifest["producer"],
        "producer_bundle": {
            "filename": bundle.manifest_path.name,
            "sha256": sha256_file(bundle.manifest_path),
            "schema_version": bundle.manifest["schema_version"],
            "bundle_type": bundle.manifest["bundle_type"],
        },
        "feature_summary": {
            key: feature_record[key]
            for key in (
                "row_count",
                "sample_count",
                "measurement_count",
                "instruments",
                "quality_flag_counts",
                "source_sha256_record_count",
                "preprocessing_id_record_count",
            )
        },
        "sample_context_columns": bundle.sample_context.columns.tolist(),
        "join_summary": join_summary,
        "software_validation": {
            "all_bundle_checksums_verified": True,
            "stable_feature_contract_validated": True,
            "sample_identity_sets_match": True,
            "row_order_join_used": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
            "model_trained": False,
            "scientific_metrics_recomputed": False,
        },
        "scientific_closeout": bundle.manifest["scientific_closeout"],
    }
    summary_path = output / SUMMARY_NAME
    report_path = output / REPORT_NAME
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_build_report(summary), encoding="utf-8")

    outputs: dict[str, Path] = {
        **handoff_paths,
        "cross_repository_summary": summary_path,
        "cross_repository_report": report_path,
    }
    manifest_output = output / MANIFEST_NAME
    consumer_manifest = {
        "schema_version": CONSUMER_SCHEMA_VERSION,
        "workflow": "cross_repository_characterization_handoff",
        "case_id": bundle.manifest["case_id"],
        "producer": bundle.manifest["producer"],
        "input_bundle": {
            "filename": bundle.manifest_path.name,
            "sha256": sha256_file(bundle.manifest_path),
            "feature_table_sha256": sha256_file(bundle.feature_path),
            "sample_context_sha256": sha256_file(bundle.sample_context_path),
            "evidence_sha256": {
                name: sha256_file(path) for name, path in sorted(bundle.evidence_paths.items())
            },
        },
        "validation": summary["software_validation"],
        "join_summary": join_summary,
        "scientific_closeout": bundle.manifest["scientific_closeout"],
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {name: sha256_file(path) for name, path in outputs.items()},
    }
    manifest_output.write_text(
        json.dumps(consumer_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs["cross_repository_manifest"] = manifest_output
    return outputs
