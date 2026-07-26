from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence
import zipfile

VERSION = "2.6.6"
PACKAGE_ID = "battery_snl_lfp_artifact_binding_audit_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_snl_lfp_artifact_binding.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_artifact_binding"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json"
EXPECTED_ARCHIVE_PATH = "data/raw/battery_archive/SNL LFP.zip"
EXPECTED_ROOT_PREFIX = "SNL LFP/"
EXPECTED_COUNTS = {"entry_count": 60, "cycle_csv_count": 30, "timeseries_csv_count": 30}
EVIDENCE_FIELDS = (
    "chemistry", "nominal_capacity", "ambient_temperature", "charge_protocol",
    "discharge_protocol", "cutoff_voltage", "measurement_calibration", "source_snapshot",
)
FALSE_FLAGS = (
    "network_called", "credentials_read", "archives_extracted", "entry_payloads_read",
    "csv_rows_read", "source_mutation_performed", "model_trained", "model_evaluated",
    "metrics_recomputed", "data_inference_performed", "document_to_archive_binding_inferred",
    "filename_labels_promoted_to_scientific_evidence",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
LABEL_RE = re.compile(
    r"^(?P<source>SNL)_(?P<form_factor>[^_]+)_(?P<chemistry>[A-Za-z0-9]+)_"
    r"(?P<temperature>-?\d+(?:\.\d+)?C)_(?P<soc_window>\d+(?:\.\d+)?-\d+(?:\.\d+)?)_"
    r"(?P<rates>\d+(?:\.\d+)?-\d+(?:\.\d+)?C)(?:_(?P<replicate>[A-Za-z0-9]+))?$"
)


def canonical_checksum(payload: Any) -> str:
    core = dict(payload) if isinstance(payload, Mapping) else payload
    if isinstance(core, dict):
        core.pop("deterministic_result_checksum", None)
    text = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _relative(name: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    path = Path(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in path.parts:
        raise ValueError(f"{name} must be repository-relative and non-traversing")
    return path.as_posix()


def repo_path(root: str | Path, value: str | Path) -> Path:
    base, target = Path(root).resolve(), (Path(root) / value).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return target


@dataclass(frozen=True)
class BindingConfig:
    case_study_id: str
    bounded_source_id: str
    archive_path: str
    source_evidence_summary_path: str
    expected_source_evidence_checksum: str
    output_root: str
    tracked_summary_path: str

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "BindingConfig":
        required = {
            "schema_version", "package_id", "case_study_id", "bounded_source_id", "archive_path",
            "source_evidence_summary_path", "expected_source_evidence_checksum",
            "expected_archive_filename", "expected_root_prefix", "expected_inventory",
            "required_evidence_fields", "read_policy", "credential_policy", "output_root",
            "tracked_summary_path", "output_policy", "dry_run",
        }
        if set(p) != required:
            raise ValueError("config fields changed")
        if p["schema_version"] != VERSION or p["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported SNL LFP artifact-binding package")
        if _relative("archive_path", p["archive_path"]) != EXPECTED_ARCHIVE_PATH:
            raise ValueError("archive_path changed from the bounded SNL LFP scope")
        if p["expected_archive_filename"] != "SNL LFP.zip" or p["expected_root_prefix"] != EXPECTED_ROOT_PREFIX:
            raise ValueError("archive identity contract changed")
        if p["expected_inventory"] != EXPECTED_COUNTS or tuple(p["required_evidence_fields"]) != EVIDENCE_FIELDS:
            raise ValueError("inventory or evidence contract changed")
        if p["read_policy"] != {
            "allow_archive_sha256": True,
            "allow_zip_central_directory": True,
            "allow_entry_payload_read": False,
            "allow_archive_extraction": False,
            "allow_csv_row_read": False,
        }:
            raise ValueError("read policy changed")
        if p["credential_policy"] != {"store_credentials": False, "network_access_required": False}:
            raise ValueError("credential policy changed")
        checksum = str(p["expected_source_evidence_checksum"])
        if not HEX64.fullmatch(checksum):
            raise ValueError("expected source checksum must be SHA-256")
        source = _relative("source_evidence_summary_path", p["source_evidence_summary_path"])
        output = _relative("output_root", p["output_root"])
        tracked = _relative("tracked_summary_path", p["tracked_summary_path"])
        if output != DEFAULT_OUTPUT_ROOT or tracked != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("output paths changed")
        if p["output_policy"] != "local_details_and_tracked_compact_summary" or p["dry_run"] is not True:
            raise ValueError("output or dry-run policy changed")
        return cls(
            str(p["case_study_id"]), str(p["bounded_source_id"]), EXPECTED_ARCHIVE_PATH,
            source, checksum, output, tracked,
        )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> BindingConfig:
    return BindingConfig.from_dict(_json(repo_path(repo_root, path)))


def verify_source_evidence(summary: Mapping[str, Any], config: BindingConfig) -> dict[str, Any]:
    checksum = summary.get("deterministic_result_checksum")
    if checksum != config.expected_source_evidence_checksum or checksum != canonical_checksum(summary):
        raise ValueError("v2.6.5 source-evidence content checksum mismatch")
    if summary.get("bounded_source_id") != config.bounded_source_id:
        raise ValueError("bounded source changed")
    if summary.get("recovery_decision", {}).get("overall_status") != "source_evidence_recovered_gate_not_passed":
        raise ValueError("v2.6.5 boundary changed")
    if summary.get("coverage_summary", {}).get("promotion_requirement_satisfied_count") != 0:
        raise ValueError("v2.6.5 evidence was silently promoted")
    return {
        "v2_6_5_source_evidence_checksum_verified": True,
        "prior_overall_status": "source_evidence_recovered_gate_not_passed",
        "prior_overall_status_preserved": True,
        "prior_promotion_count": 0,
        "filename_labels_remain_non_scientific": True,
        "model_or_metric_change_performed": False,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        name and "\x00" not in name and "\\" not in name and not path.is_absolute()
        and ".." not in path.parts and not re.match(r"^[A-Za-z]:", name)
    )


def _kind(name: str) -> str:
    lower = name.lower()
    if lower.endswith("_cycle_data.csv"):
        return "cycle_csv"
    if lower.endswith("_timeseries.csv") or lower.endswith("_timeseries_data.csv"):
        return "timeseries_csv"
    return "directory" if lower.endswith("/") else "other"


def _stem(name: str) -> str | None:
    base = PurePosixPath(name).name
    for suffix in ("_cycle_data.csv", "_timeseries_data.csv", "_timeseries.csv"):
        if base.lower().endswith(suffix):
            return base[:-len(suffix)]
    return None


def parse_filename_labels(name: str) -> dict[str, Any]:
    stem = _stem(name)
    match = LABEL_RE.fullmatch(stem or "")
    if not match:
        return {
            "parse_status": "unparsed" if stem else "not_applicable",
            "raw_stem": stem,
            "provenance": "entry_name",
            "scientific_evidence": False,
        }
    values = match.groupdict()
    charge, discharge = values["rates"][:-1].split("-", 1)
    return {
        "parse_status": "parsed_filename_labels",
        "source_label": values["source"],
        "form_factor_label": values["form_factor"],
        "chemistry_label": values["chemistry"],
        "temperature_label": values["temperature"],
        "soc_window_label": values["soc_window"],
        "charge_rate_label_c": charge,
        "discharge_rate_label_c": discharge,
        "replicate_label": values.get("replicate"),
        "provenance": "entry_name",
        "scientific_evidence": False,
    }


def pending_audit() -> dict[str, Any]:
    return {
        "status": "pending_local_artifact",
        "archive_present": False,
        "archive_sha256": None,
        "archive_size_bytes": None,
        "central_directory_read": False,
        "entry_manifest": [],
        "inventory": {
            **EXPECTED_COUNTS,
            "actual_entry_count": None,
            "actual_cycle_csv_count": None,
            "actual_timeseries_csv_count": None,
            "actual_other_entry_count": None,
            "complete_pair_count": None,
            "inventory_contract_match": False,
        },
        "safety": {
            "safe_entry_count": 0,
            "unsafe_entry_count": 0,
            "duplicate_entry_count": 0,
            "encrypted_entry_count": 0,
        },
        "label_summary": {
            "parsed_count": 0,
            "unparsed_count": 0,
            "labels_are_scientific_evidence": False,
        },
    }


def audit_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return pending_audit()
    if not path.is_file() or path.name != "SNL LFP.zip":
        raise ValueError("bounded archive is not the expected regular file")
    archive_sha256 = sha256_file(path)
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    pairs: dict[str, set[str]] = {}
    unsafe = duplicates = encrypted = 0
    for info in infos:
        name, kind = info.filename, _kind(info.filename)
        safe = _safe(name)
        unsafe += int(not safe)
        duplicates += int(name in seen)
        seen.add(name)
        encrypted += int(bool(info.flag_bits & 1))
        stem = _stem(name)
        if stem and kind in {"cycle_csv", "timeseries_csv"}:
            pairs.setdefault(str(PurePosixPath(name).parent / stem), set()).add(kind)
        entries.append({
            "entry_name": name,
            "normalized_path": PurePosixPath(name).as_posix(),
            "entry_kind": kind,
            "file_size_bytes": info.file_size,
            "compressed_size_bytes": info.compress_size,
            "crc32_hex": f"{info.CRC:08x}",
            "compression_type": info.compress_type,
            "flag_bits": info.flag_bits,
            "encrypted": bool(info.flag_bits & 1),
            "safe_path": safe,
            "under_expected_root": name.startswith(EXPECTED_ROOT_PREFIX),
            "filename_labels": parse_filename_labels(name),
        })
    cycle = sum(x["entry_kind"] == "cycle_csv" for x in entries)
    timeseries = sum(x["entry_kind"] == "timeseries_csv" for x in entries)
    other = len(entries) - cycle - timeseries
    complete_pairs = sum(kinds == {"cycle_csv", "timeseries_csv"} for kinds in pairs.values())
    parsed = sum(x["filename_labels"]["parse_status"] == "parsed_filename_labels" for x in entries)
    unparsed = sum(
        x["entry_kind"] in {"cycle_csv", "timeseries_csv"}
        and x["filename_labels"]["parse_status"] == "unparsed"
        for x in entries
    )
    contract = (
        len(entries) == 60 and cycle == 30 and timeseries == 30 and other == 0
        and complete_pairs == 30 and all(x["under_expected_root"] for x in entries)
    )
    status = (
        "rejected_unsafe_archive_inventory" if unsafe or duplicates or encrypted
        else "local_artifact_inventory_bound" if contract
        else "inventory_contract_mismatch"
    )
    return {
        "status": status,
        "archive_present": True,
        "archive_sha256": archive_sha256,
        "archive_size_bytes": path.stat().st_size,
        "central_directory_read": True,
        "entry_manifest": entries,
        "entry_manifest_checksum": canonical_checksum(entries),
        "inventory": {
            **EXPECTED_COUNTS,
            "actual_entry_count": len(entries),
            "actual_cycle_csv_count": cycle,
            "actual_timeseries_csv_count": timeseries,
            "actual_other_entry_count": other,
            "complete_pair_count": complete_pairs,
            "inventory_contract_match": contract,
        },
        "safety": {
            "safe_entry_count": len(entries) - unsafe,
            "unsafe_entry_count": unsafe,
            "duplicate_entry_count": duplicates,
            "encrypted_entry_count": encrypted,
        },
        "label_summary": {
            "parsed_count": parsed,
            "unparsed_count": unparsed,
            "labels_are_scientific_evidence": False,
        },
    }


def build_result(config: BindingConfig, source: Mapping[str, Any], repo_root: str | Path = ".") -> dict[str, Any]:
    preservation = verify_source_evidence(source, config)
    archive = audit_archive(repo_path(repo_root, config.archive_path))
    completed = archive["status"] != "pending_local_artifact"
    bound = archive["status"] == "local_artifact_inventory_bound"
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_artifact_binding_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config.case_study_id,
        "bounded_source_id": config.bounded_source_id,
        "archive_path": config.archive_path,
        "archive_audit": archive,
        "binding_decision": {
            "local_artifact_inventory_binding": archive["status"],
            "checksum_identity_recorded": bool(archive.get("archive_sha256")),
            "central_directory_inventory_recorded": bool(archive.get("central_directory_read")),
            "filename_label_inventory": "recorded_as_non_scientific_labels" if completed else "pending_local_artifact",
            "document_to_archive_binding": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": "local_artifact_inventory_bound_gate_not_passed" if bound else archive["status"],
        },
        "evidence_promotion": {
            "required_field_count": 8,
            "promotion_requirement_satisfied_count": 0,
            "remaining_blocking_fields": list(EVIDENCE_FIELDS),
        },
        "preservation_checks": preservation,
        "scientific_closeout": {
            "status": "diagnostic" if completed else "inconclusive",
            "result": "local_archive_inventory_identity_recorded" if bound else archive["status"],
            "evidence_level": "checksum_and_zip_central_directory_only" if completed else "source_documents_without_accessible_local_archive",
            "strongest_evidence": (
                "The local archive checksum and ZIP central-directory inventory were recorded without reading entry payloads."
                if completed
                else "The v2.6.5 source package is verified, but the ignored local archive is unavailable in GitHub."
            ),
            "primary_limitation": "No verified mapping connects the local archive to an official versioned snapshot, documented cells, command logs, or instrument channels.",
            "suitable_for": ["local artifact identity", "central-directory inventory", "filename-label provenance"],
            "unsuitable_for": [
                "CSV row analysis", "scientific metadata promotion", "cross-cohort equivalence",
                "predictive validation", "model selection", "engineering decisions",
            ],
        },
        "recommendations": [
            "run this audit in a local checkout containing the ignored archive",
            "retain checksum and entry manifest as local evidence",
            "do not extract the archive or read CSV rows",
            "do not promote filename labels to scientific metadata",
        ],
        "source_references": {"source_evidence_summary": config.source_evidence_summary_path},
        "archive_bytes_read_for_checksum": bool(archive["archive_present"]),
        "zip_central_directory_read": bool(archive["central_directory_read"]),
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    archive = result["archive_audit"]
    archive_keys = (
        "status", "archive_present", "archive_sha256", "archive_size_bytes",
        "central_directory_read", "entry_manifest_checksum", "inventory", "safety", "label_summary",
    )
    keep = (
        "schema_version", "package_id", "case_study_id", "bounded_source_id", "archive_path",
        "binding_decision", "evidence_promotion", "preservation_checks", "scientific_closeout",
        "recommendations", "source_references", "archive_bytes_read_for_checksum",
        "zip_central_directory_read", *FALSE_FLAGS,
    )
    output = {key: result[key] for key in keep}
    output["artifact_kind"] = "battery_snl_lfp_artifact_binding_compact_summary"
    output["archive_audit"] = {key: archive[key] for key in archive_keys if key in archive}
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def persisted_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the local full summary without the row-level manifest and checksum that exact payload."""
    output = dict(result)
    output["archive_audit"] = dict(result["archive_audit"])
    output["archive_audit"].pop("entry_manifest", None)
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def validate_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != VERSION or payload.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    if payload.get("evidence_promotion", {}).get("promotion_requirement_satisfied_count") != 0:
        raise ValueError("artifact inventory was silently promoted to scientific evidence")
    decision = payload.get("binding_decision", {})
    if decision.get("cross_cohort_comparability") != "not_admitted" or decision.get("predictive_validation") != "blocked":
        raise ValueError("scientific boundary changed")
    if any(payload.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    if payload.get("deterministic_result_checksum") != canonical_checksum(payload):
        raise ValueError("deterministic result checksum mismatch")


def execute(config: BindingConfig, repo_root: str | Path = ".", write_outputs: bool = True) -> dict[str, Any]:
    result = build_result(config, _json(repo_path(repo_root, config.source_evidence_summary_path)), repo_root)
    validate_result(result)
    if write_outputs:
        root = repo_path(repo_root, config.output_root)
        root.mkdir(parents=True, exist_ok=True)
        entries = list(result["archive_audit"].get("entry_manifest", []))
        summary = persisted_summary(result)
        validate_result(summary)
        (root / "artifact_binding_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / "central_directory_manifest.json").write_text(
            json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        tracked = repo_path(repo_root, config.tracked_summary_path)
        tracked.parent.mkdir(parents=True, exist_ok=True)
        tracked.write_text(json.dumps(compact(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def preview(config: BindingConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    verify_source_evidence(_json(repo_path(repo_root, config.source_evidence_summary_path)), config)
    return {
        "schema_version": VERSION,
        "package_id": PACKAGE_ID,
        "bounded_source_id": config.bounded_source_id,
        "archive_path": config.archive_path,
        "archive_present": repo_path(repo_root, config.archive_path).is_file(),
        "allowed_reads": ["archive SHA-256 byte stream", "ZIP central directory"],
        "prohibited_reads": ["entry payloads", "CSV rows", "archive extraction"],
        "write_outputs": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    sub.add_parser("run")
    validator = sub.add_parser("validate")
    validator.add_argument("result_path")
    args = parser.parse_args(argv)
    config = load_config(args.config, args.repo_root)
    if args.command == "preview":
        value = preview(config, args.repo_root)
    elif args.command == "run":
        value = execute(config, args.repo_root, True)
    else:
        value = _json(repo_path(args.repo_root, args.result_path))
        validate_result(value)
        value = {"valid": True, "deterministic_result_checksum": value["deterministic_result_checksum"]}
    print(
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if args.json
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
