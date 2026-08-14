"""Independent semantic evidence-binding verification for characterization bundles."""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from .characterization_features import REQUIRED_COLUMNS

CONTRACT_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SOURCE_RECORD_CONTAINER_KEYS = {
    "sources",
    "source_files",
    "source_records",
    "files",
    "input_files",
    "raw_files",
    "archive_members",
    "raw_archive_members",
}
_SOURCE_RECORD_KEYS = {
    "source",
    "source_file",
    "source_record",
    "measurement_source",
    "raw_source",
    "raw_file",
    "input_file",
    "archive_member",
    "workbook",
}
_SOURCE_IDENTITY_FIELDS = {
    "path",
    "filename",
    "source_file",
    "url",
    "download_url",
    "record_url",
    "member_path",
    "archive_member",
    "doi",
    "provenance_type",
    "source_type",
}
_EXPLICIT_SOURCE_DIGEST_KEYS = {"source_sha256", "file_sha256", "member_sha256"}


def validate_required_evidence_identity_binding(
    *,
    manifest: Mapping[str, Any],
    feature_table: pd.DataFrame,
    evidence_paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Recompute a producer-declared evidence identity contract in the consumer.

    Legacy bundles without the optional sub-contract retain checksum-only semantics.
    When the producer declares the contract as required, the consumer independently
    recomputes all semantic bindings from the checksum-verified evidence files.
    """
    contract = _contract(manifest)
    if contract is None:
        return {
            "contract_present": False,
            "contract_required": False,
            "legacy_checksum_only_validation": True,
            "semantic_identity_binding_verified": False,
            "scientific_comparability_established": False,
        }

    required_evidence = {"source_manifest", "analysis_manifest", "comparability_matrix"}
    if set(evidence_paths) != required_evidence:
        raise ValueError("consumer evidence binding requires all three evidence paths")
    case_id = manifest.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("consumer evidence binding requires bundle case_id")

    analysis = _analysis_binding(evidence_paths["analysis_manifest"], feature_table)
    source = _source_binding(
        evidence_paths["source_manifest"], feature_table, case_id=case_id.strip()
    )
    comparability = _comparability_binding(
        evidence_paths["comparability_matrix"], feature_table
    )
    return {
        "contract_present": True,
        "contract_required": True,
        "contract_schema_version": CONTRACT_VERSION,
        "legacy_checksum_only_validation": False,
        "semantic_identity_binding_verified": True,
        **analysis,
        **source,
        **comparability,
        "scientific_comparability_established": False,
    }


def _contract(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    if "evidence_identity_binding_contract" not in manifest:
        return None
    raw = manifest["evidence_identity_binding_contract"]
    if not isinstance(raw, Mapping):
        raise ValueError("evidence_identity_binding_contract must be an object")
    if set(raw) != {"schema_version", "required"}:
        raise ValueError(
            "evidence_identity_binding_contract must contain schema_version and required exactly"
        )
    if raw.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unsupported evidence_identity_binding_contract schema_version")
    if raw.get("required") is not True:
        raise ValueError("evidence_identity_binding_contract.required must be true")
    return {"schema_version": CONTRACT_VERSION, "required": True}


def _analysis_binding(path: Path, feature_table: pd.DataFrame) -> dict[str, Any]:
    payload = _load_json_object(path, "analysis manifest")
    analyses = payload.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        raise ValueError("analysis manifest must contain at least one analysis")
    analysis_count = payload.get("analysis_count")
    if isinstance(analysis_count, bool) or not isinstance(analysis_count, int):
        raise ValueError("analysis manifest analysis_count must be an integer")
    if analysis_count != len(analyses):
        raise ValueError("analysis manifest analysis_count does not match analyses")

    rows: list[dict[str, Any]] = []
    for index, analysis in enumerate(analyses):
        if not isinstance(analysis, Mapping):
            raise ValueError(f"analysis manifest entry {index} must be an object")
        features = analysis.get("features")
        if not isinstance(features, list):
            raise ValueError(f"analysis manifest entry {index} features must be a list")
        for feature_index, feature in enumerate(features):
            if not isinstance(feature, Mapping):
                raise ValueError("analysis feature entries must be objects")
            value = feature.get("value")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(
                    "analysis manifest feature value must be a finite JSON number; "
                    f"entry={index}, feature={feature_index}"
                )
            rows.append(dict(feature))
    if not rows:
        raise ValueError("analysis manifest contains no feature records")

    reconstructed = pd.DataFrame(rows)
    if reconstructed.columns.tolist() != REQUIRED_COLUMNS:
        missing = [item for item in REQUIRED_COLUMNS if item not in reconstructed.columns]
        extra = [item for item in reconstructed.columns if item not in REQUIRED_COLUMNS]
        if missing or extra:
            raise ValueError(
                f"analysis manifest feature schema mismatch; missing={missing}, extra={extra}"
            )
        reconstructed = reconstructed.loc[:, REQUIRED_COLUMNS]
    numeric = pd.to_numeric(reconstructed["value"], errors="coerce")
    if numeric.isna().any():
        raise ValueError("analysis manifest contains non-numeric feature values")
    reconstructed["value"] = numeric.astype(float)

    serialized = _csv_roundtrip(reconstructed)
    if _normalized_feature_rows(serialized) != _normalized_feature_rows(feature_table):
        raise ValueError(
            "required evidence identity binding failed: analysis manifest does not reproduce feature table"
        )
    return {
        "analysis_manifest_features_reproduced": True,
        "analysis_manifest_feature_count": len(reconstructed),
        "analysis_manifest_csv_boundary_replayed": True,
    }


def _source_binding(
    path: Path,
    feature_table: pd.DataFrame,
    *,
    case_id: str,
) -> dict[str, Any]:
    source = _load_json_object(path, "source manifest")
    source_case_id = source.get("case_id")
    case_id_checked = source_case_id is not None
    if case_id_checked and (
        not isinstance(source_case_id, str) or source_case_id.strip() != case_id
    ):
        raise ValueError(
            "required evidence identity binding failed: source manifest case_id mismatch"
        )

    raw_digests = feature_table["source_sha256"].astype("string")
    if raw_digests.isna().any() or raw_digests.str.strip().eq("").any():
        raise ValueError(
            "required evidence identity binding failed: every feature row requires source_sha256"
        )
    feature_digests = {str(value).strip().lower() for value in raw_digests}
    source_digests = _collect_source_record_sha256_values(source)
    missing = sorted(feature_digests - source_digests)
    if missing:
        raise ValueError(
            "required evidence identity binding failed: source manifest does not bind every feature source_sha256; "
            f"missing={missing}"
        )
    return {
        "every_feature_row_source_sha256_bound": True,
        "feature_source_sha256_count": len(feature_digests),
        "source_manifest_sha256_value_count": len(source_digests),
        "source_manifest_case_id_checked": case_id_checked,
        "source_digest_scope": "recognized_source_records_only",
    }


def _comparability_binding(path: Path, feature_table: pd.DataFrame) -> dict[str, Any]:
    try:
        table = pd.read_csv(path, dtype="string")
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"could not read comparability matrix: {path}") from exc
    if table.empty:
        raise ValueError("comparability matrix must not be empty")

    axes: list[str] = []
    sample_values: pd.Series | None = None
    modality_values: pd.Series | None = None
    if "sample_id" in table.columns:
        sample_values = _normalized_text_series(table["sample_id"], "sample_id")
        observed = set(sample_values)
        required = {str(value).strip() for value in feature_table["sample_id"]}
        missing = sorted(required - observed)
        if missing:
            raise ValueError(
                "required evidence identity binding failed: comparability matrix misses feature sample_id values; "
                f"missing={missing}"
            )
        axes.append("sample_id")

    modality_column = "modality" if "modality" in table.columns else None
    if modality_column is None and "instrument" in table.columns:
        modality_column = "instrument"
    if modality_column is not None:
        modality_values = _normalized_text_series(
            table[modality_column], modality_column
        ).str.casefold()
        observed = set(modality_values)
        required = {
            str(value).strip().casefold() for value in feature_table["instrument"]
        }
        missing = sorted(required - observed)
        if missing:
            raise ValueError(
                "required evidence identity binding failed: comparability matrix misses feature instruments; "
                f"missing={missing}"
            )
        axes.append(modality_column)

    pair_verified = False
    if sample_values is not None and modality_values is not None:
        observed_pairs = set(zip(sample_values, modality_values, strict=True))
        required_pairs = {
            (str(row.sample_id).strip(), str(row.instrument).strip().casefold())
            for row in feature_table[["sample_id", "instrument"]].itertuples(index=False)
        }
        missing_pairs = sorted(required_pairs - observed_pairs)
        if missing_pairs:
            raise ValueError(
                "required evidence identity binding failed: comparability matrix misses sample/instrument pairs; "
                f"missing={missing_pairs}"
            )
        pair_verified = True

    if not axes:
        raise ValueError(
            "required evidence identity binding failed: comparability matrix exposes no sample_id, modality, or instrument axis"
        )
    return {
        "comparability_identity_coverage_verified": True,
        "comparability_binding_axes": axes,
        "comparability_sample_instrument_pair_coverage_verified": pair_verified,
    }


def _normalized_text_series(series: pd.Series, label: str) -> pd.Series:
    values = series.astype("string")
    if values.isna().any() or values.str.strip().eq("").any():
        raise ValueError(f"comparability matrix contains blank {label} values")
    return values.str.strip()


def _csv_roundtrip(table: pd.DataFrame) -> pd.DataFrame:
    buffer = StringIO()
    table.to_csv(buffer, index=False, lineterminator="\n")
    buffer.seek(0)
    return pd.read_csv(buffer)


def _normalized_feature_rows(table: pd.DataFrame) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for raw in table.itertuples(index=False, name=None):
        normalized: list[object] = []
        for index, value in enumerate(raw):
            if index == 5:
                normalized.append(float(value))
            elif pd.isna(value):
                normalized.append(None)
            else:
                normalized.append(str(value).strip())
        rows.append(tuple(normalized))
    return sorted(rows, key=repr)


def _collect_source_record_sha256_values(source: Mapping[str, Any]) -> set[str]:
    """Collect digests only from records that are structurally source-scoped.

    Generic or explicit-looking checksums in audit/expected/output metadata are not
    evidence that a feature's source bytes are represented by the source manifest.
    Digests are accepted only on a recognized source record.  At the source-manifest
    root, an explicit source digest is allowed directly, while a generic ``sha256``
    still requires an independent source-identity field such as ``source`` or path.
    """
    digests: set[str] = set()

    def visit(
        value: object,
        *,
        source_scoped: bool,
        record_key: str | None,
        is_root: bool,
    ) -> None:
        if isinstance(value, Mapping):
            keys = {str(key).strip().lower() for key in value}
            current_scoped = source_scoped or (
                record_key in _SOURCE_RECORD_KEYS
                or record_key in _SOURCE_RECORD_CONTAINER_KEYS
            )
            source_record = (
                current_scoped
                or bool(keys & _SOURCE_IDENTITY_FIELDS)
                or (is_root and "source" in keys)
            )
            for key, item in value.items():
                key_text = str(key).strip().lower()
                valid_digest = (
                    isinstance(item, str)
                    and _SHA256.fullmatch(item.strip()) is not None
                )
                if (
                    key_text in _EXPLICIT_SOURCE_DIGEST_KEYS
                    and valid_digest
                    and (source_record or is_root)
                ):
                    digests.add(item.strip().lower())
                elif key_text == "sha256" and valid_digest and source_record:
                    digests.add(item.strip().lower())

                child_scoped = current_scoped or key_text in _SOURCE_RECORD_CONTAINER_KEYS
                child_record_key = key_text if isinstance(item, Mapping) else record_key
                visit(
                    item,
                    source_scoped=child_scoped,
                    record_key=child_record_key,
                    is_root=False,
                )
        elif isinstance(value, list):
            for item in value:
                visit(
                    item,
                    source_scoped=source_scoped,
                    record_key=record_key,
                    is_root=False,
                )

    visit(source, source_scoped=False, record_key=None, is_root=True)
    return digests


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in evidence binding input: {key}")
        result[key] = value
    return result


__all__ = ["CONTRACT_VERSION", "validate_required_evidence_identity_binding"]
