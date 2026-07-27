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
NORMALIZED_INPUT_NAME = "characterization_features_bundle_input.csv"
EXTERNAL_PROCESS_INPUT_NAME = "process_table_with_bundle_context.csv"
UNIT_LABEL_RULE = "replace_percent_symbol_with_percent_token"
PROCESS_IDENTITY_COLUMNS = ("case_id", "trace_number", "material", "system")


@dataclass(frozen=True)
class ValidatedCharacterizationBundle:
    manifest_path: Path
    manifest: dict[str, Any]
    feature_path: Path
    sample_context_path: Path
    evidence_paths: dict[str, Path]
    feature_table: pd.DataFrame
    sample_context: pd.DataFrame


@dataclass(frozen=True)
class ValidatedProcessInput:
    table: pd.DataFrame
    metadata: dict[str, Any]


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
        raise ValueError(
            f"Unsupported characterization bundle_type: {manifest.get('bundle_type')}"
        )
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

    evidence_records = _as_dict(
        manifest.get("evidence_references"), "evidence_references"
    )
    required_evidence = {
        "source_manifest",
        "analysis_manifest",
        "comparability_matrix",
    }
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
        raw_features, source_name=str(feature_path)
    )
    if feature_record.get("columns") != REQUIRED_COLUMNS:
        raise ValueError(
            "Bundle manifest feature columns do not match the consumer contract."
        )

    expected_feature_metadata = {
        "row_count": int(len(features)),
        "sample_count": int(features["sample_id"].nunique()),
        "measurement_count": int(features["measurement_id"].nunique()),
        "instruments": sorted(set(features["instrument"].astype(str))),
        "quality_flag_counts": dict(
            sorted(
                Counter(str(value) for value in features["quality_flag"]).items()
            )
        ),
        "source_sha256_record_count": int(
            features["source_sha256"].notna().sum()
        ),
        "preprocessing_id_record_count": int(
            features["preprocessing_id"].notna().sum()
        ),
    }
    for key, actual in expected_feature_metadata.items():
        if feature_record.get(key) != actual:
            raise ValueError(
                f"Bundle feature metadata mismatch for {key}: "
                f"expected {actual!r}, recorded {feature_record.get(key)!r}."
            )
    if expected_feature_metadata["source_sha256_record_count"] != len(features):
        raise ValueError(
            "Every cross-repository feature record must retain source_sha256."
        )
    if expected_feature_metadata["preprocessing_id_record_count"] != len(features):
        raise ValueError(
            "Every cross-repository feature record must retain preprocessing_id."
        )

    context = pd.read_csv(context_path)
    if context_record.get("columns") != context.columns.tolist():
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
    if set(context["sample_id"].astype(str)) != set(
        features["sample_id"].astype(str)
    ):
        raise ValueError(
            "Feature and sample-context sample_id sets must match exactly."
        )

    closeout = _as_dict(
        manifest.get("scientific_closeout"), "scientific_closeout"
    )
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


def _write_normalized_handoff_input(
    feature_table: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Canonicalize unit spelling for safe feature keys without changing values."""
    normalized = feature_table.copy()
    original_units = normalized["unit"].astype(str)
    normalized_units = original_units.str.replace("%", "percent", regex=False)
    mappings = {
        source: target
        for source, target in sorted(set(zip(original_units, normalized_units)))
        if source != target
    }
    normalized["unit"] = normalized_units
    normalized = validate_characterization_features(
        normalized,
        source_name="consumer unit-label-normalized feature table",
    )
    path = output_dir / NORMALIZED_INPUT_NAME
    normalized.to_csv(path, index=False)
    return path, {
        "performed": bool(mappings),
        "rule": UNIT_LABEL_RULE,
        "mappings": mappings,
        "record_count": int((original_units != normalized_units).sum()),
        "numeric_values_modified": False,
        "source_feature_table_preserved": True,
    }


def _clean_external_process_table(table: pd.DataFrame, label: str) -> pd.DataFrame:
    if "sample_id" not in table.columns:
        raise ValueError(f"{label} requires an explicit sample_id column.")
    cleaned = table.copy()
    cleaned["sample_id"] = cleaned["sample_id"].astype("string").str.strip()
    if cleaned["sample_id"].isna().any() or cleaned["sample_id"].eq("").any():
        raise ValueError(f"{label} contains blank sample_id values.")
    if cleaned["sample_id"].duplicated().any():
        duplicates = sorted(
            cleaned.loc[
                cleaned["sample_id"].duplicated(keep=False), "sample_id"
            ].astype(str).unique()
        )
        raise ValueError(
            f"{label} sample_id values must be unique; duplicate(s): "
            + ", ".join(duplicates)
        )
    return cleaned


def _normalized_identity_values(
    series: pd.Series,
    column: str,
    label: str,
) -> pd.Series:
    if column == "trace_number":
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"{label} contains invalid trace_number values.")
        return numeric.astype(float)
    text = series.astype("string").str.strip()
    if text.isna().any() or text.eq("").any():
        raise ValueError(f"{label} contains blank {column} values.")
    return text.astype(str)


def validate_external_process_input(
    bundle: ValidatedCharacterizationBundle,
    process_table_path: str | Path,
) -> ValidatedProcessInput:
    """Validate a consumer-owned process table against producer identity context."""
    path = Path(process_table_path)
    if path.is_symlink():
        raise ValueError("External process table must not be a symbolic link.")
    if not path.is_file():
        raise FileNotFoundError(f"External process table not found: {path}")

    process = _clean_external_process_table(
        pd.read_csv(path), "External process table"
    )
    context = _clean_external_process_table(
        bundle.sample_context, "Bundle sample context"
    )
    process_ids = set(process["sample_id"].astype(str))
    context_ids = set(context["sample_id"].astype(str))
    if process_ids != context_ids:
        raise ValueError(
            "External process table and bundle sample context sample_id sets must "
            f"match exactly; process_only={sorted(process_ids - context_ids)}, "
            f"bundle_only={sorted(context_ids - process_ids)}."
        )

    identity_columns = [
        column
        for column in PROCESS_IDENTITY_COLUMNS
        if column in process.columns and column in context.columns
    ]
    if not identity_columns:
        raise ValueError(
            "External process table must share at least one identity column with "
            "bundle context in addition to sample_id: case_id, trace_number, "
            "material, or system."
        )

    compared = process[["sample_id", *identity_columns]].merge(
        context[["sample_id", *identity_columns]],
        on="sample_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_process", "_bundle"),
        sort=True,
    )
    mismatches: list[str] = []
    for column in identity_columns:
        process_values = _normalized_identity_values(
            compared[f"{column}_process"],
            column,
            "External process table",
        )
        bundle_values = _normalized_identity_values(
            compared[f"{column}_bundle"],
            column,
            "Bundle sample context",
        )
        unequal = ~process_values.eq(bundle_values)
        for sample_id in compared.loc[unequal, "sample_id"].astype(str):
            mismatches.append(f"{sample_id}:{column}")
    if mismatches:
        raise ValueError(
            "External process identity conflicts with bundle context for "
            + ", ".join(mismatches[:20])
            + ("..." if len(mismatches) > 20 else "")
            + "."
        )

    context_columns_added = [
        column
        for column in context.columns
        if column != "sample_id" and column not in process.columns
    ]
    combined = process.merge(
        context[["sample_id", *context_columns_added]],
        on="sample_id",
        how="left",
        validate="one_to_one",
        sort=True,
    ).sort_values("sample_id").reset_index(drop=True)
    metadata = {
        "mode": "external_process_table_with_bundle_identity_validation",
        "external_process_table_used": True,
        "filename": path.name,
        "sha256": sha256_file(path),
        "row_count": int(len(process)),
        "columns": process.columns.tolist(),
        "sample_id_sets_match": True,
        "verified_identity_columns": identity_columns,
        "identity_mismatch_count": 0,
        "bundle_context_columns_added": context_columns_added,
        "row_order_join_used": False,
        "missing_metadata_inferred": False,
    }
    return ValidatedProcessInput(table=combined, metadata=metadata)


def _bundle_context_process_input(
    bundle: ValidatedCharacterizationBundle,
) -> ValidatedProcessInput:
    return ValidatedProcessInput(
        table=bundle.sample_context.copy(),
        metadata={
            "mode": "bundle_sample_context",
            "external_process_table_used": False,
            "filename": bundle.sample_context_path.name,
            "sha256": sha256_file(bundle.sample_context_path),
            "row_count": int(len(bundle.sample_context)),
            "columns": bundle.sample_context.columns.tolist(),
            "sample_id_sets_match": True,
            "verified_identity_columns": ["sample_id"],
            "identity_mismatch_count": 0,
            "bundle_context_columns_added": [],
            "row_order_join_used": False,
            "missing_metadata_inferred": False,
        },
    )


def _build_report(summary: dict[str, Any]) -> str:
    instruments = ", ".join(summary["feature_summary"]["instruments"])
    suitable = "\n".join(
        f"- {item}" for item in summary["scientific_closeout"]["suitable_for"]
    )
    unsuitable = "\n".join(
        f"- {item}" for item in summary["scientific_closeout"]["unsuitable_for"]
    )
    normalization = summary["unit_label_normalization"]
    process = summary["process_input"]
    verified_identity = ", ".join(process["verified_identity_columns"])
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

## Process Input

- Mode: `{process['mode']}`
- External process table used: `{str(process['external_process_table_used']).lower()}`
- Verified identity columns: {verified_identity}
- Identity mismatches: {process['identity_mismatch_count']}
- Row-order join used: `{str(process['row_order_join_used']).lower()}`

When an external process table is supplied, its sample IDs must match the bundle
exactly and every shared case, trace, material, or system identity column must
agree before process variables are admitted to the integrated table.

## Unit Label Normalization

- Rule: `{normalization['rule']}`
- Records affected: {normalization['record_count']}
- Numeric values modified: `{str(normalization['numeric_values_modified']).lower()}`
- Original producer feature table preserved: `{str(normalization['source_feature_table_preserved']).lower()}`

This is a lexical representation change for stable ASCII feature keys. For
example, `%` becomes `percent`; it is not a numeric conversion or a change of
physical unit.

## Strongest Evidence

{summary['scientific_closeout'].get('strongest_evidence', 'Not recorded by producer.')}

## Primary Limitation

{summary['scientific_closeout'].get('primary_limitation', 'Not recorded by producer.')}

## Suitable Use

{suitable}

## Unsupported Use

{unsuitable}

## Decision Boundary

This package validates software interoperability, explicit process-context
identity, and provenance transfer. It does not prove causal process-response
relationships, predictive generalization, phase or chemical-state assignments,
or engineering release readiness.
"""


def consume_characterization_bundle(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
) -> dict[str, Path]:
    """Validate a producer bundle and generate consumer-side integrated artifacts."""
    bundle = validate_characterization_bundle(manifest_path)
    process_input = (
        validate_external_process_input(bundle, process_table_path)
        if process_table_path is not None
        else _bundle_context_process_input(bundle)
    )

    output = Path(output_dir)
    _ensure_empty_output(output)
    normalized_input, normalization = _write_normalized_handoff_input(
        bundle.feature_table,
        output,
    )

    outputs: dict[str, Path] = {"normalized_bundle_input": normalized_input}
    if process_table_path is not None:
        process_input_path = output / EXTERNAL_PROCESS_INPUT_NAME
        process_input.table.to_csv(process_input_path, index=False)
        outputs["validated_process_input"] = process_input_path
    else:
        process_input_path = bundle.sample_context_path

    handoff_paths = run_characterization_handoff(
        [normalized_input],
        output,
        process_table_path=process_input_path,
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
        "process_input": process_input.metadata,
        "unit_label_normalization": normalization,
        "join_summary": join_summary,
        "software_validation": {
            "all_bundle_checksums_verified": True,
            "stable_feature_contract_validated": True,
            "sample_identity_sets_match": True,
            "external_process_table_used": bool(process_table_path is not None),
            "process_identity_columns_verified": process_input.metadata[
                "verified_identity_columns"
            ],
            "process_identity_mismatch_count": 0,
            "row_order_join_used": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
            "numeric_values_modified": False,
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

    outputs.update(
        {
            **handoff_paths,
            "cross_repository_summary": summary_path,
            "cross_repository_report": report_path,
        }
    )
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
                name: sha256_file(path)
                for name, path in sorted(bundle.evidence_paths.items())
            },
        },
        "process_input": process_input.metadata,
        "unit_label_normalization": normalization,
        "validation": summary["software_validation"],
        "join_summary": join_summary,
        "scientific_closeout": bundle.manifest["scientific_closeout"],
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {
            name: sha256_file(path) for name, path in outputs.items()
        },
    }
    manifest_output.write_text(
        json.dumps(
            consumer_manifest,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    outputs["cross_repository_manifest"] = manifest_output
    return outputs
