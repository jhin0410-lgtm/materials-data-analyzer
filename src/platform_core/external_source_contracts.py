"""Versioned, JSON-safe metadata contracts for external scientific sources.

The contract deliberately separates source systems, logical datasets,
snapshots, distributions, retrieval events, documentation, and local derived
artifacts.  It stores credential environment-variable names only and never
performs network access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import MISSING, asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Mapping, TypeVar


EXTERNAL_SOURCE_CONTRACT_VERSION = "1"

SOURCE_KINDS = (
    "authoritative_api",
    "official_catalog",
    "official_distribution",
    "official_repository",
    "verified_mirror",
    "immediate_upstream_archive",
    "community_mirror",
    "local_experimental_source",
    "security_database",
    "energy_system_service",
)

AUTHENTICATION_REQUIREMENTS = (
    "none",
    "optional_api_key",
    "required_api_key",
    "record_dependent",
    "local_only",
)

ALLOWED_CREDENTIAL_ENVIRONMENT_VARIABLES = (
    "MP_API_KEY",
    "NVD_API_KEY",
    "NREL_API_KEY",
)

PROVENANCE_STATUSES = (
    "authoritative_source_verified",
    "authoritative_metadata_verified",
    "official_distribution_verified",
    "snapshot_identity_verified",
    "immediate_upstream_verified",
    "local_copy_checksum_verified",
    "derived_lineage_verified",
    "snapshot_identity_unresolved",
    "official_original_not_locally_verified",
    "license_or_terms_unresolved",
    "documentation_incomplete",
    "mirror_only",
    "provenance_conflict",
)

MAPPING_STATUSES = (
    "exact",
    "compatible_adapter",
    "partial",
    "documentation_only",
    "blocked_missing_identity",
    "blocked_version_ambiguity",
)

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|authorization|access[_-]?token|secret)\s*[=:]\s*[^,;\s]+", re.IGNORECASE),
    re.compile(r"[?&](?:api[_-]?key|token|signature|sig|x-amz-credential)=[^&\s]+", re.IGNORECASE),
)


def canonical_json(payload: Any) -> str:
    """Return canonical logical JSON used for content checksums."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def raw_bytes_sha256(payload: bytes) -> str:
    """Hash raw distribution bytes; distinct from canonical logical JSON."""
    return hashlib.sha256(payload).hexdigest()


def _safe_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable lowercase identifier")


def _validate_relative_path(value: str, field_name: str) -> None:
    if not value:
        return
    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(value):
        raise ValueError(f"{field_name} must not contain an absolute path")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(f"{field_name} must not contain path traversal")


def _validate_safe_text(value: Any, location: str = "record") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {
                "api_key",
                "api_key_value",
                "authorization",
                "authorization_header",
                "access_token",
                "refresh_token",
                "secret",
                "signed_url",
            }:
                raise ValueError(f"{location}.{key} is a prohibited secret field")
            _validate_safe_text(item, f"{location}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _validate_safe_text(item, f"{location}[{index}]")
        return
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            normalized = value.replace("\\", "/")
            if normalized.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(value):
                raise ValueError(f"{location} contains an absolute local path")
            if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
                raise ValueError(f"{location} contains credential-like content")
        return
    raise ValueError(f"{location} contains unsupported JSON value type: {type(value).__name__}")


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


T = TypeVar("T", bound="StrictExternalSourceRecord")


@dataclass(frozen=True)
class StrictExternalSourceRecord:
    """Mixin implementing strict, no-silent-drop mapping conversion."""

    SCHEMA_ID: ClassVar[str] = "external_source_record"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def from_mapping(cls: type[T], payload: Mapping[str, Any]) -> T:
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"{cls.__name__} contains unknown fields: {unknown}")
        required = {
            field.name
            for field in fields(cls)
            if field.default is MISSING and field.default_factory is MISSING
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"{cls.__name__} is missing required fields: {missing}")
        values = dict(payload)
        for field_name in cls.TUPLE_FIELDS:
            if field_name in values:
                value = values[field_name]
                if value is None:
                    values[field_name] = ()
                elif isinstance(value, str):
                    values[field_name] = (value,)
                else:
                    values[field_name] = tuple(value)
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        payload = _json_compatible(asdict(self))
        _validate_safe_text(payload)
        return payload


@dataclass(frozen=True)
class ExternalSourceSystemRecord(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_source_system_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "domain_scope",
        "documentation_refs",
        "access_modes",
        "license_or_terms_refs",
    )

    source_system_id: str
    source_system_version: str
    name: str
    publisher: str
    source_kind: str
    domain_scope: tuple[str, ...]
    official_landing_page: str
    documentation_refs: tuple[str, ...]
    access_modes: tuple[str, ...]
    authentication_requirement: str
    authentication_environment_variable: str | None
    license_or_terms_refs: tuple[str, ...]
    update_policy: str
    status: str

    def __post_init__(self) -> None:
        _safe_identifier(self.source_system_id, "source_system_id")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unsupported source_kind: {self.source_kind}")
        if self.authentication_requirement not in AUTHENTICATION_REQUIREMENTS:
            raise ValueError(f"unsupported authentication_requirement: {self.authentication_requirement}")
        if self.authentication_environment_variable is not None:
            if self.authentication_environment_variable not in ALLOWED_CREDENTIAL_ENVIRONMENT_VARIABLES:
                raise ValueError("only approved credential environment-variable names may be persisted")
            if self.authentication_requirement not in {"optional_api_key", "required_api_key"}:
                raise ValueError("credential environment variable conflicts with authentication requirement")
        elif self.authentication_requirement in {"optional_api_key", "required_api_key"}:
            raise ValueError("API-key authentication must name its environment variable")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalDatasetRecord(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_dataset_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "domain_contexts",
        "identifiers",
        "expected_resource_types",
    )

    dataset_id: str
    source_system_id: str
    title: str
    description: str
    domain_contexts: tuple[str, ...]
    authoritative_identifier: str
    identifiers: tuple[str, ...]
    publisher: str
    citation: str
    license_or_access_conditions: str
    expected_resource_types: tuple[str, ...]
    uncertainty_availability: str
    calibration_metadata_availability: str
    status: str

    def __post_init__(self) -> None:
        _safe_identifier(self.dataset_id, "dataset_id")
        _safe_identifier(self.source_system_id, "source_system_id")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalDatasetSnapshotRecord(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_dataset_snapshot_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "schema_version_refs",
        "reproducibility_limitations",
    )

    snapshot_id: str
    dataset_id: str
    snapshot_version: str
    snapshot_date: str | None
    version_semantics: str
    authoritative_snapshot_status: str
    immediate_upstream_ref: str | None
    schema_version_refs: tuple[str, ...]
    declared_record_count: int | None
    query_or_filter_scope: str
    reproducibility_limitations: tuple[str, ...]
    status: str

    def __post_init__(self) -> None:
        _safe_identifier(self.snapshot_id, "snapshot_id")
        _safe_identifier(self.dataset_id, "dataset_id")
        if self.immediate_upstream_ref:
            _safe_identifier(self.immediate_upstream_ref, "immediate_upstream_ref")
        if self.declared_record_count is not None and self.declared_record_count < 0:
            raise ValueError("declared_record_count must be non-negative")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalDistributionArtifactRecord(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_distribution_artifact_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("manifest_refs",)

    distribution_id: str
    snapshot_id: str
    media_type: str
    format: str
    byte_size: int | None
    raw_checksum_algorithm: str | None
    raw_checksum_value: str | None
    canonical_content_checksum_algorithm: str | None
    canonical_content_checksum_value: str | None
    access_url_ref: str | None
    local_artifact_ref: str | None
    compression_or_container: str
    manifest_refs: tuple[str, ...]
    security_classification: str
    status: str

    def __post_init__(self) -> None:
        _safe_identifier(self.distribution_id, "distribution_id")
        _safe_identifier(self.snapshot_id, "snapshot_id")
        if self.byte_size is not None and self.byte_size < 0:
            raise ValueError("byte_size must be non-negative")
        if bool(self.raw_checksum_algorithm) != bool(self.raw_checksum_value):
            raise ValueError("raw checksum algorithm and value must be supplied together")
        if bool(self.canonical_content_checksum_algorithm) != bool(self.canonical_content_checksum_value):
            raise ValueError("canonical content checksum algorithm and value must be supplied together")
        if self.local_artifact_ref:
            _validate_relative_path(self.local_artifact_ref, "local_artifact_ref")
        for reference in self.manifest_refs:
            _validate_relative_path(reference, "manifest_ref")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalRetrievalEventRecord(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_retrieval_event_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("source_refs", "parent_artifact_refs")

    retrieval_id: str
    source_system_id: str
    snapshot_id: str
    distribution_id: str
    source_refs: tuple[str, ...]
    retrieval_timestamp: str | None
    access_method: str
    request_query_filter_summary: str
    authentication_mode: str
    authentication_environment_variable: str | None
    client_version: str
    pagination_or_chunking: str
    returned_count: int | None
    missing_count: int | None
    duplicate_count: int | None
    retry_or_cache_policy: str
    code_commit: str
    parent_artifact_refs: tuple[str, ...]
    status: str

    def __post_init__(self) -> None:
        _safe_identifier(self.retrieval_id, "retrieval_id")
        _safe_identifier(self.source_system_id, "source_system_id")
        _safe_identifier(self.snapshot_id, "snapshot_id")
        _safe_identifier(self.distribution_id, "distribution_id")
        if self.authentication_mode not in AUTHENTICATION_REQUIREMENTS:
            raise ValueError(f"unsupported authentication_mode: {self.authentication_mode}")
        if self.authentication_environment_variable is not None and (
            self.authentication_environment_variable not in ALLOWED_CREDENTIAL_ENVIRONMENT_VARIABLES
        ):
            raise ValueError("only approved credential environment-variable names may be persisted")
        if self.authentication_environment_variable is not None and self.authentication_mode not in {
            "optional_api_key",
            "required_api_key",
        }:
            raise ValueError("credential environment variable conflicts with authentication mode")
        if self.authentication_environment_variable is None and self.authentication_mode in {
            "optional_api_key",
            "required_api_key",
        }:
            raise ValueError("API-key authentication must name its environment variable")
        for name, value in (
            ("returned_count", self.returned_count),
            ("missing_count", self.missing_count),
            ("duplicate_count", self.duplicate_count),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for reference in self.parent_artifact_refs:
            _validate_relative_path(reference, "parent_artifact_ref")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalSourceDocumentationRecord(StrictExternalSourceRecord):
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("covered_topics", "limitations")

    documentation_id: str
    source_system_id: str
    title: str
    documentation_kind: str
    authoritative_status: str
    reference: str
    version: str
    publication_or_update_date: str | None
    covered_topics: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _safe_identifier(self.documentation_id, "documentation_id")
        _safe_identifier(self.source_system_id, "source_system_id")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ProvenanceStatusEntry(StrictExternalSourceRecord):
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("evidence_refs", "limitations")

    status: str
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in PROVENANCE_STATUSES:
            raise ValueError(f"unsupported provenance status: {self.status}")
        if not self.evidence_refs:
            raise ValueError("each provenance status requires evidence refs")
        if not self.limitations:
            raise ValueError("each provenance status requires limitations")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalSourceProvenanceAssessment(StrictExternalSourceRecord):
    SCHEMA_ID: ClassVar[str] = "external_source_provenance_assessment_schema_v1"
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("subject_refs", "status_entries", "lineage_refs")

    assessment_id: str
    source_system_id: str
    subject_refs: tuple[str, ...]
    status_entries: tuple[ProvenanceStatusEntry, ...]
    lineage_refs: tuple[str, ...]
    overall_status: str
    trust_score_used: bool = False

    def __post_init__(self) -> None:
        _safe_identifier(self.assessment_id, "assessment_id")
        _safe_identifier(self.source_system_id, "source_system_id")
        normalized = tuple(
            item if isinstance(item, ProvenanceStatusEntry) else ProvenanceStatusEntry.from_mapping(item)
            for item in self.status_entries
        )
        object.__setattr__(self, "status_entries", normalized)
        if self.trust_score_used:
            raise ValueError("external source provenance must not be compressed into a trust score")
        _validate_safe_text(self.to_dict())

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExternalSourceProvenanceAssessment":
        values = dict(payload)
        values["status_entries"] = tuple(
            ProvenanceStatusEntry.from_mapping(item) for item in payload.get("status_entries", ())
        )
        return super().from_mapping(values)


@dataclass(frozen=True)
class ExternalSourceContractSummary(StrictExternalSourceRecord):
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "registered_source_system_ids",
        "actual_dataset_ids",
        "future_declared_source_system_ids",
        "unresolved_snapshot_ids",
        "provenance_assessment_ids",
        "limitations",
    )

    schema_version: str
    status: str
    registered_source_system_ids: tuple[str, ...]
    actual_dataset_ids: tuple[str, ...]
    future_declared_source_system_ids: tuple[str, ...]
    snapshot_count: int
    distribution_count: int
    retrieval_event_count: int
    unresolved_snapshot_ids: tuple[str, ...]
    provenance_assessment_ids: tuple[str, ...]
    no_network_execution: bool
    credentials_persisted: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EXTERNAL_SOURCE_CONTRACT_VERSION:
            raise ValueError(f"unsupported external source contract version: {self.schema_version}")
        if not self.no_network_execution or self.credentials_persisted:
            raise ValueError("v2.4.1 source contract summary violates its execution boundary")
        _validate_safe_text(self.to_dict())


@dataclass(frozen=True)
class ExternalSourcePersistedRecord:
    """Persisted envelope kept separate from runtime typed objects."""

    schema_id: str
    schema_version: str
    record_type: str
    record: Mapping[str, Any]
    canonical_json_sha256: str

    @classmethod
    def from_record(cls, record: StrictExternalSourceRecord) -> "ExternalSourcePersistedRecord":
        payload = record.to_dict()
        return cls(
            schema_id=record.SCHEMA_ID,
            schema_version=EXTERNAL_SOURCE_CONTRACT_VERSION,
            record_type=type(record).__name__,
            record=payload,
            canonical_json_sha256=canonical_json_sha256(payload),
        )

    def __post_init__(self) -> None:
        if self.schema_version != EXTERNAL_SOURCE_CONTRACT_VERSION:
            raise ValueError(f"unsupported future schema version: {self.schema_version}")
        _validate_safe_text(self.record)
        if self.canonical_json_sha256 != canonical_json_sha256(self.record):
            raise ValueError("canonical JSON checksum mismatch")
        _validate_safe_text(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "record_type": self.record_type,
            "record": dict(self.record),
            "canonical_json_sha256": self.canonical_json_sha256,
        }


def build_external_source_system_registry() -> tuple[ExternalSourceSystemRecord, ...]:
    records = (
        ExternalSourceSystemRecord(
            source_system_id="materials_project",
            source_system_version="service_version_unresolved",
            name="Materials Project",
            publisher="Materials Project",
            source_kind="authoritative_api",
            domain_scope=("computed_materials", "crystal_structures", "calculated_properties"),
            official_landing_page="https://materialsproject.org",
            documentation_refs=("https://docs.materialsproject.org",),
            access_modes=("bounded_existing_id_api",),
            authentication_requirement="required_api_key",
            authentication_environment_variable="MP_API_KEY",
            license_or_terms_refs=(),
            update_policy="living_database_snapshot_must_be_recorded_per_retrieval",
            status="actual_bounded_retrieval_evidence",
        ),
        ExternalSourceSystemRecord(
            source_system_id="nasa_battery_kaggle_upstream",
            source_system_version="snapshot_version_unresolved",
            name="NASA-derived Battery Kaggle immediate upstream",
            publisher="patrickfleith Kaggle dataset publisher; NASA lineage asserted but exact official snapshot unresolved",
            source_kind="immediate_upstream_archive",
            domain_scope=("battery_cycle_measurements", "battery_protocol_metadata"),
            official_landing_page="https://www.kaggle.com/datasets/patrickfleith/nasa-battery-dataset",
            documentation_refs=("data/case_studies/kaggle_battery/source.md",),
            access_modes=("local_verified_archive", "kaggle_distribution"),
            authentication_requirement="record_dependent",
            authentication_environment_variable=None,
            license_or_terms_refs=(),
            update_policy="local_archive_checksum_fixed_official_nasa_snapshot_unresolved",
            status="actual_immediate_upstream_evidence",
        ),
        ExternalSourceSystemRecord(
            source_system_id="nist_oar",
            source_system_version="not_audited",
            name="NIST Open Access to Research",
            publisher="National Institute of Standards and Technology",
            source_kind="official_catalog",
            domain_scope=("research_data_catalog", "distribution_discovery"),
            official_landing_page="https://data.nist.gov/od/",
            documentation_refs=(),
            access_modes=("future_declared_only",),
            authentication_requirement="record_dependent",
            authentication_environment_variable=None,
            license_or_terms_refs=(),
            update_policy="future_source_requires_dataset_specific_contract",
            status="future_declared_no_retrieval_or_integration_evidence",
        ),
        ExternalSourceSystemRecord(
            source_system_id="nvd",
            source_system_version="not_audited",
            name="National Vulnerability Database",
            publisher="National Institute of Standards and Technology",
            source_kind="security_database",
            domain_scope=("cve", "cpe", "software_security"),
            official_landing_page="https://nvd.nist.gov/",
            documentation_refs=("https://nvd.nist.gov/developers",),
            access_modes=("future_declared_only",),
            authentication_requirement="optional_api_key",
            authentication_environment_variable="NVD_API_KEY",
            license_or_terms_refs=(),
            update_policy="future_security_source_only",
            status="future_declared_no_retrieval_or_integration_evidence",
        ),
        ExternalSourceSystemRecord(
            source_system_id="nrel_api",
            source_system_version="not_audited",
            name="NREL Developer APIs",
            publisher="National Renewable Energy Laboratory",
            source_kind="energy_system_service",
            domain_scope=("energy_systems", "weather", "grid", "renewables"),
            official_landing_page="https://developer.nrel.gov/",
            documentation_refs=("https://developer.nrel.gov/docs/",),
            access_modes=("future_declared_only",),
            authentication_requirement="required_api_key",
            authentication_environment_variable="NREL_API_KEY",
            license_or_terms_refs=(),
            update_policy="future_dataset_specific_contract_required",
            status="future_declared_no_retrieval_or_integration_evidence",
        ),
    )
    return tuple(sorted(records, key=lambda item: item.source_system_id))


def build_external_dataset_registry() -> tuple[ExternalDatasetRecord, ...]:
    records = (
        ExternalDatasetRecord(
            dataset_id="materials_project_fe_si_existing_id_cohort",
            source_system_id="materials_project",
            title="Materials Project Fe/Si-containing multinary existing-ID cohort",
            description="The 838 existing material IDs used by the released v2.2 structure workflow.",
            domain_contexts=("composition_only_pre_structure", "known_structure_post_relaxation"),
            authoritative_identifier="materials_project_existing_838_ids",
            identifiers=("material_id",),
            publisher="Materials Project",
            citation="Materials Project database; bounded local retrieval evidence recorded by v2.2.4",
            license_or_access_conditions="not_confirmed_in_existing_repository_evidence; raw responses remain local-only",
            expected_resource_types=("summary_document", "crystal_structure"),
            uncertainty_availability="source_does_not_provide_per_record_structure_uncertainty",
            calibration_metadata_availability="not_applicable_to_computed_structure_records",
            status="actual_existing_id_dataset",
        ),
        ExternalDatasetRecord(
            dataset_id="nasa_derived_battery_kaggle_archive",
            source_system_id="nasa_battery_kaggle_upstream",
            title="NASA-derived Battery Kaggle archive",
            description="Immediate upstream archive for the 34-cell Battery PGIR workflow.",
            domain_contexts=("battery_cycle_measurements", "battery_capacity_trajectory"),
            authoritative_identifier="patrickfleith/nasa-battery-dataset",
            identifiers=("kaggle_dataset_slug",),
            publisher="patrickfleith Kaggle dataset publisher",
            citation="Kaggle immediate upstream; exact official NASA snapshot unresolved",
            license_or_access_conditions="unresolved_from_local_package_metadata",
            expected_resource_types=("zip_archive", "metadata_csv", "per_cycle_csv"),
            uncertainty_availability="genuinely_unavailable_in_local_package",
            calibration_metadata_availability="genuinely_unavailable_in_local_package",
            status="actual_immediate_upstream_dataset",
        ),
    )
    return tuple(sorted(records, key=lambda item: item.dataset_id))


def build_external_source_contract_records() -> dict[str, tuple[StrictExternalSourceRecord, ...]]:
    snapshots = (
        ExternalDatasetSnapshotRecord(
            snapshot_id="materials_project_existing_ids_retrieved_2026_07_16",
            dataset_id="materials_project_fe_si_existing_id_cohort",
            snapshot_version="api_database_version_unavailable",
            snapshot_date=None,
            version_semantics="current API documents at retrieval time; not a named database release",
            authoritative_snapshot_status="snapshot_identity_unresolved",
            immediate_upstream_ref=None,
            schema_version_refs=("materials_project_query_plan_schema_v2", "scientific_entity_schema_v2"),
            declared_record_count=838,
            query_or_filter_scope="existing 838 material IDs only; no broad query",
            reproducibility_limitations=(
                "API database version was unavailable for all 838 records",
                "retrieval timestamp does not establish a named dataset publication snapshot",
            ),
            status="actual_bounded_snapshot_scope_with_unresolved_version_identity",
        ),
        ExternalDatasetSnapshotRecord(
            snapshot_id="nasa_battery_kaggle_local_archive_unresolved",
            dataset_id="nasa_derived_battery_kaggle_archive",
            snapshot_version="official_nasa_snapshot_unresolved",
            snapshot_date=None,
            version_semantics="local Kaggle archive identity fixed by checksum; official NASA source snapshot unresolved",
            authoritative_snapshot_status="snapshot_identity_unresolved",
            immediate_upstream_ref="nasa_battery_kaggle_upstream",
            schema_version_refs=("battery_cycle_observation_schema_v1",),
            declared_record_count=34,
            query_or_filter_scope="34 local cell lineages represented by the verified archive",
            reproducibility_limitations=(
                "retrieval timestamp was not recorded",
                "official NASA original snapshot/version is not verifiable from local package metadata",
            ),
            status="actual_local_archive_snapshot_official_identity_unresolved",
        ),
    )
    distributions = (
        ExternalDistributionArtifactRecord(
            distribution_id="materials_project_v2_2_4_api_chunks",
            snapshot_id="materials_project_existing_ids_retrieved_2026_07_16",
            media_type="application/x-ndjson",
            format="jsonl_chunk_set",
            byte_size=None,
            raw_checksum_algorithm=None,
            raw_checksum_value=None,
            canonical_content_checksum_algorithm=None,
            canonical_content_checksum_value=None,
            access_url_ref="Materials Project API materials summary collection",
            local_artifact_ref="outputs/materials_project_structure_v2_2/acquisition/chunks",
            compression_or_container="17 atomic JSONL chunks with per-chunk manifests",
            manifest_refs=(
                "outputs/materials_project_structure_v2_2/acquisition/acquisition_manifest.json",
                "outputs/materials_project_structure_v2_2/acquisition/query_plan.json",
            ),
            security_classification="local_only_raw_api_response",
            status="actual_local_distribution_manifested_per_chunk",
        ),
        ExternalDistributionArtifactRecord(
            distribution_id="nasa_battery_kaggle_zip_archive",
            snapshot_id="nasa_battery_kaggle_local_archive_unresolved",
            media_type="application/zip",
            format="zip",
            byte_size=239496734,
            raw_checksum_algorithm="sha256",
            raw_checksum_value="787ba917fc381c0bd354f515966b1831191ceb5b26985ee8b0000bb6bf96efee",
            canonical_content_checksum_algorithm=None,
            canonical_content_checksum_value=None,
            access_url_ref="https://www.kaggle.com/datasets/patrickfleith/nasa-battery-dataset",
            local_artifact_ref="data/raw/kaggle/patrickfleith_nasa-battery-dataset/nasa-battery-dataset.zip",
            compression_or_container="zip archive",
            manifest_refs=("data/processed/battery_v2_3_5_source_lineage_summary.json",),
            security_classification="local_only_external_raw",
            status="actual_local_archive_checksum_verified",
        ),
    )
    retrievals = (
        ExternalRetrievalEventRecord(
            retrieval_id="materials_project_structure_retrieval_2026_07_16",
            source_system_id="materials_project",
            snapshot_id="materials_project_existing_ids_retrieved_2026_07_16",
            distribution_id="materials_project_v2_2_4_api_chunks",
            source_refs=("materials_project_fe_si_existing_id_cohort",),
            retrieval_timestamp="2026-07-16T08:18:59+00:00",
            access_method="bounded_existing_id_api",
            request_query_filter_summary="838 pre-existing material IDs, 12 allowlisted fields, chunks of 50",
            authentication_mode="required_api_key",
            authentication_environment_variable="MP_API_KEY",
            client_version="unavailable_in_acquisition_manifest",
            pagination_or_chunking="17 deterministic chunks; maximum 838 records",
            returned_count=838,
            missing_count=0,
            duplicate_count=0,
            retry_or_cache_policy="bounded retries and local atomic chunk cache",
            code_commit="unavailable_in_acquisition_manifest",
            parent_artifact_refs=("data/processed/materials_project_v1_3_acquired.csv",),
            status="actual_historical_retrieval_no_network_in_v2_4_1",
        ),
        ExternalRetrievalEventRecord(
            retrieval_id="nasa_battery_kaggle_local_retrieval_unresolved",
            source_system_id="nasa_battery_kaggle_upstream",
            snapshot_id="nasa_battery_kaggle_local_archive_unresolved",
            distribution_id="nasa_battery_kaggle_zip_archive",
            source_refs=("nasa_derived_battery_kaggle_archive",),
            retrieval_timestamp=None,
            access_method="existing_local_archive",
            request_query_filter_summary="retrieval request metadata unavailable; local archive audited by checksum",
            authentication_mode="record_dependent",
            authentication_environment_variable=None,
            client_version="unavailable",
            pagination_or_chunking="not_applicable_to_existing_local_zip",
            returned_count=None,
            missing_count=None,
            duplicate_count=None,
            retry_or_cache_policy="unavailable",
            code_commit="unavailable_for_historical_retrieval",
            parent_artifact_refs=("data/processed/battery_v2_3_5_source_lineage_summary.json",),
            status="historical_retrieval_metadata_incomplete",
        ),
    )
    documents = (
        ExternalSourceDocumentationRecord(
            documentation_id="materials_project_api_docs",
            source_system_id="materials_project",
            title="Materials Project API documentation",
            documentation_kind="api_documentation",
            authoritative_status="publisher_documentation",
            reference="https://docs.materialsproject.org",
            version="living_documentation_version_unresolved",
            publication_or_update_date=None,
            covered_topics=("API access", "materials summary records"),
            limitations=("documentation version does not identify the retrieved dataset snapshot",),
        ),
        ExternalSourceDocumentationRecord(
            documentation_id="nasa_battery_local_source_record",
            source_system_id="nasa_battery_kaggle_upstream",
            title="Kaggle Battery Dataset Source",
            documentation_kind="local_source_lineage_document",
            authoritative_status="immediate_upstream_documentation_only",
            reference="data/case_studies/kaggle_battery/source.md",
            version="v2.3.5",
            publication_or_update_date=None,
            covered_topics=("archive checksum", "metadata checksum", "lineage boundary"),
            limitations=("official NASA original snapshot and license remain unresolved",),
        ),
    )
    provenance = (
        ExternalSourceProvenanceAssessment(
            assessment_id="materials_project_v2_2_4_provenance",
            source_system_id="materials_project",
            subject_refs=(
                "materials_project_existing_ids_retrieved_2026_07_16",
                "materials_project_v2_2_4_api_chunks",
                "materials_project_structure_retrieval_2026_07_16",
            ),
            status_entries=(
                ProvenanceStatusEntry(
                    "authoritative_source_verified",
                    ("outputs/materials_project_structure_v2_2/acquisition/acquisition_manifest.json",),
                    ("official publisher status does not independently validate every computed record",),
                ),
                ProvenanceStatusEntry(
                    "derived_lineage_verified",
                    ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",),
                    ("derived entity, descriptor, and graph bodies remain local-only",),
                ),
                ProvenanceStatusEntry(
                    "snapshot_identity_unresolved",
                    ("data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",),
                    ("API database/source version was unavailable for all 838 records",),
                ),
                ProvenanceStatusEntry(
                    "license_or_terms_unresolved",
                    ("data/case_studies/materials_project/source.md",),
                    ("access terms, license, citation requirements, and publication constraints require separate confirmation",),
                ),
            ),
            lineage_refs=(
                "v1.3_material_ids_to_v2.2.4_api_chunks",
                "api_chunks_to_crystal_structure_entities",
            ),
            overall_status="authoritative_retrieval_with_unresolved_named_snapshot",
        ),
        ExternalSourceProvenanceAssessment(
            assessment_id="nasa_battery_v2_3_5_provenance",
            source_system_id="nasa_battery_kaggle_upstream",
            subject_refs=(
                "nasa_battery_kaggle_local_archive_unresolved",
                "nasa_battery_kaggle_zip_archive",
            ),
            status_entries=(
                ProvenanceStatusEntry(
                    "immediate_upstream_verified",
                    ("data/processed/battery_v2_3_5_source_lineage_summary.json",),
                    ("Kaggle package is an intermediary and not the verified official NASA original",),
                ),
                ProvenanceStatusEntry(
                    "local_copy_checksum_verified",
                    ("data/processed/battery_v2_3_5_source_lineage_summary.json",),
                    ("checksum verifies the local archive bytes only",),
                ),
                ProvenanceStatusEntry(
                    "snapshot_identity_unresolved",
                    ("data/case_studies/kaggle_battery/source.md",),
                    ("official NASA snapshot/version cannot be recovered from local package metadata",),
                ),
                ProvenanceStatusEntry(
                    "official_original_not_locally_verified",
                    ("data/processed/battery_v2_3_5_metadata_recovery_summary.csv",),
                    ("no automatic external download or source substitution was performed",),
                ),
                ProvenanceStatusEntry(
                    "license_or_terms_unresolved",
                    ("data/case_studies/kaggle_battery/source.md",),
                    ("raw data remains local-only and is not redistributed",),
                ),
            ),
            lineage_refs=("verified_kaggle_archive_to_34_battery_trajectories",),
            overall_status="immediate_upstream_verified_official_original_unresolved",
        ),
    )
    return {
        "snapshots": tuple(sorted(snapshots, key=lambda item: item.snapshot_id)),
        "distributions": tuple(sorted(distributions, key=lambda item: item.distribution_id)),
        "retrieval_events": tuple(sorted(retrievals, key=lambda item: item.retrieval_id)),
        "documentation_records": tuple(sorted(documents, key=lambda item: item.documentation_id)),
        "provenance_assessments": tuple(sorted(provenance, key=lambda item: item.assessment_id)),
    }


def build_existing_source_contract_mapping() -> tuple[dict[str, Any], ...]:
    rows = (
        {
            "existing_record": "MaterialsProjectAcquisitionManifest",
            "current_schema_version": "2.2.4",
            "external_source_concept": "RetrievalEvent",
            "mapping_status": "compatible_adapter",
            "missing_fields": ["named_dataset_snapshot_version", "client_version"],
            "compatibility_adapter": "materials_project_acquisition_manifest_to_external_source_v1",
            "migration_required": False,
            "checksum_impact": "none_existing_payload_read_only",
            "backward_compatibility_risk": "low",
        },
        {
            "existing_record": "materials_project_v2_2_4_structure_enrichment_summary",
            "current_schema_version": "2.2.4",
            "external_source_concept": "LocalDerivedArtifact",
            "mapping_status": "compatible_adapter",
            "missing_fields": [],
            "compatibility_adapter": "materials_structure_summary_external_lineage_v1",
            "migration_required": False,
            "checksum_impact": "none_existing_payload_read_only",
            "backward_compatibility_risk": "low",
        },
        {
            "existing_record": "battery_v2_3_5_source_lineage_summary",
            "current_schema_version": "2.3.5",
            "external_source_concept": "DistributionArtifact",
            "mapping_status": "partial",
            "missing_fields": ["retrieval_timestamp", "official_nasa_snapshot_version", "license_or_terms"],
            "compatibility_adapter": "battery_source_lineage_to_external_source_v1",
            "migration_required": False,
            "checksum_impact": "none_existing_payload_read_only",
            "backward_compatibility_risk": "low",
        },
    )
    return tuple(sorted(rows, key=lambda item: item["existing_record"]))


def validate_external_source_registries() -> dict[str, Any]:
    systems = build_external_source_system_registry()
    datasets = build_external_dataset_registry()
    contracts = build_external_source_contract_records()
    errors: list[str] = []
    system_ids = {item.source_system_id for item in systems}
    dataset_ids = {item.dataset_id for item in datasets}
    snapshot_ids = {item.snapshot_id for item in contracts["snapshots"]}
    distribution_ids = {item.distribution_id for item in contracts["distributions"]}
    if len(system_ids) != len(systems):
        errors.append("duplicate_source_system_id")
    if len(dataset_ids) != len(datasets):
        errors.append("duplicate_dataset_id")
    for dataset in datasets:
        if dataset.source_system_id not in system_ids:
            errors.append(f"unknown_source_system:{dataset.dataset_id}")
    for snapshot in contracts["snapshots"]:
        if snapshot.dataset_id not in dataset_ids:
            errors.append(f"unknown_dataset:{snapshot.snapshot_id}")
    for distribution in contracts["distributions"]:
        if distribution.snapshot_id not in snapshot_ids:
            errors.append(f"unknown_snapshot:{distribution.distribution_id}")
    for retrieval in contracts["retrieval_events"]:
        if retrieval.source_system_id not in system_ids:
            errors.append(f"unknown_source_system:{retrieval.retrieval_id}")
        if retrieval.snapshot_id not in snapshot_ids:
            errors.append(f"unknown_snapshot:{retrieval.retrieval_id}")
        if retrieval.distribution_id not in distribution_ids:
            errors.append(f"unknown_distribution:{retrieval.retrieval_id}")
    return {
        "valid": not errors,
        "errors": sorted(errors),
        "source_system_count": len(systems),
        "dataset_count": len(datasets),
        "snapshot_count": len(snapshot_ids),
        "distribution_count": len(distribution_ids),
        "retrieval_event_count": len(contracts["retrieval_events"]),
        "provenance_assessment_count": len(contracts["provenance_assessments"]),
    }


def build_external_source_contract_summary() -> ExternalSourceContractSummary:
    systems = build_external_source_system_registry()
    datasets = build_external_dataset_registry()
    contracts = build_external_source_contract_records()
    future = tuple(item.source_system_id for item in systems if item.status.startswith("future_declared"))
    unresolved = tuple(
        item.snapshot_id
        for item in contracts["snapshots"]
        if item.authoritative_snapshot_status == "snapshot_identity_unresolved"
    )
    return ExternalSourceContractSummary(
        schema_version=EXTERNAL_SOURCE_CONTRACT_VERSION,
        status="versioned_external_source_contract_ready_with_provenance_gaps",
        registered_source_system_ids=tuple(item.source_system_id for item in systems),
        actual_dataset_ids=tuple(item.dataset_id for item in datasets),
        future_declared_source_system_ids=future,
        snapshot_count=len(contracts["snapshots"]),
        distribution_count=len(contracts["distributions"]),
        retrieval_event_count=len(contracts["retrieval_events"]),
        unresolved_snapshot_ids=unresolved,
        provenance_assessment_ids=tuple(item.assessment_id for item in contracts["provenance_assessments"]),
        no_network_execution=True,
        credentials_persisted=False,
        limitations=(
            "source contract is provenance governance, not data-quality certification",
            "official publisher status does not imply independent validation of every record",
            "Materials Project named snapshot and official NASA source snapshot remain unresolved",
        ),
    )


def external_source_registry_payloads() -> dict[str, dict[str, Any]]:
    systems = build_external_source_system_registry()
    datasets = build_external_dataset_registry()
    contracts = build_external_source_contract_records()
    return {
        "external_source_system_registry_v1": {
            "schema_version": EXTERNAL_SOURCE_CONTRACT_VERSION,
            "registry_id": "external_source_system_registry_v1",
            "status": "active_with_future_declared_entries",
            "source_systems": [record.to_dict() for record in systems],
            "validation": validate_external_source_registries(),
        },
        "external_dataset_registry_v1": {
            "schema_version": EXTERNAL_SOURCE_CONTRACT_VERSION,
            "registry_id": "external_dataset_registry_v1",
            "status": "actual_datasets_only",
            "datasets": [record.to_dict() for record in datasets],
        },
        "external_source_contract_registry_v1": {
            "schema_version": EXTERNAL_SOURCE_CONTRACT_VERSION,
            "registry_id": "external_source_contract_registry_v1",
            "status": "active_with_unresolved_snapshot_identities",
            "snapshots": [record.to_dict() for record in contracts["snapshots"]],
            "distributions": [record.to_dict() for record in contracts["distributions"]],
            "retrieval_events": [record.to_dict() for record in contracts["retrieval_events"]],
            "documentation_records": [record.to_dict() for record in contracts["documentation_records"]],
            "provenance_assessments": [record.to_dict() for record in contracts["provenance_assessments"]],
            "existing_contract_mappings": list(build_existing_source_contract_mapping()),
            "future_source_policy": {
                "source_system_ids": ["nist_oar", "nrel_api", "nvd"],
                "retrieval_event_count": 0,
                "dataset_snapshot_count": 0,
                "successful_integration_evidence": False,
            },
            "checksum_policy": {
                "raw_distribution": "raw_byte_checksum_only",
                "logical_json_or_text": "canonical_json_content_checksum",
                "checksums_are_not_interchangeable": True,
            },
        },
    }


def write_external_source_registry_files(repo_root: str | Path = ".") -> tuple[str, ...]:
    """Write the three deterministic tracked registries from typed records."""
    root = Path(repo_root)
    written: list[str] = []
    for registry_id, payload in sorted(external_source_registry_payloads().items()):
        relative_path = f"data/platform/{registry_id}.json"
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        temp.replace(target)
        written.append(relative_path)
    return tuple(written)


def load_and_validate_external_source_contract(path: str | Path) -> ExternalSourcePersistedRecord:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {"schema_id", "schema_version", "record_type", "record", "canonical_json_sha256"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"persisted external source record contains unknown fields: {unknown}")
    return ExternalSourcePersistedRecord(**payload)
