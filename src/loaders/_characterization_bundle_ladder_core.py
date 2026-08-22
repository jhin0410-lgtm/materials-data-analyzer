"""Validate and consume versioned cross-repository characterization bundles.

Schema 1.0 retains the historical checksum/evidence-identity contract. Schema 1.1
adds a required, independently replayed L0-L8 scientific evidence-ladder binding.
The ladder is evidence-maturity metadata only and never authorizes downstream use.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from . import _characterization_bundle_core as _core
from .characterization_evidence_binding import (
    validate_required_evidence_identity_binding,
)
from .characterization_evidence_ladder import (
    validate_characterization_evidence_ladder_record,
)
from .characterization_features import (
    REQUIRED_COLUMNS,
    run_characterization_handoff,
    sha256_file,
    validate_characterization_features,
)

BUNDLE_SCHEMA_VERSION = "1.0"
EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION = "1.1"
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = {
    BUNDLE_SCHEMA_VERSION,
    EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION,
}
BUNDLE_TYPE = _core.BUNDLE_TYPE
CONSUMER_SCHEMA_VERSION = _core.CONSUMER_SCHEMA_VERSION
SUMMARY_NAME = _core.SUMMARY_NAME
REPORT_NAME = _core.REPORT_NAME
MANIFEST_NAME = _core.MANIFEST_NAME
NORMALIZED_INPUT_NAME = _core.NORMALIZED_INPUT_NAME
EXTERNAL_PROCESS_INPUT_NAME = _core.EXTERNAL_PROCESS_INPUT_NAME
UNIT_LABEL_RULE = _core.UNIT_LABEL_RULE
PROCESS_IDENTITY_COLUMNS = _core.PROCESS_IDENTITY_COLUMNS


@dataclass(frozen=True)
class ValidatedCharacterizationBundle:
    manifest_path: Path
    manifest: dict[str, Any]
    feature_path: Path
    sample_context_path: Path
    evidence_paths: dict[str, Path]
    feature_table: pd.DataFrame
    sample_context: pd.DataFrame
    evidence_identity_binding: dict[str, Any]
    evidence_ladder_path: Path | None
    evidence_ladder_record: dict[str, Any] | None
    evidence_ladder_assessment: dict[str, Any] | None


ValidatedProcessInput = _core.ValidatedProcessInput


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in characterization bundle: {key}")
        result[key] = value
    return result


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"{label} not found or unsafe: {path}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {label}: {path}") from exc
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
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size != target.stat().st_size
    ):
        raise ValueError(f"{label} size_bytes does not match the referenced file.")
    return target


def validate_characterization_bundle(
    manifest_path: str | Path,
) -> ValidatedCharacterizationBundle:
    """Validate bundle identity, empirical evidence, and optional maturity state."""
    manifest_path = Path(manifest_path)
    manifest = _read_json_object(manifest_path, "characterization bundle manifest")
    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise ValueError(
            f"Unsupported characterization bundle schema_version: {schema_version}"
        )
    ladder_present = "scientific_evidence_ladder" in manifest
    if schema_version == BUNDLE_SCHEMA_VERSION and ladder_present:
        raise ValueError(
            "schema-1.0 characterization bundle must not contain scientific_evidence_ladder"
        )
    if schema_version == EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION and not ladder_present:
        raise ValueError(
            "schema-1.1 characterization bundle requires scientific_evidence_ladder"
        )
    if manifest.get("bundle_type") != BUNDLE_TYPE:
        raise ValueError(
            f"Unsupported characterization bundle_type: {manifest.get('bundle_type')}"
        )
    case_id = manifest.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
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
            sorted(Counter(str(value) for value in features["quality_flag"]).items())
        ),
        "source_sha256_record_count": int(features["source_sha256"].notna().sum()),
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
    if set(context["sample_id"].astype(str)) != set(features["sample_id"].astype(str)):
        raise ValueError(
            "Feature and sample-context sample_id sets must match exactly."
        )

    evidence_identity_binding = validate_required_evidence_identity_binding(
        manifest=manifest,
        feature_table=features,
        evidence_paths=evidence_paths,
    )

    closeout = _as_dict(manifest.get("scientific_closeout"), "scientific_closeout")
    if not isinstance(closeout.get("evidence_level"), str):
        raise ValueError("scientific_closeout evidence_level is required.")
    for field in ("suitable_for", "unsuitable_for"):
        if not isinstance(closeout.get(field), list):
            raise ValueError(f"scientific_closeout {field} must be a list.")

    ladder_path: Path | None = None
    ladder_record: dict[str, Any] | None = None
    ladder_assessment: dict[str, Any] | None = None
    if schema_version == EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION:
        ladder_record, ladder_path, ladder_assessment = (
            validate_characterization_evidence_ladder_record(
                root,
                manifest["scientific_evidence_ladder"],
                case_id=case_id,
                evidence_references=evidence_records,
                instruments=expected_feature_metadata["instruments"],
            )
        )

    return ValidatedCharacterizationBundle(
        manifest_path=manifest_path,
        manifest=manifest,
        feature_path=feature_path,
        sample_context_path=context_path,
        evidence_paths=evidence_paths,
        feature_table=features,
        sample_context=context,
        evidence_identity_binding=evidence_identity_binding,
        evidence_ladder_path=ladder_path,
        evidence_ladder_record=ladder_record,
        evidence_ladder_assessment=ladder_assessment,
    )


validate_external_process_input = _core.validate_external_process_input


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


def _ladder_summary(bundle: ValidatedCharacterizationBundle) -> dict[str, Any]:
    if bundle.evidence_ladder_assessment is None:
        return {
            "present": False,
            "verified": False,
            "record": None,
            "assessment": None,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
        }
    return {
        "present": True,
        "verified": True,
        "record": bundle.evidence_ladder_record,
        "assessment": bundle.evidence_ladder_assessment,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
    }


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
    _core._ensure_empty_output(output)
    normalized_input, normalization = _core._write_normalized_handoff_input(
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
    ladder = _ladder_summary(bundle)
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
        "evidence_identity_binding": bundle.evidence_identity_binding,
        "scientific_evidence_ladder": ladder,
        "software_validation": {
            "all_bundle_checksums_verified": True,
            "stable_feature_contract_validated": True,
            "sample_identity_sets_match": True,
            "evidence_identity_binding_contract_present": bundle.evidence_identity_binding[
                "contract_present"
            ],
            "semantic_evidence_identity_binding_verified": bundle.evidence_identity_binding[
                "semantic_identity_binding_verified"
            ],
            "legacy_checksum_only_evidence_validation": bundle.evidence_identity_binding[
                "legacy_checksum_only_validation"
            ],
            "scientific_evidence_ladder_present": ladder["present"],
            "scientific_evidence_ladder_independently_replayed": ladder["verified"],
            "scientific_comparability_established": False,
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
    report_path.write_text(_core._build_report(summary), encoding="utf-8")

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
            "scientific_evidence_ladder_sha256": (
                sha256_file(bundle.evidence_ladder_path)
                if bundle.evidence_ladder_path is not None
                else None
            ),
        },
        "process_input": process_input.metadata,
        "unit_label_normalization": normalization,
        "evidence_identity_binding": bundle.evidence_identity_binding,
        "scientific_evidence_ladder": ladder,
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


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION",
    "SUPPORTED_BUNDLE_SCHEMA_VERSIONS",
    "BUNDLE_TYPE",
    "CONSUMER_SCHEMA_VERSION",
    "SUMMARY_NAME",
    "REPORT_NAME",
    "MANIFEST_NAME",
    "NORMALIZED_INPUT_NAME",
    "EXTERNAL_PROCESS_INPUT_NAME",
    "UNIT_LABEL_RULE",
    "ValidatedCharacterizationBundle",
    "ValidatedProcessInput",
    "consume_characterization_bundle",
    "validate_characterization_bundle",
    "validate_external_process_input",
]
