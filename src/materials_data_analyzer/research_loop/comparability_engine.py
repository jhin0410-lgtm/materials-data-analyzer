"""Provider-independent provenance-aware comparability engine.

The engine compares two externally authenticated EvidencePacket objects for one declared claim.
It never creates empirical evidence, infers missing context, transfers calibration, or grants
predictive/engineering authority. Missing required context remains missing.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from .evidence_expectation_trust import validate_authenticated_evidence_packet
from .evidence_packet import canonical_sha256

COMPARABILITY_ASSESSMENT_SCHEMA_VERSION = "1.0"
COMPARABILITY_POLICY_VERSION = "1.0"

COMPARABLE = "COMPARABLE"
CONDITIONALLY_COMPARABLE = "CONDITIONALLY_COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"
UNKNOWN = "UNKNOWN"
ASSESSMENT_OUTCOMES = frozenset(
    {COMPARABLE, CONDITIONALLY_COMPARABLE, NOT_COMPARABLE, UNKNOWN}
)

SATISFIED = "SATISFIED"
CONFLICT = "CONFLICT"
MISSING = "MISSING"
TRANSFORMATION_REQUIRED = "TRANSFORMATION_REQUIRED"
NOT_APPLICABLE = "NOT_APPLICABLE"
DIMENSION_STATUSES = frozenset(
    {SATISFIED, CONFLICT, MISSING, TRANSFORMATION_REQUIRED, NOT_APPLICABLE}
)

TRANSFORMABLE_DIMENSIONS = frozenset({"units_reference_conventions"})

_UNIT_FAMILIES = (
    frozenset({"Pa", "kPa", "MPa", "GPa"}),
    frozenset({"m", "mm", "um", "µm", "nm"}),
    frozenset({"N", "kN"}),
    frozenset({"s", "ms", "us", "µs"}),
    frozenset({"Hz", "kHz", "MHz"}),
)

_CLAIM_KEYS = frozenset(
    {
        "claim_id",
        "claim_type",
        "required_dimensions",
        "irrelevant_dimensions",
        "allowed_transformations",
        "requires_independent_replication",
        "maximum_downstream_use_requested",
    }
)
_ALLOWED_REQUESTED_USES = frozenset(
    {"descriptive", "comparative", "predictive", "engineering"}
)
_ASSESSMENT_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "assessment_type",
        "assessment_status",
        "claim_scope",
        "claim_scope_sha256",
        "rule_registry_sha256",
        "left_packet",
        "right_packet",
        "dimension_results",
        "satisfied_dimensions",
        "conflicting_dimensions",
        "missing_context",
        "required_normalization",
        "independence_relationships",
        "unresolved_independence_relationships",
        "planner_evidence_gaps",
        "maximum_allowed_downstream_use",
        "authority_boundary",
        "assessment_sha256",
    }
)


class ComparabilityEngineError(ValueError):
    """Raised when a comparison would widen or lose scientific authority."""


class ComparabilityRule(NamedTuple):
    dimension: str
    extractor: str
    comparison_mode: str


@dataclass(frozen=True)
class AuthenticatedEvidenceInput:
    packet: Mapping[str, Any]
    artifacts: Mapping[str, bytes]
    expected: Mapping[str, Any]
    trusted_expectation_sha256: str


DEFAULT_RULE_REGISTRY = (
    ComparabilityRule("material_identity", "material_identity", "exact"),
    ComparabilityRule("material_composition", "material_composition", "exact"),
    ComparabilityRule("feedstock_lot_batch", "feedstock_lot_batch", "exact"),
    ComparabilityRule("process_route", "process_route", "exact"),
    ComparabilityRule(
        "thermal_post_treatment_history",
        "thermal_post_treatment_history",
        "exact",
    ),
    ComparabilityRule(
        "build_sample_orientation",
        "build_sample_orientation",
        "exact",
    ),
    ComparabilityRule("geometry", "geometry", "exact"),
    ComparabilityRule(
        "surface_sample_preparation",
        "surface_sample_preparation",
        "exact",
    ),
    ComparabilityRule(
        "sample_acquisition_identity",
        "sample_acquisition_identity",
        "exact",
    ),
    ComparabilityRule("instrument_detector", "instrument_detector", "exact"),
    ComparabilityRule(
        "instrument_state_calibration",
        "instrument_state_calibration",
        "exact",
    ),
    ComparabilityRule(
        "acquisition_parameters",
        "acquisition_parameters",
        "exact",
    ),
    ComparabilityRule(
        "environmental_conditions",
        "environmental_conditions",
        "exact",
    ),
    ComparabilityRule(
        "preprocessing_transformation_history",
        "preprocessing_transformation_history",
        "exact",
    ),
    ComparabilityRule(
        "units_reference_conventions",
        "units_reference_conventions",
        "units",
    ),
    ComparabilityRule(
        "target_response_semantics",
        "target_response_semantics",
        "exact",
    ),
    ComparabilityRule(
        "independence_lineage",
        "independence_lineage",
        "independence",
    ),
    ComparabilityRule(
        "protocol_reference_version",
        "protocol_reference_version",
        "exact",
    ),
)


_CONTEXT_ATTRIBUTE_ALIASES: dict[str, frozenset[str]] = {
    "material_composition": frozenset(
        {
            "composition",
            "chemical_composition",
            "alloy_composition",
            "material_grade",
            "material_specification",
        }
    ),
    "feedstock_lot_batch": frozenset(
        {"feedstock_lot", "powder_lot", "lot", "batch", "feedstock_batch"}
    ),
    "process_route": frozenset(
        {
            "process_route",
            "process_family",
            "manufacturing_process",
            "fabrication_route",
        }
    ),
    "thermal_post_treatment_history": frozenset(
        {
            "heat_treatment",
            "thermal_history",
            "post_treatment",
            "post_process_heat_treatment",
        }
    ),
    "build_sample_orientation": frozenset(
        {"build_orientation", "sample_orientation", "orientation"}
    ),
    "geometry": frozenset(
        {"geometry", "sample_geometry", "specimen_geometry", "feature_geometry"}
    ),
    "surface_sample_preparation": frozenset(
        {
            "surface_preparation",
            "sample_preparation",
            "specimen_preparation",
            "polishing_protocol",
        }
    ),
    "instrument_detector": frozenset(
        {
            "instrument",
            "instrument_id",
            "instrument_family",
            "detector",
            "detector_id",
            "detector_family",
        }
    ),
    "instrument_state_calibration": frozenset(
        {
            "instrument_state",
            "calibration_state",
            "calibration_id",
            "calibration_reference",
        }
    ),
    "acquisition_parameters": frozenset(
        {
            "laser_power",
            "actual_laser_power_w",
            "commanded_laser_power_w",
            "scan_speed",
            "scan_speed_mm_s",
            "wavelength",
            "exposure_time",
            "frame_rate",
            "beam_energy",
            "accelerating_voltage",
            "step_size",
            "pixel_size",
            "acquisition_mode",
        }
    ),
    "environmental_conditions": frozenset(
        {
            "temperature",
            "ambient_temperature",
            "humidity",
            "pressure",
            "atmosphere",
            "environment",
        }
    ),
    "protocol_reference_version": frozenset(
        {
            "protocol",
            "protocol_version",
            "standard",
            "standard_reference",
            "reference_version",
            "method_version",
        }
    ),
    "preprocessing_transformation_history": frozenset(
        {
            "preprocessing",
            "preprocessing_history",
            "transformation_history",
            "data_processing",
            "normalization",
        }
    ),
    "units_reference_conventions": frozenset(
        {"reference_convention", "coordinate_convention", "normalization_reference"}
    ),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparabilityEngineError(message)


def _typed_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return type(observed) is bool and observed is expected
    if isinstance(expected, int):
        return type(observed) is int and observed == expected
    if isinstance(expected, float):
        return type(observed) is float and observed == expected
    if expected is None:
        return observed is None
    if isinstance(expected, str):
        return type(observed) is str and observed == expected
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(observed) == len(expected)
            and all(
                _typed_equal(left, right)
                for left, right in zip(observed, expected, strict=True)
            )
        )
    if isinstance(expected, Mapping):
        return (
            isinstance(observed, Mapping)
            and set(observed) == set(expected)
            and all(_typed_equal(observed[key], expected[key]) for key in expected)
        )
    return type(observed) is type(expected) and observed == expected


def _exact_keys(
    value: object, expected: frozenset[str], *, field: str
) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    observed = set(value)
    _require(
        observed == expected,
        f"{field} must use exact keys; unknown={sorted(observed - expected)}, "
        f"missing={sorted(expected - observed)}",
    )
    return value


def _text(value: object, *, field: str) -> str:
    _require(
        isinstance(value, str) and bool(value) and value == value.strip(),
        f"{field} must be exact non-empty text",
    )
    return value


def _trusted_sha256(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    _require(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text),
        f"{field} must be an external lowercase SHA-256 digest",
    )
    return text


def _unique_text_list(value: object, *, field: str) -> list[str]:
    _require(isinstance(value, list), f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, field=f"{field}[{index}]")
        _require(text not in result, f"{field} must not contain duplicates")
        result.append(text)
    return result


def _serialized_rules(
    rules: Sequence[ComparabilityRule],
) -> list[dict[str, str]]:
    return [
        {
            "dimension": rule.dimension,
            "extractor": rule.extractor,
            "comparison_mode": rule.comparison_mode,
        }
        for rule in rules
    ]


def _validate_rule_registry(
    rules: Sequence[ComparabilityRule],
) -> tuple[ComparabilityRule, ...]:
    _require(bool(rules), "comparability rule registry must be non-empty")
    result: list[ComparabilityRule] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        _require(
            isinstance(rule, ComparabilityRule),
            f"rule_registry[{index}] must be ComparabilityRule",
        )
        _text(rule.dimension, field=f"rule_registry[{index}].dimension")
        _text(rule.extractor, field=f"rule_registry[{index}].extractor")
        _require(
            rule.comparison_mode in {"exact", "units", "independence"},
            f"unsupported comparison mode for {rule.dimension}",
        )
        _require(rule.dimension not in seen, "comparability dimensions must be unique")
        seen.add(rule.dimension)
        result.append(rule)
    normalized = tuple(result)
    _require(
        _typed_equal(
            _serialized_rules(normalized),
            _serialized_rules(DEFAULT_RULE_REGISTRY),
        ),
        "Comparability Engine v1 rule registry is immutable and may not be narrowed or widened",
    )
    return normalized


def _validate_claim_scope(
    value: Mapping[str, Any], rules: Sequence[ComparabilityRule]
) -> dict[str, Any]:
    claim = dict(_exact_keys(value, _CLAIM_KEYS, field="claim_scope"))
    _text(claim.get("claim_id"), field="claim_scope.claim_id")
    _text(claim.get("claim_type"), field="claim_scope.claim_type")
    required = _unique_text_list(
        claim.get("required_dimensions"),
        field="claim_scope.required_dimensions",
    )
    irrelevant = _unique_text_list(
        claim.get("irrelevant_dimensions"),
        field="claim_scope.irrelevant_dimensions",
    )
    transforms = _unique_text_list(
        claim.get("allowed_transformations"),
        field="claim_scope.allowed_transformations",
    )
    _require(
        isinstance(claim.get("requires_independent_replication"), bool),
        "claim_scope.requires_independent_replication must be boolean",
    )
    requested = _text(
        claim.get("maximum_downstream_use_requested"),
        field="claim_scope.maximum_downstream_use_requested",
    )
    _require(
        requested in _ALLOWED_REQUESTED_USES,
        "claim_scope.maximum_downstream_use_requested is unsupported",
    )
    dimensions = {rule.dimension for rule in rules}
    _require(
        set(required).isdisjoint(irrelevant),
        "required and irrelevant dimensions must be disjoint",
    )
    _require(
        set(required) | set(irrelevant) == dimensions,
        "every registered comparability dimension must be required or explicitly irrelevant",
    )
    _require(
        set(transforms) <= set(required),
        "allowed transformations must apply only to required dimensions",
    )
    _require(
        set(transforms) <= TRANSFORMABLE_DIMENSIONS,
        "claim requested a transformation for a non-transformable dimension",
    )
    if claim["requires_independent_replication"] is True:
        _require(
            "independence_lineage" in required,
            "independent-replication claim must require independence_lineage",
        )
    return copy.deepcopy(claim)


def _subject_identity_values(
    packet: Mapping[str, Any],
    role: str,
) -> list[dict[str, str]]:
    identities = packet["subject"]["identities"]
    assert isinstance(identities, list)
    values = [
        {
            "namespace": str(item["namespace"]),
            "value": str(item["value"]),
        }
        for item in identities
        if isinstance(item, Mapping) and item.get("role") == role
    ]
    return sorted(values, key=canonical_sha256)


def _context_values(
    packet: Mapping[str, Any],
    aliases: frozenset[str],
) -> list[dict[str, Any]]:
    contexts = packet["contexts"]
    assert isinstance(contexts, Mapping)
    result: list[dict[str, Any]] = []
    for context_name in sorted(contexts):
        block = contexts[context_name]
        if not isinstance(block, Mapping):
            continue
        attributes = block.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if not isinstance(attribute, Mapping):
                continue
            if attribute.get("name") not in aliases:
                continue
            result.append(
                {
                    "name": attribute.get("name"),
                    "value": copy.deepcopy(attribute.get("value")),
                    "value_type": attribute.get("value_type"),
                    "unit_state": attribute.get("unit_state"),
                    "unit": attribute.get("unit"),
                }
            )
    return sorted(result, key=canonical_sha256)


def _material_identity(packet: Mapping[str, Any]) -> list[dict[str, str]]:
    return _subject_identity_values(packet, "material")


def _sample_acquisition_identity(packet: Mapping[str, Any]) -> dict[str, Any] | None:
    independence = packet["independence"]
    assert isinstance(independence, Mapping)
    subject_samples = _subject_identity_values(packet, "sample")
    sample_parents = independence.get("sample_parent_ids")
    acquisition_parents = independence.get("acquisition_parent_ids")
    if (
        not subject_samples
        or not isinstance(sample_parents, list)
        or not sample_parents
        or not isinstance(acquisition_parents, list)
        or not acquisition_parents
    ):
        return None
    return {
        "subject_sample_ids": subject_samples,
        "sample_parent_ids": sorted(set(str(item) for item in sample_parents)),
        "acquisition_parent_ids": sorted(
            set(str(item) for item in acquisition_parents)
        ),
    }


def _instrument_state_calibration(
    packet: Mapping[str, Any],
) -> dict[str, Any] | None:
    calibration = packet["calibration"]
    assert isinstance(calibration, Mapping)
    status = calibration.get("status")
    instrument_state = _context_values(
        packet,
        _CONTEXT_ATTRIBUTE_ALIASES["instrument_state_calibration"],
    )
    # "unknown" is epistemic absence, not a comparable calibration state.
    if status == "unknown":
        return None

    source_bindings = packet["source_bindings"]
    uncertainty = packet["uncertainty"]
    assert isinstance(source_bindings, list)
    assert isinstance(uncertainty, list)
    binding_by_id = {
        item["binding_id"]: item
        for item in source_bindings
        if isinstance(item, Mapping) and isinstance(item.get("binding_id"), str)
    }
    uncertainty_by_id = {
        item["uncertainty_id"]: item
        for item in uncertainty
        if isinstance(item, Mapping) and isinstance(item.get("uncertainty_id"), str)
    }

    records = calibration.get("records")
    projected_records: list[dict[str, Any]] = []
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, Mapping):
                continue
            referenced_bindings = []
            for binding_id in record.get("source_binding_ids", []):
                bound = binding_by_id.get(binding_id)
                if isinstance(bound, Mapping):
                    referenced_bindings.append(
                        {
                            "binding_id": bound.get("binding_id"),
                            "role": bound.get("role"),
                            "artifact_id": bound.get("artifact_id"),
                            "locator": bound.get("locator"),
                            "sha256": bound.get("sha256"),
                        }
                    )
            referenced_uncertainty = [
                copy.deepcopy(uncertainty_by_id[uncertainty_id])
                for uncertainty_id in record.get("uncertainty_ids", [])
                if uncertainty_id in uncertainty_by_id
            ]
            projected_records.append(
                {
                    "calibration_id": record.get("calibration_id"),
                    "scope": record.get("scope"),
                    "source_bindings": sorted(
                        referenced_bindings,
                        key=canonical_sha256,
                    ),
                    "uncertainty_records": sorted(
                        referenced_uncertainty,
                        key=canonical_sha256,
                    ),
                    "notes": record.get("notes"),
                }
            )
    return {
        "status": status,
        "records": sorted(projected_records, key=canonical_sha256),
        "instrument_state": instrument_state,
    }


def _preprocessing_history(
    packet: Mapping[str, Any],
) -> dict[str, Any] | None:
    lineage = packet["derivation_lineage"]
    assert isinstance(lineage, list)
    context = _context_values(
        packet,
        _CONTEXT_ATTRIBUTE_ALIASES["preprocessing_transformation_history"],
    )
    if not lineage and not context:
        return None
    derivations: list[dict[str, Any]] = []
    for item in lineage:
        assert isinstance(item, Mapping)
        software = item.get("software")
        if not isinstance(software, Mapping):
            software = {}
        derivations.append(
            {
                "operation": item.get("operation"),
                "software_name": software.get("name"),
                "software_version": software.get("version"),
                "software_sha256": software.get("sha256"),
                "parameters": copy.deepcopy(item.get("parameters")),
            }
        )
    return {
        "derivations": derivations,
        "declared_context": context,
    }


def _units_reference_conventions(packet: Mapping[str, Any]) -> dict[str, Any]:
    results = packet["results"]
    assert isinstance(results, list)
    units = sorted(
        [
            {
                "result_kind": item.get("result_kind"),
                "unit_state": item.get("unit_state"),
                "unit": item.get("unit"),
            }
            for item in results
            if isinstance(item, Mapping)
        ],
        key=canonical_sha256,
    )
    return {
        "result_units": units,
        "reference_conventions": _context_values(
            packet,
            _CONTEXT_ATTRIBUTE_ALIASES["units_reference_conventions"],
        ),
    }


def _target_response_semantics(
    packet: Mapping[str, Any],
) -> list[dict[str, str]] | None:
    results = packet["results"]
    assert isinstance(results, list)
    projected: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        value_state = item.get("value_state")
        if value_state in {"unknown", "not_applicable"}:
            return None
        result_kind = item.get("result_kind")
        value_type = item.get("value_type")
        if not isinstance(result_kind, str) or not isinstance(value_type, str):
            return None
        projected.append(
            {
                "result_kind": result_kind,
                "value_state": str(value_state),
                "value_type": value_type,
            }
        )
    return sorted(projected, key=canonical_sha256)


def _independence_lineage(packet: Mapping[str, Any]) -> dict[str, Any]:
    independence = packet["independence"]
    assert isinstance(independence, Mapping)
    return {
        key: copy.deepcopy(independence.get(key))
        for key in (
            "source_family_id",
            "dataset_parent_id",
            "sample_parent_ids",
            "acquisition_parent_ids",
            "development_family_id",
            "overlap_status",
            "overlap_with",
            "independence_claim_status",
        )
    }


def _attribute_extractor(dimension: str):
    aliases = _CONTEXT_ATTRIBUTE_ALIASES[dimension]

    def extract(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
        return _context_values(packet, aliases)

    return extract


_EXTRACTORS = {
    "material_identity": _material_identity,
    "material_composition": _attribute_extractor("material_composition"),
    "feedstock_lot_batch": _attribute_extractor("feedstock_lot_batch"),
    "process_route": _attribute_extractor("process_route"),
    "thermal_post_treatment_history": _attribute_extractor(
        "thermal_post_treatment_history"
    ),
    "build_sample_orientation": _attribute_extractor("build_sample_orientation"),
    "geometry": _attribute_extractor("geometry"),
    "surface_sample_preparation": _attribute_extractor(
        "surface_sample_preparation"
    ),
    "sample_acquisition_identity": _sample_acquisition_identity,
    "instrument_detector": _attribute_extractor("instrument_detector"),
    "instrument_state_calibration": _instrument_state_calibration,
    "acquisition_parameters": _attribute_extractor("acquisition_parameters"),
    "environmental_conditions": _attribute_extractor("environmental_conditions"),
    "preprocessing_transformation_history": _preprocessing_history,
    "units_reference_conventions": _units_reference_conventions,
    "target_response_semantics": _target_response_semantics,
    "independence_lineage": _independence_lineage,
    "protocol_reference_version": _attribute_extractor(
        "protocol_reference_version"
    ),
}


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)) and len(value) == 0:
        return True
    return False


def _contains_unknown_quantitative_unit(value: object) -> bool:
    if isinstance(value, Mapping):
        if (
            value.get("value_type") in {"number", "integer"}
            and value.get("unit_state") == "unknown"
        ):
            return True
        return any(_contains_unknown_quantitative_unit(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unknown_quantitative_unit(item) for item in value)
    return False


def _independence_relationships(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> tuple[dict[str, bool | None], list[str]]:
    relationships: dict[str, bool | None] = {}
    unresolved: list[str] = []
    for field in (
        "source_family_id",
        "dataset_parent_id",
        "development_family_id",
    ):
        left_value = left.get(field)
        right_value = right.get(field)
        if left_value is None or right_value is None:
            relationships[f"same_{field}"] = None
            unresolved.append(field)
        else:
            relationships[f"same_{field}"] = left_value == right_value

    for field in ("sample_parent_ids", "acquisition_parent_ids"):
        left_values = left.get(field)
        right_values = right.get(field)
        if not isinstance(left_values, list) or not isinstance(right_values, list):
            relationships[f"overlap_{field}"] = None
            unresolved.append(field)
        elif not left_values or not right_values:
            relationships[f"overlap_{field}"] = None
            unresolved.append(field)
        else:
            relationships[f"overlap_{field}"] = bool(set(left_values) & set(right_values))
    return relationships, sorted(set(unresolved))


def _evaluate_independence(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    required: bool,
) -> tuple[str, str, dict[str, bool | None], list[str]]:
    relationships, unresolved = _independence_relationships(left, right)
    if not required:
        return (
            NOT_APPLICABLE,
            "Independent replication is explicitly irrelevant to this declared claim.",
            relationships,
            unresolved,
        )
    if any(value is True for value in relationships.values()):
        return (
            CONFLICT,
            "Known shared source/dataset/sample/acquisition/development lineage blocks an independent-replication claim.",
            relationships,
            unresolved,
        )
    left_claim = left.get("independence_claim_status")
    right_claim = right.get("independence_claim_status")
    left_overlap = left.get("overlap_status")
    right_overlap = right.get("overlap_status")
    left_overlap_with = left.get("overlap_with")
    right_overlap_with = right.get("overlap_with")
    if (
        left_claim == "not_independent"
        or right_claim == "not_independent"
        or left_overlap == "known_overlap"
        or right_overlap == "known_overlap"
        or (isinstance(left_overlap_with, list) and bool(left_overlap_with))
        or (isinstance(right_overlap_with, list) and bool(right_overlap_with))
    ):
        return (
            CONFLICT,
            "Authenticated lineage explicitly declares overlap or non-independence.",
            relationships,
            unresolved,
        )
    if unresolved or left_claim != "independent_within_stated_dimensions" or right_claim != "independent_within_stated_dimensions":
        return (
            MISSING,
            "Independence is not established across all required lineage dimensions.",
            relationships,
            unresolved,
        )
    return (
        SATISFIED,
        "Both packets establish independence within stated dimensions and no known lineage overlap was found.",
        relationships,
        unresolved,
    )


def _unit_family(unit: object) -> frozenset[str] | None:
    if not isinstance(unit, str):
        return None
    for family in _UNIT_FAMILIES:
        if unit in family:
            return family
    return None


def _evaluate_units(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    transformation_allowed: bool,
) -> tuple[str, str]:
    left_refs = left.get("reference_conventions")
    right_refs = right.get("reference_conventions")
    if not left_refs or not right_refs:
        return MISSING, "Required reference-convention context is missing."
    if not _typed_equal(left_refs, right_refs):
        return (
            CONFLICT,
            "Reference conventions differ; unit conversion cannot establish reference-frame equivalence.",
        )

    left_units = left.get("result_units")
    right_units = right.get("result_units")
    if not isinstance(left_units, list) or not isinstance(right_units, list):
        return MISSING, "Result-unit context is missing."

    def group(records: list[object]) -> dict[str, list[Mapping[str, Any]]]:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for item in records:
            if not isinstance(item, Mapping):
                continue
            kind = item.get("result_kind")
            if not isinstance(kind, str):
                continue
            grouped.setdefault(kind, []).append(item)
        return grouped

    left_by_kind = group(left_units)
    right_by_kind = group(right_units)
    if set(left_by_kind) != set(right_by_kind):
        return CONFLICT, "Result kinds differ, so unit normalization cannot establish response equivalence."

    transformation_needed = False
    for result_kind in sorted(left_by_kind):
        left_records = left_by_kind[result_kind]
        right_records = right_by_kind[result_kind]
        if len(left_records) != len(right_records):
            return (
                CONFLICT,
                f"Result count differs for {result_kind!r}; unit comparison is ambiguous.",
            )

        if any(record.get("unit_state") == "unknown" for record in left_records + right_records):
            return MISSING, f"Unit state is unknown for {result_kind!r}."

        left_states = sorted(str(record.get("unit_state")) for record in left_records)
        right_states = sorted(str(record.get("unit_state")) for record in right_records)
        if left_states != right_states:
            return CONFLICT, f"Unit-state semantics differ for {result_kind!r}."

        left_specified = sorted(
            str(record.get("unit"))
            for record in left_records
            if record.get("unit_state") == "specified"
        )
        right_specified = sorted(
            str(record.get("unit"))
            for record in right_records
            if record.get("unit_state") == "specified"
        )
        if left_specified == right_specified:
            continue
        if not transformation_allowed or len(left_specified) != len(right_specified):
            return (
                CONFLICT,
                f"Units for {result_kind!r} differ without an allowed exact normalization.",
            )
        for left_unit, right_unit in zip(left_specified, right_specified, strict=True):
            left_family = _unit_family(left_unit)
            right_family = _unit_family(right_unit)
            if left_family is None or right_family is None or left_family != right_family:
                return (
                    CONFLICT,
                    f"Units {left_unit!r} and {right_unit!r} for {result_kind!r} "
                    "lack an explicitly allowed, dimensionally compatible normalization.",
                )
        transformation_needed = True

    if transformation_needed:
        return (
            TRANSFORMATION_REQUIRED,
            "Result units differ only within recognized physical unit families; an explicit normalization is required.",
        )
    return SATISFIED, "All result units and reference conventions agree exactly."


def _packet_binding(packet: Mapping[str, Any]) -> dict[str, Any]:
    bindings = packet["source_bindings"]
    assert isinstance(bindings, list)
    source_bindings = [
        {
            "binding_id": item["binding_id"],
            "role": item["role"],
            "artifact_id": item["artifact_id"],
            "locator": item["locator"],
            "sha256": item["sha256"],
            "byte_size": item["byte_size"],
        }
        for item in bindings
        if isinstance(item, Mapping)
    ]
    return {
        "evidence_id": str(packet["evidence_id"]),
        "packet_sha256": str(packet["packet_sha256"]),
        "provider_id": str(packet["provider"]["provider_id"]),
        "source_bindings": source_bindings,
    }


def assess_comparability(
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    *,
    claim_scope: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
    rule_registry: Sequence[ComparabilityRule] = DEFAULT_RULE_REGISTRY,
) -> dict[str, Any]:
    """Authenticate both packets and the declared claim before comparison."""

    rules = _validate_rule_registry(rule_registry)
    claim = _validate_claim_scope(claim_scope, rules)
    trusted_claim = _trusted_sha256(
        trusted_claim_scope_sha256,
        field="trusted_claim_scope_sha256",
    )
    _require(
        canonical_sha256(claim) == trusted_claim,
        "claim scope does not match the external trust-root SHA-256",
    )
    left_packet = validate_authenticated_evidence_packet(
        left.packet,
        artifacts=left.artifacts,
        expected=left.expected,
        trusted_expectation_sha256=left.trusted_expectation_sha256,
    )
    right_packet = validate_authenticated_evidence_packet(
        right.packet,
        artifacts=right.artifacts,
        expected=right.expected,
        trusted_expectation_sha256=right.trusted_expectation_sha256,
    )

    required = set(claim["required_dimensions"])
    irrelevant = set(claim["irrelevant_dimensions"])
    allowed_transforms = set(claim["allowed_transformations"])

    dimension_results: list[dict[str, Any]] = []
    independence_relationships: dict[str, bool | None] = {}
    unresolved_independence: list[str] = []

    for rule in rules:
        _require(rule.extractor in _EXTRACTORS, f"unknown extractor: {rule.extractor}")
        extractor = _EXTRACTORS[rule.extractor]
        left_value = extractor(left_packet)
        right_value = extractor(right_packet)

        if rule.dimension in irrelevant:
            status = NOT_APPLICABLE
            reason = "Dimension was explicitly declared irrelevant for this claim."
        elif rule.comparison_mode == "independence":
            (
                status,
                reason,
                independence_relationships,
                unresolved_independence,
            ) = _evaluate_independence(
                left_value,
                right_value,
                required=bool(claim["requires_independent_replication"]),
            )
            if (
                rule.dimension in required
                and not claim["requires_independent_replication"]
            ):
                status = SATISFIED
                reason = (
                    "Lineage was assessed, but independent replication is not required "
                    "for this declared claim."
                )
        elif rule.comparison_mode == "units":
            if _is_missing(left_value) or _is_missing(right_value):
                status = MISSING
                reason = "Required unit/reference context is absent on one or both packets."
            else:
                status, reason = _evaluate_units(
                    left_value,
                    right_value,
                    transformation_allowed=rule.dimension in allowed_transforms,
                )
        elif _is_missing(left_value) or _is_missing(right_value):
            status = MISSING
            reason = "Required context is absent on one or both packets."
        elif (
            _contains_unknown_quantitative_unit(left_value)
            or _contains_unknown_quantitative_unit(right_value)
        ):
            status = MISSING
            reason = "Required quantitative context has unknown units."
        elif _typed_equal(left_value, right_value):
            status = SATISFIED
            reason = "Authenticated packet context agrees exactly for this dimension."
        else:
            status = CONFLICT
            reason = "Authenticated packet context conflicts for this required dimension."

        dimension_results.append(
            {
                "dimension": rule.dimension,
                "status": status,
                "reason": reason,
                "left": copy.deepcopy(left_value),
                "right": copy.deepcopy(right_value),
            }
        )

    conflicts = [
        item["dimension"] for item in dimension_results if item["status"] == CONFLICT
    ]
    missing = [
        item["dimension"] for item in dimension_results if item["status"] == MISSING
    ]
    transformations = [
        item["dimension"]
        for item in dimension_results
        if item["status"] == TRANSFORMATION_REQUIRED
    ]
    satisfied = [
        item["dimension"]
        for item in dimension_results
        if item["status"] == SATISFIED
    ]

    if conflicts:
        outcome = NOT_COMPARABLE
        maximum_use = "none"
    elif missing:
        outcome = UNKNOWN
        maximum_use = "none"
    elif transformations:
        outcome = CONDITIONALLY_COMPARABLE
        maximum_use = "conditional_descriptive_comparison_only"
    else:
        outcome = COMPARABLE
        maximum_use = "descriptive_comparison_only"

    planner_evidence_gaps = [
        {
            "requirement_id": f"comparability-context:{dimension}",
            "dimension": dimension,
            "requirement_status": "missing_context",
            "action_class": "evidence_acquisition",
            "scientific_status_promoted": False,
        }
        for dimension in missing
    ]

    rules_payload = _serialized_rules(rules)
    result: dict[str, Any] = {
        "schema_version": COMPARABILITY_ASSESSMENT_SCHEMA_VERSION,
        "policy_version": COMPARABILITY_POLICY_VERSION,
        "assessment_type": "provenance_aware_evidence_comparability",
        "assessment_status": outcome,
        "claim_scope": copy.deepcopy(claim),
        "claim_scope_sha256": canonical_sha256(claim),
        "rule_registry_sha256": canonical_sha256(rules_payload),
        "left_packet": _packet_binding(left_packet),
        "right_packet": _packet_binding(right_packet),
        "dimension_results": dimension_results,
        "satisfied_dimensions": satisfied,
        "conflicting_dimensions": conflicts,
        "missing_context": missing,
        "required_normalization": transformations,
        "independence_relationships": independence_relationships,
        "unresolved_independence_relationships": unresolved_independence,
        "planner_evidence_gaps": planner_evidence_gaps,
        "maximum_allowed_downstream_use": maximum_use,
        "authority_boundary": {
            "empirical_evidence_created": False,
            "scientific_status_promoted": False,
            "comparison_metadata_is_empirical_evidence": False,
            "calibration_transfer_performed": False,
            "missing_context_inferred": False,
            "causal_inference_performed": False,
            "model_fit_performed": False,
            "predictive_use_authorized": False,
            "engineering_use_authorized": False,
        },
    }
    result["assessment_sha256"] = canonical_sha256(result)
    return result


def verify_comparability_assessment(
    value: object,
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    *,
    claim_scope: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
    rule_registry: Sequence[ComparabilityRule] = DEFAULT_RULE_REGISTRY,
) -> dict[str, Any]:
    """Recompute one assessment from authenticated packets and compare exact JSON types."""

    assessment = dict(_exact_keys(value, _ASSESSMENT_KEYS, field="ComparabilityAssessment"))
    digest = assessment.pop("assessment_sha256")
    _require(
        isinstance(digest, str) and len(digest) == 64,
        "ComparabilityAssessment assessment_sha256 must be SHA-256 text",
    )
    _require(
        canonical_sha256(assessment) == digest,
        "ComparabilityAssessment self-hash mismatch",
    )
    assessment["assessment_sha256"] = digest
    expected = assess_comparability(
        left,
        right,
        claim_scope=claim_scope,
        trusted_claim_scope_sha256=trusted_claim_scope_sha256,
        rule_registry=rule_registry,
    )
    _require(
        _typed_equal(assessment, expected),
        "ComparabilityAssessment differs from authenticated recomputation",
    )
    return expected


__all__ = [
    "ASSESSMENT_OUTCOMES",
    "AuthenticatedEvidenceInput",
    "COMPARABLE",
    "COMPARABILITY_ASSESSMENT_SCHEMA_VERSION",
    "COMPARABILITY_POLICY_VERSION",
    "CONDITIONALLY_COMPARABLE",
    "ComparabilityEngineError",
    "ComparabilityRule",
    "DEFAULT_RULE_REGISTRY",
    "DIMENSION_STATUSES",
    "NOT_COMPARABLE",
    "UNKNOWN",
    "assess_comparability",
    "verify_comparability_assessment",
]
