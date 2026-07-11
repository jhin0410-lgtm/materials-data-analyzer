"""Controlled Materials Project v1.3 acquisition helpers.

This module implements the v1.3.2 live acquisition boundary.  It does not
create descriptors, train models, run splits, or update the earlier v1.2
Materials Project artifacts.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import platform
import re
import sys
import tempfile
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRET_VALUE_PATTERN = re.compile(
    r"(?:api[_-]?key|token|secret|credential|password|sk-[A-Za-z0-9])",
    flags=re.IGNORECASE,
)
SECRET_KEY_TOKENS = {"api_key", "apikey", "token", "secret", "password"}
ALLOWED_SECRET_KEYS = {"credential_policy", "credential_included"}
ACQUISITION_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_version",
    "dataset_name",
    "source_system",
    "endpoint_family",
    "query_method",
    "required_elements",
    "element_count_range",
    "requested_fields",
    "mandatory_fields",
    "target_column",
    "identifier_column",
    "query_parameters",
    "chunk_size",
    "credential_policy",
]
FORBIDDEN_QUERY_FILTERS = {"theoretical", "energy_above_hull", "is_stable", "nelements"}


class CredentialRequiredError(RuntimeError):
    """Raised when Materials Project credentials are required but unavailable."""


class AcquisitionStopError(RuntimeError):
    """Raised when acquisition must stop before writing final artifacts."""


@dataclass(frozen=True)
class AcquisitionOutputs:
    """Output locations for full acquisition artifacts."""

    raw_output: Path
    table_output: Path
    manifest_output: Path
    summary_output: Path


def load_acquisition_spec(path: str | Path) -> dict[str, Any]:
    """Load and validate the v1.3 acquisition specification."""
    spec_path = Path(path)
    with spec_path.open(encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError("Materials Project v1.3 acquisition spec must be a JSON object.")
    validate_acquisition_spec(spec)
    return spec


def validate_acquisition_spec(spec: dict[str, Any]) -> None:
    """Validate the acquisition spec without reading credentials or networking."""
    missing = [field for field in ACQUISITION_REQUIRED_FIELDS if field not in spec]
    if missing:
        raise ValueError(
            "Materials Project v1.3 acquisition spec is missing required field(s): "
            + ", ".join(missing)
        )
    _ensure_no_forbidden_secret_keys(spec)
    _ensure_no_absolute_paths(spec)

    if spec["required_elements"] != ["Fe", "Si"]:
        raise ValueError("v1.3 acquisition requires required_elements exactly ['Fe', 'Si'].")
    if spec["element_count_range"] != [2, 5]:
        raise ValueError("v1.3 acquisition requires element_count_range exactly [2, 5].")

    requested_fields = spec["requested_fields"]
    if not isinstance(requested_fields, list) or not requested_fields:
        raise ValueError("requested_fields must be a non-empty list.")
    if len(requested_fields) != len(set(requested_fields)):
        raise ValueError("requested_fields must not contain duplicate fields.")

    missing_mandatory = [
        field for field in spec["mandatory_fields"] if field not in requested_fields
    ]
    if missing_mandatory:
        raise ValueError(
            "mandatory_fields must be included in requested_fields: "
            + ", ".join(missing_mandatory)
        )

    query_parameters = spec["query_parameters"]
    if query_parameters.get("elements") != ["Fe", "Si"]:
        raise ValueError("query_parameters.elements must be ['Fe', 'Si'].")
    if query_parameters.get("num_elements") != [2, 5]:
        raise ValueError("query_parameters.num_elements must be [2, 5].")
    if query_parameters.get("deprecated") is not False:
        raise ValueError("query_parameters.deprecated must be false.")
    if query_parameters.get("include_gnome") is not False:
        raise ValueError("query_parameters.include_gnome must be false.")
    if query_parameters.get("theoretical") is not None:
        raise ValueError("theoretical must not be used as a query filter.")
    if query_parameters.get("energy_above_hull") is not None:
        raise ValueError("energy_above_hull must not be used as a query filter.")
    if query_parameters.get("is_stable") is not None:
        raise ValueError("is_stable must not be used as a query filter.")
    if "nelements" in query_parameters:
        raise ValueError("Use num_elements as a query parameter; nelements is a return field.")
    if spec["credential_policy"].get("environment_variable") != "MP_API_KEY":
        raise ValueError("credential_policy.environment_variable must be MP_API_KEY.")
    if spec["credential_policy"].get("log_value") is not False:
        raise ValueError("credential_policy.log_value must be false.")


def build_exact_query_parameters(
    spec: dict[str, Any],
    *,
    preflight: bool = False,
) -> dict[str, Any]:
    """Build exact Materials Project summary.search parameters from the spec."""
    validate_acquisition_spec(spec)
    query_parameters = spec["query_parameters"]
    chunk_size = int(spec["chunk_size"])
    if preflight:
        chunk_size = min(chunk_size, 5)

    params: dict[str, Any] = {
        "elements": list(query_parameters["elements"]),
        "num_elements": tuple(query_parameters["num_elements"]),
        "deprecated": False,
        "include_gnome": False,
        "fields": list(spec["requested_fields"]),
        "all_fields": False,
        "chunk_size": chunk_size,
    }
    if preflight:
        params["num_chunks"] = 1
    return params


def validate_query_parameters_against_signature(params: dict[str, Any]) -> None:
    """Verify query parameters against the installed public SummaryRester signature."""
    try:
        from mp_api.client.routes.materials.summary import SummaryRester
    except Exception as exc:  # pragma: no cover - depends on optional local package
        raise AcquisitionStopError(
            "Materials Project mp-api package is required for live acquisition."
        ) from exc

    signature = inspect.signature(SummaryRester.search)
    supported = set(signature.parameters)
    unsupported = sorted(set(params) - supported)
    if unsupported:
        raise AcquisitionStopError(
            "Installed SummaryRester.search does not support query parameter(s): "
            + ", ".join(unsupported)
        )
    if "nelements" in params:
        raise AcquisitionStopError(
            "Invalid query construction: nelements must not be used as a query parameter."
        )
    for forbidden in ["energy_above_hull", "is_stable", "theoretical"]:
        if forbidden in params:
            raise AcquisitionStopError(
                f"Invalid query construction: {forbidden} must not be used as a filter."
            )


def require_mp_api_key() -> str:
    """Return MP_API_KEY or raise a generic credential-required error."""
    api_key = os.getenv("MP_API_KEY")
    if not api_key:
        raise CredentialRequiredError(
            "Materials Project credentials are required for live acquisition. "
            "Set MP_API_KEY in the environment and rerun the command."
        )
    return api_key


def make_mpr_client() -> Any:
    """Create a Materials Project client using only the MP_API_KEY environment variable."""
    api_key = require_mp_api_key()
    try:
        from mp_api.client import MPRester
    except Exception as exc:  # pragma: no cover - depends on optional local package
        raise AcquisitionStopError(
            "Materials Project mp-api package is required for live acquisition."
        ) from exc
    constructor_parameters = inspect.signature(MPRester).parameters
    if "mute_progress_bars" in constructor_parameters:
        return MPRester(api_key, mute_progress_bars=True)
    return MPRester(api_key)


def get_database_version(client: Any) -> str:
    """Fetch the Materials Project database version using a public helper."""
    db_version = getattr(client, "db_version", None)
    if db_version is not None and str(db_version).strip():
        return str(db_version)
    if not hasattr(client, "get_database_version"):
        raise AcquisitionStopError(
            "Materials Project database version helper is unavailable in this client."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            version = client.get_database_version()
    except Exception as exc:
        raise AcquisitionStopError(
            "Materials Project database version capture failed; stopping acquisition."
        ) from exc
    if version is None or str(version).strip() == "":
        raise AcquisitionStopError(
            "Materials Project database version capture returned an empty value."
        )
    return str(version)


def run_preflight(
    spec: dict[str, Any],
    *,
    spec_path: str | Path,
    client_factory: Callable[[], Any] | None = None,
    validate_signature: bool = True,
) -> dict[str, Any]:
    """Run a single controlled preflight request and return a sanitized report."""
    validate_acquisition_spec(spec)
    params = build_exact_query_parameters(spec, preflight=True)
    if validate_signature:
        validate_query_parameters_against_signature(params)

    if client_factory is None:
        client_factory = make_mpr_client

    docs: list[Any]
    with _client_context(client_factory()) as client:
        database_version = get_database_version(client)
        docs = list(client.materials.summary.search(**params))

    serialized_docs, serialization_failure_count = serialize_documents(docs)
    validation = validate_materials_project_documents(serialized_docs, spec)
    status = "passed"
    stop_reasons: list[str] = []
    if not serialized_docs:
        status = "failed"
        stop_reasons.append("preflight response was empty")
    if validation["execution_status"] != "success":
        status = "failed"
        stop_reasons.extend(validation["stop_reasons"])
    if serialization_failure_count:
        status = "failed"
        stop_reasons.append("preflight document serialization failed")

    return {
        "preflight_status": status,
        "sample_row_count": len(serialized_docs),
        "mandatory_field_check": "passed"
        if not validation["missing_mandatory_field_counts"]
        else "failed",
        "required_element_check": validation["required_element_validation"]["status"],
        "element_count_check": validation["element_count_validation"]["status"],
        "target_field_check": "passed"
        if validation["missing_target_count"] < len(serialized_docs)
        else "failed",
        "database_version_available": True,
        "materials_project_database_version": database_version,
        "network_called": True,
        "credential_included": False,
        "absolute_path_included": False,
        "exact_query_parameters": _safe_query_parameters(params),
        "spec_path": _repo_relative_path(spec_path),
        "serialization_failure_count": serialization_failure_count,
        "stop_reasons": _unique(stop_reasons),
        "validation": validation,
    }


def run_full_acquisition(
    spec: dict[str, Any],
    *,
    spec_path: str | Path,
    outputs: AcquisitionOutputs,
    client_factory: Callable[[], Any] | None = None,
    retry_count: int = 1,
    validate_signature: bool = True,
) -> dict[str, Any]:
    """Run preflight and then full acquisition, writing deterministic artifacts."""
    if retry_count < 0:
        raise ValueError("retry_count must be zero or positive.")
    validate_acquisition_spec(spec)
    params = build_exact_query_parameters(spec, preflight=False)
    if validate_signature:
        validate_query_parameters_against_signature(params)

    preflight_report = run_preflight(
        spec,
        spec_path=spec_path,
        client_factory=client_factory,
        validate_signature=validate_signature,
    )
    if preflight_report["preflight_status"] != "passed":
        raise AcquisitionStopError(
            "Preflight failed; full acquisition was not executed. Stop reasons: "
            + "; ".join(preflight_report["stop_reasons"])
        )

    if client_factory is None:
        client_factory = make_mpr_client

    docs: list[Any] = []
    database_version = preflight_report["materials_project_database_version"]
    attempts = 0
    last_error: Exception | None = None
    while attempts <= retry_count:
        attempts += 1
        try:
            with _client_context(client_factory()) as client:
                current_database_version = get_database_version(client)
                if current_database_version != database_version:
                    raise AcquisitionStopError(
                        "Database version changed between preflight and acquisition."
                    )
                docs = list(client.materials.summary.search(**params))
            last_error = None
            break
        except AcquisitionStopError:
            raise
        except Exception as exc:
            last_error = exc
            if attempts > retry_count:
                break
    if last_error is not None:
        raise AcquisitionStopError(
            "Materials Project full acquisition failed; no partial success was recorded."
        ) from last_error

    serialized_docs, serialization_failure_count = serialize_documents(docs)
    if serialization_failure_count:
        raise AcquisitionStopError(
            "Document serialization failed; no partial success was recorded."
        )
    validation = validate_materials_project_documents(serialized_docs, spec)
    table = build_acquired_table(serialized_docs, spec)
    outputs = AcquisitionOutputs(
        raw_output=Path(outputs.raw_output),
        table_output=Path(outputs.table_output),
        manifest_output=Path(outputs.manifest_output),
        summary_output=Path(outputs.summary_output),
    )
    write_jsonl_atomic(serialized_docs, outputs.raw_output)
    write_dataframe_atomic(table, outputs.table_output)

    raw_sha = calculate_file_sha256(outputs.raw_output)
    table_sha = calculate_file_sha256(outputs.table_output)
    credential_included = (
        _contains_credential_like_value(serialized_docs)
        or dataframe_contains_credential_like_values(table)
    )
    absolute_path_included = (
        _contains_absolute_path(serialized_docs)
        or dataframe_contains_absolute_paths(table)
    )
    data_sufficiency_gate = evaluate_data_sufficiency(validation)
    execution_status = validation["execution_status"]
    if execution_status == "success" and data_sufficiency_gate["status"] == "stop":
        execution_status = "failed_data_sufficiency_gate"
    if credential_included or absolute_path_included:
        execution_status = "failed_safety_validation"

    stop_reasons = list(validation["stop_reasons"])
    if credential_included:
        stop_reasons.append("credential-like value detected in output artifacts")
    if absolute_path_included:
        stop_reasons.append("absolute local path detected in output artifacts")
    stop_reasons.extend(data_sufficiency_gate["stop_reasons"])

    manifest = build_acquisition_manifest(
        spec=spec,
        spec_path=spec_path,
        outputs=outputs,
        table=table,
        validation=validation,
        preflight_report=preflight_report,
        database_version=database_version,
        raw_sha256=raw_sha,
        table_sha256=table_sha,
        execution_status=execution_status,
        retry_count=attempts - 1,
        credential_included=credential_included,
        absolute_path_included=absolute_path_included,
        data_sufficiency_gate=data_sufficiency_gate,
        stop_reasons=_unique(stop_reasons),
    )
    summary = build_acquisition_summary(manifest, validation, data_sufficiency_gate)
    write_json_atomic(manifest, outputs.manifest_output)
    write_dataframe_atomic(summary, outputs.summary_output)

    return {
        "execution_status": execution_status,
        "preflight_status": preflight_report["preflight_status"],
        "raw_row_count": len(serialized_docs),
        "table_row_count": len(table),
        "column_count": len(table.columns),
        "raw_sha256": raw_sha,
        "sorted_table_sha256": table_sha,
        "data_sufficiency_gate": data_sufficiency_gate,
        "manifest": manifest,
        "summary": summary,
        "stop_reasons": _unique(stop_reasons),
    }


def serialize_documents(docs: Iterable[Any]) -> tuple[list[dict[str, Any]], int]:
    """Serialize API documents to plain JSON-safe dictionaries."""
    serialized: list[dict[str, Any]] = []
    failures = 0
    for doc in docs:
        try:
            value = _to_jsonable(doc)
            if not isinstance(value, dict):
                value = {"value": value}
            serialized.append(value)
        except Exception:
            failures += 1
    return serialized, failures


def build_acquired_table(docs: list[dict[str, Any]], spec: dict[str, Any]) -> pd.DataFrame:
    """Build a deterministic table sorted by material_id without dropping rows."""
    rows: list[dict[str, Any]] = []
    for doc in docs:
        row = {}
        for field in spec["requested_fields"]:
            row[field] = _compact_table_cell(doc.get(field))
        rows.append(row)
    df = pd.DataFrame(rows, columns=spec["requested_fields"])
    if "material_id" in df.columns:
        df = df.sort_values(
            by="material_id",
            key=lambda series: series.astype(str),
            kind="mergesort",
        ).reset_index(drop=True)
    return df


def validate_materials_project_documents(
    docs: list[dict[str, Any]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Validate returned Materials Project documents against the acquisition scope."""
    target_column = spec["target_column"]
    identifier_column = spec["identifier_column"]
    mandatory_fields = spec["mandatory_fields"]
    required_elements = set(spec["required_elements"])
    min_elements, max_elements = spec["element_count_range"]

    row_count = len(docs)
    missing_mandatory_field_counts: dict[str, int] = {}
    for field in mandatory_fields:
        count = sum(1 for doc in docs if field not in doc)
        if count:
            missing_mandatory_field_counts[field] = count

    material_ids = [doc.get(identifier_column) for doc in docs]
    material_id_series = pd.Series(material_ids, dtype="object")
    missing_material_id_count = int(material_id_series.isna().sum())
    duplicate_material_id_count = int(material_id_series.duplicated(keep=False).sum())
    unique_material_id_count = int(material_id_series.dropna().nunique())

    element_rows: list[set[str]] = [_extract_elements(doc) for doc in docs]
    fe_containing_rows = sum(1 for elements in element_rows if "Fe" in elements)
    si_containing_rows = sum(1 for elements in element_rows if "Si" in elements)
    fe_si_containing_rows = sum(
        1 for elements in element_rows if required_elements.issubset(elements)
    )
    missing_required_element_rows = row_count - fe_si_containing_rows

    element_counts = [_extract_num_elements(doc, elements) for doc, elements in zip(docs, element_rows)]
    valid_element_count_rows = sum(
        1 for count in element_counts if count is not None and min_elements <= count <= max_elements
    )
    out_of_range_element_count_rows = row_count - valid_element_count_rows

    deprecated_values = [doc.get("deprecated") for doc in docs]
    deprecated_count = sum(value is True or str(value).lower() == "true" for value in deprecated_values)
    theoretical_distribution = _value_counts([doc.get("theoretical") for doc in docs])

    targets = [_to_float_or_none(doc.get(target_column)) for doc in docs]
    missing_target_count = sum(_is_missing(doc.get(target_column)) for doc in docs)
    nonnumeric_target_count = sum(
        1 for doc, value in zip(docs, targets) if not _is_missing(doc.get(target_column)) and value is None
    )
    nonfinite_target_count = sum(
        1 for value in targets if value is not None and not math.isfinite(value)
    )
    finite_targets = [value for value in targets if value is not None and math.isfinite(value)]
    target_zero_count = sum(1 for value in finite_targets if value == 0)
    target_zero_rate = float(target_zero_count / len(finite_targets)) if finite_targets else None
    target_stats = {
        "min": min(finite_targets) if finite_targets else None,
        "median": float(pd.Series(finite_targets).median()) if finite_targets else None,
        "max": max(finite_targets) if finite_targets else None,
        "valid_count": len(finite_targets),
        "variance": float(pd.Series(finite_targets).var(ddof=0)) if len(finite_targets) else None,
    }

    reduced_formulas = [_extract_reduced_formula(doc) for doc in docs]
    chemical_systems = [_normalize_text(doc.get("chemsys")) for doc in docs]
    reduced_formula_counts = _value_counts(reduced_formulas)
    chemical_system_counts = _value_counts(chemical_systems)
    reduced_formula_group_count = sum(1 for value in reduced_formula_counts if value != "<missing>")
    chemical_system_group_count = sum(1 for value in chemical_system_counts if value != "<missing>")
    max_reduced_formula_group_size = max(reduced_formula_counts.values(), default=0)
    max_chemical_system_group_size = max(chemical_system_counts.values(), default=0)

    stop_reasons: list[str] = []
    if row_count == 0:
        stop_reasons.append("empty response")
    if missing_mandatory_field_counts:
        stop_reasons.append("mandatory fields contain missing values")
    if missing_required_element_rows:
        stop_reasons.append("returned rows missing Fe or Si")
    if out_of_range_element_count_rows:
        stop_reasons.append("returned rows outside num_elements 2-5")
    if deprecated_count:
        stop_reasons.append("deprecated rows returned despite deprecated=False")
    if duplicate_material_id_count:
        stop_reasons.append("duplicate material_id values detected")
    if missing_material_id_count:
        stop_reasons.append("missing material_id values detected")

    execution_status = "success"
    if missing_required_element_rows or out_of_range_element_count_rows:
        execution_status = "failed_scope_validation"
    elif row_count == 0 or missing_mandatory_field_counts or deprecated_count:
        execution_status = "failed_response_validation"
    elif duplicate_material_id_count or missing_material_id_count:
        execution_status = "failed_identifier_validation"

    return {
        "execution_status": execution_status,
        "row_count": row_count,
        "missing_mandatory_field_counts": missing_mandatory_field_counts,
        "unique_material_id_count": unique_material_id_count,
        "duplicate_material_id_count": duplicate_material_id_count,
        "missing_material_id_count": missing_material_id_count,
        "required_element_validation": {
            "status": "passed" if missing_required_element_rows == 0 else "failed",
            "required_elements": sorted(required_elements),
            "fe_containing_rows": fe_containing_rows,
            "si_containing_rows": si_containing_rows,
            "fe_si_containing_rows": fe_si_containing_rows,
            "missing_required_element_rows": missing_required_element_rows,
        },
        "element_count_validation": {
            "status": "passed" if out_of_range_element_count_rows == 0 else "failed",
            "range": [min_elements, max_elements],
            "valid_rows": valid_element_count_rows,
            "out_of_range_rows": out_of_range_element_count_rows,
        },
        "theoretical_distribution": theoretical_distribution,
        "deprecated_count": deprecated_count,
        "missing_target_count": missing_target_count,
        "nonnumeric_target_count": nonnumeric_target_count,
        "nonfinite_target_count": nonfinite_target_count,
        "target_min": target_stats["min"],
        "target_median": target_stats["median"],
        "target_max": target_stats["max"],
        "target_valid_count": target_stats["valid_count"],
        "target_variance": target_stats["variance"],
        "target_zero_count": target_zero_count,
        "target_zero_rate": target_zero_rate,
        "reduced_formula_group_count": reduced_formula_group_count,
        "chemical_system_group_count": chemical_system_group_count,
        "max_reduced_formula_group_size": max_reduced_formula_group_size,
        "max_chemical_system_group_size": max_chemical_system_group_size,
        "reduced_formula_group_size_distribution": _group_size_distribution(reduced_formula_counts),
        "chemical_system_group_size_distribution": _group_size_distribution(chemical_system_counts),
        "stop_reasons": _unique(stop_reasons),
    }


def evaluate_data_sufficiency(validation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether the acquisition can proceed to descriptor planning."""
    stop_reasons: list[str] = []
    warnings: list[str] = []
    valid_targets = int(validation.get("target_valid_count", 0))
    formula_groups = int(validation.get("reduced_formula_group_count", 0))
    chemsys_groups = int(validation.get("chemical_system_group_count", 0))
    target_variance = validation.get("target_variance")
    target_zero_rate = validation.get("target_zero_rate")

    if validation.get("execution_status") != "success":
        stop_reasons.append("response validation did not pass")
    if valid_targets == 0:
        stop_reasons.append("no valid target rows")
    if formula_groups < 2:
        stop_reasons.append("too few reduced-formula groups for group-aware validation planning")
    if chemsys_groups < 2:
        stop_reasons.append("too few chemical-system groups for group-aware validation planning")
    if target_variance is None or target_variance == 0:
        stop_reasons.append("target appears constant or unavailable")
    if validation.get("duplicate_material_id_count", 0):
        stop_reasons.append("duplicate material_id values are unresolved")

    if target_zero_rate is not None and target_zero_rate > 0.8:
        warnings.append("target distribution is dominated by zero values")
    if valid_targets < 100:
        warnings.append(
            "valid target row count is small for robust validation; treat as conditional"
        )

    if stop_reasons:
        status = "stop"
    elif warnings:
        status = "conditional"
    else:
        status = "ready_for_descriptor_stage"
    return {
        "status": status,
        "valid_target_rows": valid_targets,
        "reduced_formula_group_count": formula_groups,
        "chemical_system_group_count": chemsys_groups,
        "target_zero_rate": target_zero_rate,
        "warnings": warnings,
        "stop_reasons": _unique(stop_reasons),
    }


def build_acquisition_manifest(
    *,
    spec: dict[str, Any],
    spec_path: str | Path,
    outputs: AcquisitionOutputs,
    table: pd.DataFrame,
    validation: dict[str, Any],
    preflight_report: dict[str, Any],
    database_version: str,
    raw_sha256: str,
    table_sha256: str,
    execution_status: str,
    retry_count: int,
    credential_included: bool,
    absolute_path_included: bool,
    data_sufficiency_gate: dict[str, Any],
    stop_reasons: list[str],
) -> dict[str, Any]:
    """Build a compact acquisition manifest with no credentials or absolute paths."""
    columns = table.columns.tolist()
    packages = _package_versions()
    return {
        "manifest_schema_version": "1.0",
        "dataset_version": "v1.3",
        "dataset_name": spec["dataset_name"],
        "source_system": spec["source_system"],
        "acquisition_spec_path": _repo_relative_path(spec_path),
        "endpoint": spec["endpoint_family"],
        "query_method": spec["query_method"],
        "exact_query_parameters": _safe_query_parameters(
            build_exact_query_parameters(spec, preflight=False)
        ),
        "exact_requested_fields": list(spec["requested_fields"]),
        "acquisition_utc_timestamp": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "python_version": platform.python_version(),
        "mp_api_version": packages.get("mp-api"),
        "pymatgen_version": packages.get("pymatgen"),
        "emmet_core_version": packages.get("emmet-core"),
        "materials_project_database_version": database_version,
        "execution_status": execution_status,
        "preflight_status": preflight_report["preflight_status"],
        "network_called": True,
        "raw_output_path": _repo_relative_path(outputs.raw_output),
        "table_output_path": _repo_relative_path(outputs.table_output),
        "summary_output_path": _repo_relative_path(outputs.summary_output),
        "manifest_output_path": _repo_relative_path(outputs.manifest_output),
        "raw_row_count": int(validation["row_count"]),
        "table_row_count": int(len(table)),
        "column_count": int(len(columns)),
        "columns": columns,
        "raw_sha256": raw_sha256,
        "sorted_table_sha256": table_sha256,
        "unique_material_id_count": int(validation["unique_material_id_count"]),
        "duplicate_material_id_count": int(validation["duplicate_material_id_count"]),
        "missing_material_id_count": int(validation["missing_material_id_count"]),
        "missing_target_count": int(validation["missing_target_count"]),
        "required_element_validation": validation["required_element_validation"],
        "element_count_validation": validation["element_count_validation"],
        "theoretical_distribution": validation["theoretical_distribution"],
        "deprecated_count": int(validation["deprecated_count"]),
        "reduced_formula_group_count": int(validation["reduced_formula_group_count"]),
        "chemical_system_group_count": int(validation["chemical_system_group_count"]),
        "credential_included": bool(credential_included),
        "absolute_path_included": bool(absolute_path_included),
        "partial_download": False,
        "retry_count": int(retry_count),
        "data_sufficiency_gate": data_sufficiency_gate,
        "warnings": data_sufficiency_gate.get("warnings", []),
        "stop_reasons": _unique(stop_reasons),
    }


def build_acquisition_summary(
    manifest: dict[str, Any],
    validation: dict[str, Any],
    data_sufficiency_gate: dict[str, Any],
) -> pd.DataFrame:
    """Build compact metric/value/severity acquisition summary table."""
    rows = [
        _summary_row("acquisition_status", manifest["execution_status"], "error" if manifest["execution_status"] != "success" else "info", "Overall v1.3 acquisition status."),
        _summary_row("database_version_captured", bool(manifest["materials_project_database_version"]), "info", "Whether a Materials Project database version was captured."),
        _summary_row("total_rows", manifest["raw_row_count"], "info", "Returned Materials Project summary rows."),
        _summary_row("columns", manifest["column_count"], "info", "Acquired table column count."),
        _summary_row("unique_material_ids", manifest["unique_material_id_count"], "info", "Unique material_id values."),
        _summary_row("duplicate_material_ids", manifest["duplicate_material_id_count"], "warning" if manifest["duplicate_material_id_count"] else "info", "Duplicate material_id rows retained for audit."),
        _summary_row("fe_si_containing_rows", validation["required_element_validation"]["fe_si_containing_rows"], "info", "Rows containing both Fe and Si after post-query validation."),
        _summary_row("missing_required_element_rows", validation["required_element_validation"]["missing_required_element_rows"], "error" if validation["required_element_validation"]["missing_required_element_rows"] else "info", "Rows missing Fe or Si."),
        _summary_row("element_count_out_of_range_rows", validation["element_count_validation"]["out_of_range_rows"], "error" if validation["element_count_validation"]["out_of_range_rows"] else "info", "Rows outside the 2-5 element scope."),
        _summary_row("theoretical_distribution", validation["theoretical_distribution"], "info", "Distribution of returned theoretical values."),
        _summary_row("deprecated_count", validation["deprecated_count"], "error" if validation["deprecated_count"] else "info", "Deprecated rows returned despite deprecated=False."),
        _summary_row("missing_target_count", validation["missing_target_count"], "warning" if validation["missing_target_count"] else "info", "Rows with missing energy_above_hull."),
        _summary_row("target_zero_count", validation["target_zero_count"], "info", "Rows with target exactly zero."),
        _summary_row("target_zero_rate", validation["target_zero_rate"], "info", "Share of finite target rows equal to zero."),
        _summary_row("target_min", validation["target_min"], "info", "Minimum finite energy_above_hull."),
        _summary_row("target_median", validation["target_median"], "info", "Median finite energy_above_hull."),
        _summary_row("target_max", validation["target_max"], "info", "Maximum finite energy_above_hull."),
        _summary_row("reduced_formula_groups", validation["reduced_formula_group_count"], "info", "Distinct reduced formula groups."),
        _summary_row("chemical_system_groups", validation["chemical_system_group_count"], "info", "Distinct chemical-system groups."),
        _summary_row("max_reduced_formula_group_size", validation["max_reduced_formula_group_size"], "info", "Largest reduced formula group size."),
        _summary_row("max_chemical_system_group_size", validation["max_chemical_system_group_size"], "info", "Largest chemical-system group size."),
        _summary_row("data_sufficiency_gate", data_sufficiency_gate["status"], "error" if data_sufficiency_gate["status"] == "stop" else "warning" if data_sufficiency_gate["status"] == "conditional" else "info", "Descriptor-stage readiness gate; no modeling is run in v1.3.2."),
        _summary_row("provenance_complete", not bool(manifest["stop_reasons"]), "warning" if manifest["stop_reasons"] else "info", "Whether manifest validation has no stop reasons."),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "severity", "description"])


def write_jsonl_atomic(docs: list[dict[str, Any]], path: str | Path) -> None:
    """Write serialized docs as deterministic JSONL using atomic rename."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _temporary_output_path(target) as temp_path:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            for doc in docs:
                handle.write(
                    json.dumps(
                        doc,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        os.replace(temp_path, target)


def write_json_atomic(data: dict[str, Any], path: str | Path) -> None:
    """Write JSON using atomic rename."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _temporary_output_path(target) as temp_path:
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp_path, target)


def write_dataframe_atomic(df: pd.DataFrame, path: str | Path) -> None:
    """Write a CSV DataFrame with no index using atomic rename."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _temporary_output_path(target) as temp_path:
        df.to_csv(temp_path, index=False)
        os.replace(temp_path, target)


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate a SHA-256 checksum for a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataframe_contains_credential_like_values(df: pd.DataFrame) -> bool:
    """Return whether object columns contain credential-like values."""
    for column in df.select_dtypes(exclude="number").columns:
        if (
            df[column]
            .dropna()
            .astype(str)
            .str.contains(SECRET_VALUE_PATTERN, regex=True)
            .any()
        ):
            return True
    return False


def dataframe_contains_absolute_paths(df: pd.DataFrame) -> bool:
    """Return whether object columns contain absolute local paths."""
    for column in df.select_dtypes(exclude="number").columns:
        if (
            df[column]
            .dropna()
            .astype(str)
            .str.contains(r"^[A-Za-z]:\\|^/|^\\\\", regex=True)
            .any()
        ):
            return True
    return False


class _client_context:
    """Context-manager adapter for real and fake Materials Project clients."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def __enter__(self) -> Any:
        if hasattr(self.client, "__enter__"):
            return self.client.__enter__()
        return self.client

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if hasattr(self.client, "__exit__"):
            return self.client.__exit__(exc_type, exc, tb)
        close = getattr(self.client, "close", None)
        if callable(close):
            close()
        return None


class _temporary_output_path:
    """Create and clean up a temporary file path beside the target."""

    def __init__(self, target: Path) -> None:
        self.target = target
        self.temp_path: Path | None = None

    def __enter__(self) -> Path:
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.target.name}.",
            suffix=".tmp",
            dir=self.target.parent,
        )
        os.close(fd)
        self.temp_path = Path(raw_path)
        return self.temp_path

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None and self.temp_path and self.temp_path.exists():
            self.temp_path.unlink()


def _to_jsonable(value: Any) -> Any:
    """Convert common Materials Project/Pydantic objects to JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "as_dict"):
        return _to_jsonable(value.as_dict())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if hasattr(value, "value"):
        return _to_jsonable(value.value)
    return str(value)


def _compact_table_cell(value: Any) -> Any:
    jsonable = _to_jsonable(value)
    if isinstance(jsonable, (dict, list)):
        return json.dumps(
            jsonable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return jsonable


def _extract_elements(doc: dict[str, Any]) -> set[str]:
    raw_elements = doc.get("elements")
    elements: set[str] = set()
    if isinstance(raw_elements, list):
        for element in raw_elements:
            symbol = _element_symbol(element)
            if symbol:
                elements.add(symbol)
    elif raw_elements is not None:
        symbol = _element_symbol(raw_elements)
        if symbol:
            elements.add(symbol)

    if not elements:
        for source_field in ["composition_reduced", "composition", "formula_pretty"]:
            elements.update(_extract_elements_from_text(doc.get(source_field)))
            if elements:
                break
    return elements


def _extract_num_elements(doc: dict[str, Any], elements: set[str]) -> int | None:
    raw_value = doc.get("nelements")
    try:
        if raw_value is not None and not _is_missing(raw_value):
            return int(raw_value)
    except (TypeError, ValueError):
        return None
    if elements:
        return len(elements)
    return None


def _extract_reduced_formula(doc: dict[str, Any]) -> str:
    for field in ["formula_pretty", "composition_reduced", "composition"]:
        value = doc.get(field)
        if not _is_missing(value):
            return _normalize_text(value)
    return "<missing>"


def _element_symbol(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ["symbol", "element", "value"]:
            if key in value:
                return _element_symbol(value[key])
    text = str(value).strip()
    match = re.match(r"^([A-Z][a-z]?)$", text)
    if match:
        return match.group(1)
    return None


def _extract_elements_from_text(value: Any) -> set[str]:
    text = _normalize_text(value)
    if text == "<missing>":
        return set()
    return set(re.findall(r"([A-Z][a-z]?)", text))


def _normalize_text(value: Any) -> str:
    if _is_missing(value):
        return "<missing>"
    if isinstance(value, (dict, list)):
        return json.dumps(_to_jsonable(value), sort_keys=True, separators=(",", ":"))
    return str(value).strip() or "<missing>"


def _to_float_or_none(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _value_counts(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = _normalize_text(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _group_size_distribution(group_counts: dict[str, int]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for size in group_counts.values():
        key = str(size)
        distribution[key] = distribution.get(key, 0) + 1
    return dict(sorted(distribution.items(), key=lambda item: int(item[0])))


def _summary_row(metric: str, value: Any, severity: str, description: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": _compact_table_cell(value),
        "severity": severity,
        "description": description,
    }


def _safe_query_parameters(params: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in params.items():
        if key in FORBIDDEN_QUERY_FILTERS:
            continue
        safe[key] = _to_jsonable(value)
    return safe


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package_name in ["mp-api", "pymatgen", "emmet-core"]:
        try:
            versions[package_name] = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            versions[package_name] = None
    return versions


def _repo_relative_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.name


def _ensure_no_forbidden_secret_keys(value: Any) -> None:
    if _contains_forbidden_secret_key(value):
        raise ValueError("Acquisition spec must not contain forbidden secret-like keys.")


def _contains_forbidden_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if normalized_key not in ALLOWED_SECRET_KEYS:
                if any(token in normalized_key for token in SECRET_KEY_TOKENS):
                    return True
            if _contains_forbidden_secret_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_secret_key(item) for item in value)
    return False


def _ensure_no_absolute_paths(value: Any) -> None:
    if _contains_absolute_path(value):
        raise ValueError("Acquisition spec/output must not contain absolute local paths.")


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, str):
        stripped = value.strip()
        return bool(
            stripped.startswith("/")
            or stripped.startswith("\\\\")
            or (len(stripped) >= 3 and stripped[1:3] in {":\\", ":/"})
        )
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False


def _contains_credential_like_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(SECRET_VALUE_PATTERN.search(value))
    if isinstance(value, dict):
        return any(_contains_credential_like_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_credential_like_value(item) for item in value)
    return False


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def print_sanitized_json(data: dict[str, Any]) -> None:
    """Print sanitized JSON for CLI consumers."""
    print(json.dumps(_to_jsonable(data), indent=2, sort_keys=True))
