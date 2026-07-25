from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

VERSION = "2.6.5"
PACKAGE_ID = "battery_snl_lfp_source_evidence_recovery_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_snl_lfp_source_evidence_recovery.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_source_evidence"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json"
EVIDENCE_FIELDS = (
    "chemistry", "nominal_capacity", "ambient_temperature", "charge_protocol",
    "discharge_protocol", "cutoff_voltage", "measurement_calibration", "source_snapshot",
)
DOCUMENT_IDS = (
    "battery_archive_snl_study_page", "battery_archive_metadata_rules",
    "osti_1650174_article_record", "sandia_sand2020_8433j_publication_record",
)
FALSE_FLAGS = (
    "network_called", "credentials_read", "raw_data_read", "archives_extracted",
    "source_mutation_performed", "model_trained", "model_evaluated",
    "metrics_recomputed", "data_inference_performed", "local_file_binding_inferred",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = dict(payload)
    core.pop("deterministic_result_checksum", None)
    text = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _rel(name: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    if Path(text).is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in Path(text).parts:
        raise ValueError(f"{name} must be repository-relative and non-traversing")
    return Path(text).as_posix()


def repo_path(root: str | Path, value: str | Path) -> Path:
    base, target = Path(root).resolve(), (Path(root) / value).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return target


@dataclass(frozen=True)
class RecoveryConfig:
    case_study_id: str
    bounded_source_id: str
    manifest_path: str
    admission_path: str
    expected_admission_checksum: str
    expected_candidate_id: str
    output_root: str
    tracked_summary_path: str

    @property
    def schema_version(self) -> str:
        return VERSION

    @property
    def source_document_manifest_path(self) -> str:
        return self.manifest_path

    @property
    def source_admission_summary_path(self) -> str:
        return self.admission_path

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "RecoveryConfig":
        required = {
            "schema_version", "package_id", "case_study_id", "bounded_source_id",
            "source_document_manifest_path", "source_admission_summary_path",
            "expected_admission_checksum", "expected_candidate_id",
            "required_evidence_fields", "required_document_ids", "credential_policy",
            "output_root", "tracked_summary_path", "output_policy",
        }
        unknown, missing = sorted(set(p) - required), sorted(required - set(p))
        if unknown:
            raise ValueError("unknown config field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("missing config field(s): " + ", ".join(missing))
        if p["schema_version"] != VERSION or p["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported source-evidence package")
        if tuple(p["required_evidence_fields"]) != EVIDENCE_FIELDS or tuple(p["required_document_ids"]) != DOCUMENT_IDS:
            raise ValueError("predeclared evidence or document set changed")
        if p["credential_policy"] != {"store_credentials": False, "network_access_required": False}:
            raise ValueError("credential policy must disable storage and network")
        if not HEX64.fullmatch(str(p["expected_admission_checksum"])):
            raise ValueError("expected_admission_checksum must be SHA-256")
        paths = {k: _rel(k, p[k]) for k in (
            "source_document_manifest_path", "source_admission_summary_path", "output_root", "tracked_summary_path"
        )}
        if paths["output_root"] != DEFAULT_OUTPUT_ROOT or paths["tracked_summary_path"] != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("output paths do not match the v2.6.5 contract")
        if p["output_policy"] != "local_details_and_tracked_compact_summary":
            raise ValueError("unsupported output policy")
        return cls(
            case_study_id=str(p["case_study_id"]), bounded_source_id=str(p["bounded_source_id"]),
            manifest_path=paths["source_document_manifest_path"], admission_path=paths["source_admission_summary_path"],
            expected_admission_checksum=str(p["expected_admission_checksum"]),
            expected_candidate_id=str(p["expected_candidate_id"]), output_root=paths["output_root"],
            tracked_summary_path=paths["tracked_summary_path"],
        )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> RecoveryConfig:
    return RecoveryConfig.from_dict(_json(repo_path(repo_root, path)))


def validate_manifest(m: Mapping[str, Any], c: RecoveryConfig) -> None:
    required = {
        "schema_version", "manifest_id", "bounded_source_id", "candidate_archive_scope",
        "selection_rationale", "retrieval_recorded_on", "documents", "evidence_claims",
        "target_contract", "claim_policy",
    }
    if set(m) != required or m["schema_version"] != "1" or m["bounded_source_id"] != c.bounded_source_id:
        raise ValueError("invalid bounded source document manifest")
    documents = m["documents"]
    if tuple(d.get("document_id") for d in documents) != DOCUMENT_IDS:
        raise ValueError("document set changed")
    for d in documents:
        if set(d["stable_identifiers"]) != {"url", "doi", "osti_id", "sand_number"}:
            raise ValueError("stable identifier fields changed")
        if d["versioned_dataset_snapshot"] or d["local_document_copy_committed"]:
            raise ValueError("document identity may not be promoted to a local dataset snapshot")
    claims = m["evidence_claims"]
    if tuple(x.get("evidence_field") for x in claims) != EVIDENCE_FIELDS:
        raise ValueError("evidence matrix changed")
    known = set(DOCUMENT_IDS)
    for x in claims:
        if not set(x["source_document_ids"]).issubset(known):
            raise ValueError("undeclared document reference")
        if any(x[k] for k in (
            "battery_file_binding_established", "cycle_condition_binding_established",
            "instrument_channel_binding_established", "official_distribution_snapshot_established",
        )):
            raise ValueError("v2.6.5 may not claim local binding")
    if any(m["claim_policy"].values()):
        raise ValueError("claim-policy boundaries changed")


def _promoted(x: Mapping[str, Any]) -> bool:
    field = x["evidence_field"]
    key = (
        "battery_file_binding_established" if field in {"chemistry", "nominal_capacity"}
        else "cycle_condition_binding_established" if field in {"ambient_temperature", "charge_protocol", "discharge_protocol", "cutoff_voltage"}
        else "instrument_channel_binding_established" if field == "measurement_calibration"
        else "official_distribution_snapshot_established"
    )
    return bool(x["source_backed"] and x[key])


def recovery_matrix(m: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for x in m["evidence_claims"]:
        rows.append({
            **x,
            "document_evidence_recovered": bool(x["source_backed"] and not str(x["recovery_status"]).startswith("unresolved")),
            "promotion_requirement_satisfied": _promoted(x),
            "inference_performed": False,
            "same_condition_assumption_made": False,
        })
    return rows


def preservation(admission: Mapping[str, Any], c: RecoveryConfig) -> dict[str, Any]:
    if admission.get("deterministic_result_checksum") != c.expected_admission_checksum:
        raise ValueError("v2.6.4 admission checksum mismatch")
    if admission.get("candidate_id") != c.expected_candidate_id:
        raise ValueError("v2.6.4 candidate changed")
    if admission.get("admission_decision", {}).get("overall_status") != "not_admitted_for_cross_cohort_validation":
        raise ValueError("v2.6.4 admission boundary changed")
    metrics = admission.get("preservation_checks", {}).get("preserved_metrics")
    expected = [
        {"mae": 3.425575369058076, "model": "persistence"},
        {"mae": 4.15369918179312, "model": "ridge"},
    ]
    if metrics != expected:
        raise ValueError("preserved model metrics changed")
    return {
        "v2_6_4_admission_checksum_verified": True,
        "prior_overall_status": "not_admitted_for_cross_cohort_validation",
        "prior_overall_status_preserved": True,
        "model_metrics_unchanged": True,
        "model_or_metric_change_performed": False,
        "preserved_metrics": metrics,
    }


def build_result(c: RecoveryConfig, m: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(m, c)
    rows = recovery_matrix(m)
    blocking = [x["evidence_field"] for x in rows if not x["promotion_requirement_satisfied"]]
    target = dict(m["target_contract"])
    target["predictive_target_ready"] = bool(target["source_metric_documented"] and target["aligned_to_v2_6_1_five_cycle_target"])
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_source_evidence_recovery_result",
        "package_id": PACKAGE_ID,
        "case_study_id": c.case_study_id,
        "bounded_source_id": c.bounded_source_id,
        "source_document_manifest_id": m["manifest_id"],
        "source_document_manifest_checksum": canonical_checksum(m),
        "source_document_register": m["documents"],
        "recovery_matrix": rows,
        "coverage_summary": {
            "required_field_count": 8,
            "document_evidence_recovered_count": sum(x["document_evidence_recovered"] for x in rows),
            "partial_document_evidence_count": sum(str(x["recovery_status"]).startswith("partial") for x in rows),
            "promotion_requirement_satisfied_count": 0,
            "remaining_blocking_field_count": 8,
            "authoritative_document_count": 4,
            "versioned_dataset_snapshot_count": 0,
        },
        "target_contract_assessment": target,
        "recovery_decision": {
            "source_document_recovery": "completed_with_remaining_binding_gaps",
            "bounded_inventory_binding": {
                "status": "eligible_for_read_only_inventory_binding",
                "allowed_scope": ["SNL LFP.zip checksum", "zip central-directory inventory", "parsed-label provenance manifest"],
                "csv_row_read_allowed": False,
                "archive_extraction_allowed": False,
            },
            "cross_cohort_comparability": {"status": "not_admitted", "blocking_fields": blocking},
            "predictive_validation": {"status": "blocked", "target_definition_ready": False},
            "overall_status": "source_evidence_recovered_gate_not_passed",
        },
        "preservation_checks": preservation(admission, c),
        "scientific_closeout": {
            "status": "diagnostic",
            "result": "source_document_evidence_partially_recovered",
            "evidence_level": "authoritative_study_documentation_without_local_artifact_binding",
            "strongest_evidence": "Official Battery Archive, OSTI, and Sandia records document the bounded SNL cell model, nominal capacity, equipment, protocol groups, and regime-specific LFP voltage limits.",
            "primary_limitation": "No checksum-verified mapping connects local SNL LFP entries to documented cells and conditions; calibration, uncertainty, snapshot identity, and target alignment remain unresolved.",
            "suitable_for": ["bounded inventory-binding design", "metadata provenance contract", "evidence-gap prioritization"],
            "unsuitable_for": ["CSV row analysis", "cross-cohort equivalence", "predictive validation", "model selection", "mechanism claims", "engineering decisions"],
        },
        "recommendations": [
            "limit the next step to checksum and central-directory binding for SNL LFP.zip",
            "do not extract archives, read CSV rows, merge cohorts, or run a model",
        ],
        "source_references": {"manifest": c.manifest_path, "admission": c.admission_path},
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    keep = {
        "schema_version", "package_id", "case_study_id", "bounded_source_id",
        "source_document_manifest_id", "source_document_manifest_checksum",
        "coverage_summary", "target_contract_assessment", "recovery_decision",
        "preservation_checks", "scientific_closeout", "recommendations", "source_references",
        *FALSE_FLAGS,
    }
    out = {k: result[k] for k in keep}
    out["artifact_kind"] = "battery_snl_lfp_source_evidence_recovery_compact_summary"
    out["evidence_statuses"] = [
        {"evidence_field": x["evidence_field"], "recovery_status": x["recovery_status"], "promotion_requirement_satisfied": False}
        for x in result["recovery_matrix"]
    ]
    out["deterministic_result_checksum"] = canonical_checksum(out)
    return out


def validate_result(p: Mapping[str, Any]) -> None:
    if p.get("schema_version") != VERSION or p.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    if p.get("recovery_decision", {}).get("overall_status") != "source_evidence_recovered_gate_not_passed":
        raise ValueError("recovery boundary changed")
    if p.get("coverage_summary", {}).get("promotion_requirement_satisfied_count") != 0:
        raise ValueError("document evidence was silently promoted")
    if any(p.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    if p.get("deterministic_result_checksum") != canonical_checksum(p):
        raise ValueError("deterministic result checksum mismatch")


def execute(c: RecoveryConfig, repo_root: str | Path = ".", write_outputs: bool = True) -> dict[str, Any]:
    manifest, admission = _json(repo_path(repo_root, c.manifest_path)), _json(repo_path(repo_root, c.admission_path))
    result = build_result(c, manifest, admission)
    result["source_artifact_checksums"] = {
        "source_document_manifest_canonical_sha256": canonical_checksum(manifest),
        "source_admission_result_checksum": admission["deterministic_result_checksum"],
    }
    result["deterministic_result_checksum"] = canonical_checksum(result)
    validate_result(result)
    if write_outputs:
        root = repo_path(repo_root, c.output_root)
        root.mkdir(parents=True, exist_ok=True)
        for name, value in {
            "source_document_register.json": result["source_document_register"],
            "recovery_matrix.json": result["recovery_matrix"],
            "recovery_summary.json": result,
        }.items():
            (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tracked = repo_path(repo_root, c.tracked_summary_path)
        tracked.parent.mkdir(parents=True, exist_ok=True)
        tracked.write_text(json.dumps(compact(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def preview(c: RecoveryConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    r = execute(c, repo_root, False)
    return {
        "schema_version": VERSION,
        "package_id": PACKAGE_ID,
        "bounded_source_id": c.bounded_source_id,
        "document_evidence_recovered_count": r["coverage_summary"]["document_evidence_recovered_count"],
        "promotion_requirement_satisfied_count": 0,
        "overall_status": r["recovery_decision"]["overall_status"],
        "write_outputs": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview"); sub.add_parser("run")
    v = sub.add_parser("validate"); v.add_argument("result_path")
    args = parser.parse_args(argv)
    c = load_config(args.config, args.repo_root)
    if args.command == "preview":
        value = preview(c, args.repo_root)
    elif args.command == "run":
        value = execute(c, args.repo_root, True)
    else:
        value = _json(repo_path(args.repo_root, args.result_path)); validate_result(value)
        value = {"valid": True, "deterministic_result_checksum": value["deterministic_result_checksum"]}
    print(json.dumps(value, ensure_ascii=False, sort_keys=True) if args.json else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
