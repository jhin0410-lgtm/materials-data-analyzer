"""Bounded compatibility replay for two tracked external-source summaries.

This module turns the v2.4 declarative mappings into deterministic software
evidence. It is deliberately not a migration framework: dispatch is an
explicit artifact/version allowlist, inputs are read-only, and no network,
credential, model, or source-mutation operation is available.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Sequence

from .external_source_contracts import (
    EXTERNAL_SOURCE_CONTRACT_VERSION,
    _validate_relative_path,
    _validate_safe_text,
    canonical_json_sha256,
    raw_bytes_sha256,
)


COMPATIBILITY_AUDIT_VERSION = "2.5.1"
COMPATIBILITY_RESULT_SCHEMA_VERSION = "1"
COMPATIBILITY_RESULT_SCHEMA_ID = "external_source_compatibility_result_v1"
COMPATIBILITY_SUMMARY_SCHEMA_ID = "external_source_compatibility_summary_v1"
DEFAULT_CONFIG_PATH = "configs/examples/external_source_compatibility_audit.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_5_external_source_compatibility"
TRACKED_SUMMARY_PATH = "data/processed/external_source_compatibility_audit_summary_v1.json"

COMPATIBILITY_STATUSES = (
    "fully_compatible",
    "compatible_with_restrictions",
    "partial",
    "blocked",
    "unsupported",
)

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


MATERIALS_ARTIFACT_KIND = "materials_project_v2_2_4_structure_enrichment_summary"
BATTERY_ARTIFACT_KIND = "battery_v2_3_5_source_lineage_summary"

_MATERIALS_FIELDS = frozenset(
    {
        "acquisition_mode",
        "api_key_persisted",
        "api_returned_document_count",
        "case_study_id",
        "case_study_version",
        "chunk_count",
        "composition_consistent_count",
        "composition_only_pre_structure_conclusion_preserved",
        "composition_reduced_match_count",
        "decision_status",
        "descriptor_definition_count",
        "descriptor_output_column_count",
        "descriptor_row_count",
        "disordered_structure_count",
        "duplicate_returned_id_count",
        "execution_status",
        "gnn_execution",
        "graph_checksums_unique",
        "graph_count",
        "graph_eligible_count",
        "local_artifact_policy",
        "missing_material_id_count",
        "network_execution",
        "ordered_structure_count",
        "original_target_overwritten",
        "prediction_context",
        "predictive_improvement_claimed",
        "provenance_policy",
        "requested_material_id_count",
        "row_level_material_ids_in_tracked_outputs",
        "schema_version",
        "snapshot_aligned_count",
        "snapshot_exact_match_count",
        "snapshot_within_tolerance_count",
        "structure_aware_model_trained",
        "structure_entity_count",
        "target_drift_count",
        "valid_structure_entity_count",
    }
)

_BATTERY_FIELDS = frozenset(
    {
        "ambient_temperature_rows",
        "analysis_ready_rows",
        "archive_metadata_matches_extracted",
        "archive_metadata_member",
        "archive_metadata_member_sha256",
        "archive_path",
        "archive_sha256",
        "archive_size_bytes",
        "audit_id",
        "dataset_slug",
        "default_fill_performed",
        "exact_lineage_cell_count",
        "exact_source_key_match_rows",
        "full_discharge_rows",
        "full_source_key_match_rows",
        "full_summary_rows",
        "immediate_upstream_status",
        "impedance_cell_count",
        "impedance_complete_re_rct_rows",
        "impedance_rct_rows",
        "impedance_re_rows",
        "impedance_rows",
        "inference_performed",
        "measured_current_rows",
        "measured_temperature_rows",
        "measured_voltage_rows",
        "metadata_cell_count",
        "metadata_path",
        "metadata_rows",
        "metadata_sha256",
        "network_called",
        "original_nasa_snapshot_status",
        "pgir_source_checksum_sha256",
        "pgir_state_checksum_sha256",
        "pgir_trajectory_checksum_sha256",
        "physical_duration_rows",
        "protocol_document_cell_coverage",
        "protocol_document_count",
        "raw_discharge_files_verified",
        "raw_header_signatures",
        "raw_header_verified_rows",
        "row_level_output_policy",
        "schema_version",
        "source_evidence_checksum",
        "timestamp_monotonic_cells",
        "timestamp_parseable_rows",
        "timestamp_timezone_status",
        "trajectory_count",
        "uncertainty_rows",
    }
)


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


def _validate_exact_version(actual: str, expected: str, artifact_kind: str) -> None:
    if actual == expected:
        return
    if _version_parts(actual) > _version_parts(expected):
        raise ValueError(
            f"unsupported future version for {artifact_kind}: {actual}; supported version is {expected}"
        )
    raise ValueError(
        f"unsupported source version for {artifact_kind}: {actual}; supported version is {expected}"
    )


@dataclass(frozen=True)
class CompatibilityAdapterMetadata:
    adapter_id: str
    adapter_version: str
    input_artifact_kind: str
    supported_input_version: str
    expected_input_path: str
    target_contract_version: str
    target_concepts: tuple[str, ...]
    declared_mapping_status: str
    migration_performed: bool
    source_mutation_performed: bool
    expected_unresolved_fields: tuple[str, ...]
    execution_boundary: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.adapter_id, "adapter_id")
        _identifier(self.input_artifact_kind, "input_artifact_kind")
        _version_parts(self.adapter_version)
        _version_parts(self.supported_input_version)
        _validate_relative_path(self.expected_input_path, "expected_input_path")
        if self.target_contract_version != EXTERNAL_SOURCE_CONTRACT_VERSION:
            raise ValueError("adapter target contract version is unsupported")
        if self.declared_mapping_status not in {"compatible_adapter", "partial"}:
            raise ValueError("adapter declared mapping status is unsupported")
        if self.migration_performed or self.source_mutation_performed:
            raise ValueError("compatibility adapters must be read-only")
        if not self.target_concepts:
            raise ValueError("compatibility adapter requires target concept references")
        if tuple(sorted(set(self.expected_unresolved_fields))) != self.expected_unresolved_fields:
            raise ValueError("expected unresolved fields must be unique and deterministic")
        _validate_safe_text(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "input_artifact_kind": self.input_artifact_kind,
            "supported_input_version": self.supported_input_version,
            "expected_input_path": self.expected_input_path,
            "target_contract_version": self.target_contract_version,
            "target_concepts": list(self.target_concepts),
            "declared_mapping_status": self.declared_mapping_status,
            "migration_performed": self.migration_performed,
            "source_mutation_performed": self.source_mutation_performed,
            "expected_unresolved_fields": list(self.expected_unresolved_fields),
            "execution_boundary": self.execution_boundary,
            "limitations": list(self.limitations),
        }


def build_compatibility_adapter_registry() -> tuple[CompatibilityAdapterMetadata, ...]:
    adapters = (
        CompatibilityAdapterMetadata(
            adapter_id="battery_source_lineage_to_external_source_v1",
            adapter_version="1",
            input_artifact_kind=BATTERY_ARTIFACT_KIND,
            supported_input_version="2.3.5",
            expected_input_path="data/processed/battery_v2_3_5_source_lineage_summary.json",
            target_contract_version="1",
            target_concepts=("DistributionArtifact", "ExternalSourceProvenanceAssessment"),
            declared_mapping_status="partial",
            migration_performed=False,
            source_mutation_performed=False,
            expected_unresolved_fields=(
                "calibration_metadata",
                "license_or_terms",
                "measurement_uncertainty",
                "official_nasa_snapshot_version",
                "original_retrieval_timestamp",
            ),
            execution_boundary="tracked_compact_summary_read_only_no_external_retrieval",
            limitations=(
                "the locally verified Kaggle archive is an immediate upstream package, not the official NASA original",
                "compatibility does not resolve source truth, scientific comparability, or mechanism readiness",
            ),
        ),
        CompatibilityAdapterMetadata(
            adapter_id="materials_structure_summary_external_lineage_v1",
            adapter_version="1",
            input_artifact_kind=MATERIALS_ARTIFACT_KIND,
            supported_input_version="2.2.4",
            expected_input_path="data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",
            target_contract_version="1",
            target_concepts=(
                "LocalDerivedArtifact:conceptual_only",
                "ExternalSourceProvenanceAssessment",
            ),
            declared_mapping_status="compatible_adapter",
            migration_performed=False,
            source_mutation_performed=False,
            expected_unresolved_fields=(
                "api_client_version",
                "license_or_terms",
                "named_dataset_snapshot_version",
                "source_database_version",
            ),
            execution_boundary="tracked_compact_summary_read_only_without_local_acquisition_manifest",
            limitations=(
                "LocalDerivedArtifact is a documented concept without a dedicated typed v1 record",
                "the named Materials Project snapshot and API client version remain unresolved",
            ),
        ),
    )
    return tuple(sorted(adapters, key=lambda item: item.adapter_id))


def validate_compatibility_adapter_registry(
    adapters: Sequence[CompatibilityAdapterMetadata] | None = None,
) -> dict[str, Any]:
    records = tuple(
        build_compatibility_adapter_registry() if adapters is None else adapters
    )
    errors: list[str] = []
    ids: set[str] = set()
    pairs: dict[tuple[str, str], list[str]] = {}
    if not records:
        errors.append("empty_adapter_registry")
    for adapter in records:
        if adapter.adapter_id in ids:
            errors.append(f"duplicate_adapter_id:{adapter.adapter_id}")
        ids.add(adapter.adapter_id)
        pairs.setdefault(
            (adapter.input_artifact_kind, adapter.supported_input_version), []
        ).append(adapter.adapter_id)
    for pair, adapter_ids in sorted(pairs.items()):
        if len(adapter_ids) > 1:
            errors.append(f"ambiguous_adapter_pair:{pair[0]}:{pair[1]}")
    return {
        "valid": not errors,
        "status": "valid" if not errors else "invalid",
        "adapter_count": len(records),
        "errors": errors,
    }


def select_compatibility_adapter(
    artifact_kind: str,
    source_version: str,
    *,
    adapter_id: str | None = None,
    adapters: Sequence[CompatibilityAdapterMetadata] | None = None,
) -> CompatibilityAdapterMetadata:
    records = tuple(
        build_compatibility_adapter_registry() if adapters is None else adapters
    )
    validation = validate_compatibility_adapter_registry(records)
    if not validation["valid"]:
        raise ValueError("ambiguous compatibility adapter registry: " + ",".join(validation["errors"]))
    kind_matches = [item for item in records if item.input_artifact_kind == artifact_kind]
    if not kind_matches:
        raise ValueError(f"unknown compatibility artifact kind: {artifact_kind}")
    version_matches = [item for item in kind_matches if item.supported_input_version == source_version]
    if not version_matches:
        supported = max((item.supported_input_version for item in kind_matches), key=_version_parts)
        _validate_exact_version(source_version, supported, artifact_kind)
    if adapter_id is not None:
        version_matches = [item for item in version_matches if item.adapter_id == adapter_id]
        if not version_matches:
            raise ValueError(f"adapter {adapter_id} is not allowlisted for {artifact_kind} {source_version}")
    if len(version_matches) != 1:
        raise ValueError(f"ambiguous adapter match for {artifact_kind} {source_version}")
    return version_matches[0]


@dataclass(frozen=True)
class ExternalSourceCompatibilityResult:
    schema_id: str
    schema_version: str
    audit_id: str
    adapter_id: str
    adapter_version: str
    input_artifact_kind: str
    input_artifact_ref: str
    input_artifact_version: str
    input_raw_bytes_sha256: str
    input_canonical_json_sha256: str
    target_contract_version: str
    target_concept_refs: tuple[str, ...]
    declared_mapping_status: str
    compatibility_status: str
    preserved_fields: tuple[str, ...]
    mapped_fields: Mapping[str, str]
    unresolved_fields: tuple[str, ...]
    cannot_infer_fields: tuple[str, ...]
    blocked_or_unsupported_fields: tuple[str, ...]
    output_record_checksums: Mapping[str, str]
    input_mutated: bool
    migration_performed: bool
    source_mutation_performed: bool
    network_called: bool
    credentials_read: bool
    credentials_persisted: bool
    model_executed: bool
    limitations: tuple[str, ...]
    claim_boundary: tuple[str, ...]
    result_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.schema_id != COMPATIBILITY_RESULT_SCHEMA_ID:
            raise ValueError("unsupported compatibility result schema_id")
        _validate_exact_version(
            self.schema_version,
            COMPATIBILITY_RESULT_SCHEMA_VERSION,
            COMPATIBILITY_RESULT_SCHEMA_ID,
        )
        if self.compatibility_status not in COMPATIBILITY_STATUSES:
            raise ValueError(f"unsupported compatibility status: {self.compatibility_status}")
        _identifier(self.audit_id, "audit_id")
        _identifier(self.adapter_id, "adapter_id")
        _identifier(self.input_artifact_kind, "input_artifact_kind")
        adapter = select_compatibility_adapter(
            self.input_artifact_kind,
            self.input_artifact_version,
            adapter_id=self.adapter_id,
        )
        expected_status = (
            "compatible_with_restrictions"
            if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND
            else "partial"
        )
        if self.adapter_version != adapter.adapter_version:
            raise ValueError("compatibility result adapter version mismatch")
        if self.target_contract_version != adapter.target_contract_version:
            raise ValueError("compatibility result target contract version mismatch")
        if self.target_concept_refs != adapter.target_concepts:
            raise ValueError("compatibility result target concept mismatch")
        if self.declared_mapping_status != adapter.declared_mapping_status:
            raise ValueError("compatibility result declared mapping status mismatch")
        if self.compatibility_status != expected_status:
            raise ValueError("compatibility result status does not match its registered adapter")
        if self.input_artifact_ref != adapter.expected_input_path:
            raise ValueError("compatibility result input artifact is not the registered tracked path")
        if self.unresolved_fields != adapter.expected_unresolved_fields:
            raise ValueError("compatibility result unresolved fields mismatch")
        if self.cannot_infer_fields != self.unresolved_fields:
            raise ValueError("compatibility result cannot-infer fields must preserve unresolved evidence")
        if not self.preserved_fields or tuple(sorted(set(self.preserved_fields))) != self.preserved_fields:
            raise ValueError("compatibility preserved fields must be non-empty, unique, and deterministic")
        if not self.mapped_fields:
            raise ValueError("compatibility result requires explicit mapped fields")
        if any(
            (
                self.input_mutated,
                self.migration_performed,
                self.source_mutation_performed,
                self.network_called,
                self.credentials_read,
                self.credentials_persisted,
                self.model_executed,
            )
        ):
            raise ValueError("compatibility result crosses its read-only execution boundary")
        _validate_relative_path(self.input_artifact_ref, "input_artifact_ref")
        for value in (self.input_raw_bytes_sha256, self.input_canonical_json_sha256):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("compatibility input checksum must be lowercase SHA-256")
        if not self.output_record_checksums:
            raise ValueError("compatibility result requires output record checksums")
        for name, value in self.output_record_checksums.items():
            _identifier(name, "output_record_checksum key")
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("compatibility output checksum must be lowercase SHA-256")
        if self.result_checksum_sha256 != canonical_json_sha256(self._payload_without_checksum()):
            raise ValueError("compatibility result checksum mismatch")
        _validate_safe_text(self.to_dict())

    def _payload_without_checksum(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("result_checksum_sha256", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload_without_checksum(), "result_checksum_sha256": self.result_checksum_sha256}

    @classmethod
    def create(cls, **values: Any) -> "ExternalSourceCompatibilityResult":
        checksum = canonical_json_sha256(values)
        return cls(result_checksum_sha256=checksum, **values)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExternalSourceCompatibilityResult":
        allowed = {item.name for item in fields(cls)}
        _strict_mapping(payload, allowed, "ExternalSourceCompatibilityResult")
        values = dict(payload)
        for name in (
            "target_concept_refs",
            "preserved_fields",
            "unresolved_fields",
            "cannot_infer_fields",
            "blocked_or_unsupported_fields",
            "limitations",
            "claim_boundary",
        ):
            values[name] = tuple(values[name])
        return cls(**values)


@dataclass(frozen=True)
class CompatibilityArtifactRequest:
    adapter_id: str
    artifact_kind: str
    input_path: str
    expected_version: str


@dataclass(frozen=True)
class CompatibilityAuditConfig:
    schema_version: str
    audit_id: str
    target_contract_version: str
    artifacts: tuple[CompatibilityArtifactRequest, ...]
    network_enabled: bool
    source_mutation_enabled: bool
    model_execution_enabled: bool
    dry_run: bool
    read_credentials: bool
    store_credentials: bool
    output_root: str
    write_tracked_summary: bool
    tracked_summary_path: str


def validate_compatibility_config(payload: Mapping[str, Any]) -> CompatibilityAuditConfig:
    allowed = {
        "schema_version",
        "audit_id",
        "target_contract_version",
        "artifacts",
        "network_enabled",
        "source_mutation_enabled",
        "model_execution_enabled",
        "dry_run",
        "credential_policy",
        "output_root",
        "tracked_summary_policy",
    }
    _strict_mapping(payload, allowed, "compatibility audit config")
    _validate_safe_text(payload, "compatibility audit config")
    _validate_exact_version(str(payload["schema_version"]), "1", "compatibility_audit_config")
    audit_id = _identifier(payload["audit_id"], "audit_id")
    if payload["target_contract_version"] != EXTERNAL_SOURCE_CONTRACT_VERSION:
        raise ValueError("unsupported target external-source contract version")
    if payload["network_enabled"] is not False:
        raise ValueError("compatibility audit config must disable network execution")
    if payload["source_mutation_enabled"] is not False:
        raise ValueError("compatibility audit config must disable source mutation")
    if payload["model_execution_enabled"] is not False:
        raise ValueError("compatibility audit config must disable model execution")
    if payload["dry_run"] is not True:
        raise ValueError("compatibility audit config must default to dry_run true")

    credential_policy = payload["credential_policy"]
    if not isinstance(credential_policy, Mapping):
        raise ValueError("credential_policy must be an object")
    _strict_mapping(credential_policy, {"read_credentials", "store_credentials"}, "credential_policy")
    if credential_policy["read_credentials"] is not False or credential_policy["store_credentials"] is not False:
        raise ValueError("compatibility audit must not read or store credentials")

    output_root = str(payload["output_root"])
    _validate_relative_path(output_root, "output_root")
    if output_root != DEFAULT_OUTPUT_ROOT:
        raise ValueError(f"output_root must be the bounded local path {DEFAULT_OUTPUT_ROOT}")

    tracked_policy = payload["tracked_summary_policy"]
    if not isinstance(tracked_policy, Mapping):
        raise ValueError("tracked_summary_policy must be an object")
    _strict_mapping(
        tracked_policy,
        {"write_tracked_summary", "path"},
        "tracked_summary_policy",
    )
    _validate_relative_path(str(tracked_policy["path"]), "tracked_summary_policy.path")
    if tracked_policy["write_tracked_summary"] is not True:
        raise ValueError("tracked compatibility summary must remain enabled")
    if tracked_policy["path"] != TRACKED_SUMMARY_PATH:
        raise ValueError("tracked compatibility summary path is not allowlisted")

    raw_artifacts = payload["artifacts"]
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("compatibility audit config requires a non-empty artifacts list")
    requests: list[CompatibilityArtifactRequest] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_artifacts):
        if not isinstance(item, Mapping):
            raise ValueError(f"artifacts[{index}] must be an object")
        _strict_mapping(
            item,
            {"adapter_id", "artifact_kind", "input_path", "expected_version"},
            f"artifacts[{index}]",
        )
        _validate_relative_path(str(item["input_path"]), f"artifacts[{index}].input_path")
        adapter = select_compatibility_adapter(
            str(item["artifact_kind"]),
            str(item["expected_version"]),
            adapter_id=str(item["adapter_id"]),
        )
        if item["input_path"] != adapter.expected_input_path:
            raise ValueError(f"artifacts[{index}].input_path is not the registered tracked artifact")
        if adapter.adapter_id in seen:
            raise ValueError(f"duplicate configured adapter: {adapter.adapter_id}")
        seen.add(adapter.adapter_id)
        requests.append(
            CompatibilityArtifactRequest(
                adapter_id=adapter.adapter_id,
                artifact_kind=adapter.input_artifact_kind,
                input_path=adapter.expected_input_path,
                expected_version=adapter.supported_input_version,
            )
        )
    required_adapter_ids = {
        item.adapter_id for item in build_compatibility_adapter_registry()
    }
    if seen != required_adapter_ids:
        missing = sorted(required_adapter_ids - seen)
        extra = sorted(seen - required_adapter_ids)
        raise ValueError(
            f"bounded compatibility audit requires its exact registered adapter set; "
            f"missing={missing}, extra={extra}"
        )
    return CompatibilityAuditConfig(
        schema_version="1",
        audit_id=audit_id,
        target_contract_version="1",
        artifacts=tuple(sorted(requests, key=lambda item: item.adapter_id)),
        network_enabled=False,
        source_mutation_enabled=False,
        model_execution_enabled=False,
        dry_run=True,
        read_credentials=False,
        store_credentials=False,
        output_root=output_root,
        write_tracked_summary=True,
        tracked_summary_path=TRACKED_SUMMARY_PATH,
    )


def load_compatibility_config(path: str | Path) -> CompatibilityAuditConfig:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility audit config must contain a JSON object")
    return validate_compatibility_config(payload)


def _validate_source_payload(
    payload: Mapping[str, Any], adapter: CompatibilityAdapterMetadata
) -> None:
    expected_fields = (
        _MATERIALS_FIELDS if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND else _BATTERY_FIELDS
    )
    _strict_mapping(payload, set(expected_fields), adapter.input_artifact_kind)
    actual_version = str(payload["schema_version"])
    _validate_exact_version(actual_version, adapter.supported_input_version, adapter.input_artifact_kind)
    if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND:
        _validate_exact_version(
            str(payload["case_study_version"]).removeprefix("v"),
            adapter.supported_input_version,
            adapter.input_artifact_kind,
        )
        if payload["original_target_overwritten"] is not False:
            raise ValueError("Materials compatibility input indicates original target mutation")
    else:
        if payload["default_fill_performed"] is not False or payload["inference_performed"] is not False:
            raise ValueError("Battery compatibility input indicates inferred or default-filled evidence")
    _validate_safe_text(payload, adapter.input_artifact_kind)


def _materials_mapping(payload: Mapping[str, Any]) -> tuple[dict[str, str], tuple[str, ...]]:
    mapped = {
        "api_key_persisted": "ExternalRetrievalEventRecord.credential_persistence_boundary",
        "case_study_id": "LocalDerivedArtifact:conceptual_only.artifact_context",
        "execution_status": "ExternalSourceProvenanceAssessment.lineage_evidence_status",
        "local_artifact_policy": "LocalDerivedArtifact:conceptual_only.payload_policy",
        "network_execution": "ExternalRetrievalEventRecord.historical_network_execution_evidence",
        "original_target_overwritten": "ExternalSourceProvenanceAssessment.source_mutation_boundary",
        "provenance_policy": "ExternalSourceProvenanceAssessment.lineage_scope",
        "requested_material_id_count": "LocalDerivedArtifact:conceptual_only.aggregate_record_count",
        "schema_version": "compatibility_input.source_version",
        "snapshot_aligned_count": "ExternalSourceProvenanceAssessment.aggregate_alignment_evidence",
    }
    blocked = ("typed_local_derived_artifact_record",)
    return mapped, blocked


def _battery_mapping(payload: Mapping[str, Any]) -> tuple[dict[str, str], tuple[str, ...]]:
    mapped = {
        "archive_path": "ExternalDistributionArtifactRecord.local_artifact_ref",
        "archive_sha256": "ExternalDistributionArtifactRecord.raw_checksum_value",
        "archive_size_bytes": "ExternalDistributionArtifactRecord.byte_size",
        "dataset_slug": "ExternalDatasetRecord.immediate_upstream_reference",
        "immediate_upstream_status": "ExternalSourceProvenanceAssessment.overall_status",
        "metadata_sha256": "ExternalDistributionArtifactRecord.manifest_checksum_evidence",
        "network_called": "ExternalRetrievalEventRecord.replay_network_boundary",
        "original_nasa_snapshot_status": "ExternalDatasetSnapshotRecord.authoritative_snapshot_status",
        "row_level_output_policy": "ExternalDistributionArtifactRecord.security_classification",
        "schema_version": "compatibility_input.source_version",
        "source_evidence_checksum": "ExternalSourceProvenanceAssessment.derived_lineage_checksum",
        "trajectory_count": "ExternalSourceProvenanceAssessment.aggregate_subject_count",
    }
    blocked = ("official_nasa_distribution_identity",)
    return mapped, blocked


def adapt_tracked_external_source_artifact(
    path: str | Path,
    *,
    artifact_kind: str,
    expected_version: str,
    adapter_id: str | None = None,
    input_artifact_ref: str | None = None,
    audit_id: str = "external_source_compatibility_replay_v1",
    adapters: Sequence[CompatibilityAdapterMetadata] | None = None,
) -> ExternalSourceCompatibilityResult:
    adapter = select_compatibility_adapter(
        artifact_kind,
        expected_version,
        adapter_id=adapter_id,
        adapters=adapters,
    )
    source = Path(path)
    reference = input_artifact_ref or adapter.expected_input_path
    _validate_relative_path(reference, "input_artifact_ref")
    before = source.read_bytes()
    payload = json.loads(before.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility input artifact must contain a JSON object")
    _validate_source_payload(payload, adapter)

    if artifact_kind == MATERIALS_ARTIFACT_KIND:
        mapped_fields, blocked_fields = _materials_mapping(payload)
        compatibility_status = "compatible_with_restrictions"
        claim_boundary = (
            "deterministic interpretation of the tracked aggregate Materials summary is supported",
            "named source snapshot, API client version, source truth, and scientific validity are not established",
        )
    else:
        mapped_fields, blocked_fields = _battery_mapping(payload)
        compatibility_status = "partial"
        claim_boundary = (
            "deterministic interpretation of the verified immediate-upstream Battery summary is supported",
            "official NASA source identity, scientific comparability, mechanism validity, and production readiness are not established",
        )

    unresolved = tuple(sorted(adapter.expected_unresolved_fields))
    evidence_record = {
        "adapter_id": adapter.adapter_id,
        "input_artifact_ref": reference,
        "input_canonical_json_sha256": canonical_json_sha256(payload),
        "mapped_fields": dict(sorted(mapped_fields.items())),
        "target_concept_refs": list(adapter.target_concepts),
        "unresolved_fields": list(unresolved),
    }
    output_checksums = {
        "bounded_compatibility_evidence": canonical_json_sha256(evidence_record),
    }
    after = source.read_bytes()
    if before != after:
        raise ValueError("compatibility audit detected input artifact mutation")

    return ExternalSourceCompatibilityResult.create(
        schema_id=COMPATIBILITY_RESULT_SCHEMA_ID,
        schema_version=COMPATIBILITY_RESULT_SCHEMA_VERSION,
        audit_id=audit_id,
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        input_artifact_kind=adapter.input_artifact_kind,
        input_artifact_ref=reference,
        input_artifact_version=adapter.supported_input_version,
        input_raw_bytes_sha256=raw_bytes_sha256(before),
        input_canonical_json_sha256=canonical_json_sha256(payload),
        target_contract_version=adapter.target_contract_version,
        target_concept_refs=adapter.target_concepts,
        declared_mapping_status=adapter.declared_mapping_status,
        compatibility_status=compatibility_status,
        preserved_fields=tuple(sorted(payload)),
        mapped_fields=dict(sorted(mapped_fields.items())),
        unresolved_fields=unresolved,
        cannot_infer_fields=unresolved,
        blocked_or_unsupported_fields=tuple(sorted(blocked_fields)),
        output_record_checksums=output_checksums,
        input_mutated=False,
        migration_performed=False,
        source_mutation_performed=False,
        network_called=False,
        credentials_read=False,
        credentials_persisted=False,
        model_executed=False,
        limitations=adapter.limitations,
        claim_boundary=claim_boundary,
    )


def _config_payload(config: CompatibilityAuditConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "audit_id": config.audit_id,
        "target_contract_version": config.target_contract_version,
        "artifacts": [asdict(item) for item in config.artifacts],
        "network_enabled": config.network_enabled,
        "source_mutation_enabled": config.source_mutation_enabled,
        "model_execution_enabled": config.model_execution_enabled,
        "dry_run": config.dry_run,
        "credential_policy": {
            "read_credentials": config.read_credentials,
            "store_credentials": config.store_credentials,
        },
        "output_root": config.output_root,
        "tracked_summary_policy": {
            "write_tracked_summary": config.write_tracked_summary,
            "path": config.tracked_summary_path,
        },
    }


def preview_external_source_compatibility(
    config: CompatibilityAuditConfig | Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    validated = config if isinstance(config, CompatibilityAuditConfig) else validate_compatibility_config(config)
    root = Path(repo_root)
    plans: list[dict[str, Any]] = []
    for request in validated.artifacts:
        adapter = select_compatibility_adapter(
            request.artifact_kind,
            request.expected_version,
            adapter_id=request.adapter_id,
        )
        source = root / request.input_path
        if not source.is_file():
            raise ValueError(f"required tracked compatibility input is missing: {request.input_path}")
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("compatibility input artifact must contain a JSON object")
        _validate_source_payload(payload, adapter)
        plans.append(
            {
                "adapter_id": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "artifact_kind": adapter.input_artifact_kind,
                "input_path": request.input_path,
                "input_version": request.expected_version,
                "target_contract_version": adapter.target_contract_version,
                "declared_mapping_status": adapter.declared_mapping_status,
                "expected_unresolved_fields": list(adapter.expected_unresolved_fields),
                "execution_boundary": adapter.execution_boundary,
            }
        )
    return {
        "schema_version": COMPATIBILITY_AUDIT_VERSION,
        "audit_id": validated.audit_id,
        "status": "ready",
        "adapter_plan": plans,
        "config_canonical_sha256": canonical_json_sha256(_config_payload(validated)),
        "writes_performed": False,
        "network_called": False,
        "credentials_read": False,
        "credentials_persisted": False,
        "source_mutation_performed": False,
        "model_executed": False,
    }


def build_compatibility_audit_summary(
    config: CompatibilityAuditConfig,
    results: Sequence[ExternalSourceCompatibilityResult],
) -> dict[str, Any]:
    ordered = tuple(sorted(results, key=lambda item: item.adapter_id))
    configured_ids = {item.adapter_id for item in config.artifacts}
    result_ids = {item.adapter_id for item in ordered}
    if len(result_ids) != len(ordered) or result_ids != configured_ids:
        raise ValueError("compatibility summary results do not match configured adapters")
    counts = {status: 0 for status in COMPATIBILITY_STATUSES}
    for result in ordered:
        counts[result.compatibility_status] += 1
    if counts["blocked"]:
        overall_status = "blocked"
    elif counts["unsupported"]:
        overall_status = "unsupported"
    elif counts["partial"]:
        overall_status = "partial"
    elif counts["compatible_with_restrictions"]:
        overall_status = "compatible_with_restrictions"
    else:
        overall_status = "fully_compatible"
    payload = {
        "schema_id": COMPATIBILITY_SUMMARY_SCHEMA_ID,
        "schema_version": COMPATIBILITY_RESULT_SCHEMA_VERSION,
        "feature_version": COMPATIBILITY_AUDIT_VERSION,
        "audit_id": config.audit_id,
        "status": overall_status,
        "target_contract_version": config.target_contract_version,
        "adapter_count": len(ordered),
        "compatibility_status_counts": counts,
        "adapter_results": [
            {
                "adapter_id": item.adapter_id,
                "adapter_version": item.adapter_version,
                "input_artifact_kind": item.input_artifact_kind,
                "input_artifact_ref": item.input_artifact_ref,
                "input_artifact_version": item.input_artifact_version,
                "input_raw_bytes_sha256": item.input_raw_bytes_sha256,
                "input_canonical_json_sha256": item.input_canonical_json_sha256,
                "compatibility_status": item.compatibility_status,
                "declared_mapping_status": item.declared_mapping_status,
                "unresolved_fields": list(item.unresolved_fields),
                "result_checksum_sha256": item.result_checksum_sha256,
            }
            for item in ordered
        ],
        "software_validation": "supported",
        "scientific_provenance_portability": "diagnostic",
        "trust_score_used": False,
        "input_artifacts_unchanged": all(not item.input_mutated for item in ordered),
        "network_called": False,
        "credentials_read": False,
        "credentials_persisted": False,
        "source_mutation_performed": False,
        "model_executed": False,
        "compatibility_meaning": (
            "allowlisted adapters can interpret historical compact artifacts without rewriting them; "
            "supported evidence is preserved and missing evidence remains explicit"
        ),
        "claim_boundary": [
            "compatibility does not independently verify external source authenticity or data correctness",
            "compatibility does not establish scientific comparability, mechanism validity, independent validation, or production validation",
        ],
        "local_detail_policy": "per_adapter_results_under_ignored_outputs_only",
    }
    payload["summary_checksum_sha256"] = canonical_json_sha256(payload)
    _validate_safe_text(payload)
    return payload


def validate_compatibility_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_id",
        "schema_version",
        "feature_version",
        "audit_id",
        "status",
        "target_contract_version",
        "adapter_count",
        "compatibility_status_counts",
        "adapter_results",
        "software_validation",
        "scientific_provenance_portability",
        "trust_score_used",
        "input_artifacts_unchanged",
        "network_called",
        "credentials_read",
        "credentials_persisted",
        "source_mutation_performed",
        "model_executed",
        "compatibility_meaning",
        "claim_boundary",
        "local_detail_policy",
        "summary_checksum_sha256",
    }
    _strict_mapping(payload, required, "compatibility summary")
    if payload["schema_id"] != COMPATIBILITY_SUMMARY_SCHEMA_ID:
        raise ValueError("unsupported compatibility summary schema_id")
    _validate_exact_version(str(payload["schema_version"]), "1", COMPATIBILITY_SUMMARY_SCHEMA_ID)
    if payload["status"] not in COMPATIBILITY_STATUSES:
        raise ValueError("unsupported compatibility summary status")
    if payload["feature_version"] != COMPATIBILITY_AUDIT_VERSION:
        raise ValueError("unsupported compatibility audit feature version")
    if payload["target_contract_version"] != EXTERNAL_SOURCE_CONTRACT_VERSION:
        raise ValueError("unsupported compatibility target contract version")
    _identifier(payload["audit_id"], "audit_id")
    result_fields = {
        "adapter_id",
        "adapter_version",
        "input_artifact_kind",
        "input_artifact_ref",
        "input_artifact_version",
        "input_raw_bytes_sha256",
        "input_canonical_json_sha256",
        "compatibility_status",
        "declared_mapping_status",
        "unresolved_fields",
        "result_checksum_sha256",
    }
    adapter_results = payload["adapter_results"]
    if not isinstance(adapter_results, list):
        raise ValueError("compatibility summary adapter_results must be a list")
    seen_adapters: set[str] = set()
    observed_counts = {status: 0 for status in COMPATIBILITY_STATUSES}
    for index, row in enumerate(adapter_results):
        if not isinstance(row, Mapping):
            raise ValueError(f"adapter_results[{index}] must be an object")
        _strict_mapping(row, result_fields, f"adapter_results[{index}]")
        adapter_id = _identifier(row["adapter_id"], f"adapter_results[{index}].adapter_id")
        if adapter_id in seen_adapters:
            raise ValueError(f"duplicate compatibility summary adapter_id: {adapter_id}")
        seen_adapters.add(adapter_id)
        _validate_relative_path(row["input_artifact_ref"], f"adapter_results[{index}].input_artifact_ref")
        adapter = select_compatibility_adapter(
            str(row["input_artifact_kind"]),
            str(row["input_artifact_version"]),
            adapter_id=adapter_id,
        )
        expected_status = (
            "compatible_with_restrictions"
            if adapter.input_artifact_kind == MATERIALS_ARTIFACT_KIND
            else "partial"
        )
        if row["adapter_version"] != adapter.adapter_version:
            raise ValueError(f"adapter_results[{index}] adapter version mismatch")
        if row["input_artifact_ref"] != adapter.expected_input_path:
            raise ValueError(f"adapter_results[{index}] input artifact path mismatch")
        if row["declared_mapping_status"] != adapter.declared_mapping_status:
            raise ValueError(f"adapter_results[{index}] declared mapping status mismatch")
        if row["unresolved_fields"] != list(adapter.expected_unresolved_fields):
            raise ValueError(f"adapter_results[{index}] unresolved fields mismatch")
        if row["compatibility_status"] not in COMPATIBILITY_STATUSES:
            raise ValueError(f"unsupported adapter compatibility status: {row['compatibility_status']}")
        if row["compatibility_status"] != expected_status:
            raise ValueError(f"adapter_results[{index}] compatibility status mismatch")
        observed_counts[row["compatibility_status"]] += 1
        for name in (
            "input_raw_bytes_sha256",
            "input_canonical_json_sha256",
            "result_checksum_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(row[name])):
                raise ValueError(f"adapter_results[{index}].{name} must be lowercase SHA-256")
    if payload["adapter_count"] != len(adapter_results):
        raise ValueError("compatibility summary adapter_count mismatch")
    if payload["compatibility_status_counts"] != observed_counts:
        raise ValueError("compatibility summary status counts mismatch")
    required_adapter_ids = {
        item.adapter_id for item in build_compatibility_adapter_registry()
    }
    if seen_adapters != required_adapter_ids:
        raise ValueError("compatibility summary does not contain the exact registered adapter set")
    if observed_counts["blocked"]:
        expected_overall = "blocked"
    elif observed_counts["unsupported"]:
        expected_overall = "unsupported"
    elif observed_counts["partial"]:
        expected_overall = "partial"
    elif observed_counts["compatible_with_restrictions"]:
        expected_overall = "compatible_with_restrictions"
    else:
        expected_overall = "fully_compatible"
    if payload["status"] != expected_overall:
        raise ValueError("compatibility summary overall status mismatch")
    if payload["software_validation"] != "supported":
        raise ValueError("compatibility summary software verdict mismatch")
    if payload["scientific_provenance_portability"] != "diagnostic":
        raise ValueError("compatibility summary scientific verdict mismatch")
    without_checksum = dict(payload)
    checksum = without_checksum.pop("summary_checksum_sha256")
    if checksum != canonical_json_sha256(without_checksum):
        raise ValueError("compatibility summary checksum mismatch")
    if payload["trust_score_used"] is not False:
        raise ValueError("compatibility summary must not use a trust score")
    if not payload["input_artifacts_unchanged"] or any(
        payload[name]
        for name in (
            "network_called",
            "credentials_read",
            "credentials_persisted",
            "source_mutation_performed",
            "model_executed",
        )
    ):
        raise ValueError("compatibility summary crosses its read-only boundary")
    _validate_safe_text(payload)
    return {"valid": True, "status": "valid", "record_type": "summary", "audit_id": payload["audit_id"]}


def validate_external_source_compatibility_file(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("compatibility result must contain a JSON object")
    if payload.get("schema_id") == COMPATIBILITY_RESULT_SCHEMA_ID:
        result = ExternalSourceCompatibilityResult.from_mapping(payload)
        return {
            "valid": True,
            "status": "valid",
            "record_type": "adapter_result",
            "audit_id": result.audit_id,
            "adapter_id": result.adapter_id,
            "result_checksum_sha256": result.result_checksum_sha256,
        }
    return validate_compatibility_summary(payload)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)


def run_external_source_compatibility_audit(
    config: CompatibilityAuditConfig | Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
    execute: bool = False,
    write_local: bool = True,
    write_tracked: bool = True,
) -> dict[str, Any]:
    if not execute:
        raise ValueError("compatibility audit execution requires explicit execute=True")
    validated = config if isinstance(config, CompatibilityAuditConfig) else validate_compatibility_config(config)
    root = Path(repo_root)
    results = tuple(
        adapt_tracked_external_source_artifact(
            root / request.input_path,
            artifact_kind=request.artifact_kind,
            expected_version=request.expected_version,
            adapter_id=request.adapter_id,
            input_artifact_ref=request.input_path,
            audit_id=validated.audit_id,
        )
        for request in validated.artifacts
    )
    summary = build_compatibility_audit_summary(validated, results)
    written: list[str] = []
    if write_local:
        for result in results:
            relative = f"{validated.output_root}/{result.adapter_id}.json"
            _write_json_atomic(root / relative, result.to_dict())
            written.append(relative)
    if write_tracked and validated.write_tracked_summary:
        _write_json_atomic(root / validated.tracked_summary_path, summary)
        written.append(validated.tracked_summary_path)
    return {
        "status": "completed",
        "summary": summary,
        "results": [item.to_dict() for item in results],
        "written": sorted(written),
        "network_called": False,
        "credentials_read": False,
        "credentials_persisted": False,
        "source_mutation_performed": False,
        "model_executed": False,
    }
