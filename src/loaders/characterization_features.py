"""Validated characterization-feature handoff for tabular analysis."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

SCHEMA_VERSION = "1.0"
REQUIRED_COLUMNS = [
    "sample_id",
    "measurement_id",
    "instrument",
    "feature_name",
    "feature_label",
    "value",
    "unit",
    "method",
    "source_file",
    "source_sha256",
    "preprocessing_id",
    "quality_flag",
]
REQUIRED_TEXT_COLUMNS = [
    "sample_id",
    "measurement_id",
    "instrument",
    "feature_name",
    "unit",
    "method",
    "quality_flag",
]
OPTIONAL_TEXT_COLUMNS = [
    "feature_label",
    "source_file",
    "source_sha256",
    "preprocessing_id",
]
SEMANTIC_COLUMNS = ["instrument", "feature_name", "feature_label", "unit"]
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA-256 digest for a local file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_characterization_features(
    table: pd.DataFrame,
    *,
    source_name: str = "characterization feature table",
) -> pd.DataFrame:
    """Validate and normalize the stable long-format feature-record contract."""
    missing = [column for column in REQUIRED_COLUMNS if column not in table.columns]
    if missing:
        raise ValueError(
            f"{source_name} is missing required column(s): {', '.join(missing)}"
        )

    normalized = table.loc[:, REQUIRED_COLUMNS].copy()
    for column in REQUIRED_TEXT_COLUMNS:
        normalized[column] = normalized[column].map(_clean_text)
        count = int(normalized[column].isna().sum())
        if count:
            raise ValueError(
                f"{source_name} contains {count} blank value(s) in {column}."
            )

    for column in OPTIONAL_TEXT_COLUMNS:
        normalized[column] = normalized[column].map(_clean_text)

    numeric = pd.to_numeric(normalized["value"], errors="coerce")
    if numeric.isna().any() or not numeric.map(
        lambda value: math.isfinite(float(value))
    ).all():
        raise ValueError(
            f"{source_name} contains missing, non-numeric, or non-finite "
            "feature value(s)."
        )
    normalized["value"] = numeric.astype(float)

    invalid_hashes = [
        value
        for value in normalized["source_sha256"].dropna().unique()
        if not SHA256_PATTERN.fullmatch(str(value))
    ]
    if invalid_hashes:
        raise ValueError(f"{source_name} contains invalid source_sha256 value(s).")

    if normalized.duplicated(keep=False).any():
        raise ValueError(f"{source_name} contains duplicate feature record row(s).")
    return normalized


def load_characterization_features(
    paths: Iterable[str | Path],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Load one or more feature CSVs and validate cross-file consistency."""
    input_paths = [Path(path) for path in paths]
    if not input_paths:
        raise ValueError("At least one characterization feature CSV is required.")

    tables: list[pd.DataFrame] = []
    sources: list[dict[str, Any]] = []
    for path in input_paths:
        if not path.is_file():
            raise FileNotFoundError(
                f"Characterization feature file not found: {path}"
            )
        table = validate_characterization_features(
            pd.read_csv(path), source_name=str(path)
        )
        tables.append(table)
        sources.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "row_count": int(len(table)),
            }
        )

    combined = validate_characterization_features(
        pd.concat(tables, ignore_index=True),
        source_name="combined characterization features",
    )
    _validate_measurement_mapping(combined)
    _validate_semantic_consistency(combined)
    _validate_sample_feature_uniqueness(combined)
    return combined, sources


def build_feature_dictionary(table: pd.DataFrame) -> pd.DataFrame:
    """Return one definition row per pivotable characterization feature."""
    validated = validate_characterization_features(table)
    _validate_semantic_consistency(validated)
    rows: list[dict[str, Any]] = []

    for values, group in validated.groupby(
        SEMANTIC_COLUMNS, dropna=False, sort=True
    ):
        instrument, feature_name, feature_label, unit = values
        rows.append(
            {
                "feature_key": feature_key(
                    instrument, feature_name, feature_label, unit
                ),
                "instrument": instrument,
                "feature_name": feature_name,
                "feature_label": feature_label,
                "unit": unit,
                "method": _single_value(group["method"], "method"),
                "preprocessing_id": _single_value(
                    group["preprocessing_id"],
                    "preprocessing_id",
                    optional=True,
                ),
                "quality_flags_observed": "|".join(
                    sorted(set(group["quality_flag"].astype(str)))
                ),
                "sample_count": int(group["sample_id"].nunique()),
                "measurement_count": int(group["measurement_id"].nunique()),
                "record_count": int(len(group)),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("feature_key")
        .reset_index(drop=True)
    )


def pivot_characterization_features(table: pd.DataFrame) -> pd.DataFrame:
    """Pivot unambiguous long features to one row per sample."""
    validated = validate_characterization_features(table)
    _validate_measurement_mapping(validated)
    _validate_semantic_consistency(validated)
    _validate_sample_feature_uniqueness(validated)

    working = validated.copy()
    working["feature_key"] = [
        feature_key(*values)
        for values in working[SEMANTIC_COLUMNS].itertuples(
            index=False, name=None
        )
    ]
    wide = working.pivot(
        index="sample_id", columns="feature_key", values="value"
    )
    wide = wide.sort_index().sort_index(axis=1).reset_index()
    wide.columns.name = None
    return wide


def load_process_table(
    path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load a process table requiring one explicit, unique row per sample."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Process table not found: {path}")

    table = pd.read_csv(path)
    if "sample_id" not in table.columns:
        raise ValueError(
            "Process table must contain an explicit sample_id column."
        )
    table = table.copy()
    table["sample_id"] = table["sample_id"].map(_clean_text)
    if table["sample_id"].isna().any():
        raise ValueError("Process table contains blank sample_id values.")
    if table["sample_id"].duplicated().any():
        values = sorted(
            table.loc[
                table["sample_id"].duplicated(keep=False), "sample_id"
            ].unique()
        )
        raise ValueError(
            "Process table sample_id values must be unique; duplicate(s): "
            + ", ".join(values)
        )

    return table, {
        "path": str(path),
        "sha256": sha256_file(path),
        "row_count": int(len(table)),
        "column_count": int(len(table.columns)),
    }


def integrate_process_and_characterization(
    process_table: pd.DataFrame,
    characterization_wide: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Outer-join by sample_id and produce an explicit match audit."""
    if (
        "sample_id" not in process_table.columns
        or "sample_id" not in characterization_wide.columns
    ):
        raise ValueError("Both tables must contain sample_id.")
    if (
        process_table["sample_id"].duplicated().any()
        or characterization_wide["sample_id"].duplicated().any()
    ):
        raise ValueError("Both tables must contain unique sample_id values.")

    collisions = sorted(
        (set(process_table.columns) & set(characterization_wide.columns))
        - {"sample_id"}
    )
    if collisions:
        raise ValueError(
            "Process table collides with characterization feature column(s): "
            + ", ".join(collisions)
        )

    integrated = process_table.merge(
        characterization_wide,
        on="sample_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
        sort=True,
    )
    mapping = {
        "both": "matched",
        "left_only": "process_only",
        "right_only": "characterization_only",
    }
    audit = integrated[["sample_id", "_merge"]].copy()
    audit["join_status"] = audit["_merge"].astype(str).map(mapping)
    audit = (
        audit.drop(columns="_merge")
        .sort_values("sample_id")
        .reset_index(drop=True)
    )
    integrated = (
        integrated.drop(columns="_merge")
        .sort_values("sample_id")
        .reset_index(drop=True)
    )
    return integrated, audit


def run_characterization_handoff(
    characterization_paths: Iterable[str | Path],
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
) -> dict[str, Path]:
    """Execute validation, pivot, optional sample join, and manifest writing."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    long_table, sources = load_characterization_features(
        characterization_paths
    )
    dictionary = build_feature_dictionary(long_table)
    wide = pivot_characterization_features(long_table)

    paths = {
        "validated_long": output_dir
        / "characterization_features_validated_long.csv",
        "feature_dictionary": output_dir
        / "characterization_feature_dictionary.csv",
        "wide_features": output_dir / "characterization_features_wide.csv",
        "manifest": output_dir / "characterization_handoff_manifest.json",
    }
    long_table.sort_values(
        [
            "sample_id",
            "instrument",
            "feature_name",
            "feature_label",
            "measurement_id",
        ],
        na_position="last",
    ).to_csv(paths["validated_long"], index=False)
    dictionary.to_csv(paths["feature_dictionary"], index=False)
    wide.to_csv(paths["wide_features"], index=False)

    process_source = None
    join_summary = None
    if process_table_path is not None:
        process, process_source = load_process_table(process_table_path)
        integrated, audit = integrate_process_and_characterization(
            process, wide
        )
        paths["integrated_table"] = output_dir / "integrated_sample_table.csv"
        paths["join_audit"] = output_dir / "sample_join_audit.csv"
        integrated.to_csv(paths["integrated_table"], index=False)
        audit.to_csv(paths["join_audit"], index=False)
        join_summary = {
            status: int(audit["join_status"].eq(status).sum())
            for status in (
                "matched",
                "process_only",
                "characterization_only",
            )
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workflow": "characterization_feature_handoff",
        "characterization_sources": sources,
        "process_source": process_source,
        "counts": {
            "feature_record_count": int(len(long_table)),
            "sample_count": int(long_table["sample_id"].nunique()),
            "measurement_count": int(
                long_table["measurement_id"].nunique()
            ),
            "feature_definition_count": int(len(dictionary)),
            "wide_feature_count": int(max(len(wide.columns) - 1, 0)),
        },
        "quality_flag_counts": {
            str(key): int(value)
            for key, value in long_table["quality_flag"]
            .value_counts()
            .sort_index()
            .items()
        },
        "provenance_coverage": {
            "source_sha256_record_count": int(
                long_table["source_sha256"].notna().sum()
            ),
            "preprocessing_id_record_count": int(
                long_table["preprocessing_id"].notna().sum()
            ),
        },
        "join_summary": join_summary,
        "outputs": {
            name: str(path)
            for name, path in paths.items()
            if name != "manifest"
        },
        "scientific_boundary": {
            "software_validation": "handoff_contract_validated",
            "scientific_validation": "not_established_by_handoff",
            "row_order_join_used": False,
            "duplicate_feature_aggregation_performed": False,
            "mixed_method_or_preprocessing_accepted": False,
            "missing_metadata_inferred": False,
            "limitations": [
                "Feature extraction validity remains instrument- and experiment-specific.",
                "Matching sample_id values do not by themselves prove physical sample identity.",
                "Quality flags are preserved and are not automatic inclusion or exclusion decisions.",
                "The integrated table supports downstream analysis only after sample comparability and target validity review.",
            ],
        },
    }
    paths["manifest"].write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths


def feature_key(
    instrument: object,
    feature_name: object,
    feature_label: object,
    unit: object,
) -> str:
    """Build a stable, collision-resistant wide-column name."""
    parts = ["char", _slug(instrument), _slug(feature_name)]
    if not pd.isna(feature_label) and str(feature_label).strip():
        parts.append(_slug(feature_label))
    parts.append(_slug(unit))
    return "__".join(parts)


def _validate_measurement_mapping(table: pd.DataFrame) -> None:
    invalid = []
    for measurement_id, group in table.groupby(
        "measurement_id", dropna=False
    ):
        if len(group[["sample_id", "instrument"]].drop_duplicates()) != 1:
            invalid.append(str(measurement_id))
    if invalid:
        raise ValueError(
            "Each measurement_id must map to exactly one sample_id and "
            "instrument; invalid measurement_id(s): "
            + ", ".join(sorted(invalid))
        )


def _validate_semantic_consistency(table: pd.DataFrame) -> None:
    for values, group in table.groupby(SEMANTIC_COLUMNS, dropna=False):
        label = feature_key(*values)
        if group["method"].nunique(dropna=False) != 1:
            raise ValueError(f"Feature {label} has mixed method values.")
        preprocessing = group["preprocessing_id"].fillna("<missing>")
        if preprocessing.nunique(dropna=False) != 1:
            raise ValueError(
                f"Feature {label} has mixed preprocessing_id values."
            )


def _validate_sample_feature_uniqueness(table: pd.DataFrame) -> None:
    working = table.assign(
        _label_key=table["feature_label"].fillna("")
    )
    duplicate = working.duplicated(
        [
            "sample_id",
            "instrument",
            "feature_name",
            "_label_key",
            "unit",
        ],
        keep=False,
    )
    if duplicate.any():
        raise ValueError(
            "A sample has multiple records for the same semantic feature. "
            "Select or predeclare an aggregation before handoff."
        )


def _single_value(
    series: pd.Series,
    field_name: str,
    *,
    optional: bool = False,
) -> str | None:
    values = sorted(set(series.fillna("<missing>").astype(str)))
    if len(values) != 1:
        raise ValueError(
            f"Feature definition has mixed {field_name} values."
        )
    return None if optional and values[0] == "<missing>" else values[0]


def _slug(value: object) -> str:
    text = re.sub(
        r"[^a-z0-9]+", "_", str(value).strip().lower()
    ).strip("_")
    if not text:
        raise ValueError(
            f"Could not create a stable feature key from value: {value!r}"
        )
    return text


def _clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
