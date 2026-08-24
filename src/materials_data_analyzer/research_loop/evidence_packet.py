"""Canonical cross-provider EvidencePacket v1 contract.

EvidencePacket is an epistemic-ingestion transport contract. It preserves independently
validated scientific context and exact artifact bindings without granting comparability,
execution authority, or scientific promotion by normalization alone.

The core validator is intentionally provider-agnostic. Domain adapters may supply exact
expectations, but the validator never executes a provider and contains no provider-specific
branches.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

EVIDENCE_PACKET_SCHEMA_VERSION = "1.0"
EVIDENCE_PACKET_TYPE = "evidence_packet"

EVIDENCE_KINDS = frozenset(
    {
        "observation",
        "measurement",
        "derived_result",
        "characterization_result",
        "literature_claim",
        "simulation_result",
        "reference_result",
        "planning_metadata",
    }
)
CONTEXT_STATUSES = frozenset({"applicable", "not_applicable", "unknown"})
VALUE_TYPES = frozenset({"number", "integer", "text", "boolean", "json", "null"})
RESULT_VALUE_STATES = frozenset(
    {"observed", "derived", "asserted_reference", "unknown", "not_applicable"}
)
UNCERTAINTY_STATUSES = frozenset(
    {"quantified", "not_quantified", "unknown", "not_applicable"}
)
CALIBRATION_STATUSES = frozenset(
    {"calibrated", "uncalibrated", "unknown", "not_applicable"}
)
OVERLAP_STATUSES = frozenset({"no_known_overlap", "known_overlap", "unknown"})
INDEPENDENCE_CLAIM_STATUSES = frozenset(
    {"not_assessed", "not_independent", "independent_within_stated_dimensions"}
)
VERIFICATION_STATUSES = frozenset({"verified", "limited", "not_verified", "unknown"})
AUTHORITY_SOURCES = frozenset(
    {
        "none",
        "domain_verifier",
        "authority_bearing_epistemic_update",
        "preexisting_authenticated_scientific_record",
    }
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "packet_type",
        "evidence_id",
        "evidence_kind",
        "provider",
        "subject",
        "contexts",
        "results",
        "uncertainty",
        "calibration",
        "source_bindings",
        "derivation_lineage",
        "independence",
        "scientific_validity",
        "comparability",
        "limitations",
        "authority",
        "packet_sha256",
    }
)
_PROVIDER_KEYS = frozenset({"provider_id", "contract_version", "schema_version", "adapter_id"})
_SUBJECT_KEYS = frozenset({"subject_type", "identities", "material_scope", "description"})
_IDENTITY_KEYS = frozenset({"namespace", "value", "role"})
_CONTEXTS_KEYS = frozenset({"process", "sample", "method", "measurement"})
_CONTEXT_BLOCK_KEYS = frozenset({"status", "attributes"})
_ATTRIBUTE_KEYS = frozenset(
    {"name", "value", "value_type", "unit", "source_binding_ids"}
)
_RESULT_KEYS = frozenset(
    {
        "result_id",
        "result_kind",
        "value_state",
        "value",
        "value_type",
        "unit",
        "source_binding_ids",
        "derivation_ids",
        "uncertainty_ids",
        "qualifiers",
    }
)
_UNCERTAINTY_KEYS = frozenset(
    {
        "uncertainty_id",
        "status",
        "kind",
        "value",
        "unit",
        "distribution",
        "confidence_level",
        "source_binding_ids",
        "notes",
    }
)
_CALIBRATION_KEYS = frozenset({"status", "records"})
_CALIBRATION_RECORD_KEYS = frozenset(
    {"calibration_id", "scope", "source_binding_ids", "uncertainty_ids", "notes"}
)
_SOURCE_BINDING_KEYS = frozenset(
    {
        "binding_id",
        "role",
        "artifact_id",
        "locator",
        "sha256",
        "byte_size",
        "media_type",
    }
)
_DERIVATION_KEYS = frozenset(
    {
        "derivation_id",
        "operation",
        "input_binding_ids",
        "input_result_ids",
        "output_result_ids",
        "software",
        "parameters",
        "scientific_status_promoted",
    }
)
_SOFTWARE_KEYS = frozenset({"name", "version", "sha256"})
_INDEPENDENCE_KEYS = frozenset(
    {
        "source_family_id",
        "dataset_parent_id",
        "sample_parent_ids",
        "acquisition_parent_ids",
        "development_family_id",
        "overlap_status",
        "overlap_with",
        "independence_claim_status",
    }
)
_SCIENTIFIC_VALIDITY_KEYS = frozenset(
    {
        "domain_verifier_id",
        "verification_status",
        "validated_scope",
        "excluded_scope",
        "assumptions",
        "scientific_status_promoted",
    }
)
_COMPARABILITY_KEYS = frozenset(
    {
        "status",
        "requirements",
        "limitations",
        "comparison_performed",
        "comparable_claimed",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "empirical_evidence_created",
        "scientific_status_promoted",
        "downstream_use_authorized",
        "planning_metadata_only",
        "row_level_measurement_authority",
        "authority_source",
    }
)
_EXPECTATION_KEYS = frozenset(
    {
        "provider_id",
        "subject_identities",
        "source_bindings",
        "result_units",
        "calibration_status",
        "uncertainty_status_by_id",
        "existing_source_family_ids",
    }
)


class EvidencePacketError(ValueError):
    """Raised when an EvidencePacket widens, invents, or loses scientific authority."""


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic canonical JSON bytes used by EvidencePacket SHA-256 bindings."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidencePacketError("EvidencePacket contains non-canonical JSON content") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidencePacketError(message)


def _exact_keys(value: object, expected: frozenset[str], *, field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    observed = set(value)
    missing = sorted(expected - observed)
    unknown = sorted(observed - expected)
    _require(
        not missing and not unknown,
        f"{field} must use exact keys; unknown={unknown}, missing={missing}",
    )
    return value


def _text(value: object, *, field: str, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    _require(
        isinstance(value, str) and bool(value) and value == value.strip(),
        f"{field} must be exact non-empty text",
    )
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field=field)


def _sha(value: object, *, field: str, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return value


def _text_list(value: object, *, field: str, allow_empty: bool = True) -> list[str]:
    _require(isinstance(value, list), f"{field} must be a list")
    if not allow_empty:
        _require(bool(value), f"{field} must be non-empty")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, field=f"{field}[{index}]")
        assert isinstance(text, str)
        _require(text not in result, f"{field} must not contain duplicates")
        result.append(text)
    return result


def _json_value(value: object, *, field: str) -> None:
    try:
        canonical_json_bytes(value)
    except EvidencePacketError as exc:
        raise EvidencePacketError(f"{field} must contain canonical JSON values") from exc


def _validate_typed_value(value: object, value_type: object, *, field: str) -> None:
    _require(value_type in VALUE_TYPES, f"{field}.value_type is unsupported")
    if value_type == "number":
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{field}.value must be numeric",
        )
        canonical_json_bytes(value)
    elif value_type == "integer":
        _require(
            isinstance(value, int) and not isinstance(value, bool),
            f"{field}.value must be an integer",
        )
    elif value_type == "text":
        _require(isinstance(value, str), f"{field}.value must be text")
    elif value_type == "boolean":
        _require(isinstance(value, bool), f"{field}.value must be boolean")
    elif value_type == "null":
        _require(value is None, f"{field}.value must be null")
    else:
        _json_value(value, field=f"{field}.value")


def _validate_locator(value: object, *, field: str) -> str:
    locator = _text(value, field=field)
    assert isinstance(locator, str)
    path = PurePosixPath(locator)
    _require(not path.is_absolute(), f"{field} must be repository/artifact-relative")
    _require(".." not in path.parts, f"{field} may not traverse parent directories")
    _require("\\" not in locator, f"{field} must use POSIX separators")
    return locator


def _validate_provider(value: object) -> None:
    provider = _exact_keys(value, _PROVIDER_KEYS, field="provider")
    for key in _PROVIDER_KEYS:
        _text(provider.get(key), field=f"provider.{key}")


def _validate_subject(value: object) -> list[dict[str, str]]:
    subject = _exact_keys(value, _SUBJECT_KEYS, field="subject")
    _text(subject.get("subject_type"), field="subject.subject_type")
    _text(subject.get("material_scope"), field="subject.material_scope")
    _optional_text(subject.get("description"), field="subject.description")
    identities = subject.get("identities")
    _require(isinstance(identities, list) and identities, "subject.identities must be non-empty")
    observed: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(identities):
        identity = _exact_keys(item, _IDENTITY_KEYS, field=f"subject.identities[{index}]")
        normalized: dict[str, str] = {}
        for key in _IDENTITY_KEYS:
            text = _text(identity.get(key), field=f"subject.identities[{index}].{key}")
            assert isinstance(text, str)
            normalized[key] = text
        fingerprint = (normalized["namespace"], normalized["value"], normalized["role"])
        _require(fingerprint not in seen, "subject identities must be unique")
        seen.add(fingerprint)
        observed.append(normalized)
    return observed


def _validate_contexts(value: object, binding_ids: set[str]) -> None:
    contexts = _exact_keys(value, _CONTEXTS_KEYS, field="contexts")
    for context_name in sorted(_CONTEXTS_KEYS):
        block = _exact_keys(
            contexts.get(context_name),
            _CONTEXT_BLOCK_KEYS,
            field=f"contexts.{context_name}",
        )
        _require(
            block.get("status") in CONTEXT_STATUSES,
            f"contexts.{context_name}.status is unsupported",
        )
        attributes = block.get("attributes")
        _require(isinstance(attributes, list), f"contexts.{context_name}.attributes must be a list")
        names: set[str] = set()
        for index, item in enumerate(attributes):
            attribute = _exact_keys(
                item,
                _ATTRIBUTE_KEYS,
                field=f"contexts.{context_name}.attributes[{index}]",
            )
            name = _text(
                attribute.get("name"),
                field=f"contexts.{context_name}.attributes[{index}].name",
            )
            assert isinstance(name, str)
            _require(name not in names, f"contexts.{context_name} attribute names must be unique")
            names.add(name)
            _validate_typed_value(
                attribute.get("value"),
                attribute.get("value_type"),
                field=f"contexts.{context_name}.attributes[{index}]",
            )
            unit = attribute.get("unit")
            _require(unit is None or isinstance(unit, str), "context attribute unit must be text or null")
            references = _text_list(
                attribute.get("source_binding_ids"),
                field=f"contexts.{context_name}.attributes[{index}].source_binding_ids",
            )
            _require(set(references) <= binding_ids, "context attribute references unknown source binding")
        if block.get("status") == "not_applicable":
            _require(not attributes, f"contexts.{context_name} not_applicable must not carry attributes")


def _validate_source_bindings(
    value: object,
    *,
    artifacts: Mapping[str, bytes] | None,
) -> tuple[list[dict[str, Any]], set[str]]:
    _require(isinstance(value, list) and value, "source_bindings must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    binding_ids: set[str] = set()
    artifact_ids: set[str] = set()
    for index, item in enumerate(value):
        binding = _exact_keys(item, _SOURCE_BINDING_KEYS, field=f"source_bindings[{index}]")
        binding_id = _text(binding.get("binding_id"), field=f"source_bindings[{index}].binding_id")
        role = _text(binding.get("role"), field=f"source_bindings[{index}].role")
        artifact_id = _text(binding.get("artifact_id"), field=f"source_bindings[{index}].artifact_id")
        locator = _validate_locator(binding.get("locator"), field=f"source_bindings[{index}].locator")
        digest = _sha(binding.get("sha256"), field=f"source_bindings[{index}].sha256")
        size = binding.get("byte_size")
        _require(isinstance(size, int) and not isinstance(size, bool) and size >= 0, "source binding byte_size must be a non-negative integer")
        media_type = _text(binding.get("media_type"), field=f"source_bindings[{index}].media_type")
        assert isinstance(binding_id, str) and isinstance(role, str) and isinstance(artifact_id, str)
        assert isinstance(digest, str) and isinstance(media_type, str)
        _require(binding_id not in binding_ids, "source binding ids must be unique")
        _require(artifact_id not in artifact_ids, "source artifact ids must be role-unique within one packet")
        binding_ids.add(binding_id)
        artifact_ids.add(artifact_id)
        normalized_binding = {
            "binding_id": binding_id,
            "role": role,
            "artifact_id": artifact_id,
            "locator": locator,
            "sha256": digest,
            "byte_size": size,
            "media_type": media_type,
        }
        normalized.append(normalized_binding)
        if artifacts is not None:
            _require(binding_id in artifacts, f"artifact bytes missing for binding {binding_id!r}")
            raw = artifacts[binding_id]
            _require(isinstance(raw, bytes), f"artifact bytes for {binding_id!r} must be bytes")
            _require(len(raw) == size, f"artifact byte size mismatch for binding {binding_id!r}")
            _require(hashlib.sha256(raw).hexdigest() == digest, f"artifact SHA-256 mismatch for binding {binding_id!r}")
    if artifacts is not None:
        _require(set(artifacts) == binding_ids, "artifact byte set must exactly match source binding ids")
    return normalized, binding_ids


def _validate_results(value: object, binding_ids: set[str]) -> tuple[set[str], dict[str, str | None]]:
    _require(isinstance(value, list) and value, "results must be a non-empty list")
    result_ids: set[str] = set()
    units: dict[str, str | None] = {}
    for index, item in enumerate(value):
        result = _exact_keys(item, _RESULT_KEYS, field=f"results[{index}]")
        result_id = _text(result.get("result_id"), field=f"results[{index}].result_id")
        _text(result.get("result_kind"), field=f"results[{index}].result_kind")
        _require(result.get("value_state") in RESULT_VALUE_STATES, f"results[{index}].value_state is unsupported")
        _validate_typed_value(result.get("value"), result.get("value_type"), field=f"results[{index}]")
        if result.get("value_state") in {"unknown", "not_applicable"}:
            _require(result.get("value") is None and result.get("value_type") == "null", f"results[{index}] unknown/not_applicable value must remain null")
        unit = result.get("unit")
        _require(unit is None or isinstance(unit, str), f"results[{index}].unit must be text or null")
        references = _text_list(result.get("source_binding_ids"), field=f"results[{index}].source_binding_ids", allow_empty=False)
        _require(set(references) <= binding_ids, f"results[{index}] references unknown source binding")
        _text_list(result.get("derivation_ids"), field=f"results[{index}].derivation_ids")
        _text_list(result.get("uncertainty_ids"), field=f"results[{index}].uncertainty_ids")
        qualifiers = result.get("qualifiers")
        _require(isinstance(qualifiers, list), f"results[{index}].qualifiers must be a list")
        for qualifier_index, qualifier in enumerate(qualifiers):
            _text(qualifier, field=f"results[{index}].qualifiers[{qualifier_index}]")
        assert isinstance(result_id, str)
        _require(result_id not in result_ids, "result ids must be unique")
        result_ids.add(result_id)
        units[result_id] = unit
    return result_ids, units


def _validate_uncertainty(value: object, binding_ids: set[str]) -> tuple[set[str], dict[str, str]]:
    _require(isinstance(value, list), "uncertainty must be a list")
    ids: set[str] = set()
    statuses: dict[str, str] = {}
    for index, item in enumerate(value):
        record = _exact_keys(item, _UNCERTAINTY_KEYS, field=f"uncertainty[{index}]")
        uncertainty_id = _text(record.get("uncertainty_id"), field=f"uncertainty[{index}].uncertainty_id")
        status = record.get("status")
        _require(status in UNCERTAINTY_STATUSES, f"uncertainty[{index}].status is unsupported")
        _text(record.get("kind"), field=f"uncertainty[{index}].kind")
        if status == "quantified":
            _require(
                isinstance(record.get("value"), (int, float)) and not isinstance(record.get("value"), bool),
                f"uncertainty[{index}] quantified value must be numeric",
            )
            canonical_json_bytes(record.get("value"))
            _text(record.get("unit"), field=f"uncertainty[{index}].unit")
        else:
            _require(record.get("value") is None, f"uncertainty[{index}] non-quantified value must remain null")
            _require(record.get("unit") is None, f"uncertainty[{index}] non-quantified unit must remain null")
        distribution = record.get("distribution")
        _require(distribution is None or isinstance(distribution, str), "uncertainty distribution must be text or null")
        confidence = record.get("confidence_level")
        _require(
            confidence is None
            or (isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0.0 < float(confidence) <= 1.0),
            "uncertainty confidence_level must be null or in (0, 1]",
        )
        if status != "quantified":
            _require(confidence is None and distribution is None, "non-quantified uncertainty may not invent distribution/confidence")
        references = _text_list(record.get("source_binding_ids"), field=f"uncertainty[{index}].source_binding_ids")
        _require(set(references) <= binding_ids, "uncertainty references unknown source binding")
        _optional_text(record.get("notes"), field=f"uncertainty[{index}].notes")
        assert isinstance(uncertainty_id, str) and isinstance(status, str)
        _require(uncertainty_id not in ids, "uncertainty ids must be unique")
        ids.add(uncertainty_id)
        statuses[uncertainty_id] = status
    return ids, statuses


def _validate_calibration(value: object, binding_ids: set[str], uncertainty_ids: set[str]) -> str:
    calibration = _exact_keys(value, _CALIBRATION_KEYS, field="calibration")
    status = calibration.get("status")
    _require(status in CALIBRATION_STATUSES, "calibration.status is unsupported")
    records = calibration.get("records")
    _require(isinstance(records, list), "calibration.records must be a list")
    if status == "calibrated":
        _require(bool(records), "calibrated status requires at least one calibration record")
    if status in {"unknown", "not_applicable", "uncalibrated"}:
        _require(not records, "non-calibrated status may not carry calibration records")
    ids: set[str] = set()
    for index, item in enumerate(records):
        record = _exact_keys(item, _CALIBRATION_RECORD_KEYS, field=f"calibration.records[{index}]")
        calibration_id = _text(record.get("calibration_id"), field=f"calibration.records[{index}].calibration_id")
        _text(record.get("scope"), field=f"calibration.records[{index}].scope")
        source_ids = _text_list(record.get("source_binding_ids"), field=f"calibration.records[{index}].source_binding_ids", allow_empty=False)
        _require(set(source_ids) <= binding_ids, "calibration record references unknown source binding")
        uncertainty_refs = _text_list(record.get("uncertainty_ids"), field=f"calibration.records[{index}].uncertainty_ids")
        _require(set(uncertainty_refs) <= uncertainty_ids, "calibration record references unknown uncertainty")
        _optional_text(record.get("notes"), field=f"calibration.records[{index}].notes")
        assert isinstance(calibration_id, str)
        _require(calibration_id not in ids, "calibration ids must be unique")
        ids.add(calibration_id)
    assert isinstance(status, str)
    return status


def _validate_derivations(
    value: object,
    *,
    binding_ids: set[str],
    result_ids: set[str],
) -> set[str]:
    _require(isinstance(value, list), "derivation_lineage must be a list")
    derivation_ids: set[str] = set()
    for index, item in enumerate(value):
        derivation = _exact_keys(item, _DERIVATION_KEYS, field=f"derivation_lineage[{index}]")
        derivation_id = _text(derivation.get("derivation_id"), field=f"derivation_lineage[{index}].derivation_id")
        _text(derivation.get("operation"), field=f"derivation_lineage[{index}].operation")
        input_bindings = _text_list(derivation.get("input_binding_ids"), field=f"derivation_lineage[{index}].input_binding_ids")
        _require(set(input_bindings) <= binding_ids, "derivation references unknown source binding")
        input_results = _text_list(derivation.get("input_result_ids"), field=f"derivation_lineage[{index}].input_result_ids")
        output_results = _text_list(derivation.get("output_result_ids"), field=f"derivation_lineage[{index}].output_result_ids", allow_empty=False)
        _require(set(input_results) <= result_ids and set(output_results) <= result_ids, "derivation references unknown result")
        software = _exact_keys(derivation.get("software"), _SOFTWARE_KEYS, field=f"derivation_lineage[{index}].software")
        _text(software.get("name"), field=f"derivation_lineage[{index}].software.name")
        _text(software.get("version"), field=f"derivation_lineage[{index}].software.version")
        _sha(software.get("sha256"), field=f"derivation_lineage[{index}].software.sha256", allow_none=True)
        _json_value(derivation.get("parameters"), field=f"derivation_lineage[{index}].parameters")
        _require(derivation.get("scientific_status_promoted") is False, "derivation lineage may not promote scientific status")
        assert isinstance(derivation_id, str)
        _require(derivation_id not in derivation_ids, "derivation ids must be unique")
        derivation_ids.add(derivation_id)
    return derivation_ids


def _validate_result_references(value: Sequence[object], *, derivation_ids: set[str], uncertainty_ids: set[str]) -> None:
    for index, item in enumerate(value):
        assert isinstance(item, Mapping)
        _require(set(item.get("derivation_ids", [])) <= derivation_ids, f"results[{index}] references unknown derivation")
        _require(set(item.get("uncertainty_ids", [])) <= uncertainty_ids, f"results[{index}] references unknown uncertainty")


def _validate_independence(value: object) -> tuple[str | None, str]:
    independence = _exact_keys(value, _INDEPENDENCE_KEYS, field="independence")
    source_family_id = _optional_text(independence.get("source_family_id"), field="independence.source_family_id")
    _optional_text(independence.get("dataset_parent_id"), field="independence.dataset_parent_id")
    _text_list(independence.get("sample_parent_ids"), field="independence.sample_parent_ids")
    _text_list(independence.get("acquisition_parent_ids"), field="independence.acquisition_parent_ids")
    _optional_text(independence.get("development_family_id"), field="independence.development_family_id")
    overlap_status = independence.get("overlap_status")
    claim_status = independence.get("independence_claim_status")
    _require(overlap_status in OVERLAP_STATUSES, "independence.overlap_status is unsupported")
    _text_list(independence.get("overlap_with"), field="independence.overlap_with")
    _require(claim_status in INDEPENDENCE_CLAIM_STATUSES, "independence.independence_claim_status is unsupported")
    if claim_status == "independent_within_stated_dimensions":
        _require(source_family_id is not None, "independence claim requires source_family_id")
        _require(overlap_status == "no_known_overlap", "independence claim requires no_known_overlap")
        _require(not independence.get("overlap_with"), "independence claim may not list overlapping evidence")
    assert isinstance(overlap_status, str)
    return source_family_id, claim_status


def _validate_scientific_validity(value: object) -> Mapping[str, Any]:
    validity = _exact_keys(value, _SCIENTIFIC_VALIDITY_KEYS, field="scientific_validity")
    _optional_text(validity.get("domain_verifier_id"), field="scientific_validity.domain_verifier_id")
    status = validity.get("verification_status")
    _require(status in VERIFICATION_STATUSES, "scientific_validity.verification_status is unsupported")
    _text_list(validity.get("validated_scope"), field="scientific_validity.validated_scope")
    _text_list(validity.get("excluded_scope"), field="scientific_validity.excluded_scope")
    _text_list(validity.get("assumptions"), field="scientific_validity.assumptions")
    _require(isinstance(validity.get("scientific_status_promoted"), bool), "scientific_validity.scientific_status_promoted must be boolean")
    if status == "verified":
        _require(validity.get("domain_verifier_id") is not None, "verified scientific validity requires domain_verifier_id")
    return validity


def _validate_comparability(value: object) -> None:
    comparability = _exact_keys(value, _COMPARABILITY_KEYS, field="comparability")
    _require(comparability.get("status") == "not_assessed", "EvidencePacket v1 comparability must remain not_assessed")
    _text_list(comparability.get("requirements"), field="comparability.requirements")
    _text_list(comparability.get("limitations"), field="comparability.limitations")
    _require(comparability.get("comparison_performed") is False, "EvidencePacket may not perform comparability assessment")
    _require(comparability.get("comparable_claimed") is False, "EvidencePacket may not claim comparability")


def _validate_authority(value: object, *, evidence_kind: str, validity: Mapping[str, Any]) -> Mapping[str, Any]:
    authority = _exact_keys(value, _AUTHORITY_KEYS, field="authority")
    for key in _AUTHORITY_KEYS - {"authority_source"}:
        _require(isinstance(authority.get(key), bool), f"authority.{key} must be boolean")
    authority_source = authority.get("authority_source")
    _require(authority_source in AUTHORITY_SOURCES, "authority.authority_source is unsupported")
    if authority.get("scientific_status_promoted") is True:
        _require(
            authority_source == "authority_bearing_epistemic_update",
            "scientific status promotion requires authority-bearing epistemic update",
        )
    _require(
        validity.get("scientific_status_promoted") == authority.get("scientific_status_promoted"),
        "scientific validity and authority promotion flags disagree",
    )
    if evidence_kind == "simulation_result":
        _require(authority.get("empirical_evidence_created") is False, "simulation evidence may not become empirical evidence")
        _require(authority.get("row_level_measurement_authority") is False, "simulation evidence may not gain row-level measurement authority")
    if evidence_kind == "literature_claim":
        _require(authority.get("row_level_measurement_authority") is False, "literature claim may not become row-level measurement authority")
        _require(authority.get("empirical_evidence_created") is False, "literature claim may not create empirical measurement evidence")
    if evidence_kind == "planning_metadata":
        _require(authority.get("planning_metadata_only") is True, "planning metadata packet must remain planning-only")
        _require(authority.get("empirical_evidence_created") is False, "planning metadata may not create empirical evidence")
        _require(authority.get("scientific_status_promoted") is False, "planning metadata may not promote scientific status")
        _require(authority.get("downstream_use_authorized") is False, "planning metadata may not authorize downstream use")
    if authority.get("empirical_evidence_created") is True:
        _require(
            evidence_kind in {"observation", "measurement", "characterization_result"},
            "empirical evidence flag is incompatible with evidence_kind",
        )
        _require(
            validity.get("verification_status") in {"verified", "limited"}
            and validity.get("domain_verifier_id") is not None,
            "empirical evidence requires an identified domain verifier",
        )
    return authority


def _validate_expectations(
    *,
    expected: Mapping[str, Any] | None,
    packet: Mapping[str, Any],
    normalized_bindings: list[dict[str, Any]],
    subject_identities: list[dict[str, str]],
    result_units: Mapping[str, str | None],
    calibration_status: str,
    uncertainty_statuses: Mapping[str, str],
    source_family_id: str | None,
    independence_claim_status: str,
) -> None:
    if expected is None:
        return
    expected_map = _exact_keys(expected, _EXPECTATION_KEYS, field="validation expectations")
    provider_id = expected_map.get("provider_id")
    if provider_id is not None:
        _require(packet["provider"]["provider_id"] == provider_id, "provider identity substitution detected")
    expected_subject = expected_map.get("subject_identities")
    if expected_subject is not None:
        _require(subject_identities == expected_subject, "material/subject identity substitution detected")
    expected_bindings = expected_map.get("source_bindings")
    if expected_bindings is not None:
        _require(normalized_bindings == expected_bindings, "source role/path/artifact substitution detected")
    expected_units = expected_map.get("result_units")
    if expected_units is not None:
        _require(dict(result_units) == expected_units, "result unit drift detected")
    expected_calibration = expected_map.get("calibration_status")
    if expected_calibration is not None:
        _require(calibration_status == expected_calibration, "calibration status promotion/drift detected")
    expected_uncertainty = expected_map.get("uncertainty_status_by_id")
    if expected_uncertainty is not None:
        _require(dict(uncertainty_statuses) == expected_uncertainty, "uncertainty status promotion/drift detected")
    existing_families = expected_map.get("existing_source_family_ids")
    if existing_families is not None:
        _require(isinstance(existing_families, list), "existing_source_family_ids expectation must be a list")
        if independence_claim_status == "independent_within_stated_dimensions" and source_family_id is not None:
            _require(source_family_id not in existing_families, "duplicated source-family independence claim detected")


def validate_evidence_packet(
    value: object,
    *,
    artifacts: Mapping[str, bytes] | None = None,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one canonical EvidencePacket without executing providers or promoting science."""

    packet = _exact_keys(value, _TOP_LEVEL_KEYS, field="EvidencePacket")
    _require(packet.get("schema_version") == EVIDENCE_PACKET_SCHEMA_VERSION, "unsupported EvidencePacket schema_version")
    _require(packet.get("packet_type") == EVIDENCE_PACKET_TYPE, "unsupported EvidencePacket packet_type")
    _text(packet.get("evidence_id"), field="evidence_id")
    evidence_kind = packet.get("evidence_kind")
    _require(evidence_kind in EVIDENCE_KINDS, "unsupported evidence_kind")
    assert isinstance(evidence_kind, str)

    packet_sha = _sha(packet.get("packet_sha256"), field="packet_sha256")
    unsigned = dict(packet)
    unsigned.pop("packet_sha256", None)
    _require(canonical_sha256(unsigned) == packet_sha, "EvidencePacket self-hash mismatch")

    _validate_provider(packet.get("provider"))
    subject_identities = _validate_subject(packet.get("subject"))
    normalized_bindings, binding_ids = _validate_source_bindings(
        packet.get("source_bindings"), artifacts=artifacts
    )
    _validate_contexts(packet.get("contexts"), binding_ids)
    result_ids, result_units = _validate_results(packet.get("results"), binding_ids)
    uncertainty_ids, uncertainty_statuses = _validate_uncertainty(packet.get("uncertainty"), binding_ids)
    calibration_status = _validate_calibration(packet.get("calibration"), binding_ids, uncertainty_ids)
    derivation_ids = _validate_derivations(
        packet.get("derivation_lineage"), binding_ids=binding_ids, result_ids=result_ids
    )
    results = packet.get("results")
    assert isinstance(results, list)
    _validate_result_references(results, derivation_ids=derivation_ids, uncertainty_ids=uncertainty_ids)
    source_family_id, independence_claim_status = _validate_independence(packet.get("independence"))
    validity = _validate_scientific_validity(packet.get("scientific_validity"))
    _validate_comparability(packet.get("comparability"))
    limitations = _text_list(packet.get("limitations"), field="limitations")
    _require(bool(limitations), "limitations must be explicit and non-empty")
    _validate_authority(packet.get("authority"), evidence_kind=evidence_kind, validity=validity)

    _validate_expectations(
        expected=expected,
        packet=packet,
        normalized_bindings=normalized_bindings,
        subject_identities=subject_identities,
        result_units=result_units,
        calibration_status=calibration_status,
        uncertainty_statuses=uncertainty_statuses,
        source_family_id=source_family_id,
        independence_claim_status=independence_claim_status,
    )
    return copy.deepcopy(dict(packet))


def finalize_evidence_packet(unsigned_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Add the canonical packet SHA without changing any scientific/authority field."""

    _require("packet_sha256" not in unsigned_packet, "unsigned EvidencePacket already has packet_sha256")
    value = copy.deepcopy(dict(unsigned_packet))
    value["packet_sha256"] = canonical_sha256(value)
    return validate_evidence_packet(value)


def normalize_evidence_packet(
    value: object,
    *,
    artifacts: Mapping[str, bytes] | None = None,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a detached validated packet; normalization performs no authority promotion."""

    return validate_evidence_packet(value, artifacts=artifacts, expected=expected)


__all__ = [
    "AUTHORITY_SOURCES",
    "CALIBRATION_STATUSES",
    "CONTEXT_STATUSES",
    "EVIDENCE_KINDS",
    "EVIDENCE_PACKET_SCHEMA_VERSION",
    "EVIDENCE_PACKET_TYPE",
    "EvidencePacketError",
    "INDEPENDENCE_CLAIM_STATUSES",
    "OVERLAP_STATUSES",
    "RESULT_VALUE_STATES",
    "UNCERTAINTY_STATUSES",
    "VERIFICATION_STATUSES",
    "canonical_json_bytes",
    "canonical_sha256",
    "finalize_evidence_packet",
    "normalize_evidence_packet",
    "validate_evidence_packet",
]
