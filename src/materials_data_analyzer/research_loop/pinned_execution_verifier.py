"""Execution-time verifiers bound to the exact authorized request snapshot.

The public typed verifiers intentionally re-open the recorded request pathname for
long-lived provenance checks. During an authorized execution, however, that live
pathname is outside the transaction and may be replaced after authorization. These
version-specific verifiers preserve every substantive typed verification while
binding the *current* action request to the in-memory snapshot that was authorized
and executed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import nasa_audit_executor as audit
from . import nasa_external_data_requirement_action as external
from . import nasa_protocol_stratification_action as protocol
from . import nasa_target_reference_action as target


def _pinned_record(
    report: Mapping[str, Any],
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
    action_type: str,
    error_type: type[Exception],
) -> dict[str, Any]:
    recorded = report.get("request")
    expected = dict(request_record)
    if not isinstance(recorded, dict) or recorded != expected:
        raise error_type("action report request binding does not match the pinned request")
    if expected.get("path") != str(request_path):
        raise error_type("pinned request record path does not match request_path")
    if request_value.get("action_type") != action_type:
        raise error_type("pinned request action_type does not match the action report")
    if request_value.get("action_id") != report.get("action_id"):
        raise error_type("pinned request action_id does not match the action report")
    return expected


def verify_nasa_audit_action_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-verify one audit without re-opening its mutable request pathname."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = audit._load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != audit.REPORT_SCHEMA_VERSION:
        raise audit.NasaAuditActionError("invalid NASA audit action report schema")
    if report.get("action_type") != audit.ACTION_TYPE:
        raise audit.NasaAuditActionError("action report has the wrong action_type")
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise audit.NasaAuditActionError("action report has an invalid execution_status")
    _pinned_record(
        report,
        request_value=request_value,
        request_path=request_path,
        request_record=request_record,
        action_type=audit.ACTION_TYPE,
        error_type=audit.NasaAuditActionError,
    )

    for record in report.get("immutable_inputs", []):
        if audit._file_record(Path(record["path"])) != record:
            raise audit.NasaAuditActionError(
                f"immutable input no longer matches the action report: {record['path']}"
            )
    for record in report.get("outputs", []):
        current = audit._file_record(Path(record["path"]))
        expected = {key: record[key] for key in ("path", "bytes", "sha256")}
        if current != expected:
            raise audit.NasaAuditActionError(
                f"action output no longer matches the report: {record['path']}"
            )

    research_run = Path(report["research_run"])
    state = audit.load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise audit.NasaAuditActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = audit._file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise audit.NasaAuditActionError(
            "research ledger does not checksum-bind the current action report"
        )
    return {
        "valid": True,
        "execution_status": status,
        "action_id": report["action_id"],
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
    }


def verify_nasa_target_reference_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute target-reference outputs against the pinned current request."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = target._load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != target.REPORT_SCHEMA_VERSION:
        raise target.NasaTargetReferenceActionError(
            "invalid target-reference action report schema"
        )
    if report.get("action_type") != target.ACTION_TYPE:
        raise target.NasaTargetReferenceActionError("action report has the wrong action_type")
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise target.NasaTargetReferenceActionError(
            "action report has an invalid execution_status"
        )
    _pinned_record(
        report,
        request_value=request_value,
        request_path=request_path,
        request_record=request_record,
        action_type=target.ACTION_TYPE,
        error_type=target.NasaTargetReferenceActionError,
    )
    for record in report.get("immutable_inputs", []):
        if target._file_record(Path(record["path"])) != record:
            raise target.NasaTargetReferenceActionError(
                f"immutable input no longer matches the report: {record['path']}"
            )
    audit_record = report.get("prior_audit_report")
    if not isinstance(audit_record, dict) or target._file_record(
        Path(audit_record["path"])
    ) != audit_record:
        raise target.NasaTargetReferenceActionError(
            "prior audit report no longer matches the target-reference report"
        )
    audit.verify_nasa_audit_action_report(audit_record["path"])

    if status == "completed":
        result = target._compute(Path(report["analysis_run"]))
        if report.get("summary") != result["summary"]:
            raise target.NasaTargetReferenceActionError(
                "reported target-reference summary is not reproducible"
            )
        with tempfile.TemporaryDirectory(
            prefix="mda-target-reference-verify-"
        ) as temporary:
            expected_root = Path(temporary)
            expected_paths = target._write_outputs(expected_root, result)
            expected = {
                path.relative_to(expected_root).as_posix(): path
                for path in expected_paths
            }
            records = report.get("outputs", [])
            if not isinstance(records, list) or len(records) != len(expected):
                raise target.NasaTargetReferenceActionError(
                    "action report does not bind every required output"
                )
            for record in records:
                relative = str(record["relative_path"])
                source = expected.get(relative)
                current_path = Path(record["path"])
                current = target._file_record(current_path)
                recorded = {
                    key: record[key] for key in ("path", "bytes", "sha256")
                }
                if source is None or current != recorded:
                    raise target.NasaTargetReferenceActionError(
                        f"action output no longer matches the report: {relative}"
                    )
                if current_path.read_bytes() != source.read_bytes():
                    raise target.NasaTargetReferenceActionError(
                        f"action output is not reproducible from source inputs: {relative}"
                    )

    research_run = Path(report["research_run"])
    state = target.load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise target.NasaTargetReferenceActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = target._file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise target.NasaTargetReferenceActionError(
            "research ledger does not checksum-bind the current action report"
        )
    return {
        "valid": True,
        "execution_status": status,
        "action_id": report["action_id"],
        "outcome": report.get("outcome"),
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
    }


def verify_nasa_protocol_stratification_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute protocol outputs against the pinned current request."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = protocol._load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != protocol.REPORT_SCHEMA_VERSION:
        raise protocol.NasaProtocolStratificationActionError(
            "invalid protocol-stratification action report schema"
        )
    if report.get("action_type") != protocol.ACTION_TYPE:
        raise protocol.NasaProtocolStratificationActionError(
            "action report has the wrong action_type"
        )
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise protocol.NasaProtocolStratificationActionError(
            "action report has an invalid execution_status"
        )
    _pinned_record(
        report,
        request_value=request_value,
        request_path=request_path,
        request_record=request_record,
        action_type=protocol.ACTION_TYPE,
        error_type=protocol.NasaProtocolStratificationActionError,
    )
    for record in report.get("immutable_inputs", []):
        if protocol._file_record(Path(record["path"])) != record:
            raise protocol.NasaProtocolStratificationActionError(
                f"immutable input no longer matches the report: {record['path']}"
            )
    audit_record = report.get("prior_audit_report")
    if not isinstance(audit_record, dict) or protocol._file_record(
        Path(audit_record["path"])
    ) != audit_record:
        raise protocol.NasaProtocolStratificationActionError(
            "prior audit report no longer matches the protocol report"
        )
    audit.verify_nasa_audit_action_report(audit_record["path"])
    target_record = report.get("prior_target_reference_report")
    if target_record is not None:
        if not isinstance(target_record, dict) or protocol._file_record(
            Path(target_record["path"])
        ) != target_record:
            raise protocol.NasaProtocolStratificationActionError(
                "prior target-reference report no longer matches the protocol report"
            )
        target_result = target.verify_nasa_target_reference_report(target_record["path"])
        if target_result.get("outcome") != protocol._REQUIRED_TARGET_OUTCOME:
            raise protocol.NasaProtocolStratificationActionError(
                "verified target-reference outcome is not stable"
            )

    if status == "completed":
        result = protocol._compute(
            Path(report["import_run"]), Path(report["analysis_run"])
        )
        if report.get("summary") != result["summary"]:
            raise protocol.NasaProtocolStratificationActionError(
                "reported protocol summary is not reproducible"
            )
        with tempfile.TemporaryDirectory(prefix="mda-protocol-verify-") as temporary:
            expected_root = Path(temporary)
            expected_paths = protocol._write_outputs(expected_root, result)
            expected = {
                path.relative_to(expected_root).as_posix(): path
                for path in expected_paths
            }
            records = report.get("outputs", [])
            if not isinstance(records, list) or len(records) != len(expected):
                raise protocol.NasaProtocolStratificationActionError(
                    "action report does not bind every required output"
                )
            for record in records:
                relative = str(record["relative_path"])
                source = expected.get(relative)
                current_path = Path(record["path"])
                current = protocol._file_record(current_path)
                recorded = {
                    key: record[key] for key in ("path", "bytes", "sha256")
                }
                if source is None or current != recorded:
                    raise protocol.NasaProtocolStratificationActionError(
                        f"action output no longer matches the report: {relative}"
                    )
                if current_path.read_bytes() != source.read_bytes():
                    raise protocol.NasaProtocolStratificationActionError(
                        f"action output is not reproducible from source inputs: {relative}"
                    )

    research_run = Path(report["research_run"])
    state = protocol.load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise protocol.NasaProtocolStratificationActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = protocol._file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise protocol.NasaProtocolStratificationActionError(
            "research ledger does not checksum-bind the current action report"
        )
    return {
        "valid": True,
        "execution_status": status,
        "action_id": report["action_id"],
        "outcome": report.get("outcome"),
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
    }


def verify_nasa_external_data_requirement_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute external-data requirement evidence using the pinned request."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = external._load_json(report_path)
    if not isinstance(report, dict):
        raise external.NasaExternalDataRequirementActionError(
            "action report must be a JSON object"
        )
    if report.get("schema_version") != external.REPORT_SCHEMA_VERSION:
        raise external.NasaExternalDataRequirementActionError(
            "invalid external-data action report schema"
        )
    if report.get("execution_status") != "completed":
        raise external.NasaExternalDataRequirementActionError(
            "external-data action report must be completed"
        )
    if report.get("action_type") != external.ACTION_TYPE:
        raise external.NasaExternalDataRequirementActionError(
            "action report has the wrong action_type"
        )
    if report.get("stop_reason") != external.STOP_REASON:
        raise external.NasaExternalDataRequirementActionError(
            "action report has the wrong terminal reason"
        )
    if report.get("verification") != external._VERIFICATION_FLAGS:
        raise external.NasaExternalDataRequirementActionError(
            "action report verification flags do not match the fixed contract"
        )
    _pinned_record(
        report,
        request_value=request_value,
        request_path=request_path,
        request_record=request_record,
        action_type=external.ACTION_TYPE,
        error_type=external.NasaExternalDataRequirementActionError,
    )
    request = external._validate_request(request_value, base=request_path.parent)
    if request["action_id"] != report.get("action_id"):
        raise external.NasaExternalDataRequirementActionError(
            "action report action_id does not match the request"
        )
    expected_report_path = (
        request["research_run"]
        / "actions"
        / request["action_id"]
        / external.ACTION_REPORT_FILENAME
    ).resolve(strict=True)
    if report_path != expected_report_path:
        raise external.NasaExternalDataRequirementActionError(
            "action report path does not match the request and research run"
        )
    if report.get("research_run") != str(request["research_run"]):
        raise external.NasaExternalDataRequirementActionError(
            "action report research_run does not match the request"
        )

    registry = external.load_action_registry(
        request["registry"], repository_root=request["repository_root"]
    )
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise external.NasaExternalDataRequirementActionError(
            "action registry no longer matches the request"
        )
    contract = external.describe_action(registry, external.ACTION_TYPE)
    expected_registry = {
        "registry_id": registry["registry_id"],
        "registry_path": registry["registry_path"],
        "registry_sha256": registry["registry_sha256"],
    }
    if report.get("registry") != expected_registry:
        raise external.NasaExternalDataRequirementActionError(
            "action report registry binding is invalid"
        )
    if report.get("action_version") != contract["version"]:
        raise external.NasaExternalDataRequirementActionError(
            "action report version does not match the registry"
        )
    if report.get("cost_units") != contract["cost_units"]:
        raise external.NasaExternalDataRequirementActionError(
            "action report cost does not match the registry"
        )

    state = external.load_research_state(request["research_run"])
    requirement, source_paths = external._build_requirement(state)
    expected_inputs = [external._file_record(path) for path in source_paths]
    if report.get("immutable_inputs") != expected_inputs:
        raise external.NasaExternalDataRequirementActionError(
            "immutable input bindings do not match the verified prerequisite evidence"
        )
    if report.get("requirement") != requirement:
        raise external.NasaExternalDataRequirementActionError(
            "reported external-data requirement is not reproducible"
        )
    if report.get("outcome") != requirement["outcome"]:
        raise external.NasaExternalDataRequirementActionError(
            "action report outcome does not match the recomputed requirement"
        )

    output_record = report.get("output")
    if not isinstance(output_record, dict):
        raise external.NasaExternalDataRequirementActionError(
            "action report is missing output binding"
        )
    if output_record.get("relative_path") != external.OUTPUT_RELATIVE_PATH:
        raise external.NasaExternalDataRequirementActionError(
            "action report output relative path is invalid"
        )
    output_path = Path(output_record.get("path", "")).resolve(strict=True)
    expected_output_path = (
        request["research_run"]
        / "actions"
        / request["action_id"]
        / external.OUTPUT_RELATIVE_PATH
    ).resolve(strict=True)
    if output_path != expected_output_path:
        raise external.NasaExternalDataRequirementActionError(
            "action output path does not match the request and research run"
        )
    recorded_file = {
        key: output_record[key] for key in ("path", "bytes", "sha256")
    }
    if external._file_record(output_path) != recorded_file:
        raise external.NasaExternalDataRequirementActionError(
            "requirement output no longer matches the report"
        )
    if external._load_json(output_path) != requirement:
        raise external.NasaExternalDataRequirementActionError(
            "requirement output is not reproducible"
        )

    matching = [
        recorded
        for recorded in state["actions"]
        if recorded["action_id"] == report["action_id"]
    ]
    if len(matching) != 1:
        raise external.NasaExternalDataRequirementActionError(
            "research ledger must contain exactly one matching action"
        )
    ledger_action = matching[0]
    if (
        ledger_action["action_type"] != external.ACTION_TYPE
        or ledger_action["status"] != "completed"
        or ledger_action["cost_units"] != contract["cost_units"]
    ):
        raise external.NasaExternalDataRequirementActionError(
            "research ledger action does not match the verified action contract"
        )
    expected_artifacts = [
        external._file_record(report_path),
        external._file_record(output_path),
    ]
    if ledger_action.get("artifacts") != expected_artifacts:
        raise external.NasaExternalDataRequirementActionError(
            "research ledger artifacts do not match the action report and output"
        )
    if state["status"] != "stopped":
        raise external.NasaExternalDataRequirementActionError(
            "research loop was not stopped after requirement generation"
        )
    stop = state.get("stop")
    if not isinstance(stop, dict) or stop.get("reason_code") != external.STOP_REASON:
        raise external.NasaExternalDataRequirementActionError(
            "research loop has the wrong terminal reason"
        )
    return {
        "valid": True,
        "execution_status": "completed",
        "action_id": report["action_id"],
        "outcome": report["outcome"],
        "research_id": state["research_id"],
        "research_status": state["status"],
        "stop_reason": external.STOP_REASON,
        "ledger_sha256": state["ledger_sha256"],
        "action_report": str(report_path),
    }


__all__ = [
    "verify_nasa_audit_action_report_pinned",
    "verify_nasa_target_reference_report_pinned",
    "verify_nasa_protocol_stratification_report_pinned",
    "verify_nasa_external_data_requirement_report_pinned",
]
