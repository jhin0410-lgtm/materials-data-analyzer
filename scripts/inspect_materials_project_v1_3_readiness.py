"""Inspect Materials Project v1.3 contract readiness without network access."""

from __future__ import annotations

import argparse
import inspect
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_KEY_TOKENS = {"api_key", "apikey", "token", "secret", "password"}
ALLOWED_CREDENTIAL_POLICY_KEYS = {
    "credential_policy",
    "credential_included",
}
ACQUISITION_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_version",
    "dataset_name",
    "source_system",
    "endpoint_family",
    "query_method",
    "execution_status",
    "query_scope",
    "required_elements",
    "element_count_range",
    "exclude_elements",
    "deprecated_policy",
    "theoretical_policy",
    "include_gnome_policy",
    "target_filter_policy",
    "requested_fields",
    "mandatory_fields",
    "optional_fields",
    "target_column",
    "identifier_column",
    "composition_source_column",
    "query_parameters",
    "chunk_size",
    "result_limit",
    "ordering_policy",
    "duplicate_policy",
    "polymorph_policy",
    "local_output_path",
    "provenance_output_path",
    "credential_policy",
    "tracking_policy",
    "scientific_scope",
    "limitations",
    "stop_conditions",
]
MODELING_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_version",
    "dataset_name",
    "modeling_goal",
    "target",
    "prediction_context",
    "primary_feature_tier",
    "optional_comparison_feature_tiers",
    "forbidden_features",
    "leakage_candidates",
    "grouping_columns",
    "split_strategies",
    "metrics",
    "baseline_models",
    "reproducibility_policy",
    "uncertainty_policy",
    "interpretation_limits",
    "minimum_data_requirements",
    "stop_conditions",
]
REQUIRED_PROVENANCE_CAPTURE_FIELDS = [
    "acquisition_utc_timestamp",
    "python_version",
    "mp_api_version",
    "pymatgen_version",
    "emmet_core_version",
    "api_endpoint",
    "materials_project_database_version",
    "exact_query_parameters",
    "exact_requested_fields",
    "returned_row_count",
    "returned_column_count",
    "chunk_size",
    "chunk_count",
    "raw_output_sha256",
    "sorted_output_sha256",
    "duplicate_material_id_count",
    "null_target_count",
    "credential_included",
    "absolute_path_included",
    "execution_status",
    "partial_download_or_error_status",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Materials Project v1.3 acquisition/modeling contract "
            "readiness without API or network access."
        )
    )
    parser.add_argument(
        "--acquisition-spec",
        default="data/case_studies/materials_project/acquisition_spec_v1_3.json",
        help="v1.3 acquisition contract JSON.",
    )
    parser.add_argument(
        "--modeling-contract",
        default="data/case_studies/materials_project/modeling_contract_v1_3.json",
        help="v1.3 modeling contract JSON.",
    )
    return parser.parse_args()


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object deterministically."""
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def validate_acquisition_spec(spec: dict[str, Any]) -> None:
    """Validate the Materials Project v1.3 acquisition contract."""
    _validate_required_fields(spec, ACQUISITION_REQUIRED_FIELDS, "acquisition spec")
    _ensure_no_forbidden_secret_keys(spec)
    _ensure_no_absolute_paths(spec)

    if spec["execution_status"] not in {"planned", "validated_not_executed"}:
        raise ValueError("execution_status must be planned or validated_not_executed.")
    if spec["required_elements"] != ["Fe", "Si"]:
        raise ValueError("required_elements must be exactly ['Fe', 'Si'] for v1.3.")
    if spec["element_count_range"] != [2, 5]:
        raise ValueError("element_count_range must be [2, 5].")
    if _has_duplicates(spec["requested_fields"]):
        raise ValueError("requested_fields must not contain duplicates.")
    missing_mandatory = [
        field for field in spec["mandatory_fields"] if field not in spec["requested_fields"]
    ]
    if missing_mandatory:
        raise ValueError(
            "mandatory_fields must be included in requested_fields: "
            + ", ".join(missing_mandatory)
        )
    if spec["target_column"] not in spec["requested_fields"]:
        raise ValueError("target_column must be included in requested_fields.")
    if spec["identifier_column"] not in spec["requested_fields"]:
        raise ValueError("identifier_column must be included in requested_fields.")
    if spec["composition_source_column"] not in spec["requested_fields"]:
        raise ValueError("composition_source_column must be included in requested_fields.")

    query_parameters = spec["query_parameters"]
    if query_parameters.get("energy_above_hull") is not None:
        raise ValueError("energy_above_hull must not be used as an acquisition filter.")
    if query_parameters.get("is_stable") is not None:
        raise ValueError("is_stable must not be used as an acquisition filter.")
    if spec["target_filter_policy"].get("energy_above_hull") != "do_not_filter":
        raise ValueError("target_filter_policy must forbid energy_above_hull filtering.")
    if spec["target_filter_policy"].get("is_stable") != "do_not_filter":
        raise ValueError("target_filter_policy must forbid is_stable filtering.")
    if query_parameters.get("include_gnome") is None:
        raise ValueError("include_gnome must be explicitly set.")
    if query_parameters.get("deprecated") is not False:
        raise ValueError("deprecated query parameter must be false.")
    if query_parameters.get("num_elements") != [2, 5]:
        raise ValueError("query_parameters.num_elements must be [2, 5].")
    if query_parameters.get("chunk_size") != spec["chunk_size"]:
        raise ValueError("query chunk_size must match top-level chunk_size.")
    if spec["credential_policy"].get("environment_variable") != "MP_API_KEY":
        raise ValueError("credential policy must use MP_API_KEY.")
    if spec["credential_policy"].get("log_value") is not False:
        raise ValueError("credential policy must forbid logging credential values.")


def validate_modeling_contract(contract: dict[str, Any]) -> None:
    """Validate the Materials Project v1.3 modeling contract."""
    _validate_required_fields(contract, MODELING_REQUIRED_FIELDS, "modeling contract")
    _ensure_no_forbidden_secret_keys(contract)
    _ensure_no_absolute_paths(contract)

    target_column = contract["target"]["column"]
    if target_column != "energy_above_hull":
        raise ValueError("Modeling target must be energy_above_hull.")

    forbidden_features = set(contract["forbidden_features"])
    required_forbidden = {
        "material_id",
        "energy_above_hull",
        "is_stable",
        "energy_above_hull_rank",
        "energy_above_hull_label",
        "target_derived_screening_score",
    }
    missing_forbidden = sorted(required_forbidden - forbidden_features)
    if missing_forbidden:
        raise ValueError(
            "forbidden_features missing required leakage exclusions: "
            + ", ".join(missing_forbidden)
        )

    primary_sources = set(contract["primary_feature_tier"]["source_fields"])
    if target_column in primary_sources or "is_stable" in primary_sources:
        raise ValueError("Primary feature tier must not include target/leakage fields.")
    if "composition" not in primary_sources and "composition_reduced" not in primary_sources:
        raise ValueError("Primary feature tier must include composition sources.")

    split_names = {split["name"] for split in contract["split_strategies"]}
    required_splits = {
        "deterministic_random_split",
        "reduced_formula_group_split",
        "chemical_system_group_split",
    }
    missing_splits = sorted(required_splits - split_names)
    if missing_splits:
        raise ValueError(
            "split_strategies missing required strategy/strategies: "
            + ", ".join(missing_splits)
        )
    for metric in ["MAE", "RMSE", "R2", "Spearman rank correlation"]:
        if metric not in contract["metrics"]:
            raise ValueError(f"metrics missing required metric: {metric}")


def inspect_installed_api_contract() -> dict[str, Any]:
    """Inspect installed Materials Project package signatures without networking."""
    packages = {}
    for package_name in ["mp-api", "pymatgen", "emmet-core"]:
        try:
            version = metadata.version(package_name)
            packages[package_name] = {"installed": True, "version": version}
        except metadata.PackageNotFoundError:
            packages[package_name] = {"installed": False, "version": None}

    inspection: dict[str, Any] = {
        "python_version": platform.python_version(),
        "packages": packages,
        "network_called": False,
        "api_key_read": False,
    }

    try:
        from mp_api.client import MPRester

        inspection["mpr_importable"] = True
        constructor_parameters = list(inspect.signature(MPRester).parameters)
        inspection["mpr_constructor_parameters"] = constructor_parameters
        inspection["mpr_database_version_methods"] = [
            name
            for name in ["get_database_version", "get_emmet_version"]
            if hasattr(MPRester, name)
        ]
    except Exception as exc:
        inspection["mpr_importable"] = False
        inspection["mpr_error"] = f"{type(exc).__name__}: {exc}"

    try:
        from mp_api.client.routes.materials.summary import SummaryRester

        signature = inspect.signature(SummaryRester.search)
        parameters = list(signature.parameters)
        inspection["summary_search_importable"] = True
        inspection["summary_search_parameters"] = parameters
        inspection["summary_search_supported_contract_parameters"] = {
            "elements": "elements" in parameters,
            "exclude_elements": "exclude_elements" in parameters,
            "num_elements": "num_elements" in parameters,
            "nelements": "nelements" in parameters,
            "deprecated": "deprecated" in parameters,
            "theoretical": "theoretical" in parameters,
            "include_gnome": "include_gnome" in parameters,
            "fields": "fields" in parameters,
            "all_fields": "all_fields" in parameters,
            "chunk_size": "chunk_size" in parameters,
            "num_chunks": "num_chunks" in parameters,
            "_sort_fields": "_sort_fields" in parameters,
            "energy_above_hull": "energy_above_hull" in parameters,
            "is_stable": "is_stable" in parameters,
        }
    except Exception as exc:
        inspection["summary_search_importable"] = False
        inspection["summary_search_error"] = f"{type(exc).__name__}: {exc}"

    try:
        from emmet.core.summary import SummaryDoc

        if hasattr(SummaryDoc, "model_fields"):
            fields = list(SummaryDoc.model_fields)
        elif hasattr(SummaryDoc, "__fields__"):
            fields = list(SummaryDoc.__fields__)
        else:
            fields = []
        inspection["summary_doc_importable"] = True
        inspection["summary_doc_field_count"] = len(fields)
        inspection["summary_doc_fields"] = fields
    except Exception as exc:
        inspection["summary_doc_importable"] = False
        inspection["summary_doc_error"] = f"{type(exc).__name__}: {exc}"

    return inspection


def validate_installed_contract_support(
    acquisition_spec: dict[str, Any],
    inspection: dict[str, Any],
) -> list[str]:
    """Return readiness stop reasons from installed package inspection."""
    stop_reasons: list[str] = []
    supported = inspection.get("summary_search_supported_contract_parameters", {})
    for parameter in ["elements", "num_elements", "deprecated", "theoretical", "include_gnome", "fields", "all_fields", "chunk_size", "num_chunks"]:
        if not supported.get(parameter):
            stop_reasons.append(f"summary.search parameter unavailable: {parameter}")

    fields = set(inspection.get("summary_doc_fields", []))
    for field in acquisition_spec["requested_fields"]:
        if field not in fields:
            stop_reasons.append(f"SummaryDoc field unavailable: {field}")
    return stop_reasons


def build_readiness_report(
    acquisition_spec: dict[str, Any],
    modeling_contract: dict[str, Any],
    inspection: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact readiness report."""
    stop_reasons = validate_installed_contract_support(acquisition_spec, inspection)
    unresolved_live_preflight = [
        "Confirm live API returned rows all contain Fe and Si.",
        "Record Materials Project database version during authenticated acquisition.",
        "Record returned row count, target null count, duplicate material_id count, and output SHA-256 values.",
        "Audit target distribution before training any model.",
    ]
    return {
        "readiness_status": "pass" if not stop_reasons else "blocked",
        "stop_reasons": stop_reasons,
        "python_version": inspection.get("python_version"),
        "installed_versions": inspection.get("packages", {}),
        "mpr_importable": inspection.get("mpr_importable", False),
        "summary_search_importable": inspection.get("summary_search_importable", False),
        "summary_search_supported_contract_parameters": inspection.get(
            "summary_search_supported_contract_parameters",
            {},
        ),
        "requested_fields": acquisition_spec["requested_fields"],
        "mandatory_fields": acquisition_spec["mandatory_fields"],
        "optional_fields": acquisition_spec["optional_fields"],
        "target": modeling_contract["target"]["column"],
        "primary_feature_tier": modeling_contract["primary_feature_tier"]["name"],
        "split_strategies": [
            split["name"] for split in modeling_contract["split_strategies"]
        ],
        "provenance_capture_required_fields": REQUIRED_PROVENANCE_CAPTURE_FIELDS,
        "unresolved_live_preflight": unresolved_live_preflight,
        "network_called": False,
        "api_key_read": False,
    }


def _validate_required_fields(data: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise ValueError(f"{label} missing required field(s): {', '.join(missing)}")


def _ensure_no_forbidden_secret_keys(value: Any) -> None:
    if _contains_forbidden_secret_key(value):
        raise ValueError("Contract contains forbidden secret-like keys.")


def _contains_forbidden_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if normalized_key not in ALLOWED_CREDENTIAL_POLICY_KEYS:
                if any(token in normalized_key for token in SECRET_KEY_TOKENS):
                    return True
            if _contains_forbidden_secret_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_secret_key(item) for item in value)
    return False


def _ensure_no_absolute_paths(value: Any) -> None:
    if _contains_absolute_path(value):
        raise ValueError("Contract contains absolute local paths.")


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


def _has_duplicates(values: list[Any]) -> bool:
    return len(values) != len(set(values))


def main() -> None:
    """Run readiness inspection and print a sanitized JSON report."""
    args = parse_args()
    try:
        acquisition_spec = load_json(args.acquisition_spec)
        modeling_contract = load_json(args.modeling_contract)
        validate_acquisition_spec(acquisition_spec)
        validate_modeling_contract(modeling_contract)
        inspection = inspect_installed_api_contract()
        report = build_readiness_report(acquisition_spec, modeling_contract, inspection)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Materials Project v1.3 readiness inspection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
