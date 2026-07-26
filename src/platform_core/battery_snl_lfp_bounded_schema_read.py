from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence
import zipfile

VERSION = "2.6.8"
PACKAGE_ID = "battery_snl_lfp_bounded_schema_read_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_snl_lfp_bounded_schema_read.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_snl_lfp_bounded_schema_read_contract_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_bounded_schema_read"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_8_snl_lfp_bounded_schema_read_summary.json"
EXPECTED_ARCHIVE_PATH = "data/raw/battery_archive/SNL LFP.zip"
EXPECTED_ARCHIVE_SHA256 = "006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d"
EXPECTED_V267_CHECKSUM = "38fb66269706938513bb000d14427b33147ee13f04d917696e47dff7f2699248"
EXPECTED_V266_CHECKSUM = "f4c02c38652848ddba6a69ffe47010e0cb7ada3ad411fd028afdd5ff552b89e5"
MAX_ROWS = 5
MAX_LINE_BYTES = 65536
REPRESENTATIVE_ENTRIES = (
    "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_timeseries.csv",
    "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_timeseries.csv",
    "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_timeseries.csv",
)
FALSE_FLAGS = (
    "archive_extracted",
    "nonrepresentative_entry_read",
    "full_csv_read",
    "network_called",
    "credentials_read",
    "source_mutation_performed",
    "cohort_merge_performed",
    "model_trained",
    "model_evaluated",
    "metrics_recomputed",
    "physical_cell_binding_inferred",
    "cycle_command_binding_inferred",
    "instrument_channel_binding_inferred",
    "capacity_check_classification_promoted",
)
UNIT_PARENS = re.compile(r"(?:\(([^()]*)\)|\[([^\[\]]*)\])\s*$")
UNIT_SLASH = re.compile(r"/\s*([A-Za-z°µμ%][A-Za-z0-9°µμ%*/^._-]*)\s*$")


def canonical_checksum(payload: Any) -> str:
    core = dict(payload) if isinstance(payload, Mapping) else payload
    if isinstance(core, dict):
        core.pop("deterministic_result_checksum", None)
    text = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    base = Path(root).resolve()
    target = (Path(root) / value).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return target


@dataclass(frozen=True)
class SchemaReadConfig:
    case_study_id: str
    bounded_source_id: str
    contract_path: str
    v2_6_7_summary_path: str
    v2_6_6_summary_path: str
    archive_path: str
    output_root: str
    tracked_summary_path: str
    max_data_rows_per_entry: int
    max_line_bytes: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SchemaReadConfig":
        required = {
            "schema_version",
            "package_id",
            "case_study_id",
            "bounded_source_id",
            "schema_read_contract_path",
            "v2_6_7_source_entry_binding_summary_path",
            "v2_6_6_artifact_binding_summary_path",
            "expected_v2_6_7_checksum",
            "expected_v2_6_6_checksum",
            "archive_path",
            "expected_archive_sha256",
            "representative_entries",
            "csv_policy",
            "read_policy",
            "credential_policy",
            "output_root",
            "tracked_summary_path",
            "output_policy",
            "execution_mode",
            "dry_run",
        }
        if set(payload) != required:
            raise ValueError("config fields changed")
        if payload["schema_version"] != VERSION or payload["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported bounded schema-read package")
        if payload["bounded_source_id"] != "snl_lfp_commercial_18650_study":
            raise ValueError("bounded source changed")
        if payload["expected_v2_6_7_checksum"] != EXPECTED_V267_CHECKSUM:
            raise ValueError("v2.6.7 checksum contract changed")
        if payload["expected_v2_6_6_checksum"] != EXPECTED_V266_CHECKSUM:
            raise ValueError("v2.6.6 checksum contract changed")
        if payload["expected_archive_sha256"] != EXPECTED_ARCHIVE_SHA256:
            raise ValueError("archive checksum contract changed")
        if tuple(payload["representative_entries"]) != REPRESENTATIVE_ENTRIES:
            raise ValueError("representative entry set changed")
        if payload["csv_policy"] != {
            "delimiter": ",",
            "encoding": "utf-8-sig",
            "max_data_rows_per_entry": MAX_ROWS,
            "max_line_bytes": MAX_LINE_BYTES,
            "retain_raw_sample_values": False,
        }:
            raise ValueError("CSV read limits changed")
        if payload["read_policy"] != {
            "allow_tracked_json_reads": True,
            "allow_archive_sha256": True,
            "allow_zip_central_directory": True,
            "allow_representative_entry_payload_read": True,
            "allow_csv_header_read": True,
            "allow_csv_data_row_read": True,
            "allow_nonrepresentative_entry_read": False,
            "allow_full_csv_read": False,
            "allow_archive_extraction": False,
        }:
            raise ValueError("read policy changed")
        if payload["credential_policy"] != {
            "store_credentials": False,
            "network_access_required": False,
        }:
            raise ValueError("credential policy changed")
        if payload["output_policy"] != "local_full_result_and_tracked_compact_summary":
            raise ValueError("output policy changed")
        if payload["execution_mode"] != "bounded_local_schema_read":
            raise ValueError("execution mode changed")
        if payload["dry_run"] is not False:
            raise ValueError("bounded schema read is not a dry run")

        contract = _relative("schema_read_contract_path", payload["schema_read_contract_path"])
        v267 = _relative(
            "v2_6_7_source_entry_binding_summary_path",
            payload["v2_6_7_source_entry_binding_summary_path"],
        )
        v266 = _relative(
            "v2_6_6_artifact_binding_summary_path",
            payload["v2_6_6_artifact_binding_summary_path"],
        )
        archive = _relative("archive_path", payload["archive_path"])
        output = _relative("output_root", payload["output_root"])
        tracked = _relative("tracked_summary_path", payload["tracked_summary_path"])
        if contract != DEFAULT_CONTRACT_PATH:
            raise ValueError("contract path changed")
        if archive != EXPECTED_ARCHIVE_PATH:
            raise ValueError("archive path changed")
        if output != DEFAULT_OUTPUT_ROOT or tracked != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("output paths changed")

        return cls(
            case_study_id=str(payload["case_study_id"]),
            bounded_source_id=str(payload["bounded_source_id"]),
            contract_path=contract,
            v2_6_7_summary_path=v267,
            v2_6_6_summary_path=v266,
            archive_path=archive,
            output_root=output,
            tracked_summary_path=tracked,
            max_data_rows_per_entry=MAX_ROWS,
            max_line_bytes=MAX_LINE_BYTES,
        )


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> SchemaReadConfig:
    return SchemaReadConfig.from_dict(_json(repo_path(repo_root, path)))


def validate_contract(contract: Mapping[str, Any], config: SchemaReadConfig) -> None:
    required = {
        "schema_version",
        "contract_id",
        "bounded_source_id",
        "contract_recorded_on",
        "scientific_question",
        "archive_identity",
        "representative_selection",
        "representative_entries",
        "file_kind_requirements",
        "unit_observation_policy",
        "stop_rules",
        "claim_policy",
    }
    if set(contract) != required:
        raise ValueError("schema-read contract fields changed")
    if contract["schema_version"] != "1":
        raise ValueError("unsupported schema-read contract")
    if contract["contract_id"] != "battery_snl_lfp_bounded_schema_read_contract_v1":
        raise ValueError("contract id changed")
    if contract["bounded_source_id"] != config.bounded_source_id:
        raise ValueError("contract bounded source changed")
    if contract["archive_identity"] != {
        "archive_path": EXPECTED_ARCHIVE_PATH,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "entry_manifest_checksum": "f85e6f1ac333f7ff20b7bfd01b8599cfe86e8950c4971e9fc074a367da86a75c",
    }:
        raise ValueError("archive identity contract changed")

    entries = contract["representative_entries"]
    if tuple(item.get("entry_name") for item in entries) != REPRESENTATIVE_ENTRIES:
        raise ValueError("representative entry order changed")
    for item in entries:
        if set(item) != {
            "entry_name",
            "file_kind",
            "protocol_family",
            "selection_rationale",
            "max_data_rows",
        }:
            raise ValueError("representative entry fields changed")
        expected_kind = (
            "cycle_data" if item["entry_name"].endswith("_cycle_data.csv") else "timeseries"
        )
        if item["file_kind"] != expected_kind or item["max_data_rows"] != MAX_ROWS:
            raise ValueError("representative entry read contract changed")

    requirements = contract["file_kind_requirements"]
    if set(requirements) != {"cycle_data", "timeseries"}:
        raise ValueError("file-kind requirements changed")
    for kind, groups in requirements.items():
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"invalid role requirements for {kind}")
        for group in groups:
            if not isinstance(group, list) or not group:
                raise ValueError(f"invalid role alternative group for {kind}")

    if contract["unit_observation_policy"] != {
        "record_only_if_explicit_in_header": True,
        "infer_missing_units": False,
        "convert_units": False,
        "treat_header_unit_as_calibration_evidence": False,
    }:
        raise ValueError("unit observation policy changed")
    if any(contract["claim_policy"].values()):
        raise ValueError("claim policy may not promote bounded samples")


def verify_upstream(
    v267: Mapping[str, Any],
    v266: Mapping[str, Any],
    config: SchemaReadConfig,
) -> dict[str, Any]:
    del config
    if v267.get("deterministic_result_checksum") != EXPECTED_V267_CHECKSUM:
        raise ValueError("v2.6.7 checksum mismatch")
    if canonical_checksum(v267) != EXPECTED_V267_CHECKSUM:
        raise ValueError("v2.6.7 content checksum mismatch")
    if v267.get("binding_decision", {}).get("overall_status") != (
        "condition_group_nomenclature_bound_gate_not_passed"
    ):
        raise ValueError("v2.6.7 binding boundary changed")
    if v266.get("deterministic_result_checksum") != EXPECTED_V266_CHECKSUM:
        raise ValueError("v2.6.6 checksum mismatch")
    if canonical_checksum(v266) != EXPECTED_V266_CHECKSUM:
        raise ValueError("v2.6.6 content checksum mismatch")
    audit = v266.get("archive_audit", {})
    if audit.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("v2.6.6 archive checksum changed")
    if audit.get("status") != "local_artifact_inventory_bound":
        raise ValueError("v2.6.6 artifact identity boundary changed")
    return {
        "v2_6_7_checksum_verified": True,
        "v2_6_6_checksum_verified": True,
        "archive_sha256_preserved": True,
        "prior_binding_gate_preserved": True,
        "model_or_metric_change_performed": False,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_entry_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        name
        and "\x00" not in name
        and "\\" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and not re.match(r"^[A-Za-z]:", name)
    )


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _explicit_unit(value: str) -> str | None:
    match = UNIT_PARENS.search(value)
    if match:
        unit = (match.group(1) or match.group(2) or "").strip()
        return unit or None
    match = UNIT_SLASH.search(value)
    if match:
        unit = match.group(1).strip()
        return unit or None
    return None


def _candidate_roles(header: str) -> list[str]:
    normalized = _normalize_header(header)
    roles: list[str] = []
    if "cycle" in normalized and (
        "index" in normalized or "count" in normalized or normalized == "cycle"
    ):
        roles.append("cycle_index")
    if "step" in normalized and (
        "index" in normalized or "count" in normalized or normalized == "step"
    ):
        roles.append("step_index")
    if "testtime" in normalized or "elapsedtime" in normalized:
        roles.append("test_time")
    if "voltage" in normalized or normalized in {"volt", "volts"}:
        roles.append("voltage")
    if "current" in normalized or normalized in {"amp", "amps", "ampere"}:
        roles.append("current")
    if "temperature" in normalized or normalized.endswith("temp"):
        roles.append("temperature")
    if "dischargecapacity" in normalized:
        roles.append("discharge_capacity")
    elif "chargecapacity" in normalized:
        roles.append("charge_capacity")
    elif "capacity" in normalized:
        roles.append("capacity")
    if "dischargeenergy" in normalized:
        roles.append("discharge_energy")
    elif "chargeenergy" in normalized:
        roles.append("charge_energy")
    elif "energy" in normalized:
        roles.append("energy")
    if "datetime" in normalized or "timestamp" in normalized or "unixtime" in normalized:
        roles.append("timestamp")
    return roles


def _parse_csv_line(raw: bytes, max_line_bytes: int) -> list[str]:
    if len(raw) > max_line_bytes:
        raise ValueError("CSV line exceeds bounded byte limit")
    if b"\x00" in raw:
        raise ValueError("NUL byte found in CSV line")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV line is not valid UTF-8") from exc
    try:
        rows = list(csv.reader([text], delimiter=",", strict=True))
    except csv.Error as exc:
        raise ValueError("CSV line parse failure") from exc
    if len(rows) != 1:
        raise ValueError("one physical line must contain one CSV record")
    return [cell.strip() for cell in rows[0]]


def _numeric(value: str) -> bool:
    if value == "":
        return False
    try:
        float(value)
    except ValueError:
        return False
    return True


def _role_contract(
    headers: Sequence[Mapping[str, Any]],
    requirement_groups: Sequence[Sequence[str]],
) -> dict[str, Any]:
    observed = {
        role
        for item in headers
        for role in item.get("candidate_roles", [])
    }
    group_results = []
    for alternatives in requirement_groups:
        matched = sorted(set(alternatives) & observed)
        group_results.append(
            {
                "alternatives": list(alternatives),
                "matched_roles": matched,
                "satisfied": bool(matched),
            }
        )
    return {
        "observed_candidate_roles": sorted(observed),
        "requirement_groups": group_results,
        "required_role_contract_match": all(x["satisfied"] for x in group_results),
        "candidate_roles_are_scientific_bindings": False,
    }


def read_csv_sample(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    representative: Mapping[str, Any],
    requirements: Sequence[Sequence[str]],
    max_line_bytes: int,
) -> dict[str, Any]:
    bytes_read = 0
    raw_rows: list[list[str]] = []
    with archive.open(info, "r") as handle:
        header_line = handle.readline(max_line_bytes + 1)
        bytes_read += len(header_line)
        if not header_line:
            return {
                "entry_name": info.filename,
                "file_kind": representative["file_kind"],
                "protocol_family": representative["protocol_family"],
                "read_status": "empty_file",
                "bytes_read": bytes_read,
                "sample_data_rows_read": 0,
                "raw_sample_values_retained": False,
            }
        try:
            header = _parse_csv_line(header_line, max_line_bytes)
            for _ in range(int(representative["max_data_rows"])):
                line = handle.readline(max_line_bytes + 1)
                if not line:
                    break
                bytes_read += len(line)
                raw_rows.append(_parse_csv_line(line, max_line_bytes))
        except ValueError as exc:
            return {
                "entry_name": info.filename,
                "file_kind": representative["file_kind"],
                "protocol_family": representative["protocol_family"],
                "read_status": "bounded_parse_error",
                "error": str(exc),
                "bytes_read": bytes_read,
                "sample_data_rows_read": len(raw_rows),
                "raw_sample_values_retained": False,
            }

    duplicate_headers = sorted({name for name in header if name and header.count(name) > 1})
    widths = [len(row) for row in raw_rows]
    width_match = all(width == len(header) for width in widths)
    header_observations = []
    for index, name in enumerate(header):
        values = [row[index] for row in raw_rows if index < len(row)]
        header_observations.append(
            {
                "index": index,
                "raw_header": name,
                "normalized_header": _normalize_header(name),
                "explicit_unit": _explicit_unit(name),
                "candidate_roles": _candidate_roles(name),
                "sample_nonempty_count": sum(value != "" for value in values),
                "sample_numeric_count": sum(_numeric(value) for value in values),
            }
        )
    role_contract = _role_contract(header_observations, requirements)
    structural_match = bool(
        header
        and all(name != "" for name in header)
        and not duplicate_headers
        and width_match
        and role_contract["required_role_contract_match"]
    )
    return {
        "entry_name": info.filename,
        "file_kind": representative["file_kind"],
        "protocol_family": representative["protocol_family"],
        "read_status": (
            "bounded_schema_observed"
            if structural_match
            else "bounded_schema_contract_mismatch"
        ),
        "bytes_read": bytes_read,
        "header_column_count": len(header),
        "header_checksum": canonical_checksum(header),
        "duplicate_headers": duplicate_headers,
        "sample_data_rows_read": len(raw_rows),
        "sample_row_widths": widths,
        "row_width_contract_match": width_match,
        "header_observations": header_observations,
        "role_contract": role_contract,
        "raw_sample_values_retained": False,
        "full_file_read": False,
    }


def pending_result(
    config: SchemaReadConfig,
    contract: Mapping[str, Any],
    preservation: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_bounded_schema_read_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config.case_study_id,
        "bounded_source_id": config.bounded_source_id,
        "contract_id": contract["contract_id"],
        "contract_checksum": canonical_checksum(contract),
        "archive_path": config.archive_path,
        "archive_audit": {
            "status": "pending_local_artifact",
            "archive_present": False,
            "expected_archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "observed_archive_sha256": None,
            "central_directory_read": False,
        },
        "representative_read_summary": {
            "status": "pending_local_artifact",
            "declared_entry_count": len(REPRESENTATIVE_ENTRIES),
            "opened_entry_count": 0,
            "header_count": 0,
            "sample_data_row_count": 0,
            "schema_contract_match_count": 0,
            "schema_contract_mismatch_count": 0,
        },
        "file_observations": [],
        "schema_read_decision": {
            "bounded_schema_observation": "pending_local_artifact",
            "capacity_check_vs_bulk_cycle_discrimination": "not_established",
            "physical_cell_to_entry": "not_established",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": "pending_local_artifact",
        },
        "preservation_checks": dict(preservation),
        "scientific_closeout": {
            "status": "inconclusive",
            "result": "pending_bounded_local_schema_read",
            "evidence_level": "contract_defined_without_local_payload_observation",
            "strongest_evidence": (
                "The exact six representative entries and bounded read limits are "
                "predeclared against the v2.6.6 archive identity."
            ),
            "primary_limitation": (
                "GitHub cannot access the ignored local archive, so no CSV header "
                "or bounded sample row has been observed."
            ),
            "suitable_for": ["schema-read execution planning", "read-boundary validation"],
            "unsuitable_for": [
                "capacity-check classification",
                "cycle-command binding",
                "instrument-channel binding",
                "cohort comparison",
                "predictive validation",
                "engineering decisions",
            ],
        },
        "recommendations": [
            "run the bounded audit in the local checkout containing SNL LFP.zip",
            "commit only the compact schema observation after validation",
            "do not expand the read set or row limit without a new contract",
        ],
        "source_references": {
            "contract": config.contract_path,
            "v2_6_7_summary": config.v2_6_7_summary_path,
            "v2_6_6_summary": config.v2_6_6_summary_path,
        },
        "archive_bytes_read_for_checksum": False,
        "zip_central_directory_read": False,
        "representative_entry_payloads_read": False,
        "csv_headers_read": False,
        "csv_data_rows_read": False,
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def build_result(
    config: SchemaReadConfig,
    contract: Mapping[str, Any],
    v267: Mapping[str, Any],
    v266: Mapping[str, Any],
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    validate_contract(contract, config)
    preservation = verify_upstream(v267, v266, config)
    archive_path = repo_path(repo_root, config.archive_path)
    if not archive_path.is_file():
        return pending_result(config, contract, preservation)

    observed_sha = sha256_file(archive_path)
    if observed_sha != EXPECTED_ARCHIVE_SHA256:
        result = pending_result(config, contract, preservation)
        result["archive_audit"] = {
            "status": "rejected_archive_identity_mismatch",
            "archive_present": True,
            "expected_archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "observed_archive_sha256": observed_sha,
            "central_directory_read": False,
        }
        result["representative_read_summary"]["status"] = "rejected_archive_identity_mismatch"
        result["schema_read_decision"]["bounded_schema_observation"] = "rejected_archive_identity_mismatch"
        result["schema_read_decision"]["overall_status"] = "rejected_archive_identity_mismatch"
        result["archive_bytes_read_for_checksum"] = True
        result["scientific_closeout"] = {
            "status": "unsupported",
            "result": "archive_identity_mismatch",
            "evidence_level": "checksum_rejection_before_payload_read",
            "strongest_evidence": "The observed archive SHA-256 does not match the v2.6.6 identity.",
            "primary_limitation": "No representative payload was opened after mismatch.",
            "suitable_for": ["artifact rejection"],
            "unsuitable_for": ["schema interpretation", "scientific analysis"],
        }
        result["deterministic_result_checksum"] = canonical_checksum(result)
        return result

    observations: list[dict[str, Any]] = []
    opened: list[str] = []
    central_directory_status = "verified"
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos: dict[str, list[zipfile.ZipInfo]] = {}
        for info in archive.infolist():
            infos.setdefault(info.filename, []).append(info)
        for representative in contract["representative_entries"]:
            name = representative["entry_name"]
            matches = infos.get(name, [])
            if len(matches) != 1:
                central_directory_status = "representative_entry_contract_mismatch"
                observations.append(
                    {
                        "entry_name": name,
                        "file_kind": representative["file_kind"],
                        "protocol_family": representative["protocol_family"],
                        "read_status": (
                            "missing_representative_entry"
                            if not matches
                            else "duplicate_representative_entry"
                        ),
                        "raw_sample_values_retained": False,
                    }
                )
                continue
            info = matches[0]
            if info.is_dir() or not _safe_entry_name(info.filename) or bool(info.flag_bits & 1):
                central_directory_status = "representative_entry_contract_mismatch"
                observations.append(
                    {
                        "entry_name": name,
                        "file_kind": representative["file_kind"],
                        "protocol_family": representative["protocol_family"],
                        "read_status": "unsafe_or_encrypted_representative_entry",
                        "raw_sample_values_retained": False,
                    }
                )
                continue
            requirements = contract["file_kind_requirements"][representative["file_kind"]]
            observations.append(
                read_csv_sample(
                    archive,
                    info,
                    representative,
                    requirements,
                    config.max_line_bytes,
                )
            )
            opened.append(name)

    statuses = [item["read_status"] for item in observations]
    all_observed = bool(
        len(opened) == len(REPRESENTATIVE_ENTRIES)
        and all(status == "bounded_schema_observed" for status in statuses)
    )
    parse_or_schema_mismatch = any(
        status in {"bounded_parse_error", "bounded_schema_contract_mismatch", "empty_file"}
        for status in statuses
    )
    if all_observed:
        overall = "bounded_schema_observed_gate_not_passed"
        observation_status = "bounded_schema_observed"
    elif central_directory_status != "verified":
        overall = "representative_entry_contract_mismatch"
        observation_status = "representative_entry_contract_mismatch"
    elif parse_or_schema_mismatch:
        overall = "bounded_schema_contract_mismatch"
        observation_status = "bounded_schema_contract_mismatch"
    else:
        overall = "bounded_schema_read_incomplete"
        observation_status = "bounded_schema_read_incomplete"

    total_headers = sum(int(item.get("header_column_count", 0) > 0) for item in observations)
    total_rows = sum(int(item.get("sample_data_rows_read", 0)) for item in observations)
    match_count = sum(item.get("read_status") == "bounded_schema_observed" for item in observations)

    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_bounded_schema_read_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config.case_study_id,
        "bounded_source_id": config.bounded_source_id,
        "contract_id": contract["contract_id"],
        "contract_checksum": canonical_checksum(contract),
        "archive_path": config.archive_path,
        "archive_audit": {
            "status": central_directory_status,
            "archive_present": True,
            "expected_archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "observed_archive_sha256": observed_sha,
            "central_directory_read": True,
        },
        "representative_read_summary": {
            "status": observation_status,
            "declared_entry_count": len(REPRESENTATIVE_ENTRIES),
            "opened_entry_count": len(opened),
            "opened_entries": opened,
            "header_count": total_headers,
            "sample_data_row_count": total_rows,
            "max_data_rows_per_entry": MAX_ROWS,
            "max_line_bytes": MAX_LINE_BYTES,
            "schema_contract_match_count": match_count,
            "schema_contract_mismatch_count": len(observations) - match_count,
        },
        "file_observations": observations,
        "schema_read_decision": {
            "bounded_schema_observation": observation_status,
            "capacity_check_vs_bulk_cycle_discrimination": "header_and_first_rows_insufficient",
            "physical_cell_to_entry": "not_established",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": overall,
        },
        "preservation_checks": dict(preservation),
        "scientific_closeout": {
            "status": "diagnostic" if all_observed else "inconclusive",
            "result": (
                "bounded_representative_schema_observed"
                if all_observed
                else "bounded_schema_contract_not_fully_satisfied"
            ),
            "evidence_level": "six_predeclared_headers_and_up_to_five_rows_per_file",
            "strongest_evidence": (
                "Only the six predeclared representative entries were opened, "
                "with one header and at most five data rows read from each."
            ),
            "primary_limitation": (
                "The bounded samples cannot establish full-file consistency, "
                "capacity-check classification, exact cycle commands, instrument "
                "channel mapping, calibration, or cohort equivalence."
            ),
            "suitable_for": [
                "observed CSV schema inventory",
                "candidate column-role planning",
                "next read-contract design",
            ],
            "unsuitable_for": [
                "capacity-check classification",
                "cycle-command binding",
                "instrument-channel binding",
                "unit conversion",
                "cohort comparison",
                "model evaluation",
                "engineering decisions",
            ],
        },
        "recommendations": [
            "review observed headers and candidate roles before authorizing any larger read",
            "define a separate cycle/step discrimination contract only if the observed schema supports it",
            "do not merge cohorts or execute a model",
        ],
        "source_references": {
            "contract": config.contract_path,
            "v2_6_7_summary": config.v2_6_7_summary_path,
            "v2_6_6_summary": config.v2_6_6_summary_path,
        },
        "archive_bytes_read_for_checksum": True,
        "zip_central_directory_read": True,
        "representative_entry_payloads_read": bool(opened),
        "csv_headers_read": bool(total_headers),
        "csv_data_rows_read": bool(total_rows),
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    observation_keys = (
        "entry_name",
        "file_kind",
        "protocol_family",
        "read_status",
        "bytes_read",
        "header_column_count",
        "header_checksum",
        "duplicate_headers",
        "sample_data_rows_read",
        "sample_row_widths",
        "row_width_contract_match",
        "header_observations",
        "role_contract",
        "raw_sample_values_retained",
        "full_file_read",
        "error",
    )
    keep = (
        "schema_version",
        "package_id",
        "case_study_id",
        "bounded_source_id",
        "contract_id",
        "contract_checksum",
        "archive_path",
        "archive_audit",
        "representative_read_summary",
        "schema_read_decision",
        "preservation_checks",
        "scientific_closeout",
        "recommendations",
        "source_references",
        "archive_bytes_read_for_checksum",
        "zip_central_directory_read",
        "representative_entry_payloads_read",
        "csv_headers_read",
        "csv_data_rows_read",
        *FALSE_FLAGS,
    )
    output = {key: result[key] for key in keep}
    output["artifact_kind"] = "battery_snl_lfp_bounded_schema_read_compact_summary"
    output["file_observations"] = [
        {key: item[key] for key in observation_keys if key in item}
        for item in result["file_observations"]
    ]
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def validate_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != VERSION or payload.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    decision = payload.get("schema_read_decision", {})
    if decision.get("cross_cohort_comparability") != "not_admitted":
        raise ValueError("comparability boundary changed")
    if decision.get("predictive_validation") != "blocked":
        raise ValueError("predictive-validation boundary changed")
    if decision.get("physical_cell_to_entry") != "not_established":
        raise ValueError("physical-cell binding was promoted")
    if decision.get("cycle_command_to_rows") != "not_established":
        raise ValueError("cycle-command binding was promoted")
    if decision.get("instrument_channel_to_columns") != "not_established":
        raise ValueError("instrument-channel binding was promoted")
    if any(payload.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    for item in payload.get("file_observations", []):
        if item.get("raw_sample_values_retained") is not False:
            raise ValueError("raw sample values were retained")
        if item.get("sample_data_rows_read", 0) > MAX_ROWS:
            raise ValueError("bounded row limit exceeded")
        if item.get("full_file_read") is True:
            raise ValueError("full file read was performed")
        for header in item.get("header_observations", []):
            if header.get("candidate_roles") and item.get(
                "role_contract", {}
            ).get("candidate_roles_are_scientific_bindings") is not False:
                raise ValueError("candidate roles were promoted")
    if payload.get("deterministic_result_checksum") != canonical_checksum(payload):
        raise ValueError("deterministic result checksum mismatch")


def execute(
    config: SchemaReadConfig,
    repo_root: str | Path = ".",
    write_outputs: bool = True,
) -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config.contract_path))
    v267 = _json(repo_path(repo_root, config.v2_6_7_summary_path))
    v266 = _json(repo_path(repo_root, config.v2_6_6_summary_path))
    result = build_result(config, contract, v267, v266, repo_root)
    validate_result(result)
    if write_outputs:
        output_root = repo_path(repo_root, config.output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "bounded_schema_read_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tracked = repo_path(repo_root, config.tracked_summary_path)
        tracked.parent.mkdir(parents=True, exist_ok=True)
        compact_result = compact(result)
        validate_result(compact_result)
        tracked.write_text(
            json.dumps(compact_result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def preview(config: SchemaReadConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config.contract_path))
    validate_contract(contract, config)
    return {
        "schema_version": VERSION,
        "package_id": PACKAGE_ID,
        "bounded_source_id": config.bounded_source_id,
        "archive_path": config.archive_path,
        "archive_present": repo_path(repo_root, config.archive_path).is_file(),
        "representative_entries": list(REPRESENTATIVE_ENTRIES),
        "max_data_rows_per_entry": MAX_ROWS,
        "max_line_bytes": MAX_LINE_BYTES,
        "allowed_reads": [
            "archive SHA-256 stream",
            "ZIP central directory",
            "six exact representative entry payloads",
            "one header and at most five data rows per representative entry",
        ],
        "prohibited_reads": [
            "nonrepresentative entries",
            "full CSV files",
            "archive extraction",
            "network",
            "credentials",
        ],
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
        value = {
            "valid": True,
            "deterministic_result_checksum": value["deterministic_result_checksum"],
        }
    print(
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if args.json
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
