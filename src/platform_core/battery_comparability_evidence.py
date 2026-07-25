from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import pandas as pd

PACKAGE_VERSION = "2.6.3"
PACKAGE_ID = "battery_comparability_evidence_package_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_comparability_evidence.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_comparability"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_3_comparability_evidence_summary.json"
REQUIRED_EVIDENCE_FIELDS = (
    "chemistry", "nominal_capacity", "ambient_temperature", "charge_protocol",
    "discharge_protocol", "cutoff_voltage", "measurement_calibration", "source_snapshot",
)
CONFIG_FIELDS = {
    "schema_version", "package_id", "case_study_id", "source_analysis_ready_path",
    "source_lineage_path", "metadata_recovery_summary_path", "source_benchmark_summary_path",
    "source_diagnostic_summary_path", "expected_benchmark_checksum",
    "expected_diagnostic_checksum", "group_column", "temperature_column",
    "required_evidence_fields", "credential_policy", "output_root",
    "tracked_summary_path", "output_policy",
}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FALSE_FLAGS = (
    "network_called", "credentials_read", "source_mutation_performed", "model_retrained",
    "metrics_recomputed", "data_inference_performed", "same_condition_assumption_made",
)


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = dict(payload)
    core.pop("deterministic_result_checksum", None)
    return hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_repo_path(repo_root: str | Path, value: str | Path) -> Path:
    root = Path(repo_root).resolve()
    path = (root / Path(value)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return path


def _relative(field: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    if Path(text).is_absolute() or re.match(r"^[A-Za-z]:", text) or text.startswith("//") or ".." in Path(text).parts:
        raise ValueError(f"{field} must be repository-relative and non-traversing")
    return Path(text).as_posix()


@dataclass(frozen=True)
class BatteryComparabilityEvidenceConfig:
    schema_version: str
    package_id: str
    case_study_id: str
    source_analysis_ready_path: str
    source_lineage_path: str
    metadata_recovery_summary_path: str
    source_benchmark_summary_path: str
    source_diagnostic_summary_path: str
    expected_benchmark_checksum: str
    expected_diagnostic_checksum: str
    group_column: str
    temperature_column: str
    required_evidence_fields: tuple[str, ...]
    credential_policy: Mapping[str, bool]
    output_root: str
    tracked_summary_path: str
    output_policy: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BatteryComparabilityEvidenceConfig":
        unknown, missing = sorted(set(payload) - CONFIG_FIELDS), sorted(CONFIG_FIELDS - set(payload))
        if unknown:
            raise ValueError("unknown config field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("missing config field(s): " + ", ".join(missing))
        if payload["schema_version"] != PACKAGE_VERSION or payload["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported comparability package version or id")
        required = tuple(str(item) for item in payload["required_evidence_fields"])
        if required != REQUIRED_EVIDENCE_FIELDS:
            raise ValueError("required_evidence_fields must match the predeclared evidence matrix")
        for field in ("expected_benchmark_checksum", "expected_diagnostic_checksum"):
            if not HEX_SHA256.fullmatch(str(payload[field])):
                raise ValueError(f"{field} must be a lowercase SHA-256 checksum")
        for field in ("group_column", "temperature_column"):
            if not SAFE_COLUMN.fullmatch(str(payload[field])):
                raise ValueError(f"{field} is not a safe column name")
        paths = {field: _relative(field, payload[field]) for field in (
            "source_analysis_ready_path", "source_lineage_path", "metadata_recovery_summary_path",
            "source_benchmark_summary_path", "source_diagnostic_summary_path", "output_root",
            "tracked_summary_path",
        )}
        if payload["credential_policy"] != {"store_credentials": False, "network_access_required": False}:
            raise ValueError("credential policy must disable storage and network")
        if paths["output_root"] != DEFAULT_OUTPUT_ROOT or paths["tracked_summary_path"] != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("output paths do not match the v2.6.3 contract")
        if payload["output_policy"] != "local_details_and_tracked_compact_summary":
            raise ValueError("unsupported output_policy")
        return cls(
            schema_version=PACKAGE_VERSION, package_id=PACKAGE_ID,
            case_study_id=str(payload["case_study_id"]),
            expected_benchmark_checksum=str(payload["expected_benchmark_checksum"]),
            expected_diagnostic_checksum=str(payload["expected_diagnostic_checksum"]),
            group_column=str(payload["group_column"]), temperature_column=str(payload["temperature_column"]),
            required_evidence_fields=required, credential_policy=dict(payload["credential_policy"]),
            output_policy=str(payload["output_policy"]), **paths,
        )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> BatteryComparabilityEvidenceConfig:
    return BatteryComparabilityEvidenceConfig.from_mapping(_load_json(resolve_repo_path(repo_root, path)))


def _load_sources(config: BatteryComparabilityEvidenceConfig, repo_root: str | Path):
    refs = {
        "analysis_ready": config.source_analysis_ready_path,
        "lineage": config.source_lineage_path,
        "metadata_recovery": config.metadata_recovery_summary_path,
        "benchmark_summary": config.source_benchmark_summary_path,
        "diagnostic_summary": config.source_diagnostic_summary_path,
    }
    paths = {name: resolve_repo_path(repo_root, value) for name, value in refs.items()}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    hashes = {name: file_sha256(path) for name, path in paths.items()}
    return (
        pd.read_csv(paths["analysis_ready"]), _load_json(paths["lineage"]),
        pd.read_csv(paths["metadata_recovery"]), _load_json(paths["benchmark_summary"]),
        _load_json(paths["diagnostic_summary"]), refs, hashes,
    )


def _recovery(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    required = {"metadata_field", "supported_records", "limitation", "external_data_required"}
    if not required.issubset(frame.columns):
        raise ValueError("metadata recovery summary lacks required columns")
    return frame.set_index("metadata_field").to_dict(orient="index")


def _row(field: str, status: str, scope: str, battery_count: int, supported_batteries: int,
         supported_records: int, values: int | None, reference: str, statement: str,
         limitation: str, external: bool) -> dict[str, Any]:
    return {
        "evidence_field": field, "evidence_status": status, "evidence_scope": scope,
        "expected_battery_count": battery_count, "supported_battery_count": supported_batteries,
        "supported_record_count": supported_records, "observed_value_count": values,
        "source_reference": reference, "evidence_statement": statement, "limitation": limitation,
        "external_data_required": external, "comparability_established": False,
        "inference_performed": False, "same_condition_assumption_made": False,
    }


def build_evidence_matrix(source: pd.DataFrame, lineage: Mapping[str, Any], recovery_frame: pd.DataFrame,
                          config: BatteryComparabilityEvidenceConfig) -> pd.DataFrame:
    for column in (config.group_column, config.temperature_column):
        if column not in source.columns:
            raise ValueError(f"required analysis-ready column missing: {column}")
    recovery = _recovery(recovery_frame)
    n_batteries = int(source[config.group_column].nunique(dropna=True))
    n_rows = int(len(source))
    temp = pd.to_numeric(source[config.temperature_column], errors="coerce")
    if temp.isna().any():
        raise ValueError("ambient temperature contains missing or nonnumeric values")
    variable_temp = int(source.assign(__temp=temp).groupby(config.group_column)["__temp"].nunique().gt(1).sum())
    protocol = recovery.get("documented_protocol_group", {})
    measured_current = recovery.get("measured_current_summary", {})
    uncertainty = recovery.get("measurement_uncertainty", {})
    snapshot = recovery.get("official_original_snapshot_version", {})
    rows = [
        _row("chemistry", "unresolved", "none", n_batteries, 0, 0, None,
             f"{config.source_analysis_ready_path}; {config.metadata_recovery_summary_path}",
             "No chemistry field is present in the tracked analysis-ready or metadata-recovery artifacts.",
             "Chemistry equivalence cannot be verified.", True),
        _row("nominal_capacity", "unresolved_derived_reference_only", "derived_analysis_value_only",
             n_batteries, 0, 0, None, config.source_analysis_ready_path,
             "reference_capacity_ah is derived by first_n_median and is not treated as nominal capacity.",
             "Nominal capacity comparability cannot be verified.", True),
        _row("ambient_temperature", "observed_heterogeneous", "cycle_level_observation",
             n_batteries, n_batteries, n_rows, int(temp.nunique()),
             f"{config.source_analysis_ready_path}:{config.temperature_column}",
             f"Recorded ambient temperature covers {n_rows} rows and {n_batteries} batteries; "
             f"{variable_temp} batteries span more than one recorded value.",
             "Observed temperature variation does not establish equal test conditions or measurement uncertainty.", False),
        _row("charge_protocol", "partial_group_level_only", "documented_group", n_batteries,
             int(protocol.get("supported_records", 0)), int(protocol.get("supported_records", 0)), None,
             f"{config.metadata_recovery_summary_path}:documented_protocol_group",
             "Local protocol documents provide group-level coverage only.",
             str(protocol.get("limitation", "cycle-specific commanded charge log unavailable")), True),
        _row("discharge_protocol", "partial_group_and_measured_signal_only",
             "documented_group_plus_measured_summary", n_batteries,
             int(protocol.get("supported_records", 0)), int(measured_current.get("supported_records", 0)), None,
             f"{config.metadata_recovery_summary_path}:documented_protocol_group,measured_current_summary",
             "Group documents and measured-current summaries are present, but measured current is not a commanded protocol log.",
             str(measured_current.get("limitation", "observed current is not a commanded protocol log")), True),
        _row("cutoff_voltage", "unresolved", "none", n_batteries, 0, 0, None,
             f"{config.source_analysis_ready_path}; {config.metadata_recovery_summary_path}",
             "No cycle-specific cutoff-voltage policy is present in the tracked evidence artifacts.",
             "Cutoff comparability cannot be verified.", True),
        _row("measurement_calibration", "unresolved", "none", n_batteries, 0,
             int(uncertainty.get("supported_records", 0)), None,
             f"{config.metadata_recovery_summary_path}:measurement_uncertainty",
             "Calibration, instrument accuracy, and measurement uncertainty are not present; zero uncertainty is not assigned.",
             str(uncertainty.get("limitation", "zero uncertainty was not assigned")), True),
        _row("source_snapshot", "immediate_upstream_verified_official_snapshot_unresolved",
             "local_distribution_artifact", n_batteries, int(lineage.get("exact_lineage_cell_count", 0)),
             int(lineage.get("analysis_ready_rows", 0)), None, config.source_lineage_path,
             "The immediate local Kaggle package and archive checksum are verified.",
             "The official original NASA snapshot/version is not verifiable from local package metadata.",
             bool(snapshot.get("external_data_required", True))),
    ]
    if tuple(row["evidence_field"] for row in rows) != REQUIRED_EVIDENCE_FIELDS:
        raise AssertionError("evidence matrix order changed")
    return pd.DataFrame(rows)


def _preservation(benchmark: Mapping[str, Any], diagnostic: Mapping[str, Any], config: BatteryComparabilityEvidenceConfig) -> dict[str, Any]:
    if benchmark.get("deterministic_result_checksum") != config.expected_benchmark_checksum:
        raise ValueError("source benchmark checksum mismatch")
    if diagnostic.get("deterministic_result_checksum") != config.expected_diagnostic_checksum:
        raise ValueError("source diagnostic checksum mismatch")
    if benchmark.get("scientific_assessment", {}).get("status") != "unsupported":
        raise ValueError("v2.6.1 unsupported assessment changed")
    if diagnostic.get("comparability_readiness", {}).get("status") != "comparability_not_established":
        raise ValueError("v2.6.2 comparability status changed")
    metrics = benchmark.get("aggregate_metrics", [])
    by_model = {str(row.get("model")): row for row in metrics}
    expected = {"persistence": 3.425575369058076, "ridge": 4.15369918179312}
    if any(abs(float(by_model.get(model, {}).get("mae", float("nan"))) - mae) > 1e-12 for model, mae in expected.items()):
        raise ValueError("v2.6.1 pooled MAE changed")
    preserved = [{key: row[key] for key in ("model", "prediction_count", "mae", "rmse") if key in row}
                 for row in metrics if row.get("model") in expected]
    return {
        "benchmark_checksum_verified": True, "diagnostic_checksum_verified": True,
        "prior_scientific_assessment": "unsupported", "prior_scientific_assessment_preserved": True,
        "prior_comparability_status": "comparability_not_established",
        "prior_comparability_status_preserved": True, "model_metrics_unchanged": True,
        "model_or_metric_change_performed": False, "preserved_metrics": preserved,
    }


def _build_payload(config: BatteryComparabilityEvidenceConfig, repo_root: str | Path):
    source, lineage, recovery, benchmark, diagnostic, refs, hashes = _load_sources(config, repo_root)
    matrix = build_evidence_matrix(source, lineage, recovery, config)
    preservation = _preservation(benchmark, diagnostic, config)
    status_counts = {
        "established_for_comparability": 0,
        "unresolved": int(matrix["evidence_status"].str.startswith("unresolved").sum()),
        "partial": int(matrix["evidence_status"].str.startswith("partial").sum()),
        "observed_heterogeneous": int((matrix["evidence_status"] == "observed_heterogeneous").sum()),
        "immediate_upstream_only": int(matrix["evidence_status"].str.startswith("immediate_upstream").sum()),
    }
    unresolved = list(REQUIRED_EVIDENCE_FIELDS)
    payload = {
        "schema_version": PACKAGE_VERSION, "artifact_kind": "battery_comparability_evidence_result",
        "package_id": PACKAGE_ID, "case_study_id": config.case_study_id, "source_references": refs,
        "source_artifact_checksums": {
            "archive_sha256": lineage.get("archive_sha256"),
            "metadata_sha256": lineage.get("metadata_sha256"),
            "lineage_source_evidence_checksum": lineage.get("source_evidence_checksum"),
            "benchmark_summary_checksum": config.expected_benchmark_checksum,
            "diagnostic_summary_checksum": config.expected_diagnostic_checksum,
        },
        "required_evidence_fields": list(REQUIRED_EVIDENCE_FIELDS),
        "evidence_matrix": matrix.to_dict(orient="records"),
        "coverage_summary": {
            "battery_count": int(source[config.group_column].nunique(dropna=True)),
            "analysis_ready_row_count": int(len(source)), "required_field_count": len(matrix),
            "comparability_established_field_count": 0, "all_required_fields_audited": True,
            "status_counts": status_counts,
        },
        "preservation_checks": preservation,
        "comparability_decision": {
            "status": "comparability_not_established", "blocking_fields": unresolved,
            "cross_battery_condition_equivalence_allowed": False, "same_condition_claim_allowed": False,
            "new_model_experiment_justified_by_current_metadata": False,
            "decision_basis": "No predeclared evidence field is established at the granularity required for cross-battery test-condition equivalence.",
        },
        "scientific_closeout": {
            "status": "inconclusive", "result": "comparability_not_established",
            "evidence_level": "insufficient_metadata_for_condition_equivalence",
            "strongest_evidence": "Immediate Kaggle package lineage and cycle-level ambient temperature are verified without inference.",
            "primary_limitation": "Chemistry, nominal capacity, cycle-specific commanded protocols, cutoff policy, calibration/uncertainty, and the official NASA snapshot remain unresolved; recorded temperatures are heterogeneous.",
            "what_would_change_conclusion": [
                "source-backed chemistry and nominal-capacity metadata per battery",
                "cycle-specific commanded charge and discharge protocol logs",
                "cycle-specific cutoff-voltage policy",
                "instrument calibration and measurement-uncertainty records",
                "an independently verifiable official source snapshot/version",
            ],
            "suitable_for": ["metadata gap audit", "source-evidence acquisition specification", "scientific boundary enforcement"],
            "unsuitable_for": ["causal explanation of Ridge failure", "cross-battery condition equivalence", "mechanism inference", "new predictive-generalization claim", "engineering decision"],
        },
        "unresolved_information": unresolved,
        "recommendations": [
            "retain the v2.6.1 unsupported benchmark and v2.6.2 diagnostic closeout",
            "do not tune, replace, or add a model from this audit",
            "recover source-backed metadata only for the blocking evidence fields",
            "predeclare any future comparable cohort before model evaluation",
        ],
        "prohibited_claims": [
            "battery chemistry is the same across trajectories", "reference_capacity_ah is nominal capacity",
            "recorded temperature proves equal thermal exposure", "measured current is the commanded protocol",
            "cutoff voltage or calibration can be inferred from trajectories",
            "the local Kaggle package identifies the official NASA snapshot",
            "current metadata explains the Ridge failure causally",
            "current metadata justifies a new predictive model claim",
        ],
        **{field: False for field in FALSE_FLAGS},
        "source_hashes_before": hashes, "source_hashes_after": dict(hashes),
    }
    run_checksum = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    payload["first_run_checksum"] = run_checksum
    payload["second_run_checksum"] = run_checksum
    payload["deterministic_rerun_match"] = True
    payload["deterministic_result_checksum"] = canonical_checksum(payload)
    return payload, matrix


def build_result(config: BatteryComparabilityEvidenceConfig, repo_root: str | Path = "."):
    first, matrix = _build_payload(config, repo_root)
    second, _ = _build_payload(config, repo_root)
    if first["first_run_checksum"] != second["first_run_checksum"]:
        raise ValueError("deterministic rerun mismatch")
    return first, matrix


def build_compact_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    compact = {k: v for k, v in result.items() if k not in {"source_hashes_before", "source_hashes_after", "first_run_checksum", "second_run_checksum", "deterministic_rerun_match", "deterministic_result_checksum"}}
    compact["artifact_kind"] = "battery_comparability_evidence_compact_summary"
    run_checksum = hashlib.sha256(canonical_json(compact).encode("utf-8")).hexdigest()
    compact.update(first_run_checksum=run_checksum, second_run_checksum=run_checksum, deterministic_rerun_match=True)
    compact["deterministic_result_checksum"] = canonical_checksum(compact)
    return compact


def preview_package(config: BatteryComparabilityEvidenceConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    result, _ = build_result(config, repo_root)
    return {
        "schema_version": PACKAGE_VERSION, "status": "ready", "package_id": PACKAGE_ID,
        "battery_count": result["coverage_summary"]["battery_count"],
        "analysis_ready_row_count": result["coverage_summary"]["analysis_ready_row_count"],
        "required_field_count": len(REQUIRED_EVIDENCE_FIELDS),
        "comparability_status": "comparability_not_established", "writes_performed": False,
        **{field: False for field in FALSE_FLAGS},
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def run_package(config: BatteryComparabilityEvidenceConfig, repo_root: str | Path = ".", *,
                write_outputs: bool = True, write_tracked_summary: bool = True) -> dict[str, Any]:
    result, matrix = build_result(config, repo_root)
    compact = build_compact_summary(result)
    written: list[str] = []
    if write_outputs:
        root = Path(repo_root).resolve()
        output_root = resolve_repo_path(repo_root, config.output_root)
        matrix_path, result_path = output_root / "evidence_matrix.csv", output_root / "comparability_summary.json"
        output_root.mkdir(parents=True, exist_ok=True)
        matrix.to_csv(matrix_path, index=False)
        _write_json(result_path, result)
        written.extend([matrix_path.relative_to(root).as_posix(), result_path.relative_to(root).as_posix()])
        if write_tracked_summary:
            tracked = resolve_repo_path(repo_root, config.tracked_summary_path)
            _write_json(tracked, compact)
            written.append(tracked.relative_to(root).as_posix())
    return {"status": "completed", "result": result, "compact_summary": compact,
            "frames": {"evidence_matrix": matrix}, "written": written,
            **{field: False for field in FALSE_FLAGS}}


def validate_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("schema_version") != PACKAGE_VERSION or payload.get("package_id") != PACKAGE_ID:
        errors.append("package identity mismatch")
    if payload.get("artifact_kind") not in {"battery_comparability_evidence_result", "battery_comparability_evidence_compact_summary"}:
        errors.append("unsupported artifact_kind")
    matrix = payload.get("evidence_matrix")
    if not isinstance(matrix, list) or [row.get("evidence_field") for row in matrix] != list(REQUIRED_EVIDENCE_FIELDS):
        errors.append("evidence_matrix field contract mismatch")
    elif any(row.get("inference_performed") is not False or row.get("same_condition_assumption_made") is not False or row.get("comparability_established") is not False for row in matrix):
        errors.append("inference, same-condition assumption, or unsupported comparability detected")
    if payload.get("comparability_decision", {}).get("status") != "comparability_not_established":
        errors.append("comparability decision mismatch")
    if payload.get("preservation_checks", {}).get("model_metrics_unchanged") is not True:
        errors.append("model metric preservation is not verified")
    for field in FALSE_FLAGS:
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    checksum = payload.get("deterministic_result_checksum")
    if not isinstance(checksum, str) or not HEX_SHA256.fullmatch(checksum) or checksum != canonical_checksum(payload):
        errors.append("deterministic checksum mismatch")
    return {"schema_version": PACKAGE_VERSION, "status": "valid" if not errors else "invalid", "valid": not errors, "errors": errors}


def validate_result_file(path: str | Path, repo_root: str | Path = ".") -> dict[str, Any]:
    return validate_result_payload(_load_json(resolve_repo_path(repo_root, path)))


def _emit(payload: Mapping[str, Any], as_json: bool) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) if as_json else payload.get("status", "unknown"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Battery comparability evidence without inference, model execution, metric changes, network access, or source mutation.")
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview"); preview.add_argument("config", nargs="?", default=DEFAULT_CONFIG_PATH)
    run = commands.add_parser("run"); run.add_argument("config", nargs="?", default=DEFAULT_CONFIG_PATH); run.add_argument("--local-only", action="store_true")
    validate = commands.add_parser("validate"); validate.add_argument("path")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            payload = validate_result_file(args.path, Path.cwd()); _emit(payload, args.json); return 0 if payload["valid"] else 2
        config = load_config(args.config, Path.cwd())
        if args.command == "preview":
            payload = preview_package(config, Path.cwd()); _emit(payload, args.json); return 0
        execution = run_package(config, Path.cwd(), write_outputs=True, write_tracked_summary=not args.local_only)
        payload = {"schema_version": PACKAGE_VERSION, "status": execution["status"],
                   "comparability_decision": execution["result"]["comparability_decision"],
                   "scientific_closeout": execution["result"]["scientific_closeout"],
                   "preservation_checks": execution["result"]["preservation_checks"],
                   "written": execution["written"], **{field: False for field in FALSE_FLAGS}}
        _emit(payload, args.json); return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        payload = {"schema_version": PACKAGE_VERSION, "status": "invalid", "error": str(exc), **{field: False for field in FALSE_FLAGS}}
        _emit(payload, args.json); return 2


if __name__ == "__main__":
    raise SystemExit(main())
