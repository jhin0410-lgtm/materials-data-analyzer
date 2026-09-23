"""Typed planning-only Evidence Provider Contract.

ProviderState normalizes verified domain readiness and unresolved evidence requirements for the
research planner. It is not an EvidencePacket and cannot create empirical/scientific authority.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any

from .characterization_evidence_bridge import (
    build_verified_characterization_planning_requirement,
)
from .comparability_engine import (
    COMPARABLE,
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    UNKNOWN,
    AuthenticatedEvidenceInput,
    verify_comparability_assessment,
)
from .evidence_packet import canonical_sha256

PROVIDER_STATE_SCHEMA_VERSION = "1.0"
PROVIDER_STATE_POLICY_VERSION = "1.0"
PROVIDER_STATE_TYPE = "evidence_provider_state"

REQUIREMENT_ACTION_CLASSES = frozenset(
    {
        "blocked_external",
        "authorization_required",
        "review_required",
        "evidence_acquisition",
        "analysis",
        "simulation",
        "engineering_validation",
    }
)
READINESS_STATUSES = frozenset({"ready", "limited", "blocked", "unknown"})
BINDING_KINDS = frozenset({"artifact_sha256", "canonical_object_sha256"})

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "provider_state_type",
        "provider",
        "domain",
        "modality",
        "subject_scope",
        "source_bindings",
        "readiness",
        "unresolved_requirements",
        "authority_boundary",
        "provider_state_sha256",
    }
)
_PROVIDER_KEYS = frozenset(
    {"provider_id", "contract_version", "schema_version", "adapter_id"}
)
_BINDING_KEYS = frozenset(
    {"binding_id", "role", "sha256", "binding_kind", "locator"}
)
_READINESS_KEYS = frozenset(
    {"status", "maturity_label", "maturity_index", "first_blocker"}
)
_REQUIREMENT_KEYS = frozenset(
    {
        "requirement_id",
        "requirement_class",
        "action_class",
        "description",
        "status",
        "source_binding_ids",
        "automatic_execution_authorized",
        "scientific_status_promoted",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "planning_metadata_only",
        "empirical_evidence_created",
        "scientific_status_promoted",
        "downstream_use_authorized",
        "execution_authorized",
    }
)
_AGGREGATE_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "aggregate_type",
        "provider_state_sha256s",
        "requirements",
        "composite_binding_sha256",
        "authority_boundary",
        "aggregate_sha256",
    }
)

_AGGREGATE_PROVIDER_STATE_KEYS = frozenset(
    {"provider_id", "provider_state_sha256"}
)
_AGGREGATE_REQUIREMENT_KEYS = frozenset(
    {
        "aggregate_requirement_id",
        "provider_id",
        "provider_state_sha256",
        "requirement",
    }
)


class EvidenceProviderContractError(ValueError):
    """Raised when provider planning state widens or loses its trust boundary."""


@dataclass(frozen=True)
class AuthenticatedProviderStateInput:
    """One ProviderState plus an independently obtained complete-state SHA-256 root."""

    state: Mapping[str, Any]
    trusted_provider_state_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceProviderContractError(message)


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


def _optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field=field)


def _sha(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    _require(
        len(text) == 64 and all(character in "0123456789abcdef" for character in text),
        f"{field} must be lowercase SHA-256",
    )
    return text


def _typed_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return type(observed) is bool and observed is expected
    if isinstance(expected, int):
        return type(observed) is int and observed == expected
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


def _authority_boundary() -> dict[str, bool]:
    return {
        "planning_metadata_only": True,
        "empirical_evidence_created": False,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "execution_authorized": False,
    }


def _validate_binding(value: object, *, index: int) -> dict[str, Any]:
    binding = _exact_keys(
        value, _BINDING_KEYS, field=f"source_bindings[{index}]"
    )
    result = {
        "binding_id": _text(
            binding.get("binding_id"),
            field=f"source_bindings[{index}].binding_id",
        ),
        "role": _text(
            binding.get("role"),
            field=f"source_bindings[{index}].role",
        ),
        "sha256": _sha(
            binding.get("sha256"),
            field=f"source_bindings[{index}].sha256",
        ),
        "binding_kind": _text(
            binding.get("binding_kind"),
            field=f"source_bindings[{index}].binding_kind",
        ),
        "locator": _optional_text(
            binding.get("locator"),
            field=f"source_bindings[{index}].locator",
        ),
    }
    _require(
        result["binding_kind"] in BINDING_KINDS,
        f"source_bindings[{index}].binding_kind is unsupported",
    )
    return result


def _validate_readiness(value: object) -> dict[str, Any]:
    readiness = _exact_keys(value, _READINESS_KEYS, field="readiness")
    status = _text(readiness.get("status"), field="readiness.status")
    _require(status in READINESS_STATUSES, "readiness.status is unsupported")
    label = _optional_text(
        readiness.get("maturity_label"), field="readiness.maturity_label"
    )
    index = readiness.get("maturity_index")
    _require(
        index is None or (type(index) is int and index >= 0),
        "readiness.maturity_index must be null or an exact non-negative integer",
    )
    blocker = _optional_text(
        readiness.get("first_blocker"), field="readiness.first_blocker"
    )
    if status == "ready":
        _require(blocker is None, "ready provider state may not retain a first blocker")
    return {
        "status": status,
        "maturity_label": label,
        "maturity_index": index,
        "first_blocker": blocker,
    }


def _validate_requirement(
    value: object,
    *,
    index: int,
    binding_ids: set[str],
) -> dict[str, Any]:
    requirement = _exact_keys(
        value, _REQUIREMENT_KEYS, field=f"unresolved_requirements[{index}]"
    )
    requirement_id = _text(
        requirement.get("requirement_id"),
        field=f"unresolved_requirements[{index}].requirement_id",
    )
    requirement_class = _text(
        requirement.get("requirement_class"),
        field=f"unresolved_requirements[{index}].requirement_class",
    )
    action_class = _text(
        requirement.get("action_class"),
        field=f"unresolved_requirements[{index}].action_class",
    )
    _require(
        requirement_class in REQUIREMENT_ACTION_CLASSES,
        f"unresolved_requirements[{index}].requirement_class is unsupported",
    )
    _require(
        action_class in REQUIREMENT_ACTION_CLASSES,
        f"unresolved_requirements[{index}].action_class is unsupported",
    )
    description = _text(
        requirement.get("description"),
        field=f"unresolved_requirements[{index}].description",
    )
    status = _text(
        requirement.get("status"),
        field=f"unresolved_requirements[{index}].status",
    )
    _require(
        status == "unresolved",
        f"unresolved_requirements[{index}].status must remain unresolved",
    )
    refs = requirement.get("source_binding_ids")
    _require(
        isinstance(refs, list)
        and all(isinstance(item, str) and item for item in refs),
        f"unresolved_requirements[{index}].source_binding_ids must be text list",
    )
    _require(
        len(set(refs)) == len(refs),
        f"unresolved_requirements[{index}].source_binding_ids contain duplicates",
    )
    _require(
        set(refs) <= binding_ids,
        f"unresolved_requirements[{index}] references unknown source binding",
    )
    _require(
        requirement.get("automatic_execution_authorized") is False,
        "provider requirement may not authorize automatic execution",
    )
    _require(
        requirement.get("scientific_status_promoted") is False,
        "provider requirement may not promote scientific status",
    )
    return {
        "requirement_id": requirement_id,
        "requirement_class": requirement_class,
        "action_class": action_class,
        "description": description,
        "status": status,
        "source_binding_ids": list(refs),
        "automatic_execution_authorized": False,
        "scientific_status_promoted": False,
    }


def validate_provider_state(value: object) -> dict[str, Any]:
    """Validate exact provider planning state and its self-hash fail-closed."""

    root = dict(_exact_keys(value, _TOP_LEVEL_KEYS, field="ProviderState"))
    digest = _sha(root.pop("provider_state_sha256"), field="provider_state_sha256")
    _require(
        canonical_sha256(root) == digest,
        "ProviderState self-hash mismatch",
    )
    root["provider_state_sha256"] = digest

    _require(
        root.get("schema_version") == PROVIDER_STATE_SCHEMA_VERSION,
        "unsupported ProviderState schema_version",
    )
    _require(
        root.get("policy_version") == PROVIDER_STATE_POLICY_VERSION,
        "unsupported ProviderState policy_version",
    )
    _require(
        root.get("provider_state_type") == PROVIDER_STATE_TYPE,
        "unsupported provider_state_type",
    )
    provider = _exact_keys(root.get("provider"), _PROVIDER_KEYS, field="provider")
    for key in _PROVIDER_KEYS:
        _text(provider.get(key), field=f"provider.{key}")
    _text(root.get("domain"), field="domain")
    _text(root.get("modality"), field="modality")
    _text(root.get("subject_scope"), field="subject_scope")

    raw_bindings = root.get("source_bindings")
    _require(
        isinstance(raw_bindings, list) and raw_bindings,
        "source_bindings must be a non-empty list",
    )
    bindings = [
        _validate_binding(item, index=index)
        for index, item in enumerate(raw_bindings)
    ]
    binding_ids = [item["binding_id"] for item in bindings]
    _require(
        len(set(binding_ids)) == len(binding_ids),
        "ProviderState source binding ids must be unique",
    )

    readiness = _validate_readiness(root.get("readiness"))
    raw_requirements = root.get("unresolved_requirements")
    _require(
        isinstance(raw_requirements, list),
        "unresolved_requirements must be a list",
    )
    requirements = [
        _validate_requirement(
            item,
            index=index,
            binding_ids=set(binding_ids),
        )
        for index, item in enumerate(raw_requirements)
    ]
    requirement_ids = [item["requirement_id"] for item in requirements]
    _require(
        len(set(requirement_ids)) == len(requirement_ids),
        "ProviderState requirement ids must be unique",
    )
    if readiness["status"] == "ready":
        _require(
            not requirements,
            "ready ProviderState may not contain unresolved requirements",
        )

    boundary = _exact_keys(
        root.get("authority_boundary"),
        _AUTHORITY_KEYS,
        field="authority_boundary",
    )
    _require(
        _typed_equal(boundary, _authority_boundary()),
        "ProviderState authority boundary drifted",
    )
    return copy.deepcopy(root)


def finalize_provider_state(unsigned_state: Mapping[str, Any]) -> dict[str, Any]:
    _require(
        "provider_state_sha256" not in unsigned_state,
        "unsigned ProviderState already contains provider_state_sha256",
    )
    value = copy.deepcopy(dict(unsigned_state))
    value["provider_state_sha256"] = canonical_sha256(value)
    return validate_provider_state(value)


_ACTION_CLASS_MAP = {
    "existing_data_reanalysis": "analysis",
    "sensitivity_analysis": "analysis",
    "analysis": "analysis",
    "simulation": "simulation",
    "external_evidence_search": "evidence_acquisition",
    "evidence_acquisition": "evidence_acquisition",
    "replication": "evidence_acquisition",
    "physical_experiment_design": "engineering_validation",
    "engineering_validation": "engineering_validation",
    "manual_review": "review_required",
    "review_required": "review_required",
    "authorization_required": "authorization_required",
    "blocked_external": "blocked_external",
}


def _generic_action_class(value: object) -> str:
    if isinstance(value, str) and value in _ACTION_CLASS_MAP:
        return _ACTION_CLASS_MAP[value]
    return "review_required"


def adapt_characterization_provider_state(
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize independently reverified characterization maturity as planning-only state."""

    projection = build_verified_characterization_planning_requirement(assessment)
    verified = projection["verified_assessment"]
    requirement_projection = projection["planning_requirement"]
    action_projection = projection["planning_action"]

    bindings: list[dict[str, Any]] = [
        {
            "binding_id": "characterization-assessment",
            "role": "verified_characterization_assessment",
            "sha256": verified["assessment_sha256"],
            "binding_kind": "canonical_object_sha256",
            "locator": None,
        },
    ]
    for index, source in enumerate(verified["source_bindings"]):
        bindings.append(
            {
                "binding_id": f"characterization-source-{index}",
                "role": source["role"],
                "sha256": source["sha256"],
                "binding_kind": "artifact_sha256",
                "locator": None,
            }
        )

    requirements: list[dict[str, Any]] = []
    if requirement_projection is not None:
        _require(
            isinstance(requirement_projection, Mapping)
            and isinstance(action_projection, Mapping),
            "characterization planning projection is malformed",
        )
        action_class = _generic_action_class(action_projection.get("action_class"))
        requirements.append(
            {
                "requirement_id": _text(
                    requirement_projection.get("gap_id"),
                    field="characterization planning requirement.gap_id",
                ),
                "requirement_class": action_class,
                "action_class": action_class,
                "description": _text(
                    requirement_projection.get("requirement"),
                    field="characterization planning requirement.requirement",
                ),
                "status": "unresolved",
                "source_binding_ids": ["characterization-assessment"],
                "automatic_execution_authorized": False,
                "scientific_status_promoted": False,
            }
        )

    subject = verified["subject"]
    assert isinstance(subject, Mapping)
    highest = verified["highest_supported_level"]
    blocker = verified["first_blocking_level"]
    status = "ready" if blocker is None else "blocked"
    return finalize_provider_state(
        {
            "schema_version": PROVIDER_STATE_SCHEMA_VERSION,
            "policy_version": PROVIDER_STATE_POLICY_VERSION,
            "provider_state_type": PROVIDER_STATE_TYPE,
            "provider": {
                "provider_id": "characterization-evidence-ladder",
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": "verified-characterization-provider-state-v1",
            },
            "domain": "characterization",
            "modality": _text(subject.get("modality"), field="characterization modality"),
            "subject_scope": (
                f"{_text(subject.get('target_material_domain'), field='target material domain')} | "
                f"{_text(subject.get('claim_scope'), field='claim scope')}"
            ),
            "source_bindings": bindings,
            "readiness": {
                "status": status,
                "maturity_label": highest,
                "maturity_index": (
                    None
                    if verified["highest_supported_index"] < 0
                    else verified["highest_supported_index"]
                ),
                "first_blocker": blocker,
            },
            "unresolved_requirements": requirements,
            "authority_boundary": _authority_boundary(),
        }
    )


def verify_characterization_provider_state(
    value: object,
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute a characterization ProviderState from the independently verified assessment."""

    supplied = validate_provider_state(value)
    expected = adapt_characterization_provider_state(assessment)
    _require(
        _typed_equal(supplied, expected),
        "characterization ProviderState differs from verified domain recomputation",
    )
    return expected


def adapt_authenticated_planning_gaps(
    state: Mapping[str, Any],
    *,
    trusted_state_sha256: str,
) -> dict[str, Any]:
    """Normalize externally hash-authenticated unresolved planner gaps without reinterpreting them."""

    trusted = _sha(trusted_state_sha256, field="trusted_state_sha256")
    _require(
        canonical_sha256(state) == trusted,
        "planning state does not match external trust-root SHA-256",
    )
    provider = "validated-recursive-planning"
    gaps = state.get("unresolved_evidence_gaps")
    _require(
        isinstance(gaps, list),
        "authenticated planning state unresolved_evidence_gaps must be a list",
    )
    binding_id = "authenticated-planning-state"
    requirements: list[dict[str, Any]] = []
    for index, raw in enumerate(gaps):
        _require(
            isinstance(raw, Mapping),
            f"unresolved_evidence_gaps[{index}] must be an object",
        )
        description_raw = raw.get("requirement")
        if not isinstance(description_raw, str) or not description_raw.strip():
            description_raw = raw.get("description")
        description = _text(
            description_raw,
            field=f"unresolved_evidence_gaps[{index}] requirement/description",
        )
        raw_id = raw.get("gap_id")
        if isinstance(raw_id, str) and raw_id.strip():
            requirement_id = raw_id.strip()
        else:
            requirement_id = f"planning-gap:{canonical_sha256(raw)[:16]}"
        action_class = _generic_action_class(
            raw.get("action_class", raw.get("action_class_hint"))
        )
        requirements.append(
            {
                "requirement_id": requirement_id,
                "requirement_class": action_class,
                "action_class": action_class,
                "description": description,
                "status": "unresolved",
                "source_binding_ids": [binding_id],
                "automatic_execution_authorized": False,
                "scientific_status_promoted": False,
            }
        )

    return finalize_provider_state(
        {
            "schema_version": PROVIDER_STATE_SCHEMA_VERSION,
            "policy_version": PROVIDER_STATE_POLICY_VERSION,
            "provider_state_type": PROVIDER_STATE_TYPE,
            "provider": {
                "provider_id": provider,
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": "authenticated-planning-gap-provider-state-v1",
            },
            "domain": "orchestrator_planning",
            "modality": "unresolved_evidence_gap_state",
            "subject_scope": "externally_hash_authenticated_planning_context",
            "source_bindings": [
                {
                    "binding_id": binding_id,
                    "role": "authenticated_planning_state",
                    "sha256": trusted,
                    "binding_kind": "canonical_object_sha256",
                    "locator": None,
                }
            ],
            "readiness": {
                "status": "blocked" if requirements else "ready",
                "maturity_label": None,
                "maturity_index": None,
                "first_blocker": (
                    requirements[0]["requirement_id"] if requirements else None
                ),
            },
            "unresolved_requirements": requirements,
            "authority_boundary": _authority_boundary(),
        }
    )


def verify_authenticated_planning_provider_state(
    value: object,
    state: Mapping[str, Any],
    *,
    trusted_state_sha256: str,
) -> dict[str, Any]:
    """Recompute one planning-gap ProviderState from the externally bound planning state."""

    supplied = validate_provider_state(value)
    expected = adapt_authenticated_planning_gaps(
        state,
        trusted_state_sha256=trusted_state_sha256,
    )
    _require(
        _typed_equal(supplied, expected),
        "planning ProviderState differs from authenticated state recomputation",
    )
    return expected


def _comparability_side_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)) and len(value) == 0:
        return True

    def has_unknown_quantitative_unit(item: object) -> bool:
        if isinstance(item, Mapping):
            if (
                item.get("value_type") in {"number", "integer"}
                and item.get("unit_state") == "unknown"
            ):
                return True
            return any(
                has_unknown_quantitative_unit(nested)
                for nested in item.values()
            )
        if isinstance(item, (list, tuple, set)):
            return any(has_unknown_quantitative_unit(nested) for nested in item)
        return False

    return has_unknown_quantitative_unit(value)

def adapt_verified_comparability_provider_state(
    assessment: Mapping[str, Any],
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    *,
    claim_scope: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
) -> dict[str, Any]:
    """Project one independently recomputed comparability assessment into planning state.

    Only missing scientific context becomes an evidence-acquisition requirement. A verified
    physical/context conflict is *not* rewritten as a missing-evidence gap, and a conditional
    normalization requirement remains a limited-readiness blocker rather than silently
    authorizing a transformation.
    """

    verified = verify_comparability_assessment(
        assessment,
        left,
        right,
        claim_scope=claim_scope,
        trusted_claim_scope_sha256=trusted_claim_scope_sha256,
    )
    outcome = _text(
        verified.get("assessment_status"),
        field="comparability assessment_status",
    )
    _require(
        outcome in {COMPARABLE, CONDITIONALLY_COMPARABLE, NOT_COMPARABLE, UNKNOWN},
        "comparability assessment_status is unsupported",
    )

    assessment_sha = _sha(
        verified.get("assessment_sha256"),
        field="comparability assessment_sha256",
    )
    claim_sha = _sha(
        verified.get("claim_scope_sha256"),
        field="comparability claim_scope_sha256",
    )
    claim = _exact_keys(
        verified.get("claim_scope"),
        frozenset(
            {
                "claim_id",
                "claim_type",
                "required_dimensions",
                "irrelevant_dimensions",
                "allowed_transformations",
                "requires_independent_replication",
                "maximum_downstream_use_requested",
            }
        ),
        field="comparability claim_scope",
    )
    claim_id = _text(claim.get("claim_id"), field="comparability claim_scope.claim_id")

    left_packet = _exact_keys(
        verified.get("left_packet"),
        frozenset(
            {
                "evidence_id",
                "packet_sha256",
                "provider_id",
                "source_bindings",
            }
        ),
        field="comparability left_packet",
    )
    right_packet = _exact_keys(
        verified.get("right_packet"),
        frozenset(
            {
                "evidence_id",
                "packet_sha256",
                "provider_id",
                "source_bindings",
            }
        ),
        field="comparability right_packet",
    )
    left_evidence_id = _text(
        left_packet.get("evidence_id"),
        field="comparability left_packet.evidence_id",
    )
    right_evidence_id = _text(
        right_packet.get("evidence_id"),
        field="comparability right_packet.evidence_id",
    )

    bindings: list[dict[str, Any]] = [
        {
            "binding_id": "comparability-assessment",
            "role": "verified_comparability_assessment",
            "sha256": assessment_sha,
            "binding_kind": "canonical_object_sha256",
            "locator": None,
        },
        {
            "binding_id": "comparability-claim-scope",
            "role": "authenticated_comparison_claim_scope",
            "sha256": claim_sha,
            "binding_kind": "canonical_object_sha256",
            "locator": None,
        },
        {
            "binding_id": "comparability-left-packet",
            "role": "authenticated_left_evidence_packet",
            "sha256": _sha(
                left_packet.get("packet_sha256"),
                field="comparability left_packet.packet_sha256",
            ),
            "binding_kind": "canonical_object_sha256",
            "locator": None,
        },
        {
            "binding_id": "comparability-right-packet",
            "role": "authenticated_right_evidence_packet",
            "sha256": _sha(
                right_packet.get("packet_sha256"),
                field="comparability right_packet.packet_sha256",
            ),
            "binding_kind": "canonical_object_sha256",
            "locator": None,
        },
    ]

    for side, packet in (("left", left_packet), ("right", right_packet)):
        raw_sources = packet.get("source_bindings")
        _require(
            isinstance(raw_sources, list),
            f"comparability {side}_packet.source_bindings must be a list",
        )
        for index, raw in enumerate(raw_sources):
            _require(
                isinstance(raw, Mapping),
                f"comparability {side}_packet.source_bindings[{index}] must be an object",
            )
            bindings.append(
                {
                    "binding_id": f"comparability-{side}-source-{index}",
                    "role": f"authenticated_{side}_source_artifact",
                    "sha256": _sha(
                        raw.get("sha256"),
                        field=f"comparability {side} source[{index}].sha256",
                    ),
                    "binding_kind": "artifact_sha256",
                    "locator": _optional_text(
                        raw.get("locator"),
                        field=f"comparability {side} source[{index}].locator",
                    ),
                }
            )

    gaps = verified.get("planner_evidence_gaps")
    _require(
        isinstance(gaps, list),
        "comparability planner_evidence_gaps must be a list",
    )
    missing = verified.get("missing_context")
    conflicts = verified.get("conflicting_dimensions")
    normalization = verified.get("required_normalization")
    _require(
        isinstance(missing, list)
        and all(isinstance(item, str) and item for item in missing),
        "comparability missing_context must be a text list",
    )
    _require(
        isinstance(conflicts, list)
        and all(isinstance(item, str) and item for item in conflicts),
        "comparability conflicting_dimensions must be a text list",
    )
    _require(
        isinstance(normalization, list)
        and all(isinstance(item, str) and item for item in normalization),
        "comparability required_normalization must be a text list",
    )

    dimension_results = verified.get("dimension_results")
    _require(
        isinstance(dimension_results, list),
        "comparability dimension_results must be a list",
    )
    dimension_by_name: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(dimension_results):
        _require(
            isinstance(raw, Mapping),
            f"comparability dimension_results[{index}] must be an object",
        )
        dimension_name = _text(
            raw.get("dimension"),
            field=f"comparability dimension_results[{index}].dimension",
        )
        _require(
            dimension_name not in dimension_by_name,
            "comparability dimension_results contain duplicate dimensions",
        )
        dimension_by_name[dimension_name] = raw

    requirements: list[dict[str, Any]] = []
    verified_missing_gaps: list[tuple[str, str, tuple[str, ...]]] = []
    for index, raw in enumerate(gaps):
        _require(
            isinstance(raw, Mapping),
            f"comparability planner_evidence_gaps[{index}] must be an object",
        )
        gap_id = _text(
            raw.get("requirement_id"),
            field=f"comparability planner_evidence_gaps[{index}].requirement_id",
        )
        dimension = _text(
            raw.get("dimension"),
            field=f"comparability planner_evidence_gaps[{index}].dimension",
        )
        _require(
            dimension in missing,
            "comparability planner gap must correspond to verified missing context",
        )
        _require(
            raw.get("requirement_status") == "missing_context"
            and raw.get("action_class") == "evidence_acquisition"
            and raw.get("scientific_status_promoted") is False,
            "comparability planner gap semantics drifted",
        )
        dimension_result = dimension_by_name.get(dimension)
        _require(
            isinstance(dimension_result, Mapping)
            and dimension_result.get("status") == "MISSING",
            "comparability planner gap lacks matching MISSING dimension result",
        )
        left_missing = _comparability_side_missing(dimension_result.get("left"))
        right_missing = _comparability_side_missing(dimension_result.get("right"))
        if left_missing and not right_missing:
            missing_evidence_ids = (left_evidence_id,)
        elif right_missing and not left_missing:
            missing_evidence_ids = (right_evidence_id,)
        else:
            # Cross-packet lineage/relationship gaps can be unresolved without one
            # packet carrying a syntactically empty value; preserve both targets.
            missing_evidence_ids = (left_evidence_id, right_evidence_id)
        verified_missing_gaps.append((gap_id, dimension, missing_evidence_ids))

    # A missing-context acquisition task is actionable only when missing context is the
    # reason the declared comparison remains UNKNOWN. If an authenticated conflict already
    # makes the declared comparison NOT_COMPARABLE, acquiring the additional missing field
    # must not be presented as though it could erase that conflict.
    if outcome == UNKNOWN:
        for gap_id, dimension, missing_evidence_ids in verified_missing_gaps:
            missing_targets = ", ".join(missing_evidence_ids)
            requirements.append(
                {
                    "requirement_id": gap_id,
                    "requirement_class": "evidence_acquisition",
                    "action_class": "evidence_acquisition",
                    "description": (
                        "Acquire authoritative source or experiment evidence for missing "
                        f"comparability dimension '{dimension}' under claim '{claim_id}'. "
                        f"Missing/affected evidence target(s): {missing_targets}. "
                        "Preserve sample/acquisition identity, calibration, units, protocol, "
                        "and exact provenance where applicable; do not infer or impute the "
                        "missing context."
                    ),
                    "status": "unresolved",
                    "source_binding_ids": [
                        "comparability-assessment",
                        "comparability-claim-scope",
                        "comparability-left-packet",
                        "comparability-right-packet",
                    ],
                    "automatic_execution_authorized": False,
                    "scientific_status_promoted": False,
                }
            )

    if outcome == COMPARABLE:
        _require(
            not requirements and not conflicts and not normalization,
            "COMPARABLE assessment may not retain unresolved comparison blockers",
        )
        readiness_status = "ready"
        first_blocker = None
    elif outcome == UNKNOWN:
        _require(
            bool(requirements) and not conflicts,
            "UNKNOWN assessment requires verified missing context without conflicts",
        )
        readiness_status = "blocked"
        first_blocker = requirements[0]["requirement_id"]
    elif outcome == NOT_COMPARABLE:
        _require(
            bool(conflicts),
            "NOT_COMPARABLE assessment requires at least one verified conflict",
        )
        _require(
            not requirements,
            "NOT_COMPARABLE conflicts may not be rewritten as acquisition requirements",
        )
        readiness_status = "blocked"
        first_blocker = "comparability-conflict:" + ",".join(conflicts)
    else:
        _require(
            outcome == CONDITIONALLY_COMPARABLE
            and bool(normalization)
            and not conflicts
            and not requirements,
            "CONDITIONALLY_COMPARABLE requires normalization only",
        )
        readiness_status = "limited"
        first_blocker = "comparability-normalization-required:" + ",".join(
            normalization
        )

    comparison_identity_sha256 = canonical_sha256(
        {
            "claim_id": claim_id,
            "left_evidence_id": left_evidence_id,
            "right_evidence_id": right_evidence_id,
        }
    )

    return finalize_provider_state(
        {
            "schema_version": PROVIDER_STATE_SCHEMA_VERSION,
            "policy_version": PROVIDER_STATE_POLICY_VERSION,
            "provider_state_type": PROVIDER_STATE_TYPE,
            "provider": {
                "provider_id": (
                    "provenance-aware-comparability-engine:"
                    + comparison_identity_sha256
                ),
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": "verified-comparability-provider-state-v1",
            },
            "domain": "cross_source_comparability",
            "modality": "comparability_assessment",
            "subject_scope": (
                f"{left_evidence_id} vs {right_evidence_id} | claim {claim_id}"
            ),
            "source_bindings": bindings,
            "readiness": {
                "status": readiness_status,
                "maturity_label": outcome,
                "maturity_index": None,
                "first_blocker": first_blocker,
            },
            "unresolved_requirements": requirements,
            "authority_boundary": _authority_boundary(),
        }
    )


def verify_comparability_provider_state(
    value: object,
    assessment: Mapping[str, Any],
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    *,
    claim_scope: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
) -> dict[str, Any]:
    """Recompute a comparability ProviderState from authenticated scientific inputs."""

    supplied = validate_provider_state(value)
    expected = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim_scope,
        trusted_claim_scope_sha256=trusted_claim_scope_sha256,
    )
    _require(
        _typed_equal(supplied, expected),
        "comparability ProviderState differs from authenticated assessment recomputation",
    )
    return expected


def aggregate_provider_requirements(
    inputs: Sequence[AuthenticatedProviderStateInput],
) -> dict[str, Any]:
    """Aggregate externally authenticated ProviderStates with immutable SHA ancestry."""

    _require(bool(inputs), "provider aggregation requires at least one authenticated state")
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(inputs):
        _require(
            isinstance(item, AuthenticatedProviderStateInput),
            f"provider input[{index}] must be AuthenticatedProviderStateInput",
        )
        state = validate_provider_state(item.state)
        trusted = _sha(
            item.trusted_provider_state_sha256,
            field=f"provider input[{index}].trusted_provider_state_sha256",
        )
        _require(
            state["provider_state_sha256"] == trusted,
            f"provider input[{index}] does not match its external trust-root SHA-256",
        )
        validated.append(state)

    provider_ids = [item["provider"]["provider_id"] for item in validated]
    _require(
        len(set(provider_ids)) == len(provider_ids),
        "provider aggregation requires unique provider ids",
    )
    ordered = sorted(
        validated,
        key=lambda item: (
            str(item["provider"]["provider_id"]),
            str(item["provider_state_sha256"]),
        ),
    )
    state_hashes = [
        {
            "provider_id": item["provider"]["provider_id"],
            "provider_state_sha256": item["provider_state_sha256"],
        }
        for item in ordered
    ]
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for state in ordered:
        provider_id = state["provider"]["provider_id"]
        for requirement in state["unresolved_requirements"]:
            aggregate_id = f"{provider_id}:{requirement['requirement_id']}"
            _require(
                aggregate_id not in seen,
                "aggregate provider requirement ids must be unique",
            )
            seen.add(aggregate_id)
            requirements.append(
                {
                    "aggregate_requirement_id": aggregate_id,
                    "provider_id": provider_id,
                    "provider_state_sha256": state["provider_state_sha256"],
                    "requirement": copy.deepcopy(requirement),
                }
            )
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "aggregate_type": "evidence_provider_requirement_aggregate",
        "provider_state_sha256s": state_hashes,
        "requirements": requirements,
        "composite_binding_sha256": canonical_sha256(state_hashes),
        "authority_boundary": _authority_boundary(),
    }
    result["aggregate_sha256"] = canonical_sha256(result)
    return result


def verify_provider_requirement_aggregate(
    value: object,
    inputs: Sequence[AuthenticatedProviderStateInput],
) -> dict[str, Any]:
    """Recompute one provider aggregate from externally authenticated ProviderStates."""

    supplied = validate_provider_requirement_aggregate(value)
    expected = aggregate_provider_requirements(inputs)
    _require(
        _typed_equal(supplied, expected),
        "ProviderRequirementAggregate differs from provider-state recomputation",
    )
    return expected


def _validate_aggregate_requirement_record(
    value: object,
    *,
    index: int,
    provider_hashes: Mapping[str, str],
) -> dict[str, Any]:
    record = _exact_keys(
        value,
        _AGGREGATE_REQUIREMENT_KEYS,
        field=f"requirements[{index}]",
    )
    provider_id = _text(
        record.get("provider_id"),
        field=f"requirements[{index}].provider_id",
    )
    _require(
        provider_id in provider_hashes,
        f"requirements[{index}] references unknown provider",
    )
    provider_sha = _sha(
        record.get("provider_state_sha256"),
        field=f"requirements[{index}].provider_state_sha256",
    )
    _require(
        provider_sha == provider_hashes[provider_id],
        f"requirements[{index}] provider-state SHA does not match provider ancestry",
    )
    requirement = _exact_keys(
        record.get("requirement"),
        _REQUIREMENT_KEYS,
        field=f"requirements[{index}].requirement",
    )
    requirement_id = _text(
        requirement.get("requirement_id"),
        field=f"requirements[{index}].requirement.requirement_id",
    )
    requirement_class = _text(
        requirement.get("requirement_class"),
        field=f"requirements[{index}].requirement.requirement_class",
    )
    action_class = _text(
        requirement.get("action_class"),
        field=f"requirements[{index}].requirement.action_class",
    )
    _require(
        requirement_class in REQUIREMENT_ACTION_CLASSES,
        f"requirements[{index}] requirement_class is unsupported",
    )
    _require(
        action_class in REQUIREMENT_ACTION_CLASSES,
        f"requirements[{index}] action_class is unsupported",
    )
    _text(
        requirement.get("description"),
        field=f"requirements[{index}].requirement.description",
    )
    _require(
        requirement.get("status") == "unresolved",
        f"requirements[{index}] status must remain unresolved",
    )
    refs = requirement.get("source_binding_ids")
    _require(
        isinstance(refs, list)
        and all(isinstance(item, str) and bool(item) for item in refs)
        and len(set(refs)) == len(refs),
        f"requirements[{index}] source_binding_ids must be unique non-empty text",
    )
    _require(
        requirement.get("automatic_execution_authorized") is False,
        f"requirements[{index}] may not authorize automatic execution",
    )
    _require(
        requirement.get("scientific_status_promoted") is False,
        f"requirements[{index}] may not promote scientific status",
    )
    aggregate_id = _text(
        record.get("aggregate_requirement_id"),
        field=f"requirements[{index}].aggregate_requirement_id",
    )
    _require(
        aggregate_id == f"{provider_id}:{requirement_id}",
        f"requirements[{index}] aggregate requirement id drifted",
    )
    return copy.deepcopy(dict(record))


def validate_provider_requirement_aggregate(value: object) -> dict[str, Any]:
    root = dict(_exact_keys(value, _AGGREGATE_KEYS, field="ProviderRequirementAggregate"))
    digest = _sha(root.pop("aggregate_sha256"), field="aggregate_sha256")
    _require(
        canonical_sha256(root) == digest,
        "ProviderRequirementAggregate self-hash mismatch",
    )
    root["aggregate_sha256"] = digest
    _require(
        root.get("schema_version") == "1.0"
        and root.get("policy_version") == "1.0"
        and root.get("aggregate_type") == "evidence_provider_requirement_aggregate",
        "unsupported provider requirement aggregate contract",
    )

    ancestry = root.get("provider_state_sha256s")
    _require(
        isinstance(ancestry, list) and bool(ancestry),
        "provider_state_sha256s must be a non-empty list",
    )
    provider_hashes: dict[str, str] = {}
    for index, raw in enumerate(ancestry):
        item = _exact_keys(
            raw,
            _AGGREGATE_PROVIDER_STATE_KEYS,
            field=f"provider_state_sha256s[{index}]",
        )
        provider_id = _text(
            item.get("provider_id"),
            field=f"provider_state_sha256s[{index}].provider_id",
        )
        _require(
            provider_id not in provider_hashes,
            "provider_state_sha256s provider ids must be unique",
        )
        provider_hashes[provider_id] = _sha(
            item.get("provider_state_sha256"),
            field=f"provider_state_sha256s[{index}].provider_state_sha256",
        )

    requirements = root.get("requirements")
    _require(
        isinstance(requirements, list),
        "aggregate requirements must be a list",
    )
    aggregate_ids: set[str] = set()
    for index, raw in enumerate(requirements):
        record = _validate_aggregate_requirement_record(
            raw,
            index=index,
            provider_hashes=provider_hashes,
        )
        aggregate_id = record["aggregate_requirement_id"]
        _require(
            aggregate_id not in aggregate_ids,
            "aggregate requirement ids must be unique",
        )
        aggregate_ids.add(aggregate_id)

    boundary = _exact_keys(
        root.get("authority_boundary"),
        _AUTHORITY_KEYS,
        field="authority_boundary",
    )
    _require(
        _typed_equal(boundary, _authority_boundary()),
        "provider aggregate authority boundary drifted",
    )
    expected_composite = canonical_sha256(root["provider_state_sha256s"])
    _require(
        root.get("composite_binding_sha256") == expected_composite,
        "provider aggregate composite binding drifted",
    )
    return copy.deepcopy(root)


__all__ = [
    "AuthenticatedProviderStateInput",
    "BINDING_KINDS",
    "EvidenceProviderContractError",
    "PROVIDER_STATE_POLICY_VERSION",
    "PROVIDER_STATE_SCHEMA_VERSION",
    "PROVIDER_STATE_TYPE",
    "READINESS_STATUSES",
    "REQUIREMENT_ACTION_CLASSES",
    "adapt_authenticated_planning_gaps",
    "adapt_characterization_provider_state",
    "adapt_verified_comparability_provider_state",
    "aggregate_provider_requirements",
    "finalize_provider_state",
    "validate_provider_requirement_aggregate",
    "validate_provider_state",
    "verify_authenticated_planning_provider_state",
    "verify_characterization_provider_state",
    "verify_comparability_provider_state",
    "verify_provider_requirement_aggregate",
]
