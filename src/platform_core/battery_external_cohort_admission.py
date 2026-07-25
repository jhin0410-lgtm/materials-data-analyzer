from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import pandas as pd

GATE_VERSION = "2.6.4"
GATE_ID = "battery_external_cohort_admission_gate_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_external_cohort_admission.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_external_cohort_admission"
DEFAULT_TRACKED_SUMMARY = (
    "data/processed/battery_v2_6_4_external_cohort_admission_summary.json"
)
REQUIRED_EVIDENCE_FIELDS = (
    "chemistry",
    "nominal_capacity",
    "ambient_temperature",
    "charge_protocol",
    "discharge_protocol",
    "cutoff_voltage",
    "measurement_calibration",
    "source_snapshot",
)
ADMISSION_STAGES = (
    "inventory_review",
    "cross_cohort_comparability",
    "predictive_validation",
)
REQUIRED_GRANULARITY = {
    "chemistry": "battery_level_source_record",
    "nominal_capacity": "battery_level_source_record",
    "ambient_temperature": "cycle_level_commanded_or_controlled",
    "charge_protocol": "cycle_level_commanded",
    "discharge_protocol": "cycle_level_commanded",
    "cutoff_voltage": "cycle_level_commanded",
    "measurement_calibration": "instrument_or_channel_level",
    "source_snapshot": "official_distribution_level",
}
CONFIG_FIELDS = {
    "schema_version",
    "gate_id",
    "case_study_id",
    "candidate_manifest_path",
    "source_comparability_summary_path",
    "source_inventory_audit_path",
    "source_case_study_spec_path",
    "expected_comparability_checksum",
    "expected_persistence_mae",
    "expected_ridge_mae",
    "required_evidence_fields",
    "admission_stages",
    "credential_policy",
    "output_root",
    "tracked_summary_path",
    "output_policy",
}
MANIFEST_FIELDS = {
    "schema_version",
    "manifest_id",
    "candidate_id",
    "candidate_kind",
    "intended_use",
    "source_bundle",
    "evidence_declarations",
    "validation_plan",
    "claim_policy",
}
DECLARATION_FIELDS = {
    "evidence_field",
    "availability_status",
    "evidence_basis",
    "granularity",
    "source_reference",
    "source_backed",
    "inference_required",
    "filename_derived",
    "commanded_condition_evidence",
    "limitation",
}
SOURCE_BUNDLE_FIELDS = {
    "archive_count",
    "cycle_file_count",
    "timeseries_file_count",
    "dedicated_metadata_sidecar_present",
    "official_snapshot_identifier_present",
    "raw_inventory_verified",
}
VALIDATION_PLAN_FIELDS = {
    "evaluation_scenario",
    "target_definition_status",
    "target_source_reference",
    "predeclared_before_model_evaluation",
    "model_training_requested",
    "model_evaluation_requested",
    "harmonization_requested",
}
CLAIM_POLICY_FIELDS = {
    "filename_labels_are_source_evidence",
    "derived_reference_is_nominal_capacity",
    "observed_signal_is_commanded_protocol",
    "missing_metadata_may_be_inferred",
}
FALSE_FLAGS = (
    "network_called",
    "credentials_read",
    "raw_data_read",
    "archives_extracted",
    "filename_metadata_parsed",
    "source_mutation_performed",
    "model_trained",
    "model_evaluated",
    "metrics_recomputed",
    "data_inference_performed",
)
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True)
class BatteryExternalCohortAdmissionConfig:
    schema_version: str
    gate_id: str
    case_study_id: str
    candidate_manifest_path: str
    source_comparability_summary_path: str
    source_inventory_audit_path: str
    source_case_study_spec_path: str
    expected_comparability_checksum: str
    expected_persistence_mae: float
    expected_ridge_mae: float
    required_evidence_fields: tuple[str, ...]
    admission_stages: tuple[str, ...]
    credential_policy: Mapping[str, bool]
    output_root: str
    tracked_summary_path: str
    output_policy: str

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> "BatteryExternalCohortAdmissionConfig":
        _exact_fields(payload, CONFIG_FIELDS, "config")
        if payload["schema_version"] != GATE_VERSION or payload["gate_id"] != GATE_ID:
            raise ValueError("unsupported external cohort admission version or id")
        if tuple(payload["required_evidence_fields"]) != REQUIRED_EVIDENCE_FIELDS:
            raise ValueError("required_evidence_fields must match the predeclared gate")
        if tuple(payload["admission_stages"]) != ADMISSION_STAGES:
            raise ValueError("admission_stages must match the predeclared gate")
        if not HEX_SHA256.fullmatch(str(payload["expected_comparability_checksum"])):
            raise ValueError("expected_comparability_checksum must be lowercase SHA-256")
        for field in ("expected_persistence_mae", "expected_ridge_mae"):
            value = float(payload[field])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be finite and nonnegative")
        if payload["credential_policy"] != {
            "store_credentials": False,
            "network_access_required": False,
        }:
            raise ValueError("credential policy must disable storage and network")
        paths = {
            field: _relative(field, payload[field])
            for field in (
                "candidate_manifest_path",
                "source_comparability_summary_path",
                "source_inventory_audit_path",
                "source_case_study_spec_path",
                "output_root",
                "tracked_summary_path",
            )
        }
        if paths["output_root"] != DEFAULT_OUTPUT_ROOT:
            raise ValueError("output_root does not match the v2.6.4 contract")
        if paths["tracked_summary_path"] != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("tracked_summary_path does not match the v2.6.4 contract")
        if payload["output_policy"] != "local_details_and_tracked_compact_summary":
            raise ValueError("unsupported output_policy")
        return cls(
            schema_version=GATE_VERSION,
            gate_id=GATE_ID,
            case_study_id=str(payload["case_study_id"]),
            expected_comparability_checksum=str(payload["expected_comparability_checksum"]),
            expected_persistence_mae=float(payload["expected_persistence_mae"]),
            expected_ridge_mae=float(payload["expected_ridge_mae"]),
            required_evidence_fields=REQUIRED_EVIDENCE_FIELDS,
            admission_stages=ADMISSION_STAGES,
            credential_policy=dict(payload["credential_policy"]),
            output_policy=str(payload["output_policy"]),
            **paths,
        )


def _exact_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    unknown = sorted(set(payload) - expected)
    missing = sorted(expected - set(payload))
    if unknown:
        raise ValueError(f"unknown {label} field(s): " + ", ".join(unknown))
    if missing:
        raise ValueError(f"missing {label} field(s): " + ", ".join(missing))


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item"):
        try:
            return _safe(value.item())
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        _safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = dict(payload)
    core.pop("deterministic_result_checksum", None)
    return hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()


def _relative(field: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    if (
        Path(text).is_absolute()
        or re.match(r"^[A-Za-z]:", text)
        or text.startswith("//")
        or ".." in Path(text).parts
    ):
        raise ValueError(f"{field} must be repository-relative and non-traversing")
    return Path(text).as_posix()


def resolve_repo_path(repo_root: str | Path, value: str | Path) -> Path:
    root = Path(repo_root).resolve()
    path = (root / Path(value)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = "."
) -> BatteryExternalCohortAdmissionConfig:
    return BatteryExternalCohortAdmissionConfig.from_mapping(
        _load_json(resolve_repo_path(repo_root, path))
    )


def validate_candidate_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(payload, MANIFEST_FIELDS, "candidate manifest")
    if payload["schema_version"] != "1":
        raise ValueError("unsupported candidate manifest schema_version")
    for field in ("manifest_id", "candidate_id"):
        if not SAFE_ID.fullmatch(str(payload[field])):
            raise ValueError(f"{field} must be a stable lowercase identifier")
    if payload["candidate_kind"] != "external_battery_cohort_bundle":
        raise ValueError("candidate_kind must be external_battery_cohort_bundle")
    if payload["intended_use"] != "cross_cohort_validation":
        raise ValueError("intended_use must be cross_cohort_validation")

    source = payload["source_bundle"]
    if not isinstance(source, Mapping):
        raise ValueError("source_bundle must be an object")
    _exact_fields(source, SOURCE_BUNDLE_FIELDS, "source_bundle")
    for field in ("archive_count", "cycle_file_count", "timeseries_file_count"):
        if not isinstance(source[field], int) or source[field] < 0:
            raise ValueError(f"source_bundle.{field} must be a nonnegative integer")
    for field in SOURCE_BUNDLE_FIELDS - {
        "archive_count", "cycle_file_count", "timeseries_file_count"
    }:
        if not isinstance(source[field], bool):
            raise ValueError(f"source_bundle.{field} must be boolean")

    declarations = payload["evidence_declarations"]
    if not isinstance(declarations, list) or len(declarations) != 8:
        raise ValueError("evidence_declarations must contain the eight gate fields")
    for row in declarations:
        if not isinstance(row, Mapping):
            raise ValueError("each evidence declaration must be an object")
        _exact_fields(row, DECLARATION_FIELDS, "evidence declaration")
        for field in (
            "source_backed", "inference_required", "filename_derived", "commanded_condition_evidence"
        ):
            if not isinstance(row[field], bool):
                raise ValueError(f"evidence declaration {field} must be boolean")
    if tuple(row["evidence_field"] for row in declarations) != REQUIRED_EVIDENCE_FIELDS:
        raise ValueError("evidence declaration order must match the predeclared gate")

    plan = payload["validation_plan"]
    if not isinstance(plan, Mapping):
        raise ValueError("validation_plan must be an object")
    _exact_fields(plan, VALIDATION_PLAN_FIELDS, "validation_plan")
    if plan["evaluation_scenario"] != "cross_cohort_external_validation":
        raise ValueError("unsupported validation scenario")
    if plan["predeclared_before_model_evaluation"] is not True:
        raise ValueError("validation plan must be predeclared before model evaluation")

    policy = payload["claim_policy"]
    if not isinstance(policy, Mapping):
        raise ValueError("claim_policy must be an object")
    _exact_fields(policy, CLAIM_POLICY_FIELDS, "claim_policy")
    if any(value is not False for value in policy.values()):
        raise ValueError("candidate claim policy must prohibit inferred equivalence")
    return _safe(payload)


def _load_sources(
    config: BatteryExternalCohortAdmissionConfig, repo_root: str | Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    refs = {
        "candidate_manifest": config.candidate_manifest_path,
        "source_comparability_summary": config.source_comparability_summary_path,
        "source_inventory_audit": config.source_inventory_audit_path,
        "source_case_study_spec": config.source_case_study_spec_path,
    }
    paths = {name: resolve_repo_path(repo_root, value) for name, value in refs.items()}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    return (
        validate_candidate_manifest(_load_json(paths["candidate_manifest"])),
        _load_json(paths["source_comparability_summary"]),
        refs,
    )


def _preservation(
    prior: Mapping[str, Any], config: BatteryExternalCohortAdmissionConfig
) -> dict[str, Any]:
    if prior.get("deterministic_result_checksum") != config.expected_comparability_checksum:
        raise ValueError("source comparability checksum mismatch")
    if prior.get("comparability_decision", {}).get("status") != "comparability_not_established":
        raise ValueError("source comparability decision changed unexpectedly")
    for field in ("data_inference_performed", "model_retrained", "metrics_recomputed"):
        if prior.get(field) is not False:
            raise ValueError(f"source comparability package must preserve {field}=false")
    metrics = {
        str(row.get("model")): row
        for row in prior.get("preservation_checks", {}).get("preserved_metrics", [])
    }
    expected = {
        "persistence": config.expected_persistence_mae,
        "ridge": config.expected_ridge_mae,
    }
    for model, mae in expected.items():
        actual = float(metrics.get(model, {}).get("mae", math.nan))
        if not math.isclose(actual, mae, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{model} MAE changed unexpectedly")
    return {
        "comparability_checksum_verified": True,
        "prior_comparability_status": "comparability_not_established",
        "prior_comparability_status_preserved": True,
        "model_metrics_unchanged": True,
        "model_or_metric_change_performed": False,
        "preserved_metrics": [
            {"model": "persistence", "mae": expected["persistence"]},
            {"model": "ridge", "mae": expected["ridge"]},
        ],
    }


def build_admission_matrix(manifest: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    controlled_fields = {
        "ambient_temperature", "charge_protocol", "discharge_protocol", "cutoff_voltage"
    }
    for item in manifest["evidence_declarations"]:
        field = str(item["evidence_field"])
        satisfied = bool(
            item["source_backed"]
            and not item["inference_required"]
            and not item["filename_derived"]
            and item["granularity"] == REQUIRED_GRANULARITY[field]
        )
        if field in controlled_fields:
            satisfied = satisfied and bool(item["commanded_condition_evidence"])
        rows.append(
            {
                "evidence_field": field,
                "required_granularity": REQUIRED_GRANULARITY[field],
                "declared_availability_status": item["availability_status"],
                "declared_evidence_basis": item["evidence_basis"],
                "declared_granularity": item["granularity"],
                "source_reference": item["source_reference"],
                "source_backed": bool(item["source_backed"]),
                "inference_required": bool(item["inference_required"]),
                "filename_derived": bool(item["filename_derived"]),
                "commanded_condition_evidence": bool(item["commanded_condition_evidence"]),
                "requirement_satisfied": bool(satisfied),
                "limitation": item["limitation"],
                "same_condition_assumption_made": False,
                "inference_performed": False,
            }
        )
    frame = pd.DataFrame(rows)
    if tuple(frame["evidence_field"]) != REQUIRED_EVIDENCE_FIELDS:
        raise AssertionError("admission matrix order changed")
    return frame


def _decision(manifest: Mapping[str, Any], matrix: pd.DataFrame) -> dict[str, Any]:
    bundle = manifest["source_bundle"]
    inventory_ready = bool(
        bundle["raw_inventory_verified"]
        and bundle["archive_count"] > 0
        and bundle["cycle_file_count"] > 0
    )
    blocking = matrix.loc[~matrix["requirement_satisfied"], "evidence_field"].tolist()
    comparable = not blocking
    target_ready = manifest["validation_plan"]["target_definition_status"] == "source_defined_verified"
    predictive = comparable and target_ready
    return {
        "candidate_id": manifest["candidate_id"],
        "intended_use": manifest["intended_use"],
        "inventory_review": {
            "status": "admitted_with_restrictions" if inventory_ready else "not_admitted",
            "raw_data_analysis_authorized": False,
            "allowed_scope": [
                "archive and file inventory review",
                "source-document recovery planning",
                "loader software-contract testing with synthetic fixtures",
            ],
        },
        "cross_cohort_comparability": {
            "status": "admitted" if comparable else "not_admitted",
            "blocking_fields": blocking,
            "same_condition_claim_allowed": False,
            "heterogeneous_dataset_merge_allowed": False,
        },
        "predictive_validation": {
            "status": "admitted" if predictive else "blocked",
            "target_definition_ready": target_ready,
            "model_training_allowed": False,
            "model_evaluation_allowed": False,
            "metric_comparison_allowed": False,
        },
        "overall_status": (
            "admitted_for_cross_cohort_validation"
            if predictive
            else "not_admitted_for_cross_cohort_validation"
        ),
    }


def _evaluate_once(
    config: BatteryExternalCohortAdmissionConfig, repo_root: str | Path
) -> dict[str, Any]:
    manifest, prior, refs = _load_sources(config, repo_root)
    matrix = build_admission_matrix(manifest)
    decision = _decision(manifest, matrix)
    satisfied = int(matrix["requirement_satisfied"].sum())
    result: dict[str, Any] = {
        "schema_version": GATE_VERSION,
        "artifact_kind": "battery_external_cohort_admission_result",
        "gate_id": GATE_ID,
        "case_study_id": config.case_study_id,
        "candidate_id": manifest["candidate_id"],
        "source_references": refs,
        "source_artifact_checksums": {
            "candidate_manifest_canonical_sha256": canonical_checksum(manifest),
            "source_comparability_summary_checksum": config.expected_comparability_checksum,
            "source_inventory_audit_status": "tracked_reference_present",
            "source_case_study_spec_status": "tracked_reference_present",
        },
        "candidate_manifest_checksum": canonical_checksum(manifest),
        "required_evidence_fields": list(REQUIRED_EVIDENCE_FIELDS),
        "admission_stages": list(ADMISSION_STAGES),
        "candidate_manifest": manifest,
        "admission_matrix": matrix.to_dict(orient="records"),
        "coverage_summary": {
            "required_field_count": 8,
            "requirement_satisfied_count": satisfied,
            "blocking_field_count": 8 - satisfied,
            "inference_required_field_count": int(matrix["inference_required"].sum()),
            "filename_derived_field_count": int(matrix["filename_derived"].sum()),
            "all_required_fields_audited": True,
        },
        "admission_decision": decision,
        "preservation_checks": _preservation(prior, config),
        "scientific_closeout": {
            "status": "inconclusive",
            "result": decision["overall_status"],
            "evidence_level": "candidate_inventory_without_source_backed_comparability",
            "strongest_evidence": (
                "The local Battery Archive bundle inventory records nine archives, "
                "196 cycle files, and 196 time-series files without reading raw data."
            ),
            "primary_limitation": (
                "Chemistry and protocol labels are filename-encoded rather than source-backed "
                "records; nominal capacity, cycle-specific commanded conditions, cutoff policy, "
                "calibration/uncertainty, and an official snapshot identifier remain unavailable."
            ),
            "suitable_for": [
                "raw inventory review",
                "source-document recovery planning",
                "software-contract testing with synthetic fixtures",
            ],
            "unsuitable_for": [
                "cross-cohort condition equivalence",
                "heterogeneous cohort merging",
                "predictive validation",
                "model selection or tuning",
                "mechanism or causal interpretation",
                "engineering decision",
            ],
            "what_would_change_conclusion": [
                "battery-level source records for chemistry and nominal capacity",
                "cycle-specific commanded charge and discharge protocols",
                "cycle-specific cutoff-voltage policy",
                "instrument calibration and measurement-uncertainty records",
                "an independently verifiable official distribution snapshot",
                "a source-defined or prospectively verified target contract",
            ],
        },
        "unresolved_information": decision["cross_cohort_comparability"]["blocking_fields"],
        "recommendations": [
            "retain filename-derived values only as parsed labels with explicit provenance",
            "do not use filename labels as scientific comparability evidence",
            "recover official source documentation before processing a validation cohort",
            "do not merge the Battery Archive bundle with the Kaggle NASA-derived cohort",
            "do not evaluate or train a model until this gate is passed prospectively",
        ],
        "prohibited_claims": [
            "filename-encoded chemistry is verified battery chemistry",
            "filename temperature proves controlled thermal exposure",
            "filename C-rate proves a cycle-specific commanded protocol",
            "minimum or maximum measured voltage proves cutoff policy",
            "derived first-cycle capacity is nominal capacity",
            "the local archive bundle identifies an official source snapshot",
            "the candidate is comparable to the Kaggle NASA-derived cohort",
            "the candidate is eligible for predictive validation",
        ],
        **{flag: False for flag in FALSE_FLAGS},
    }
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def _compact(result: Mapping[str, Any]) -> dict[str, Any]:
    omitted = {"candidate_manifest", "deterministic_result_checksum"}
    payload = {key: value for key, value in result.items() if key not in omitted}
    payload["artifact_kind"] = "battery_external_cohort_admission_compact_summary"
    payload["deterministic_result_checksum"] = canonical_checksum(payload)
    return payload


def preview_admission(
    config: BatteryExternalCohortAdmissionConfig, repo_root: str | Path = "."
) -> dict[str, Any]:
    result = _evaluate_once(config, repo_root)
    return {
        "schema_version": GATE_VERSION,
        "status": "ready",
        "candidate_id": result["candidate_id"],
        "overall_status": result["admission_decision"]["overall_status"],
        "blocking_fields": result["unresolved_information"],
        "writes_performed": False,
        **{flag: False for flag in FALSE_FLAGS},
    }


def run_admission(
    config: BatteryExternalCohortAdmissionConfig,
    repo_root: str | Path = ".",
    *,
    write_outputs: bool = True,
    write_tracked_summary: bool = True,
) -> dict[str, Any]:
    first = _evaluate_once(config, repo_root)
    second = _evaluate_once(config, repo_root)
    if first["deterministic_result_checksum"] != second["deterministic_result_checksum"]:
        raise RuntimeError("external cohort admission result is not deterministic")
    result = dict(first)
    result.pop("deterministic_result_checksum")
    result["first_run_checksum"] = first["deterministic_result_checksum"]
    result["second_run_checksum"] = second["deterministic_result_checksum"]
    result["deterministic_rerun_match"] = True
    result["deterministic_result_checksum"] = canonical_checksum(result)
    compact = _compact(result)
    written: list[str] = []
    root = Path(repo_root).resolve()
    if write_outputs:
        output = resolve_repo_path(repo_root, config.output_root)
        output.mkdir(parents=True, exist_ok=True)
        matrix_path = output / "admission_matrix.csv"
        result_path = output / "admission_summary.json"
        pd.DataFrame(result["admission_matrix"]).to_csv(matrix_path, index=False)
        result_path.write_text(json.dumps(_safe(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.extend([matrix_path.relative_to(root).as_posix(), result_path.relative_to(root).as_posix()])
        if write_tracked_summary:
            tracked = resolve_repo_path(repo_root, config.tracked_summary_path)
            tracked.parent.mkdir(parents=True, exist_ok=True)
            tracked.write_text(json.dumps(_safe(compact), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(tracked.relative_to(root).as_posix())
    return {
        "status": "completed",
        "result": result,
        "compact_summary": compact,
        "written": written,
        **{flag: False for flag in FALSE_FLAGS},
    }


def validate_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = []
    if payload.get("schema_version") != GATE_VERSION:
        errors.append("schema_version must be 2.6.4")
    if payload.get("gate_id") != GATE_ID:
        errors.append("gate_id mismatch")
    if payload.get("artifact_kind") not in {
        "battery_external_cohort_admission_result",
        "battery_external_cohort_admission_compact_summary",
    }:
        errors.append("unsupported artifact_kind")
    if tuple(payload.get("required_evidence_fields", [])) != REQUIRED_EVIDENCE_FIELDS:
        errors.append("required evidence fields changed")
    if tuple(payload.get("admission_stages", [])) != ADMISSION_STAGES:
        errors.append("admission stages changed")
    matrix = payload.get("admission_matrix")
    if not isinstance(matrix, list) or tuple(
        row.get("evidence_field") for row in matrix if isinstance(row, Mapping)
    ) != REQUIRED_EVIDENCE_FIELDS:
        errors.append("admission matrix is missing or reordered")
    else:
        for row in matrix:
            if row.get("inference_performed") is not False:
                errors.append("admission matrix performed inference")
            if row.get("same_condition_assumption_made") is not False:
                errors.append("admission matrix made a same-condition assumption")
    if payload.get("admission_decision", {}).get("overall_status") not in {
        "not_admitted_for_cross_cohort_validation",
        "admitted_for_cross_cohort_validation",
    }:
        errors.append("invalid overall admission status")
    for flag in FALSE_FLAGS:
        if payload.get(flag) is not False:
            errors.append(f"{flag} must be false")
    checksum = payload.get("deterministic_result_checksum")
    if not isinstance(checksum, str) or not HEX_SHA256.fullmatch(checksum):
        errors.append("deterministic_result_checksum must be lowercase SHA-256")
    elif checksum != canonical_checksum(payload):
        errors.append("deterministic checksum mismatch")
    return {
        "schema_version": GATE_VERSION,
        "status": "valid" if not errors else "invalid",
        "valid": not errors,
        "errors": errors,
    }


def validate_result_file(path: str | Path, repo_root: str | Path = ".") -> dict[str, Any]:
    return validate_result_payload(_load_json(resolve_repo_path(repo_root, path)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a Battery cohort before external validation.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preview")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--local-only", action="store_true")
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("path")
    return parser


def _emit(payload: Mapping[str, Any], as_json: bool) -> None:
    print(json.dumps(_safe(payload), indent=2, sort_keys=True) if as_json else payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            payload = validate_result_file(args.path, Path.cwd())
            _emit(payload, args.as_json)
            return 0 if payload["valid"] else 2
        config = load_config(args.config, Path.cwd())
        if args.command == "preview":
            _emit(preview_admission(config, Path.cwd()), args.as_json)
            return 0
        execution = run_admission(
            config, Path.cwd(), write_tracked_summary=not args.local_only
        )
        payload = {
            "schema_version": GATE_VERSION,
            "status": execution["status"],
            "candidate_id": execution["result"]["candidate_id"],
            "admission_decision": execution["result"]["admission_decision"],
            "scientific_closeout": execution["result"]["scientific_closeout"],
            "written": execution["written"],
            **{flag: False for flag in FALSE_FLAGS},
        }
        _emit(payload, args.as_json)
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _emit(
            {
                "schema_version": GATE_VERSION,
                "status": "invalid",
                "error": str(exc),
                **{flag: False for flag in FALSE_FLAGS},
            },
            args.as_json,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
