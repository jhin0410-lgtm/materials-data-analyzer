"""Identity-only readiness audit for an independent Materials Project cohort.

The audit intentionally does not read benchmark-v1 locked-test content, query
energy_above_hull, fit a model, execute an acquisition policy, or decide a new
benchmark size.  It answers one narrower question: under the already-versioned
v1.3 Materials Project query scope, does the current database expose material
identities that were not part of the original 838-row retrospective benchmark?
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from config import PROJECT_ROOT
from connectors.materials_project_acquisition import (
    AcquisitionStopError,
    build_exact_query_parameters,
    get_database_version,
    load_acquisition_spec,
    make_mpr_client,
    serialize_documents,
    validate_query_parameters_against_signature,
)
from platform_core.output_safety import transactional_output_directory


SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "independent_source_readiness.json"
CANDIDATE_NAME = "independent_candidate_identity.csv"


class MaterialsProjectIndependentSourceReadinessError(ValueError):
    """Raised when the independent-source readiness contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise MaterialsProjectIndependentSourceReadinessError(
            f"invalid JSON in {resolved}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MaterialsProjectIndependentSourceReadinessError(
            f"JSON root must be an object: {resolved}"
        )
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MaterialsProjectIndependentSourceReadinessError(
            f"{field} must be a non-empty repository-relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MaterialsProjectIndependentSourceReadinessError(
            f"{field} must be a safe repository-relative path"
        )
    return (PROJECT_ROOT / candidate).resolve(strict=True)


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "readiness_id",
        "acquisition_spec",
        "benchmark_config",
        "benchmark_directory",
        "benchmark_membership_output_key",
        "identity_fields",
        "independent_identifier_column",
        "independent_group_column",
        "original_identifier_column",
        "original_group_column",
        "scientific_boundary",
        "decision_rules",
        "next_stage",
    }
    if set(config) != expected or config.get("schema_version") != SCHEMA_VERSION:
        raise MaterialsProjectIndependentSourceReadinessError(
            "independent-source readiness config keys/schema do not match contract"
        )
    identity_fields = config["identity_fields"]
    if not isinstance(identity_fields, list) or not identity_fields:
        raise MaterialsProjectIndependentSourceReadinessError(
            "identity_fields must be a non-empty list"
        )
    if len(identity_fields) != len(set(identity_fields)):
        raise MaterialsProjectIndependentSourceReadinessError(
            "identity_fields must be unique"
        )
    forbidden_identity_fields = {"energy_above_hull", "is_stable"}
    if forbidden_identity_fields.intersection(identity_fields):
        raise MaterialsProjectIndependentSourceReadinessError(
            "target or target-derived fields are forbidden from the identity query"
        )
    for required in ("material_id", "chemsys", "elements", "nelements", "deprecated"):
        if required not in identity_fields:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"identity query is missing required field: {required}"
            )

    boundary = config["scientific_boundary"]
    required_false = {
        "benchmark_v1_locked_target_read_authorized",
        "benchmark_v1_locked_file_read_authorized",
        "current_target_property_query_authorized",
        "policy_execution_authorized",
        "model_fit_authorized",
        "policy_v2_freeze_authorized",
        "independent_benchmark_execution_authorized",
    }
    required_true = {
        "benchmark_partition_membership_read_authorized",
        "current_materials_project_identity_query_authorized",
    }
    if not isinstance(boundary, dict):
        raise MaterialsProjectIndependentSourceReadinessError(
            "scientific_boundary must be an object"
        )
    if any(boundary.get(key) is not False for key in required_false):
        raise MaterialsProjectIndependentSourceReadinessError(
            "stronger target/model/policy actions must remain disabled"
        )
    if any(boundary.get(key) is not True for key in required_true):
        raise MaterialsProjectIndependentSourceReadinessError(
            "required identity-only readiness actions are not authorized"
        )

    rules = config["decision_rules"]
    if not isinstance(rules, dict) or any(value is not True for value in rules.values()):
        raise MaterialsProjectIndependentSourceReadinessError(
            "all independent-source decision rules must be enabled"
        )
    return config


def _load_benchmark_membership(
    *,
    config: Mapping[str, Any],
    benchmark_dir: Path,
    benchmark_config_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], Path]:
    benchmark_config = _load_json(benchmark_config_path)
    manifest_path = benchmark_dir / "benchmark_manifest.json"
    manifest = _load_json(manifest_path)

    if manifest.get("benchmark_id") != benchmark_config.get("benchmark_id"):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark manifest/config id mismatch"
        )
    expected_source_rows = benchmark_config.get("expected_source", {}).get("row_count")
    if not isinstance(expected_source_rows, int) or expected_source_rows <= 0:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark expected source row count is invalid"
        )
    manifest_config = manifest.get("benchmark_config")
    if not isinstance(manifest_config, Mapping):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark manifest config binding is missing"
        )
    if manifest_config.get("sha256") != _sha256_file(benchmark_config_path):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark config checksum binding mismatch"
        )

    outputs = manifest.get("outputs")
    checksums = manifest.get("output_sha256")
    if not isinstance(outputs, Mapping) or not isinstance(checksums, Mapping):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark output bindings are missing"
        )
    output_key = str(config["benchmark_membership_output_key"])
    relative = outputs.get(output_key)
    if not isinstance(relative, str) or not relative:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership output is not declared"
        )
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership output path is unsafe"
        )
    membership_path = (benchmark_dir / relative_path).resolve(strict=True)
    if checksums.get(output_key) != _sha256_file(membership_path):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership checksum mismatch"
        )

    # This is the only benchmark CSV read by this audit.  In particular, the
    # locked/locked_test.csv path is never resolved or opened.
    membership = pd.read_csv(membership_path)
    identifier = str(config["original_identifier_column"])
    group = str(config["original_group_column"])
    required = {identifier, group, "benchmark_partition"}
    missing = sorted(required - set(membership.columns))
    if missing:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership missing columns: " + ", ".join(missing)
        )
    if "energy_above_hull" in membership.columns:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership unexpectedly contains the locked target"
        )
    ids = membership[identifier].astype(str).str.strip()
    groups = membership[group].astype(str).str.strip()
    if len(membership) != expected_source_rows:
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership row count does not match the locked source contract"
        )
    if ids.eq("").any() or ids.duplicated().any():
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership material IDs must be unique and nonblank"
        )
    if groups.eq("").any():
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark membership chemical-system groups must be nonblank"
        )

    manifest_partitions = manifest.get("partitions")
    if not isinstance(manifest_partitions, Mapping):
        raise MaterialsProjectIndependentSourceReadinessError(
            "benchmark manifest partition summary is missing"
        )
    observed_counts = membership["benchmark_partition"].value_counts().to_dict()
    for partition, record in manifest_partitions.items():
        if not isinstance(record, Mapping) or not isinstance(record.get("rows"), int):
            raise MaterialsProjectIndependentSourceReadinessError(
                f"invalid benchmark partition summary: {partition}"
            )
        if observed_counts.get(partition, 0) != int(record["rows"]):
            raise MaterialsProjectIndependentSourceReadinessError(
                f"benchmark membership partition count drifted: {partition}"
            )
    return membership, manifest, benchmark_config, membership_path


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _query_current_identity(
    *,
    acquisition_spec: dict[str, Any],
    identity_fields: list[str],
    client_factory: Callable[[], Any] | None,
    validate_signature: bool,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    params = build_exact_query_parameters(acquisition_spec, preflight=False)
    params["fields"] = list(identity_fields)
    params["all_fields"] = False
    if validate_signature:
        validate_query_parameters_against_signature(params)
    factory = client_factory or make_mpr_client

    client = factory()
    try:
        database_version_before = get_database_version(client)
        docs = list(client.materials.summary.search(**params))
    finally:
        _close_client(client)

    verification_client = factory()
    try:
        database_version_after = get_database_version(verification_client)
    finally:
        _close_client(verification_client)
    if database_version_after != database_version_before:
        raise MaterialsProjectIndependentSourceReadinessError(
            "Materials Project database version changed during the readiness query"
        )

    serialized, failures = serialize_documents(docs)
    if failures:
        raise MaterialsProjectIndependentSourceReadinessError(
            "Materials Project identity document serialization failed"
        )
    safe_params = dict(params)
    safe_params["fields"] = list(identity_fields)
    if any(field in safe_params["fields"] for field in ("energy_above_hull", "is_stable")):
        raise MaterialsProjectIndependentSourceReadinessError(
            "target property leaked into the identity query"
        )
    return serialized, database_version_before, safe_params


def _element_symbols(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    result: set[str] = set()
    for item in value:
        if isinstance(item, str):
            symbol = item.strip()
        elif isinstance(item, Mapping):
            raw = item.get("symbol") or item.get("element")
            symbol = str(raw).strip() if raw is not None else ""
        else:
            symbol = str(item).strip()
        if symbol:
            result.add(symbol)
    return result


def _validate_identity_documents(
    docs: list[dict[str, Any]],
    *,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    fields = list(config["identity_fields"])
    rows: list[dict[str, Any]] = []
    for index, doc in enumerate(docs):
        missing = [field for field in fields if field not in doc]
        if missing:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"identity response row {index} missing fields: {', '.join(missing)}"
            )
        material_id = str(doc.get("material_id") or "").strip()
        chemsys = str(doc.get("chemsys") or "").strip()
        formula = str(doc.get("formula_pretty") or "").strip()
        elements = _element_symbols(doc.get("elements"))
        try:
            nelements = int(doc.get("nelements"))
        except (TypeError, ValueError) as exc:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"identity response row {index} has invalid nelements"
            ) from exc
        deprecated = doc.get("deprecated")
        if not material_id or not chemsys:
            raise MaterialsProjectIndependentSourceReadinessError(
                "current identity response contains blank material_id or chemsys"
            )
        if not {"Fe", "Si"}.issubset(elements):
            raise MaterialsProjectIndependentSourceReadinessError(
                f"current identity response is outside Fe/Si scope: {material_id}"
            )
        if nelements < 2 or nelements > 5:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"current identity response is outside 2-5 element scope: {material_id}"
            )
        if deprecated is not False:
            raise MaterialsProjectIndependentSourceReadinessError(
                f"deprecated material returned despite deprecated=False: {material_id}"
            )
        rows.append(
            {
                "material_id": material_id,
                "formula_pretty": formula,
                "chemsys": chemsys,
                "nelements": nelements,
            }
        )
    frame = pd.DataFrame(rows, columns=["material_id", "formula_pretty", "chemsys", "nelements"])
    if frame.empty:
        raise MaterialsProjectIndependentSourceReadinessError(
            "current Materials Project identity query returned no rows"
        )
    if frame["material_id"].duplicated().any():
        raise MaterialsProjectIndependentSourceReadinessError(
            "current Materials Project identity query returned duplicate material_id values"
        )
    return frame.sort_values("material_id", kind="mergesort").reset_index(drop=True)


def run_materials_project_independent_source_readiness(
    *,
    config_path: str | Path,
    benchmark_dir: str | Path | None = None,
    output_dir: str | Path,
    client_factory: Callable[[], Any] | None = None,
    validate_signature: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Inventory current independent identities without querying target properties."""
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    acquisition_spec_path = _repo_path(config["acquisition_spec"], "acquisition_spec")
    benchmark_config_path = _repo_path(config["benchmark_config"], "benchmark_config")
    if benchmark_dir is None:
        benchmark_root = _repo_path(config["benchmark_directory"], "benchmark_directory")
    else:
        benchmark_root = Path(benchmark_dir).expanduser().resolve(strict=True)

    membership, benchmark_manifest, benchmark_config, membership_path = _load_benchmark_membership(
        config=config,
        benchmark_dir=benchmark_root,
        benchmark_config_path=benchmark_config_path,
    )
    acquisition_spec = load_acquisition_spec(acquisition_spec_path)
    docs, database_version, query_params = _query_current_identity(
        acquisition_spec=acquisition_spec,
        identity_fields=list(config["identity_fields"]),
        client_factory=client_factory,
        validate_signature=validate_signature,
    )
    current = _validate_identity_documents(docs, config=config)

    original_identifier = str(config["original_identifier_column"])
    original_group = str(config["original_group_column"])
    original_ids = set(membership[original_identifier].astype(str))
    original_groups = set(membership[original_group].astype(str))
    current_ids = set(current["material_id"])
    overlap_ids = original_ids.intersection(current_ids)
    new_ids = current_ids - original_ids
    missing_original_ids = original_ids - current_ids
    independent = current[current["material_id"].isin(new_ids)].copy()
    independent = independent.sort_values("material_id", kind="mergesort").reset_index(drop=True)
    independent_groups = set(independent["chemsys"].astype(str))
    exact_group_overlap = independent_groups.intersection(original_groups)

    source_outcome = "new_identity_cohort_available" if len(independent) else "no_new_identity_cohort"
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "readiness_id": config["readiness_id"],
        "execution_status": "independent_source_identity_inventory_completed",
        "scientific_evidence_level": "DevelopmentDiagnostic",
        "source_outcome": source_outcome,
        "materials_project_database_version": database_version,
        "source_binding": {
            "acquisition_spec_sha256": _sha256_file(acquisition_spec_path),
            "benchmark_config_sha256": _sha256_file(benchmark_config_path),
            "benchmark_manifest_sha256": _sha256_file(benchmark_root / "benchmark_manifest.json"),
            "benchmark_membership_sha256": _sha256_file(membership_path),
            "canonical_query_scope": {
                "elements": list(query_params["elements"]),
                "num_elements": list(query_params["num_elements"]),
                "deprecated": query_params["deprecated"],
                "include_gnome": query_params["include_gnome"],
                "fields": list(query_params["fields"]),
                "target_filters_used": False,
            },
        },
        "original_benchmark": {
            "benchmark_id": benchmark_config["benchmark_id"],
            "rows": int(len(membership)),
            "unique_material_ids": int(len(original_ids)),
            "chemical_system_groups": int(len(original_groups)),
            "partition_rows": {
                key: int(value["rows"])
                for key, value in benchmark_manifest["partitions"].items()
            },
            "partition_membership_read": True,
            "locked_test_file_read": False,
            "locked_target_read": False,
        },
        "current_identity_query": {
            "rows": int(len(current)),
            "unique_material_ids": int(len(current_ids)),
            "chemical_system_groups": int(current["chemsys"].nunique()),
            "identity_fields_only": True,
            "target_property_queried": False,
            "policy_executed": False,
            "model_fit": False,
        },
        "overlap": {
            "original_ids_still_present": int(len(overlap_ids)),
            "original_ids_absent_from_current_query": int(len(missing_original_ids)),
            "new_material_ids_after_original_exclusion": int(len(new_ids)),
        },
        "independent_candidate_inventory": {
            "rows": int(len(independent)),
            "chemical_system_groups": int(len(independent_groups)),
            "groups_also_seen_in_original_benchmark": int(len(exact_group_overlap)),
            "groups_not_seen_in_original_benchmark": int(len(independent_groups - original_groups)),
            "candidate_ranking_performed": False,
            "target_values_used": False,
            "adequacy_threshold_applied": False,
        },
        "policy_v2_freeze_authorized": False,
        "independent_benchmark_execution_authorized": False,
        "next_stage": config["next_stage"],
    }

    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(config_resolved, acquisition_spec_path, benchmark_config_path, benchmark_root),
        recognized_markers=(MANIFEST_NAME,),
    ) as staging:
        independent.to_csv(staging / CANDIDATE_NAME, index=False, lineterminator="\n")
        result["outputs"] = {
            "readiness": MANIFEST_NAME,
            "candidate_identity": CANDIDATE_NAME,
        }
        result["candidate_identity_sha256"] = _sha256_file(staging / CANDIDATE_NAME)
        (staging / MANIFEST_NAME).write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return result


__all__ = [
    "MaterialsProjectIndependentSourceReadinessError",
    "run_materials_project_independent_source_readiness",
]
