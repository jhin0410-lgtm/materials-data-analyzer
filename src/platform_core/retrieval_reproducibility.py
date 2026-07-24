"""Bounded retrieval-reproducibility evidence audit.

The audit distinguishes exact bytes, canonical logical content, retrieval
metadata, and missing paired evidence. It reads only allowlisted compact JSON
artifacts by default and never performs retrieval, migration, model execution,
or credential access.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Sequence

from .external_source_compatibility import (
    BATTERY_ARTIFACT_KIND,
    COMPATIBILITY_SUMMARY_SCHEMA_ID,
    MATERIALS_ARTIFACT_KIND,
    adapt_tracked_external_source_artifact,
    build_compatibility_adapter_registry,
    select_compatibility_adapter,
    validate_compatibility_summary,
)
from .external_source_contracts import (
    _validate_relative_path,
    _validate_safe_text,
    canonical_json_sha256,
    raw_bytes_sha256,
)


RETRIEVAL_REPRODUCIBILITY_VERSION = "2.5.2"
RETRIEVAL_SCHEMA_VERSION = "1"
EVIDENCE_SCHEMA_ID = "retrieval_reproducibility_evidence_v1"
COMPARISON_SCHEMA_ID = "retrieval_reproducibility_comparison_v1"
SUMMARY_SCHEMA_ID = "retrieval_reproducibility_summary_v1"
DEFAULT_CONFIG_PATH = "configs/examples/retrieval_reproducibility_audit.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_5_retrieval_reproducibility"
TRACKED_SUMMARY_PATH = "data/processed/retrieval_reproducibility_audit_summary_v1.json"
COMPATIBILITY_SUMMARY_PATH = "data/processed/external_source_compatibility_audit_summary_v1.json"

ASSESSMENT_STATUSES = (
    "exact_reproducible",
    "logically_reproducible",
    "content_changed",
    "metadata_mismatch",
    "not_comparable",
    "insufficient_evidence",
)

RETRIEVAL_METADATA_FIELDS = (
    "retrieval_timestamp",
    "client_name",
    "client_version",
    "endpoint_or_method",
    "query_or_parameters",
    "requested_entity_identifiers",
    "response_count",
    "input_schema_version",
    "transformation_boundary",
)

_IDENTITY_FIELDS = (
    "source_system_ref",
    "dataset_ref",
    "distribution_ref",
    "snapshot_ref",
)

_COMPARABLE_METADATA_FIELDS = tuple(
    field for field in RETRIEVAL_METADATA_FIELDS if field != "retrieval_timestamp"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _strict_mapping(payload: Mapping[str, Any], allowed: set[str], location: str) -> None:
    unknown = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if unknown:
        raise ValueError(f"{location} contains unknown fields: {unknown}")
    if missing:
        raise ValueError(f"{location} is missing required fields: {missing}")


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable lowercase identifier")
    return value


def _version_parts(value: str) -> tuple[int, ...]:
    normalized = value.removeprefix("v")
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid schema version: {value}")
    return tuple(int(part) for part in parts)


def _validate_exact_version(actual: str, expected: str, record_type: str) -> None:
    if actual == expected:
        return
    if _version_parts(actual) > _version_parts(expected):
        raise ValueError(
            f"unsupported future version for {record_type}: {actual}; "
            f"supported version is {expected}"
        )
    raise ValueError(
        f"unsupported source version for {record_type}: {actual}; "
        f"supported version is {expected}"
    )


def _validate_sha256(value: str | None, field_name: str, *, required: bool = False) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256")


def _ordered_unique(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if result != tuple(sorted(set(result))):
        raise ValueError(f"{field_name} must be unique and deterministic")
    return result


@dataclass(frozen=True)
class RetrievalEvidenceRecord:
    schema_id: str
    schema_version: str
    evidence_id: str
    case_study_id: str
    artifact_role: str
    artifact_kind: str
    artifact_version: str
    artifact_ref: str
    source_system_ref: str | None
    dataset_ref: str | None
    distribution_ref: str | None
    snapshot_ref: str | None
    retrieval_event_ref: str | None
    artifact_raw_bytes_sha256: str | None
    canonical_logical_sha256: str | None
    source_distribution_raw_sha256: str | None
    retrieval_metadata: Mapping[str, Any]
    known_missing_metadata: tuple[str, ...]
    evidence_field_sources: Mapping[str, str]
    independent_retrieval_event: bool
    source_input_mutated: bool
    limitations: tuple[str, ...]
    record_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.schema_id != EVIDENCE_SCHEMA_ID:
            raise ValueError("unsupported retrieval evidence schema_id")
        _validate_exact_version(
            self.schema_version, RETRIEVAL_SCHEMA_VERSION, EVIDENCE_SCHEMA_ID
        )
        for name in ("evidence_id", "case_study_id", "artifact_role", "artifact_kind"):
            _identifier(getattr(self, name), name)
        _version_parts(self.artifact_version)
        _validate_relative_path(self.artifact_ref, "artifact_ref")
        if not self.artifact_ref.endswith(".json"):
            raise ValueError("retrieval evidence artifact_ref must be a JSON artifact")
        if self.source_input_mutated:
            raise ValueError("retrieval evidence cannot report source mutation")
        _strict_mapping(
            self.retrieval_metadata,
            set(RETRIEVAL_METADATA_FIELDS),
            "retrieval_metadata",
        )
        _ordered_unique(self.known_missing_metadata, "known_missing_metadata")
        _ordered_unique(self.limitations, "limitations")
        expected_sources = set(_IDENTITY_FIELDS) | {
            "artifact_ref",
            "artifact_version",
            "retrieval_event_ref",
            *RETRIEVAL_METADATA_FIELDS,
        }
        _strict_mapping(
            self.evidence_field_sources,
            expected_sources,
            "evidence_field_sources",
        )
        for field_name in (
            "artifact_raw_bytes_sha256",
            "canonical_logical_sha256",
            "source_distribution_raw_sha256",
        ):
            _validate_sha256(getattr(self, field_name), field_name)
        if not self.artifact_raw_bytes_sha256 and not self.canonical_logical_sha256:
            raise ValueError("retrieval evidence requires a raw or canonical checksum")
        if self.record_checksum_sha256 != canonical_json_sha256(
            self._payload_without_checksum()
        ):
            raise ValueError("retrieval evidence checksum mismatch")
        _validate_safe_text(self.to_dict(), "retrieval evidence")

    def _payload_without_checksum(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("record_checksum_sha256", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload_without_checksum(),
            "record_checksum_sha256": self.record_checksum_sha256,
        }

    @classmethod
    def create(cls, **values: Any) -> "RetrievalEvidenceRecord":
        return cls(
            record_checksum_sha256=canonical_json_sha256(values),
            **values,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RetrievalEvidenceRecord":
        _strict_mapping(
            payload,
            {field.name for field in fields(cls)},
            "RetrievalEvidenceRecord",
        )
        values = dict(payload)
        values["known_missing_metadata"] = tuple(values["known_missing_metadata"])
        values["limitations"] = tuple(values["limitations"])
        return cls(**values)


@dataclass(frozen=True)
class RetrievalComparisonResult:
    schema_id: str
    schema_version: str
    audit_id: str
    pair_id: str
    case_study_id: str
    left_evidence_id: str
    right_evidence_id: str
    comparison_eligible: bool
    source_identity_match: bool | None
    artifact_role_match: bool
    schema_version_compatible: bool
    raw_byte_match: bool | None
    canonical_logical_match: bool | None
    metadata_match: bool | None
    matched_metadata_fields: tuple[str, ...]
    mismatched_metadata_fields: tuple[str, ...]
    unresolved_metadata_fields: tuple[str, ...]
    blocked_comparison_reasons: tuple[str, ...]
    final_assessment: str
    claim_boundary: tuple[str, ...]
    software_validation_level: str
    scientific_evidence_level: str
    network_called: bool
    credentials_read: bool
    source_mutation_performed: bool
    model_executed: bool
    result_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.schema_id != COMPARISON_SCHEMA_ID:
            raise ValueError("unsupported retrieval comparison schema_id")
        _validate_exact_version(
            self.schema_version, RETRIEVAL_SCHEMA_VERSION, COMPARISON_SCHEMA_ID
        )
        for name in (
            "audit_id",
            "pair_id",
            "case_study_id",
            "left_evidence_id",
            "right_evidence_id",
        ):
            _identifier(getattr(self, name), name)
        if self.left_evidence_id == self.right_evidence_id:
            raise ValueError("same evidence cannot be used as a reproducibility pair")
        if self.final_assessment not in ASSESSMENT_STATUSES:
            raise ValueError(
                f"unregistered retrieval assessment status: {self.final_assessment}"
            )
        for name in (
            "matched_metadata_fields",
            "mismatched_metadata_fields",
            "unresolved_metadata_fields",
            "blocked_comparison_reasons",
            "claim_boundary",
        ):
            _ordered_unique(getattr(self, name), name)
        if any(
            (
                self.network_called,
                self.credentials_read,
                self.source_mutation_performed,
                self.model_executed,
            )
        ):
            raise ValueError("retrieval comparison crosses its read-only boundary")
        if self.result_checksum_sha256 != canonical_json_sha256(
            self._payload_without_checksum()
        ):
            raise ValueError("retrieval comparison checksum mismatch")
        _validate_safe_text(self.to_dict(), "retrieval comparison")

    def _payload_without_checksum(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("result_checksum_sha256", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload_without_checksum(),
            "result_checksum_sha256": self.result_checksum_sha256,
        }

    @classmethod
    def create(cls, **values: Any) -> "RetrievalComparisonResult":
        return cls(
            result_checksum_sha256=canonical_json_sha256(values),
            **values,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RetrievalComparisonResult":
        _strict_mapping(
            payload,
            {field.name for field in fields(cls)},
            "RetrievalComparisonResult",
        )
        values = dict(payload)
        for name in (
            "matched_metadata_fields",
            "mismatched_metadata_fields",
            "unresolved_metadata_fields",
            "blocked_comparison_reasons",
            "claim_boundary",
        ):
            values[name] = tuple(values[name])
        return cls(**values)


def build_retrieval_evidence_record(
    *,
    evidence_id: str,
    case_study_id: str,
    artifact_role: str,
    artifact_kind: str,
    artifact_version: str,
    artifact_ref: str,
    artifact_bytes: bytes,
    logical_payload: Mapping[str, Any],
    source_system_ref: str | None,
    dataset_ref: str | None,
    distribution_ref: str | None,
    snapshot_ref: str | None,
    retrieval_event_ref: str | None,
    source_distribution_raw_sha256: str | None,
    retrieval_metadata: Mapping[str, Any],
    known_missing_metadata: Sequence[str],
    evidence_field_sources: Mapping[str, str],
    independent_retrieval_event: bool,
    limitations: Sequence[str],
) -> RetrievalEvidenceRecord:
    """Create one checksum-bearing evidence record without changing its source."""

    parsed_payload = json.loads(artifact_bytes.decode("utf-8"))
    if not isinstance(parsed_payload, Mapping):
        raise ValueError("retrieval evidence artifact must contain a JSON object")
    if canonical_json_sha256(parsed_payload) != canonical_json_sha256(logical_payload):
        raise ValueError("artifact bytes and declared logical payload disagree")
    return RetrievalEvidenceRecord.create(
        schema_id=EVIDENCE_SCHEMA_ID,
        schema_version=RETRIEVAL_SCHEMA_VERSION,
        evidence_id=evidence_id,
        case_study_id=case_study_id,
        artifact_role=artifact_role,
        artifact_kind=artifact_kind,
        artifact_version=artifact_version,
        artifact_ref=artifact_ref,
        source_system_ref=source_system_ref,
        dataset_ref=dataset_ref,
        distribution_ref=distribution_ref,
        snapshot_ref=snapshot_ref,
        retrieval_event_ref=retrieval_event_ref,
        artifact_raw_bytes_sha256=raw_bytes_sha256(artifact_bytes),
        canonical_logical_sha256=canonical_json_sha256(logical_payload),
        source_distribution_raw_sha256=source_distribution_raw_sha256,
        retrieval_metadata=dict(retrieval_metadata),
        known_missing_metadata=tuple(sorted(set(known_missing_metadata))),
        evidence_field_sources=dict(sorted(evidence_field_sources.items())),
        independent_retrieval_event=independent_retrieval_event,
        source_input_mutated=False,
        limitations=tuple(sorted(set(limitations))),
    )


def _unresolved_fields(record: RetrievalEvidenceRecord) -> tuple[str, ...]:
    unresolved: set[str] = set(record.known_missing_metadata)
    for field_name in _IDENTITY_FIELDS:
        if getattr(record, field_name) is None:
            unresolved.add(field_name)
    if record.retrieval_event_ref is None:
        unresolved.add("retrieval_event_ref")
    for field_name in RETRIEVAL_METADATA_FIELDS:
        if record.retrieval_metadata[field_name] is None:
            unresolved.add(field_name)
    return tuple(sorted(unresolved))


def compare_retrieval_evidence(
    left: RetrievalEvidenceRecord,
    right: RetrievalEvidenceRecord,
    *,
    audit_id: str,
    pair_id: str,
) -> RetrievalComparisonResult:
    """Compare two independent, same-domain retrieval evidence records."""

    if left.case_study_id != right.case_study_id:
        raise ValueError("cross-domain retrieval comparison is prohibited")
    if left.evidence_id == right.evidence_id:
        raise ValueError("same evidence cannot be used as a reproducibility pair")
    if left.artifact_ref == right.artifact_ref:
        raise ValueError("same-file self-comparison is not reproducibility evidence")

    role_match = left.artifact_role == right.artifact_role
    schema_compatible = (
        left.artifact_kind == right.artifact_kind
        and left.artifact_version == right.artifact_version
    )
    blocked: list[str] = []
    if not role_match:
        blocked.append("artifact_role_mismatch")
    if not schema_compatible:
        blocked.append("artifact_schema_or_version_mismatch")
    if not left.independent_retrieval_event or not right.independent_retrieval_event:
        blocked.append("independent_retrieval_event_not_established")

    identity_matches: list[bool] = []
    matched: list[str] = []
    mismatched: list[str] = []
    unresolved = set(_unresolved_fields(left)) | set(_unresolved_fields(right))
    for field_name in _IDENTITY_FIELDS:
        left_value = getattr(left, field_name)
        right_value = getattr(right, field_name)
        if left_value is None or right_value is None:
            continue
        same = left_value == right_value
        identity_matches.append(same)
        (matched if same else mismatched).append(field_name)

    for field_name in _COMPARABLE_METADATA_FIELDS:
        left_value = left.retrieval_metadata[field_name]
        right_value = right.retrieval_metadata[field_name]
        if left_value is None or right_value is None:
            continue
        (matched if left_value == right_value else mismatched).append(field_name)

    left_timestamp = left.retrieval_metadata["retrieval_timestamp"]
    right_timestamp = right.retrieval_metadata["retrieval_timestamp"]
    if left_timestamp is not None and right_timestamp is not None:
        matched.append("retrieval_timestamp_available")

    comparison_eligible = role_match and schema_compatible
    source_identity_match = (
        all(identity_matches) if len(identity_matches) == len(_IDENTITY_FIELDS) else None
    )
    raw_match = (
        left.artifact_raw_bytes_sha256 == right.artifact_raw_bytes_sha256
        if left.artifact_raw_bytes_sha256 and right.artifact_raw_bytes_sha256
        else None
    )
    canonical_match = (
        left.canonical_logical_sha256 == right.canonical_logical_sha256
        if left.canonical_logical_sha256 and right.canonical_logical_sha256
        else None
    )
    metadata_match = None if unresolved else not mismatched

    if not comparison_eligible:
        assessment = "not_comparable"
    elif blocked or unresolved:
        assessment = "insufficient_evidence"
    elif mismatched or source_identity_match is False:
        assessment = "metadata_mismatch"
    elif canonical_match is False:
        assessment = "content_changed"
    elif raw_match is True:
        assessment = "exact_reproducible"
    elif canonical_match is True:
        assessment = "logically_reproducible"
    else:
        assessment = "insufficient_evidence"

    return RetrievalComparisonResult.create(
        schema_id=COMPARISON_SCHEMA_ID,
        schema_version=RETRIEVAL_SCHEMA_VERSION,
        audit_id=audit_id,
        pair_id=pair_id,
        case_study_id=left.case_study_id,
        left_evidence_id=left.evidence_id,
        right_evidence_id=right.evidence_id,
        comparison_eligible=comparison_eligible,
        source_identity_match=source_identity_match,
        artifact_role_match=role_match,
        schema_version_compatible=schema_compatible,
        raw_byte_match=raw_match,
        canonical_logical_match=canonical_match,
        metadata_match=metadata_match,
        matched_metadata_fields=tuple(sorted(set(matched))),
        mismatched_metadata_fields=tuple(sorted(set(mismatched))),
        unresolved_metadata_fields=tuple(sorted(unresolved)),
        blocked_comparison_reasons=tuple(sorted(set(blocked))),
        final_assessment=assessment,
        claim_boundary=(
            "checksum agreement is evidence only for the compared artifact role and declared retrieval conditions",
            "reproducibility does not establish source truth, scientific comparability, mechanism validity, independent validation, or production validation",
        ),
        software_validation_level="deterministic_bounded_comparison",
        scientific_evidence_level=(
            "paired_retrieval_evidence"
            if assessment
            in {
                "exact_reproducible",
                "logically_reproducible",
                "content_changed",
                "metadata_mismatch",
            }
            else "insufficient_or_ineligible_pair"
        ),
        network_called=False,
        credentials_read=False,
        source_mutation_performed=False,
        model_executed=False,
    )


@dataclass(frozen=True)
class TrackedEvidenceRequest:
    evidence_id: str
    case_study_id: str
    adapter_id: str
    artifact_kind: str
    input_path: str
    expected_version: str


@dataclass(frozen=True)
class OptionalEvidencePair:
    pair_id: str
    case_study_id: str
    left_evidence_path: str
    right_evidence_path: str


@dataclass(frozen=True)
class RetrievalReproducibilityConfig:
    schema_version: str
    audit_id: str
    evidence: tuple[TrackedEvidenceRequest, ...]
    compatibility_summary_path: str
    optional_comparison_pairs: tuple[OptionalEvidencePair, ...]
    network_enabled: bool
    source_mutation_enabled: bool
    model_execution_enabled: bool
    read_credentials: bool
    store_credentials: bool
    dry_run: bool
    output_root: str
    write_tracked_summary: bool
    tracked_summary_path: str


def _expected_evidence_requests() -> tuple[TrackedEvidenceRequest, ...]:
    rows = []
    for adapter in build_compatibility_adapter_registry():
        case_study_id = (
            "materials_project"
            if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND
            else "battery"
        )
        rows.append(
            TrackedEvidenceRequest(
                evidence_id=f"{case_study_id}_tracked_retrieval_evidence_v1",
                case_study_id=case_study_id,
                adapter_id=adapter.adapter_id,
                artifact_kind=adapter.input_artifact_kind,
                input_path=adapter.expected_input_path,
                expected_version=adapter.supported_input_version,
            )
        )
    return tuple(sorted(rows, key=lambda item: item.evidence_id))


def validate_retrieval_reproducibility_config(
    payload: Mapping[str, Any],
) -> RetrievalReproducibilityConfig:
    allowed = {
        "schema_version",
        "audit_id",
        "evidence",
        "compatibility_summary_path",
        "optional_comparison_pairs",
        "network_enabled",
        "source_mutation_enabled",
        "model_execution_enabled",
        "credential_policy",
        "dry_run",
        "output_root",
        "tracked_summary_policy",
    }
    _strict_mapping(payload, allowed, "retrieval reproducibility config")
    _validate_safe_text(payload, "retrieval reproducibility config")
    _validate_exact_version(
        str(payload["schema_version"]), RETRIEVAL_SCHEMA_VERSION, "retrieval_config"
    )
    audit_id = _identifier(payload["audit_id"], "audit_id")
    if payload["network_enabled"] is not False:
        raise ValueError("retrieval reproducibility audit must disable network access")
    if payload["source_mutation_enabled"] is not False:
        raise ValueError("retrieval reproducibility audit must disable source mutation")
    if payload["model_execution_enabled"] is not False:
        raise ValueError("retrieval reproducibility audit must disable model execution")
    if payload["dry_run"] is not True:
        raise ValueError("retrieval reproducibility audit must default to dry_run true")

    credential_policy = payload["credential_policy"]
    if not isinstance(credential_policy, Mapping):
        raise ValueError("credential_policy must be an object")
    _strict_mapping(
        credential_policy,
        {"read_credentials", "store_credentials"},
        "credential_policy",
    )
    if (
        credential_policy["read_credentials"] is not False
        or credential_policy["store_credentials"] is not False
    ):
        raise ValueError("retrieval reproducibility audit must not access credentials")

    output_root = str(payload["output_root"])
    _validate_relative_path(output_root, "output_root")
    if output_root != DEFAULT_OUTPUT_ROOT:
        raise ValueError(f"output_root must be the bounded local path {DEFAULT_OUTPUT_ROOT}")

    compatibility_path = str(payload["compatibility_summary_path"])
    _validate_relative_path(compatibility_path, "compatibility_summary_path")
    if compatibility_path != COMPATIBILITY_SUMMARY_PATH:
        raise ValueError("compatibility_summary_path is not allowlisted")

    tracked_policy = payload["tracked_summary_policy"]
    if not isinstance(tracked_policy, Mapping):
        raise ValueError("tracked_summary_policy must be an object")
    _strict_mapping(
        tracked_policy,
        {"write_tracked_summary", "path"},
        "tracked_summary_policy",
    )
    _validate_relative_path(
        str(tracked_policy["path"]), "tracked_summary_policy.path"
    )
    if tracked_policy["write_tracked_summary"] is not True:
        raise ValueError("tracked retrieval reproducibility summary must remain enabled")
    if tracked_policy["path"] != TRACKED_SUMMARY_PATH:
        raise ValueError("tracked retrieval summary path is not allowlisted")

    raw_evidence = payload["evidence"]
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("retrieval audit requires tracked evidence declarations")
    requests: list[TrackedEvidenceRequest] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_evidence):
        if not isinstance(item, Mapping):
            raise ValueError(f"evidence[{index}] must be an object")
        _strict_mapping(
            item,
            {
                "evidence_id",
                "case_study_id",
                "adapter_id",
                "artifact_kind",
                "input_path",
                "expected_version",
            },
            f"evidence[{index}]",
        )
        request = TrackedEvidenceRequest(
            evidence_id=_identifier(item["evidence_id"], f"evidence[{index}].evidence_id"),
            case_study_id=_identifier(
                item["case_study_id"], f"evidence[{index}].case_study_id"
            ),
            adapter_id=_identifier(item["adapter_id"], f"evidence[{index}].adapter_id"),
            artifact_kind=_identifier(
                item["artifact_kind"], f"evidence[{index}].artifact_kind"
            ),
            input_path=str(item["input_path"]),
            expected_version=str(item["expected_version"]),
        )
        _validate_relative_path(request.input_path, f"evidence[{index}].input_path")
        adapter = select_compatibility_adapter(
            request.artifact_kind,
            request.expected_version,
            adapter_id=request.adapter_id,
        )
        expected_case = (
            "materials_project"
            if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND
            else "battery"
        )
        if request.input_path != adapter.expected_input_path:
            raise ValueError(f"evidence[{index}].input_path is not registered")
        if request.case_study_id != expected_case:
            raise ValueError(f"evidence[{index}] case-study and adapter mismatch")
        if request.evidence_id in seen_ids:
            raise ValueError(f"duplicate evidence_id: {request.evidence_id}")
        seen_ids.add(request.evidence_id)
        requests.append(request)
    if tuple(sorted(requests, key=lambda item: item.evidence_id)) != _expected_evidence_requests():
        raise ValueError("retrieval audit requires the exact registered tracked evidence set")

    raw_pairs = payload["optional_comparison_pairs"]
    if not isinstance(raw_pairs, list):
        raise ValueError("optional_comparison_pairs must be a list")
    pairs: list[OptionalEvidencePair] = []
    seen_pair_ids: set[str] = set()
    seen_paths: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_pairs):
        if not isinstance(item, Mapping):
            raise ValueError(f"optional_comparison_pairs[{index}] must be an object")
        _strict_mapping(
            item,
            {
                "pair_id",
                "case_study_id",
                "left_evidence_path",
                "right_evidence_path",
            },
            f"optional_comparison_pairs[{index}]",
        )
        pair = OptionalEvidencePair(
            pair_id=_identifier(
                item["pair_id"], f"optional_comparison_pairs[{index}].pair_id"
            ),
            case_study_id=_identifier(
                item["case_study_id"],
                f"optional_comparison_pairs[{index}].case_study_id",
            ),
            left_evidence_path=str(item["left_evidence_path"]),
            right_evidence_path=str(item["right_evidence_path"]),
        )
        for side, path in (
            ("left", pair.left_evidence_path),
            ("right", pair.right_evidence_path),
        ):
            _validate_relative_path(
                path, f"optional_comparison_pairs[{index}].{side}_evidence_path"
            )
        if pair.left_evidence_path == pair.right_evidence_path:
            raise ValueError("same-file self-comparison is prohibited")
        path_key = tuple(sorted((pair.left_evidence_path, pair.right_evidence_path)))
        if pair.pair_id in seen_pair_ids or path_key in seen_paths:
            raise ValueError("ambiguous evidence pair declaration")
        seen_pair_ids.add(pair.pair_id)
        seen_paths.add(path_key)
        pairs.append(pair)

    return RetrievalReproducibilityConfig(
        schema_version=RETRIEVAL_SCHEMA_VERSION,
        audit_id=audit_id,
        evidence=tuple(sorted(requests, key=lambda item: item.evidence_id)),
        compatibility_summary_path=COMPATIBILITY_SUMMARY_PATH,
        optional_comparison_pairs=tuple(sorted(pairs, key=lambda item: item.pair_id)),
        network_enabled=False,
        source_mutation_enabled=False,
        model_execution_enabled=False,
        read_credentials=False,
        store_credentials=False,
        dry_run=True,
        output_root=DEFAULT_OUTPUT_ROOT,
        write_tracked_summary=True,
        tracked_summary_path=TRACKED_SUMMARY_PATH,
    )


def load_retrieval_reproducibility_config(
    path: str | Path,
) -> RetrievalReproducibilityConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("retrieval reproducibility config must be a JSON object")
    return validate_retrieval_reproducibility_config(payload)


def _config_payload(config: RetrievalReproducibilityConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "audit_id": config.audit_id,
        "evidence": [asdict(item) for item in config.evidence],
        "compatibility_summary_path": config.compatibility_summary_path,
        "optional_comparison_pairs": [
            asdict(item) for item in config.optional_comparison_pairs
        ],
        "network_enabled": config.network_enabled,
        "source_mutation_enabled": config.source_mutation_enabled,
        "model_execution_enabled": config.model_execution_enabled,
        "credential_policy": {
            "read_credentials": config.read_credentials,
            "store_credentials": config.store_credentials,
        },
        "dry_run": config.dry_run,
        "output_root": config.output_root,
        "tracked_summary_policy": {
            "write_tracked_summary": config.write_tracked_summary,
            "path": config.tracked_summary_path,
        },
    }


def _build_tracked_evidence(
    request: TrackedEvidenceRequest,
    *,
    repo_root: Path,
    audit_id: str,
) -> RetrievalEvidenceRecord:
    source = repo_root / request.input_path
    before = source.read_bytes()
    payload = json.loads(before.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("tracked retrieval evidence input must be a JSON object")
    compatibility = adapt_tracked_external_source_artifact(
        source,
        artifact_kind=request.artifact_kind,
        expected_version=request.expected_version,
        adapter_id=request.adapter_id,
        input_artifact_ref=request.input_path,
        audit_id=audit_id,
    )
    adapter = select_compatibility_adapter(
        request.artifact_kind,
        request.expected_version,
        adapter_id=request.adapter_id,
    )
    common_sources = {
        "artifact_ref": "audit_config.input_path",
        "artifact_version": "tracked_summary.schema_version",
        "retrieval_event_ref": "tracked_summary.provenance_boundary",
    }
    if request.case_study_id == "materials_project":
        metadata = {
            "retrieval_timestamp": None,
            "client_name": "mp-api",
            "client_version": None,
            "endpoint_or_method": "enrich_existing_ids",
            "query_or_parameters": {
                "mode": payload["acquisition_mode"],
                "requested_count": payload["requested_material_id_count"],
            },
            "requested_entity_identifiers": None,
            "response_count": payload["api_returned_document_count"],
            "input_schema_version": payload["schema_version"],
            "transformation_boundary": payload["provenance_policy"],
        }
        sources = {
            **common_sources,
            "source_system_ref": "tracked_summary.network_execution",
            "dataset_ref": "tracked_summary.case_study_id",
            "distribution_ref": "not_provided",
            "snapshot_ref": "not_provided",
            "retrieval_timestamp": "not_provided",
            "client_name": "compatibility_contract.known_client_family",
            "client_version": "not_provided",
            "endpoint_or_method": "tracked_summary.acquisition_mode",
            "query_or_parameters": "tracked_summary.acquisition_mode_and_counts",
            "requested_entity_identifiers": "row_level_identifiers_local_only",
            "response_count": "tracked_summary.api_returned_document_count",
            "input_schema_version": "tracked_summary.schema_version",
            "transformation_boundary": "tracked_summary.provenance_policy",
        }
        record = build_retrieval_evidence_record(
            evidence_id=request.evidence_id,
            case_study_id=request.case_study_id,
            artifact_role="retrieval_aggregate_summary",
            artifact_kind=request.artifact_kind,
            artifact_version=request.expected_version,
            artifact_ref=request.input_path,
            artifact_bytes=before,
            logical_payload=payload,
            source_system_ref="materials_project_api",
            dataset_ref="materials_project_existing_id_structure_enrichment",
            distribution_ref=None,
            snapshot_ref=None,
            retrieval_event_ref="materials_project_v2_2_4_bounded_execution",
            source_distribution_raw_sha256=None,
            retrieval_metadata=metadata,
            known_missing_metadata=(
                *adapter.expected_unresolved_fields,
                "independent_second_retrieval_event",
                "requested_entity_identifiers",
                "retrieval_timestamp",
            ),
            evidence_field_sources=sources,
            independent_retrieval_event=False,
            limitations=(
                "the tracked aggregate is not the raw API response distribution",
                "no independent second retrieval event is present in the repository",
            ),
        )
    else:
        metadata = {
            "retrieval_timestamp": None,
            "client_name": None,
            "client_version": None,
            "endpoint_or_method": None,
            "query_or_parameters": None,
            "requested_entity_identifiers": None,
            "response_count": payload["metadata_rows"],
            "input_schema_version": payload["schema_version"],
            "transformation_boundary": payload["immediate_upstream_status"],
        }
        sources = {
            **common_sources,
            "source_system_ref": "tracked_summary.dataset_slug",
            "dataset_ref": "tracked_summary.dataset_slug",
            "distribution_ref": "tracked_summary.archive_sha256",
            "snapshot_ref": "tracked_summary.original_nasa_snapshot_status",
            "retrieval_timestamp": "not_provided",
            "client_name": "not_provided",
            "client_version": "not_provided",
            "endpoint_or_method": "not_provided",
            "query_or_parameters": "not_provided",
            "requested_entity_identifiers": "not_provided",
            "response_count": "tracked_summary.metadata_rows",
            "input_schema_version": "tracked_summary.schema_version",
            "transformation_boundary": "tracked_summary.immediate_upstream_status",
        }
        record = build_retrieval_evidence_record(
            evidence_id=request.evidence_id,
            case_study_id=request.case_study_id,
            artifact_role="retrieval_aggregate_summary",
            artifact_kind=request.artifact_kind,
            artifact_version=request.expected_version,
            artifact_ref=request.input_path,
            artifact_bytes=before,
            logical_payload=payload,
            source_system_ref="kaggle_immediate_upstream_archive",
            dataset_ref=payload["dataset_slug"],
            distribution_ref=f"sha256:{payload['archive_sha256']}",
            snapshot_ref=None,
            retrieval_event_ref=None,
            source_distribution_raw_sha256=payload["archive_sha256"],
            retrieval_metadata=metadata,
            known_missing_metadata=(
                *adapter.expected_unresolved_fields,
                "client_name",
                "client_version",
                "endpoint_or_method",
                "independent_second_retrieval_event",
                "query_or_parameters",
                "requested_entity_identifiers",
            ),
            evidence_field_sources=sources,
            independent_retrieval_event=False,
            limitations=(
                "the verified Kaggle archive is not an identified official NASA snapshot",
                "no independent second retrieval event is present in the repository",
            ),
        )
    if record.canonical_logical_sha256 != compatibility.input_canonical_json_sha256:
        raise ValueError("retrieval and compatibility canonical checksums disagree")
    if record.artifact_raw_bytes_sha256 != compatibility.input_raw_bytes_sha256:
        raise ValueError("retrieval and compatibility raw checksums disagree")
    if source.read_bytes() != before:
        raise ValueError("retrieval evidence audit detected source mutation")
    return record


def _load_optional_pair(
    pair: OptionalEvidencePair,
    *,
    repo_root: Path,
    audit_id: str,
) -> RetrievalComparisonResult:
    left = RetrievalEvidenceRecord.from_mapping(
        json.loads((repo_root / pair.left_evidence_path).read_text(encoding="utf-8"))
    )
    right = RetrievalEvidenceRecord.from_mapping(
        json.loads((repo_root / pair.right_evidence_path).read_text(encoding="utf-8"))
    )
    if left.case_study_id != pair.case_study_id or right.case_study_id != pair.case_study_id:
        raise ValueError("optional evidence pair case-study mismatch")
    return compare_retrieval_evidence(
        left,
        right,
        audit_id=audit_id,
        pair_id=pair.pair_id,
    )


def _load_compatibility_context(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility summary must be a JSON object")
    validate_compatibility_summary(payload)
    if payload["schema_id"] != COMPATIBILITY_SUMMARY_SCHEMA_ID:
        raise ValueError("unexpected compatibility summary schema")
    return payload


def preview_retrieval_reproducibility_audit(
    config: RetrievalReproducibilityConfig | Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    validated = (
        config
        if isinstance(config, RetrievalReproducibilityConfig)
        else validate_retrieval_reproducibility_config(config)
    )
    root = Path(repo_root)
    inputs = [
        validated.compatibility_summary_path,
        *(request.input_path for request in validated.evidence),
        *(
            path
            for pair in validated.optional_comparison_pairs
            for path in (pair.left_evidence_path, pair.right_evidence_path)
        ),
    ]
    for relative in sorted(set(inputs)):
        if not (root / relative).is_file():
            raise ValueError(f"required retrieval evidence input is missing: {relative}")
    compatibility = _load_compatibility_context(
        root / validated.compatibility_summary_path
    )
    return {
        "schema_version": RETRIEVAL_REPRODUCIBILITY_VERSION,
        "audit_id": validated.audit_id,
        "status": "ready",
        "tracked_evidence": [
            {
                "evidence_id": request.evidence_id,
                "case_study_id": request.case_study_id,
                "artifact_kind": request.artifact_kind,
                "artifact_version": request.expected_version,
                "input_path": request.input_path,
            }
            for request in validated.evidence
        ],
        "optional_pair_count": len(validated.optional_comparison_pairs),
        "valid_paired_retrieval_available": bool(
            validated.optional_comparison_pairs
        ),
        "expected_tracked_output": validated.tracked_summary_path,
        "expected_local_output_root": validated.output_root,
        "compatibility_context_status": compatibility["status"],
        "config_canonical_sha256": canonical_json_sha256(_config_payload(validated)),
        "writes_performed": False,
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": False,
    }


def build_retrieval_reproducibility_summary(
    config: RetrievalReproducibilityConfig,
    evidence: Sequence[RetrievalEvidenceRecord],
    comparisons: Sequence[RetrievalComparisonResult],
    compatibility: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_evidence = tuple(sorted(evidence, key=lambda item: item.evidence_id))
    ordered_comparisons = tuple(sorted(comparisons, key=lambda item: item.pair_id))
    configured_ids = {item.evidence_id for item in config.evidence}
    if {item.evidence_id for item in ordered_evidence} != configured_ids:
        raise ValueError("retrieval summary evidence does not match its config")
    configured_cases = {item.case_study_id for item in config.evidence}
    if any(item.case_study_id not in configured_cases for item in ordered_comparisons):
        raise ValueError("optional comparison result is outside the configured cases")
    compatibility_by_kind = {
        row["input_artifact_kind"]: row for row in compatibility["adapter_results"]
    }
    case_results = []
    for record in ordered_evidence:
        compatibility_row = compatibility_by_kind[record.artifact_kind]
        missing = set(_unresolved_fields(record))
        missing.add("independent_second_retrieval_event")
        case_results.append(
            {
                "case_study_id": record.case_study_id,
                "evidence_id": record.evidence_id,
                "input_artifact_ref": record.artifact_ref,
                "input_artifact_version": record.artifact_version,
                "input_canonical_logical_sha256": record.canonical_logical_sha256,
                "compatibility_status": compatibility_row["compatibility_status"],
                "available_evidence": sorted(
                    {
                        "artifact_schema_version",
                        "canonical_logical_checksum",
                        "tracked_aggregate_provenance_boundary",
                        *(
                            {"source_distribution_raw_checksum"}
                            if record.source_distribution_raw_sha256
                            else set()
                        ),
                    }
                ),
                "missing_evidence": sorted(missing),
                "valid_comparison_pair_exists": False,
                "minimum_additional_evidence": [
                    "an independent second retrieval event for the same artifact role",
                    "a complete and comparable source/snapshot/retrieval metadata record",
                    "checksums for both independently retrieved artifacts",
                ],
                "assessment_status": "insufficient_evidence",
                "claim_boundary": (
                    "the tracked artifact establishes one bounded evidence point; "
                    "it does not establish real-world retrieval reproducibility"
                ),
            }
        )
    # Optional local pairs never alter the portable tracked readiness result.
    comparison_counts = {status: 0 for status in ASSESSMENT_STATUSES}
    payload = {
        "schema_id": SUMMARY_SCHEMA_ID,
        "schema_version": RETRIEVAL_SCHEMA_VERSION,
        "feature_version": RETRIEVAL_REPRODUCIBILITY_VERSION,
        "audit_id": config.audit_id,
        "status": "insufficient_evidence",
        "evidence_record_count": len(ordered_evidence),
        "declared_pair_count": 0,
        "evaluated_pair_count": 0,
        "comparison_status_counts": comparison_counts,
        "case_study_results": case_results,
        "compatibility_context": {
            "summary_canonical_json_sha256": canonical_json_sha256(compatibility),
            "materials_status": compatibility_by_kind[MATERIALS_ARTIFACT_KIND][
                "compatibility_status"
            ],
            "battery_status": compatibility_by_kind[BATTERY_ARTIFACT_KIND][
                "compatibility_status"
            ],
            "software_validation": compatibility["software_validation"],
            "scientific_provenance_portability": compatibility[
                "scientific_provenance_portability"
            ],
        },
        "software_validation": "supported",
        "scientific_validation": "insufficient_paired_retrieval_evidence",
        "exact_byte_reproducibility_established": False,
        "logical_content_reproducibility_established": False,
        "metadata_reproducibility_established": False,
        "source_truth_verified": False,
        "cross_domain_comparison_performed": False,
        "self_comparison_used": False,
        "input_artifacts_unchanged": all(
            not item.source_input_mutated for item in ordered_evidence
        ),
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": False,
        "raw_checksum_policy": (
            "checkout-dependent input raw hashes remain in ignored local detail; "
            "the tracked summary stores canonical logical identity only"
        ),
        "claim_boundary": [
            "one tracked evidence point per case study cannot establish retrieval reproducibility",
            "Materials and Battery are separate domains and are never treated as a retrieval pair",
            "compatibility and checksum evidence do not establish source truth, scientific comparability, mechanism validity, independent validation, or production validation",
        ],
    }
    payload["summary_checksum_sha256"] = canonical_json_sha256(payload)
    _validate_safe_text(payload, "retrieval reproducibility summary")
    return payload


def validate_retrieval_reproducibility_summary(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "schema_id",
        "schema_version",
        "feature_version",
        "audit_id",
        "status",
        "evidence_record_count",
        "declared_pair_count",
        "evaluated_pair_count",
        "comparison_status_counts",
        "case_study_results",
        "compatibility_context",
        "software_validation",
        "scientific_validation",
        "exact_byte_reproducibility_established",
        "logical_content_reproducibility_established",
        "metadata_reproducibility_established",
        "source_truth_verified",
        "cross_domain_comparison_performed",
        "self_comparison_used",
        "input_artifacts_unchanged",
        "network_called",
        "credentials_read",
        "source_mutation_performed",
        "model_executed",
        "raw_checksum_policy",
        "claim_boundary",
        "summary_checksum_sha256",
    }
    _strict_mapping(payload, required, "retrieval reproducibility summary")
    if payload["schema_id"] != SUMMARY_SCHEMA_ID:
        raise ValueError("unsupported retrieval reproducibility summary schema_id")
    _validate_exact_version(
        str(payload["schema_version"]), RETRIEVAL_SCHEMA_VERSION, SUMMARY_SCHEMA_ID
    )
    if payload["feature_version"] != RETRIEVAL_REPRODUCIBILITY_VERSION:
        raise ValueError("unsupported retrieval reproducibility feature version")
    if payload["status"] not in ASSESSMENT_STATUSES:
        raise ValueError("unregistered retrieval summary status")
    _identifier(payload["audit_id"], "audit_id")
    if set(payload["comparison_status_counts"]) != set(ASSESSMENT_STATUSES):
        raise ValueError("retrieval summary comparison status registry mismatch")
    if sum(payload["comparison_status_counts"].values()) != payload["evaluated_pair_count"]:
        raise ValueError("retrieval summary comparison counts mismatch")
    rows = payload["case_study_results"]
    if not isinstance(rows, list) or len(rows) != payload["evidence_record_count"]:
        raise ValueError("retrieval summary evidence count mismatch")
    row_fields = {
        "case_study_id",
        "evidence_id",
        "input_artifact_ref",
        "input_artifact_version",
        "input_canonical_logical_sha256",
        "compatibility_status",
        "available_evidence",
        "missing_evidence",
        "valid_comparison_pair_exists",
        "minimum_additional_evidence",
        "assessment_status",
        "claim_boundary",
    }
    case_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"case_study_results[{index}] must be an object")
        _strict_mapping(row, row_fields, f"case_study_results[{index}]")
        case_id = _identifier(
            row["case_study_id"], f"case_study_results[{index}].case_study_id"
        )
        if case_id in case_ids:
            raise ValueError(f"duplicate case-study result: {case_id}")
        case_ids.add(case_id)
        _validate_relative_path(
            row["input_artifact_ref"],
            f"case_study_results[{index}].input_artifact_ref",
        )
        _validate_sha256(
            row["input_canonical_logical_sha256"],
            f"case_study_results[{index}].input_canonical_logical_sha256",
            required=True,
        )
        if row["assessment_status"] != "insufficient_evidence":
            raise ValueError("tracked case-study readiness must preserve insufficient evidence")
        if row["valid_comparison_pair_exists"] is not False:
            raise ValueError("tracked summary cannot claim an optional local pair")
    if case_ids != {"battery", "materials_project"}:
        raise ValueError("retrieval summary must contain Materials and Battery separately")
    if payload["status"] != "insufficient_evidence":
        raise ValueError("tracked retrieval conclusion must remain insufficient evidence")
    compatibility_fields = {
        "summary_canonical_json_sha256",
        "materials_status",
        "battery_status",
        "software_validation",
        "scientific_provenance_portability",
    }
    _strict_mapping(
        payload["compatibility_context"],
        compatibility_fields,
        "compatibility_context",
    )
    _validate_sha256(
        payload["compatibility_context"]["summary_canonical_json_sha256"],
        "compatibility_context.summary_canonical_json_sha256",
        required=True,
    )
    if payload["compatibility_context"]["materials_status"] != "compatible_with_restrictions":
        raise ValueError("Materials compatibility status was not preserved")
    if payload["compatibility_context"]["battery_status"] != "partial":
        raise ValueError("Battery compatibility status was not preserved")
    if payload["software_validation"] != "supported":
        raise ValueError("retrieval software validation mismatch")
    if payload["scientific_validation"] != "insufficient_paired_retrieval_evidence":
        raise ValueError("retrieval scientific validation mismatch")
    prohibited_true = (
        "exact_byte_reproducibility_established",
        "logical_content_reproducibility_established",
        "metadata_reproducibility_established",
        "source_truth_verified",
        "cross_domain_comparison_performed",
        "self_comparison_used",
        "network_called",
        "credentials_read",
        "source_mutation_performed",
        "model_executed",
    )
    if any(payload[name] for name in prohibited_true):
        raise ValueError("retrieval summary crosses its evidence or execution boundary")
    if payload["input_artifacts_unchanged"] is not True:
        raise ValueError("retrieval summary must preserve source inputs")
    without_checksum = dict(payload)
    checksum = without_checksum.pop("summary_checksum_sha256")
    if checksum != canonical_json_sha256(without_checksum):
        raise ValueError("retrieval reproducibility summary checksum mismatch")
    _validate_safe_text(payload, "retrieval reproducibility summary")
    return {
        "valid": True,
        "status": "valid",
        "record_type": "summary",
        "audit_id": payload["audit_id"],
        "assessment": payload["status"],
    }


def validate_retrieval_reproducibility_file(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("retrieval reproducibility record must be a JSON object")
    schema_id = payload.get("schema_id")
    if schema_id == EVIDENCE_SCHEMA_ID:
        record = RetrievalEvidenceRecord.from_mapping(payload)
        return {
            "valid": True,
            "status": "valid",
            "record_type": "evidence",
            "evidence_id": record.evidence_id,
            "record_checksum_sha256": record.record_checksum_sha256,
        }
    if schema_id == COMPARISON_SCHEMA_ID:
        result = RetrievalComparisonResult.from_mapping(payload)
        return {
            "valid": True,
            "status": "valid",
            "record_type": "comparison",
            "pair_id": result.pair_id,
            "assessment": result.final_assessment,
            "result_checksum_sha256": result.result_checksum_sha256,
        }
    return validate_retrieval_reproducibility_summary(payload)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(path)


def run_retrieval_reproducibility_audit(
    config: RetrievalReproducibilityConfig | Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
    execute: bool = False,
    write_local: bool = True,
    write_tracked: bool = True,
) -> dict[str, Any]:
    if not execute:
        raise ValueError("retrieval reproducibility audit requires explicit execute=True")
    validated = (
        config
        if isinstance(config, RetrievalReproducibilityConfig)
        else validate_retrieval_reproducibility_config(config)
    )
    root = Path(repo_root)
    input_paths = [
        root / validated.compatibility_summary_path,
        *(root / item.input_path for item in validated.evidence),
        *(
            root / path
            for pair in validated.optional_comparison_pairs
            for path in (pair.left_evidence_path, pair.right_evidence_path)
        ),
    ]
    before = {path: path.read_bytes() for path in input_paths}
    compatibility = _load_compatibility_context(
        root / validated.compatibility_summary_path
    )
    evidence = tuple(
        _build_tracked_evidence(
            request,
            repo_root=root,
            audit_id=validated.audit_id,
        )
        for request in validated.evidence
    )
    comparisons = tuple(
        _load_optional_pair(
            pair,
            repo_root=root,
            audit_id=validated.audit_id,
        )
        for pair in validated.optional_comparison_pairs
    )
    summary = build_retrieval_reproducibility_summary(
        validated, evidence, comparisons, compatibility
    )
    for path, original in before.items():
        if path.read_bytes() != original:
            raise ValueError("retrieval reproducibility audit detected input mutation")

    written: list[str] = []
    if write_local:
        for record in evidence:
            relative = f"{validated.output_root}/{record.evidence_id}.json"
            _write_json_atomic(root / relative, record.to_dict())
            written.append(relative)
        for result in comparisons:
            relative = f"{validated.output_root}/{result.pair_id}.json"
            _write_json_atomic(root / relative, result.to_dict())
            written.append(relative)
    if write_tracked and validated.write_tracked_summary:
        _write_json_atomic(root / validated.tracked_summary_path, summary)
        written.append(validated.tracked_summary_path)
    return {
        "status": "completed",
        "assessment": summary["status"],
        "summary": summary,
        "evidence": [item.to_dict() for item in evidence],
        "comparisons": [item.to_dict() for item in comparisons],
        "written": sorted(written),
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": False,
    }
