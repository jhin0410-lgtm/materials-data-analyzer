from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import socket
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = "2.6.13"
PACKAGE_ID = "battery_michigan_formation_deepblue_metadata_retrieval_gate_v1"
CONTRACT_ID = "battery_michigan_formation_deepblue_metadata_retrieval_contract_v1"
EVIDENCE_ID = "battery_deepblue_rest_api_metadata_evidence_v1"

DEFAULT_CONFIG_PATH = "configs/examples/battery_michigan_formation_deepblue_metadata_retrieval_gate.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_michigan_formation_deepblue_metadata_retrieval_contract_v1.json"
DEFAULT_EVIDENCE_PATH = "data/platform/battery_deepblue_rest_api_metadata_evidence_v1.json"
DEFAULT_V2612_PATH = "data/processed/battery_v2_6_12_michigan_formation_provider_package_summary.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_michigan_formation_deepblue_metadata"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_13_michigan_formation_deepblue_metadata_summary.json"

EXPECTED_V2612_CHECKSUM = "b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d"
EXPECTED_CONTRACT_CHECKSUM = "7e9791087a25d03230f54118d04c53bb429d6bd79b3ce8d5c13bb9132dcf74e3"
EXPECTED_EVIDENCE_CHECKSUM = "797786d50b4266a91c6d534ea94ca63b20eeeeeca2f97f31811fc7dd423aa04f"

DATASET_ID = "b2773w109"
DATASET_DOI = "10.7302/pa3f-4w30"
DATASET_TITLE = "Battery test data - fast formation study"
DATASET_URL = f"https://deepblue.lib.umich.edu/data/concern/data_sets/{DATASET_ID}.json"
FILE_SET_URL_TEMPLATE = "https://deepblue.lib.umich.edu/data/concern/file_sets/{file_set_id}.json"

DATASET_FIELDS = (
    "id", "title", "doi", "total_file_count", "total_file_size",
    "total_file_size_human_readable", "file_set_ids",
)
FILE_SET_FIELDS = (
    "id", "title", "label", "date_uploaded", "date_modified", "file_size",
    "file_size_human_readable", "checksum_algorithm", "checksum_value",
    "original_checksum", "mime_type",
)
PROHIBITED_TRUE_FLAGS = (
    "credentials_read", "credentials_sent", "provider_dataset_downloaded",
    "provider_file_payload_read", "local_archive_read", "local_csv_payload_read",
    "raw_response_retained", "personal_contact_metadata_retained",
    "filename_metadata_inferred", "command_semantics_inferred",
    "missing_metadata_inferred", "candidate_admitted",
    "cross_cohort_comparability_promoted", "cohort_merge_performed",
    "model_trained", "model_evaluated", "metrics_recomputed",
    "source_mutation_performed",
)


class MetadataRetrievalError(RuntimeError):
    """Safe, categorized metadata retrieval failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MetadataRetrievalError("redirect_rejected")


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = copy.deepcopy(dict(payload))
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


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> dict[str, Any]:
    value = _json(repo_path(repo_root, path))
    required = {
        "schema_version", "package_id", "case_study_id", "contract_path",
        "api_evidence_path", "v2_6_12_provider_package_summary_path",
        "expected_v2_6_12_checksum", "execution_policy", "credential_policy",
        "output_root", "tracked_summary_path", "output_policy",
        "execution_mode", "dry_run",
    }
    if set(value) != required:
        raise ValueError("config fields changed")
    if value["schema_version"] != VERSION or value["package_id"] != PACKAGE_ID:
        raise ValueError("unsupported metadata retrieval package")
    if value["expected_v2_6_12_checksum"] != EXPECTED_V2612_CHECKSUM:
        raise ValueError("v2.6.12 checksum contract changed")
    expected_policy = {
        "network_access": True,
        "metadata_get_only": True,
        "provider_dataset_download": False,
        "provider_file_payload_read": False,
        "local_archive_read": False,
        "local_csv_payload_read": False,
        "command_inference": False,
        "cohort_merge": False,
        "model_execution": False,
        "metric_recomputation": False,
    }
    if value["execution_policy"] != expected_policy:
        raise ValueError("execution policy changed")
    if value["credential_policy"] != {
        "network_access_required": True,
        "store_credentials": False,
        "send_credentials": False,
    }:
        raise ValueError("credential policy changed")
    paths = {
        "contract_path": DEFAULT_CONTRACT_PATH,
        "api_evidence_path": DEFAULT_EVIDENCE_PATH,
        "v2_6_12_provider_package_summary_path": DEFAULT_V2612_PATH,
        "output_root": DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
    }
    for key, expected in paths.items():
        if _relative(key, value[key]) != expected:
            raise ValueError(f"{key} changed")
    if value["output_policy"] != "tracked_compact_summary_and_local_full_result":
        raise ValueError("output policy changed")
    if value["execution_mode"] != "bounded_metadata_retrieval":
        raise ValueError("execution mode changed")
    if value["dry_run"] is not False:
        raise ValueError("dry-run boundary changed")
    return value


def validate_contract(value: Mapping[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract identity changed")
    if canonical_checksum(value) != EXPECTED_CONTRACT_CHECKSUM:
        raise ValueError("contract checksum mismatch")
    upstream = value.get("upstream_identity", {})
    if upstream != {
        "v2_6_12_checksum": EXPECTED_V2612_CHECKSUM,
        "provider_dataset_id": DATASET_ID,
        "provider_dataset_doi": DATASET_DOI,
        "provider_dataset_title": DATASET_TITLE,
        "expected_top_level_file_set_count": 2,
    }:
        raise ValueError("contract upstream identity changed")
    network = value.get("network_contract", {})
    if network.get("scheme") != "https" or network.get("host") != "deepblue.lib.umich.edu":
        raise ValueError("network origin changed")
    if network.get("dataset_path") != f"/data/concern/data_sets/{DATASET_ID}.json":
        raise ValueError("dataset endpoint changed")
    if network.get("file_set_path_template") != "/data/concern/file_sets/{file_set_id}.json":
        raise ValueError("file-set endpoint changed")
    if network.get("method") != "GET":
        raise ValueError("HTTP method changed")
    if network.get("redirects_allowed") or network.get("credentials_allowed"):
        raise ValueError("network safety boundary changed")
    if network.get("query_parameters_allowed"):
        raise ValueError("query parameters are not allowed")
    if network.get("max_file_set_requests") != 2:
        raise ValueError("file-set request bound changed")
    if any(value.get("claim_policy", {}).values()):
        raise ValueError("claim policy was promoted")


def validate_api_evidence(value: Mapping[str, Any]) -> None:
    if value.get("evidence_record_id") != EVIDENCE_ID:
        raise ValueError("API evidence identity changed")
    if canonical_checksum(value) != EXPECTED_EVIDENCE_CHECKSUM:
        raise ValueError("API evidence checksum mismatch")
    if any(value.get("evidence_boundary", {}).values()):
        raise ValueError("API evidence was promoted beyond documentation")


def verify_upstream(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("deterministic_result_checksum") != EXPECTED_V2612_CHECKSUM:
        raise ValueError("v2.6.12 checksum mismatch")
    if canonical_checksum(value) != EXPECTED_V2612_CHECKSUM:
        raise ValueError("v2.6.12 content checksum mismatch")
    decision = value.get("decision", {})
    expected = "provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed"
    if decision.get("overall_status") != expected:
        raise ValueError("v2.6.12 boundary changed")
    return {
        "v2_6_12_checksum_verified": True,
        "v2_6_12_overall_status": expected,
        "model_or_metric_change_performed": False,
    }


def _safe_url(url: str, *, file_set_id: str | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "deepblue.lib.umich.edu":
        raise MetadataRetrievalError("origin_rejected")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise MetadataRetrievalError("query_or_credentials_rejected")
    if "/downloads/" in parsed.path or "zip_download" in parsed.path:
        raise MetadataRetrievalError("download_endpoint_rejected")
    if file_set_id is None:
        expected = f"/data/concern/data_sets/{DATASET_ID}.json"
    else:
        if not re.fullmatch(r"[a-z0-9]{9}", file_set_id):
            raise MetadataRetrievalError("invalid_file_set_id")
        expected = f"/data/concern/file_sets/{file_set_id}.json"
    if parsed.path != expected:
        raise MetadataRetrievalError("metadata_path_rejected")


def _default_fetch(url: str, max_bytes: int, timeout: int) -> tuple[bytes, str]:
    file_set_id = None if url == DATASET_URL else url.rsplit("/", 1)[-1][:-5]
    _safe_url(url, file_set_id=file_set_id)
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "materials-data-analyzer/2.6.13 metadata-only audit",
        },
    )
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "application/ld+json"}:
                raise MetadataRetrievalError("non_json_content_type")
            payload = response.read(max_bytes + 1)
    except MetadataRetrievalError:
        raise
    except HTTPError as exc:
        raise MetadataRetrievalError(f"http_status_{exc.code}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise MetadataRetrievalError("network_unavailable") from exc
    if len(payload) > max_bytes:
        raise MetadataRetrievalError("response_too_large")
    return payload, content_type


def _decode_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetadataRetrievalError("invalid_json_response") from exc
    if not isinstance(value, dict):
        raise MetadataRetrievalError("json_object_required")
    return value


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, list):
        if len(value) != 1 or not isinstance(value[0], str):
            return None
        return value[0]
    return value if isinstance(value, str) else None


def _retain_dataset(value: Mapping[str, Any]) -> dict[str, Any]:
    retained = {key: copy.deepcopy(value.get(key)) for key in DATASET_FIELDS}
    retained["title"] = _scalar_text(retained["title"])
    retained["doi"] = _scalar_text(retained["doi"])
    return retained


def _retain_file_set(value: Mapping[str, Any]) -> dict[str, Any]:
    retained = {key: copy.deepcopy(value.get(key)) for key in FILE_SET_FIELDS}
    retained["title"] = _scalar_text(retained["title"])
    return retained


def _validate_dataset_identity(dataset: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if dataset.get("id") != DATASET_ID:
        issues.append("dataset_id_mismatch")
    doi = str(dataset.get("doi") or "").replace("https://doi.org/", "").strip()
    if doi != DATASET_DOI:
        issues.append("dataset_doi_mismatch")
    if dataset.get("title") != DATASET_TITLE:
        issues.append("dataset_title_mismatch")
    if dataset.get("total_file_count") != 2:
        issues.append("top_level_file_count_mismatch")
    ids = dataset.get("file_set_ids")
    if not isinstance(ids, list) or len(ids) != 2:
        issues.append("file_set_ids_missing_or_count_mismatch")
    elif len(set(ids)) != len(ids):
        issues.append("duplicate_file_set_ids")
    elif any(not isinstance(item, str) or not re.fullmatch(r"[a-z0-9]{9}", item) for item in ids):
        issues.append("malformed_file_set_id")
    return issues


def _metadata_completeness(file_sets: list[Mapping[str, Any]]) -> dict[str, Any]:
    def all_present(key: str) -> bool:
        return all(item.get(key) not in (None, "", []) for item in file_sets)
    return {
        "file_set_ids_recovered": len(file_sets) == 2,
        "labels_recovered": all_present("label"),
        "sizes_recovered": all(isinstance(item.get("file_size"), int) and item["file_size"] >= 0 for item in file_sets),
        "mime_types_recovered": all_present("mime_type"),
        "repository_checksums_recovered": all(item.get("checksum_algorithm") not in (None, "") and item.get("checksum_value") not in (None, "") for item in file_sets),
        "original_checksums_recovered": all(item.get("original_checksum") not in (None, "") for item in file_sets),
    }


def _base_result(contract_checksum: str, evidence_checksum: str, preservation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "artifact_kind": "battery_michigan_formation_deepblue_metadata_retrieval_compact_summary",
        "package_id": PACKAGE_ID,
        "case_study_id": "battery_michigan_formation_deepblue_metadata_retrieval",
        "contract_id": CONTRACT_ID,
        "contract_checksum": contract_checksum,
        "api_evidence_id": EVIDENCE_ID,
        "api_evidence_checksum": evidence_checksum,
        "preservation_checks": dict(preservation),
        "dataset_endpoint": DATASET_URL,
        "credentials_read": False,
        "credentials_sent": False,
        "provider_dataset_downloaded": False,
        "provider_file_payload_read": False,
        "local_archive_read": False,
        "local_csv_payload_read": False,
        "raw_response_retained": False,
        "personal_contact_metadata_retained": False,
        "filename_metadata_inferred": False,
        "command_semantics_inferred": False,
        "missing_metadata_inferred": False,
        "candidate_admitted": False,
        "cross_cohort_comparability_promoted": False,
        "cohort_merge_performed": False,
        "model_trained": False,
        "model_evaluated": False,
        "metrics_recomputed": False,
        "source_mutation_performed": False,
    }


def _pending_result(contract_checksum: str, evidence_checksum: str, preservation: Mapping[str, Any]) -> dict[str, Any]:
    result = _base_result(contract_checksum, evidence_checksum, preservation)
    result.update({
        "retrieval_status": "pending_local_metadata_retrieval",
        "network_call_count": 0,
        "network_called": False,
        "dataset_response": None,
        "file_set_records": [],
        "metadata_completeness": {
            "file_set_ids_recovered": False,
            "labels_recovered": False,
            "sizes_recovered": False,
            "mime_types_recovered": False,
            "repository_checksums_recovered": False,
            "original_checksums_recovered": False,
        },
        "decision": {
            "provider_dataset_identity": "documented_not_api_verified",
            "top_level_file_set_metadata": "pending",
            "internal_provider_manifest": "not_established",
            "local_archive_binding": "not_established",
            "provider_to_standardized_row_binding": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": "pending_local_metadata_retrieval",
        },
        "scientific_closeout": {
            "status": "inconclusive",
            "result": "metadata_retrieval_not_run",
            "strongest_evidence": "The official Deep Blue REST API documents dataset and file-set metadata fields, but dataset-specific JSON has not yet been retained.",
            "primary_limitation": "No dataset-specific API response has been reviewed.",
            "suitable_for": ["software contract validation"],
            "unsuitable_for": ["provider-to-local binding", "cross-cohort comparability", "predictive validation", "model training or evaluation"],
        },
    })
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


FetchFn = Callable[[str, int, int], tuple[bytes, str]]


def _actual_result(contract: Mapping[str, Any], evidence: Mapping[str, Any], preservation: Mapping[str, Any], fetch: FetchFn) -> dict[str, Any]:
    network = contract["network_contract"]
    dataset_raw, dataset_content_type = fetch(DATASET_URL, int(network["max_dataset_response_bytes"]), int(network["timeout_seconds"]))
    dataset_sha = hashlib.sha256(dataset_raw).hexdigest()
    dataset_json = _decode_json(dataset_raw)
    dataset = _retain_dataset(dataset_json)
    issues = _validate_dataset_identity(dataset)
    if issues:
        raise MetadataRetrievalError(",".join(issues))
    embedded = dataset_json.get("file_sets")
    file_set_ids = dataset["file_set_ids"]
    file_sets: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    call_count = 1
    if isinstance(embedded, list) and len(embedded) == len(file_set_ids):
        by_id = {item.get("id"): item for item in embedded if isinstance(item, dict) and isinstance(item.get("id"), str)}
        if set(by_id) != set(file_set_ids):
            raise MetadataRetrievalError("embedded_file_set_identity_mismatch")
        for file_set_id in file_set_ids:
            file_sets.append(_retain_file_set(by_id[file_set_id]))
            audits.append({"file_set_id": file_set_id, "record_source": "embedded_dataset_response", "response_bytes": None, "response_sha256": dataset_sha, "content_type": dataset_content_type})
    else:
        if len(file_set_ids) > int(network["max_file_set_requests"]):
            raise MetadataRetrievalError("file_set_request_bound_exceeded")
        for file_set_id in file_set_ids:
            url = FILE_SET_URL_TEMPLATE.format(file_set_id=file_set_id)
            _safe_url(url, file_set_id=file_set_id)
            raw, content_type = fetch(url, int(network["max_file_set_response_bytes"]), int(network["timeout_seconds"]))
            call_count += 1
            retained = _retain_file_set(_decode_json(raw))
            if retained.get("id") != file_set_id:
                raise MetadataRetrievalError("file_set_identity_mismatch")
            file_sets.append(retained)
            audits.append({"file_set_id": file_set_id, "record_source": "file_set_endpoint", "response_bytes": len(raw), "response_sha256": hashlib.sha256(raw).hexdigest(), "content_type": content_type})
    if [item.get("id") for item in file_sets] != file_set_ids:
        raise MetadataRetrievalError("file_set_order_or_identity_mismatch")
    completeness = _metadata_completeness(file_sets)
    top_level_complete = all(completeness[key] for key in ("file_set_ids_recovered", "labels_recovered", "sizes_recovered", "mime_types_recovered", "repository_checksums_recovered"))
    overall = "top_level_file_set_metadata_recovered_internal_manifest_not_established" if top_level_complete else "top_level_file_set_metadata_partial_internal_manifest_not_established"
    result = _base_result(canonical_checksum(contract), canonical_checksum(evidence), preservation)
    result.update({
        "retrieval_status": "succeeded",
        "network_call_count": call_count,
        "network_called": True,
        "dataset_response": {"retained_metadata": dataset, "response_bytes": len(dataset_raw), "response_sha256": dataset_sha, "content_type": dataset_content_type},
        "file_set_records": file_sets,
        "file_set_response_audits": audits,
        "metadata_completeness": completeness,
        "decision": {
            "provider_dataset_identity": "api_verified",
            "top_level_file_set_metadata": "recovered" if top_level_complete else "partially_recovered",
            "internal_provider_manifest": "not_established",
            "local_archive_binding": "not_established",
            "provider_to_standardized_row_binding": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": overall,
        },
        "scientific_closeout": {
            "status": "diagnostic",
            "result": overall,
            "strongest_evidence": "Payload-free official API metadata recovered stable top-level file-set identities and available preservation fields.",
            "primary_limitation": "Top-level file-set metadata does not reveal the internal provider file manifest or establish provider-to-local archive binding.",
            "suitable_for": ["top-level provider artifact identity review", "provider-to-local binding contract design"],
            "unsuitable_for": ["internal file inventory claims", "command or cycle-row binding", "cross-cohort comparability", "predictive validation", "model training or evaluation"],
        },
    })
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def validate_result(value: Mapping[str, Any], *, allow_pending: bool = True) -> None:
    if value.get("schema_version") != VERSION or value.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported metadata result")
    if canonical_checksum(value) != value.get("deterministic_result_checksum"):
        raise ValueError("metadata result checksum mismatch")
    for flag in PROHIBITED_TRUE_FLAGS:
        if value.get(flag) is not False:
            raise ValueError(f"prohibited result flag promoted: {flag}")
    status = value.get("retrieval_status")
    decision = value.get("decision", {})
    if status == "pending_local_metadata_retrieval":
        if not allow_pending:
            raise ValueError("pending result is not an executed retrieval")
        if value.get("network_called") is not False or value.get("network_call_count") != 0:
            raise ValueError("pending result network boundary changed")
        if decision.get("overall_status") != "pending_local_metadata_retrieval":
            raise ValueError("pending decision changed")
        return
    if status != "succeeded":
        raise ValueError("unsupported retrieval status")
    if value.get("network_called") is not True:
        raise ValueError("successful retrieval must record network access")
    if not 1 <= int(value.get("network_call_count", 0)) <= 3:
        raise ValueError("network call count outside contract")
    allowed_overall = {"top_level_file_set_metadata_recovered_internal_manifest_not_established", "top_level_file_set_metadata_partial_internal_manifest_not_established"}
    if decision.get("overall_status") not in allowed_overall:
        raise ValueError("scientific decision changed")
    if decision.get("internal_provider_manifest") != "not_established":
        raise ValueError("internal manifest claim was promoted")
    if value.get("scientific_closeout", {}).get("status") != "diagnostic":
        raise ValueError("scientific closeout changed")
    dataset = value.get("dataset_response", {}).get("retained_metadata", {})
    if _validate_dataset_identity(dataset):
        raise ValueError("retained dataset identity invalid")
    file_sets = value.get("file_set_records")
    if not isinstance(file_sets, list) or len(file_sets) != 2:
        raise ValueError("file-set record count changed")
    if set(dataset) != set(DATASET_FIELDS):
        raise ValueError("unapproved dataset metadata retained")
    if any(set(item) != set(FILE_SET_FIELDS) for item in file_sets):
        raise ValueError("unapproved file-set metadata retained")


def execute(config: Mapping[str, Any], *, repo_root: str | Path = ".", fetch: FetchFn | None = None, run_network: bool = False, write_outputs: bool = False) -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config["contract_path"]))
    evidence = _json(repo_path(repo_root, config["api_evidence_path"]))
    upstream = _json(repo_path(repo_root, config["v2_6_12_provider_package_summary_path"]))
    validate_contract(contract)
    validate_api_evidence(evidence)
    preservation = verify_upstream(upstream)
    result = _actual_result(contract, evidence, preservation, fetch or _default_fetch) if run_network else _pending_result(canonical_checksum(contract), canonical_checksum(evidence), preservation)
    validate_result(result)
    if write_outputs:
        output_root = repo_path(repo_root, config["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        (output_root / "deepblue_metadata_result.json").write_text(text, encoding="utf-8")
        repo_path(repo_root, config["tracked_summary_path"]).write_text(text, encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v2.6.13 Deep Blue payload-free file-set metadata retrieval gate")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    sub.add_parser("run")
    validate = sub.add_parser("validate")
    validate.add_argument("result_path")
    validate.add_argument("--require-executed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            value = _json(repo_path(args.repo_root, args.result_path))
            validate_result(value, allow_pending=not args.require_executed)
            payload = {"valid": True, "retrieval_status": value["retrieval_status"], "deterministic_result_checksum": value["deterministic_result_checksum"]}
        else:
            config = load_config(args.config, repo_root=args.repo_root)
            payload = execute(config, repo_root=args.repo_root, run_network=args.command == "run", write_outputs=args.command == "run")
    except MetadataRetrievalError as exc:
        payload = {"valid": False, "retrieval_status": "failed", "error_category": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json else json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json else json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
