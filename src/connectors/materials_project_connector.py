"""Materials Project ingestion connector."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import hashlib
from datetime import datetime, timezone

import pandas as pd

from config import PROJECT_ROOT

from connectors.base import BaseConnector, IngestionResult


RAW_DIR = PROJECT_ROOT / "data" / "raw" / "materials_project"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "materials_project_fe_si.csv"
RAW_PATH = RAW_DIR / "mp_fe_si_raw.json"
MP_FIELDS = [
    "material_id",
    "formula_pretty",
    "band_gap",
    "formation_energy_per_atom",
    "energy_above_hull",
    "density",
    "volume",
]
MP_FIELD_TO_OUTPUT_COLUMN = {
    "material_id": "material_id",
    "formula_pretty": "formula",
    "band_gap": "band_gap_ev",
    "formation_energy_per_atom": "formation_energy_ev_atom",
    "energy_above_hull": "energy_above_hull_ev_atom",
    "density": "density_g_cm3",
    "volume": "volume_a3",
}
QUERY_SPEC_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_name",
    "source_system",
    "case_study_scope",
    "query_mode",
    "required_elements",
    "excluded_elements",
    "chemical_system_policy",
    "requested_fields",
    "optional_filters",
    "result_limit",
    "expected_identifier_column",
    "provenance_status",
    "notes",
]
ALLOWED_PROVENANCE_STATUS = {"exact", "reconstructed", "incomplete"}
QUERY_SPEC_CREDENTIAL_TOKENS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "credential",
    "password",
}


def serialize_mp_doc(doc: Any) -> dict[str, Any]:
    """Convert Materials Project document objects to plain dictionaries."""
    if hasattr(doc, "model_dump"):
        return doc.model_dump()
    if hasattr(doc, "dict"):
        return doc.dict()
    if isinstance(doc, dict):
        return doc
    return {
        field: getattr(doc, field, None)
        for field in MP_FIELDS
    }


def build_materials_project_dataframe(docs: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the analyzer-ready Materials Project processed table."""
    rows = []
    for doc in docs:
        rows.append(
            {
                "material_id": str(doc.get("material_id", "")),
                "formula": doc.get("formula_pretty"),
                "band_gap_ev": doc.get("band_gap"),
                "formation_energy_ev_atom": doc.get("formation_energy_per_atom"),
                "energy_above_hull_ev_atom": doc.get("energy_above_hull"),
                "density_g_cm3": doc.get("density"),
                "volume_a3": doc.get("volume"),
            }
        )
    return pd.DataFrame(rows)


def load_query_spec(path: str | Path) -> dict[str, Any]:
    """Load a credential-free Materials Project query specification."""
    with Path(path).open(encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError("Materials Project query spec must be a JSON object.")
    validate_query_spec(spec)
    return spec


def _contains_absolute_path(value: Any) -> bool:
    """Return whether a JSON value contains an absolute local path string."""
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped.startswith("/") or (len(stripped) >= 3 and stripped[1:3] == ":\\"))
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False


def _contains_credential_like_key(value: Any) -> bool:
    """Return whether a JSON object contains credential-like keys."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(token in normalized_key for token in QUERY_SPEC_CREDENTIAL_TOKENS):
                return True
            if _contains_credential_like_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_credential_like_key(item) for item in value)
    return False


def validate_query_spec(spec: dict[str, Any]) -> None:
    """Validate a credential-free Materials Project query contract."""
    missing_fields = [field for field in QUERY_SPEC_REQUIRED_FIELDS if field not in spec]
    if missing_fields:
        raise ValueError(
            "Materials Project query spec is missing required field(s): "
            + ", ".join(missing_fields)
        )
    if _contains_credential_like_key(spec):
        raise ValueError("Materials Project query spec must not contain credential-like keys.")
    if _contains_absolute_path(spec):
        raise ValueError("Materials Project query spec must not contain absolute paths.")

    required_elements = spec["required_elements"]
    if (
        not isinstance(required_elements, list)
        or not required_elements
        or not all(isinstance(element, str) and element for element in required_elements)
    ):
        raise ValueError("required_elements must be a non-empty list of element symbols.")

    requested_fields = spec["requested_fields"]
    if (
        not isinstance(requested_fields, list)
        or not requested_fields
        or not all(isinstance(field, str) and field for field in requested_fields)
    ):
        raise ValueError("requested_fields must be a non-empty list of field names.")
    if len(requested_fields) != len(set(requested_fields)):
        raise ValueError("requested_fields must not contain duplicate field names.")

    result_limit = spec.get("result_limit")
    if result_limit is not None:
        if not isinstance(result_limit, int) or result_limit <= 0:
            raise ValueError("result_limit must be a positive integer when provided.")

    if spec["provenance_status"] not in ALLOWED_PROVENANCE_STATUS:
        raise ValueError(
            "provenance_status must be one of: "
            + ", ".join(sorted(ALLOWED_PROVENANCE_STATUS))
        )


def build_query_parameters(spec: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic API query parameters from a validated query spec."""
    validate_query_spec(spec)
    return {
        "elements": list(spec["required_elements"]),
        "fields": list(spec["requested_fields"]),
        "num_chunks": 1,
        "chunk_size": spec.get("result_limit"),
    }


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate SHA-256 for a local artifact without modifying it."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _credential_like_value_count(df: pd.DataFrame) -> int:
    """Count credential-like strings in object columns."""
    text_columns = df.select_dtypes(exclude="number").columns
    count = 0
    for column in text_columns:
        count += int(
            df[column]
            .dropna()
            .astype(str)
            .str.contains(
                r"api[_-]?key|token|secret|credential|password|sk-",
                case=False,
                regex=True,
            )
            .sum()
        )
    return count


def _absolute_path_value_count(df: pd.DataFrame) -> int:
    """Count absolute local path-like strings in object columns."""
    text_columns = df.select_dtypes(exclude="number").columns
    count = 0
    for column in text_columns:
        count += int(
            df[column]
            .dropna()
            .astype(str)
            .str.contains(r"^[A-Za-z]:\\|^/|^\\\\", regex=True)
            .sum()
        )
    return count


def create_provenance_manifest(
    *,
    df: pd.DataFrame,
    artifact_path: str | Path,
    query_spec: dict[str, Any],
    query_spec_path: str | Path,
    generated_manifest_timestamp: str | None = None,
) -> dict[str, Any]:
    """Create a compact local-artifact provenance manifest."""
    validate_query_spec(query_spec)
    artifact = Path(artifact_path)
    identifier_column = query_spec["expected_identifier_column"]
    unique_identifier_count = (
        int(df[identifier_column].nunique(dropna=True))
        if identifier_column in df.columns
        else 0
    )
    duplicate_identifier_count = (
        int(df[identifier_column].duplicated().sum())
        if identifier_column in df.columns
        else 0
    )
    credential_count = _credential_like_value_count(df)
    absolute_path_count = _absolute_path_value_count(df)
    return {
        "manifest_schema_version": "1.0",
        "dataset_name": query_spec["dataset_name"],
        "source_system": query_spec["source_system"],
        "query_spec_path": Path(query_spec_path).as_posix(),
        "local_artifact_path": artifact.as_posix(),
        "artifact_file_name": artifact.name,
        "artifact_sha256": calculate_file_sha256(artifact),
        "file_size_bytes": artifact.stat().st_size,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": df.columns.tolist(),
        "identifier_column": identifier_column,
        "unique_identifier_count": unique_identifier_count,
        "duplicate_identifier_count": duplicate_identifier_count,
        "required_elements": list(query_spec["required_elements"]),
        "scope_description": query_spec["case_study_scope"],
        "query_provenance_status": query_spec["provenance_status"],
        "retrieval_timestamp": None,
        "api_version": None,
        "generated_manifest_timestamp": generated_manifest_timestamp
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "credential_included": bool(credential_count),
        "absolute_path_included": bool(absolute_path_count),
        "requested_fields": list(query_spec["requested_fields"]),
        "mapped_requested_columns": [
            MP_FIELD_TO_OUTPUT_COLUMN.get(field, field)
            for field in query_spec["requested_fields"]
        ],
        "missing_requested_columns": [
            MP_FIELD_TO_OUTPUT_COLUMN.get(field, field)
            for field in query_spec["requested_fields"]
            if MP_FIELD_TO_OUTPUT_COLUMN.get(field, field) not in df.columns
        ],
        "extra_columns": [
            column
            for column in df.columns
            if column
            not in {
                MP_FIELD_TO_OUTPUT_COLUMN.get(field, field)
                for field in query_spec["requested_fields"]
            }
        ],
        "notes": [
            "Local artifact provenance is incomplete; retrieval timestamp and API version are unknown.",
            "This is an Fe/Si-containing multi-component sample, not a binary Fe-Si dataset.",
            "No API key or credential is included in this manifest.",
        ],
    }


def _example_values(series: pd.Series, limit: int = 3) -> str:
    """Return short example values for a property inventory cell."""
    values = series.dropna().astype(str).drop_duplicates().head(limit).tolist()
    return "; ".join(values)


def build_property_inventory(df: pd.DataFrame) -> pd.DataFrame:
    """Build a compact Materials Project property/field inventory."""
    rows: list[dict[str, Any]] = []
    for column in df.columns:
        series = df[column]
        is_numeric = pd.api.types.is_numeric_dtype(series)
        semantic_role, unit, target_candidate, feature_candidate, leakage_risk, note = (
            _classify_materials_project_column(column)
        )
        rows.append(
            {
                "column_name": column,
                "inferred_dtype": str(series.dtype),
                "semantic_role": semantic_role,
                "unit": unit,
                "non_null_count": int(series.notna().sum()),
                "null_count": int(series.isna().sum()),
                "null_percentage": round(float(series.isna().mean() * 100.0), 4),
                "unique_count": int(series.nunique(dropna=True)),
                "example_values": _example_values(series),
                "numeric_min": series.min() if is_numeric else pd.NA,
                "numeric_median": series.median() if is_numeric else pd.NA,
                "numeric_max": series.max() if is_numeric else pd.NA,
                "constant_column": bool(series.nunique(dropna=False) <= 1),
                "identifier_column": bool(column == "material_id"),
                "target_candidate": bool(target_candidate),
                "feature_candidate": bool(feature_candidate),
                "leakage_risk": leakage_risk,
                "interpretation_note": note,
            }
        )
    return pd.DataFrame(rows)


def _classify_materials_project_column(
    column: str,
) -> tuple[str, str, bool, bool, str, str]:
    """Classify one current Materials Project processed column."""
    if column == "material_id":
        return (
            "identifier",
            "unknown",
            False,
            False,
            "identifier only",
            "Use for uniqueness/provenance checks, not as a predictive feature.",
        )
    if column == "formula":
        return (
            "composition",
            "unknown",
            False,
            False,
            "conditional",
            "Composition label; featurize or group before modeling.",
        )
    if column == "band_gap_ev":
        return (
            "electronic_property",
            "eV",
            True,
            True,
            "conditional",
            "Potential pilot target; avoid identifier/formula leakage.",
        )
    if column == "formation_energy_ev_atom":
        return (
            "thermodynamic_property",
            "eV/atom",
            True,
            True,
            "leakage candidate",
            "Closely related to thermodynamic stability tasks.",
        )
    if column == "energy_above_hull_ev_atom":
        return (
            "thermodynamic_property",
            "eV/atom",
            True,
            True,
            "leakage candidate",
            "Direct stability proxy; do not use to predict a derived stability label.",
        )
    if column == "density_g_cm3":
        return (
            "structure",
            "g/cm3",
            True,
            True,
            "conditional",
            "Structure-dependent descriptor; useful for descriptive screening.",
        )
    if column == "volume_a3":
        return (
            "structure",
            "A^3",
            True,
            True,
            "conditional",
            "Ambiguous without number of sites or normalization.",
        )
    return (
        "ambiguous",
        "unknown",
        False,
        False,
        "unknown",
        "Column was not part of the current audited Materials Project schema.",
    )


class MaterialsProjectConnector(BaseConnector):
    """Small Materials Project API probe connector."""

    source_name = "materials_project"

    def __init__(self, elements: list[str] | None = None) -> None:
        self.elements = ["Fe", "Si"] if elements is None else elements

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Fetch Materials Project summary docs and save raw JSON/processed CSV."""
        api_key = os.getenv("MP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MP_API_KEY is not set. Set it in your environment; do not store "
                "API keys in code, README files, source.md files, or tests."
            )

        try:
            from mp_api.client import MPRester
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The mp-api package is required for Materials Project ingestion.\n"
                "Install it with: pip install mp-api"
            ) from exc

        query_limit = limit if not full else max(limit, 50)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)

        with MPRester(api_key) as mpr:
            docs = mpr.materials.summary.search(
                elements=self.elements,
                fields=MP_FIELDS,
                num_chunks=1,
                chunk_size=query_limit,
            )

        plain_docs = [serialize_mp_doc(doc) for doc in docs[:query_limit]]
        RAW_PATH.write_text(
            json.dumps(plain_docs, indent=2, default=str),
            encoding="utf-8",
        )
        processed_df = build_materials_project_dataframe(plain_docs)
        processed_df.to_csv(PROCESSED_PATH, index=False)

        return IngestionResult(
            source_name=self.source_name,
            raw_paths=[RAW_PATH],
            processed_paths=[PROCESSED_PATH],
            row_count=len(processed_df),
            column_count=len(processed_df.columns),
            warnings=[
                "Materials Project values are computed materials properties, "
                "not direct experimental measurements."
            ],
        )
