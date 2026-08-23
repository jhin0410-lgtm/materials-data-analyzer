"""Typed contracts for fail-closed autonomous capability expansion.

This module does not generate or execute arbitrary code. It converts a scientifically valid
research action that lacks an audited executor into a provenance-bound capability gap and a
machine-readable capability specification. Later resolver/builder stages may only satisfy that
spec through separately verified bounded mechanisms.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

CAPABILITY_GAP_SCHEMA_VERSION = "1.0"
CAPABILITY_SPEC_SCHEMA_VERSION = "1.0"
CAPABILITY_EXPANSION_POLICY_VERSION = "1.0"

_ALLOWED_GAP_CLASSES = frozenset(
    {
        "missing_executor",
        "missing_source_adapter",
        "missing_parser",
        "missing_analysis_executor",
        "missing_simulation_executor",
        "unavailable_physical_interface",
        "policy_forbidden",
    }
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CapabilityExpansionError(ValueError):
    """Raised when capability expansion inputs are ambiguous or exceed authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityExpansionError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strict_text(value: object, field: str) -> str:
    _require(
        isinstance(value, str) and value.strip() == value and bool(value),
        f"{field} must be non-empty trimmed text",
    )
    return value


def _string_list(value: object, field: str) -> list[str]:
    _require(isinstance(value, list), f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_strict_text(item, f"{field}[{index}]"))
    _require(len(set(result)) == len(result), f"{field} must be unique")
    return result


def _predecessor_binding(predecessor_report: Mapping[str, Any]) -> str:
    for field in (
        "report_sha256_without_self_field",
        "manifest_sha256_without_self_field",
        "state_sha256_without_self_field",
    ):
        value = predecessor_report.get(field)
        if isinstance(value, str) and _HEX64.fullmatch(value):
            return value
    return _canonical_sha(predecessor_report)


def classify_capability_gap(
    action_class: str,
    *,
    policy_forbidden: bool = False,
) -> str:
    """Classify why a valid next action cannot currently execute."""
    action_class = _strict_text(action_class, "action_class")
    if policy_forbidden:
        return "policy_forbidden"
    lowered = action_class.lower()
    if any(token in lowered for token in ("physical_experiment", "instrument_control")):
        return "unavailable_physical_interface"
    if "simulation" in lowered:
        return "missing_simulation_executor"
    if any(token in lowered for token in ("analysis", "assessment", "inference")):
        return "missing_analysis_executor"
    if "parser" in lowered or "parse" in lowered:
        return "missing_parser"
    if any(token in lowered for token in ("acquisition", "source_discovery", "evidence_search")):
        return "missing_source_adapter"
    return "missing_executor"


def build_capability_gap(
    *,
    requested_action: Mapping[str, Any],
    predecessor_report: Mapping[str, Any],
    available_action_classes: Sequence[str],
    policy_forbidden: bool = False,
) -> dict[str, Any]:
    """Build an authenticated gap artifact for one unavailable research action."""
    _require(isinstance(requested_action, Mapping), "requested_action must be an object")
    action_class = _strict_text(requested_action.get("action_class"), "action_class")
    available = [_strict_text(item, "available_action_class") for item in available_action_classes]
    _require(len(set(available)) == len(available), "available action classes must be unique")
    _require(
        action_class not in set(available),
        "capability gap cannot be emitted for an already available action class",
    )
    objective = requested_action.get("objective")
    if objective is None:
        objective = f"Execute the verified next research action {action_class}."
    objective = _strict_text(objective, "objective")
    raw_lanes = requested_action.get("eligible_evidence_lanes", [])
    evidence_lanes = _string_list(raw_lanes, "eligible_evidence_lanes")
    gap_class = classify_capability_gap(
        action_class,
        policy_forbidden=policy_forbidden,
    )
    _require(gap_class in _ALLOWED_GAP_CLASSES, "unsupported capability gap class")

    gap: dict[str, Any] = {
        "schema_version": CAPABILITY_GAP_SCHEMA_VERSION,
        "policy_version": CAPABILITY_EXPANSION_POLICY_VERSION,
        "artifact_type": "capability_gap",
        "gap_class": gap_class,
        "requested_action_class": action_class,
        "requested_action_objective": objective,
        "eligible_evidence_lanes": evidence_lanes,
        "requested_action_binding_sha256": _canonical_sha(dict(requested_action)),
        "predecessor_research_state_sha256": _predecessor_binding(predecessor_report),
        "available_action_classes_at_detection": sorted(available),
        "evidence_absence_claimed": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
        "execution_authority_granted": False,
        "network_authority_granted": False,
        "arbitrary_code_execution_granted": False,
        "requires_capability_expansion": gap_class != "policy_forbidden",
        "requires_external_authorization": gap_class
        in {"policy_forbidden", "unavailable_physical_interface"},
    }
    gap["capability_gap_sha256_without_self_field"] = _canonical_sha(gap)
    return gap


def _action_requirements(action_class: str) -> dict[str, Any]:
    if action_class == "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition":
        return {
            "required_inputs": [
                "verified_mds2_2923_scientific_intake",
                "verified_geometry_condition_mapping_assessment",
                "mission_pinned_source_authority",
            ],
            "required_outputs": [
                "experiment_specific_machine_setting_to_calibrated_power_relation_or_explicit_absence",
                "experiment_identity_and_scope",
                "laser_spot_definition_and_measurement_basis",
                "cross_section_protocol_identity_and_uncertainty",
                "source_level_provenance_receipts",
            ],
            "scientific_acceptance": [
                "Do not infer mds2 machine-setting power as AMB2018 calibrated actual power without an explicit experiment-scoped bridge.",
                "Do not pool EOS M270 rows with AMMT rows.",
                "Preserve calibration, spot-size, protocol, and uncertainty conflicts when unresolved.",
                "Issue #76 remains 0/3 unless its exact requested AMMT cells are separately proven.",
                "A failed or empty network retrieval is operational evidence only, not proof that scientific evidence does not exist.",
            ],
        }
    if action_class == "experiment_specific_calibration_record_source_discovery":
        return {
            "required_inputs": [
                "verified_calibration_protocol_bridge_frontier",
                "mission_pinned_official_source_index_policy",
            ],
            "required_outputs": [
                "exact_source_index_provenance_receipt",
                "bounded_ranked_calibration_record_candidates",
                "candidate_link_authority_classification",
                "next_candidate_acquisition_action_without_implicit_authority",
            ],
            "scientific_acceptance": [
                "Read only the separately mission-pinned official source index and do not perform unrestricted search.",
                "Do not follow discovered candidate links during discovery.",
                "A discovered URL is a candidate identifier only and does not gain acquisition authority.",
                "Do not treat publication-index text or candidate metadata as row-level measurements.",
                "An empty candidate set is not proof that calibration evidence does not exist globally.",
                "Preserve direct comparable rows at 0 and Issue #76 at 0/3 unless later independently acquired evidence proves otherwise.",
            ],
        }
    return {
        "required_inputs": ["verified_predecessor_research_state"],
        "required_outputs": ["provenance_bound_action_result"],
        "scientific_acceptance": [
            "Preserve uncertainty and unresolved semantics.",
            "Do not promote operational success to scientific truth.",
        ],
    }


def build_capability_specification(capability_gap: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one capability gap into a bounded implementation/verification contract."""
    _require(isinstance(capability_gap, Mapping), "capability_gap must be an object")
    _require(
        capability_gap.get("schema_version") == CAPABILITY_GAP_SCHEMA_VERSION,
        "capability gap schema drifted",
    )
    supplied_gap_hash = capability_gap.get("capability_gap_sha256_without_self_field")
    _require(
        isinstance(supplied_gap_hash, str) and _HEX64.fullmatch(supplied_gap_hash) is not None,
        "capability gap self binding is missing",
    )
    unsigned_gap = dict(capability_gap)
    unsigned_gap.pop("capability_gap_sha256_without_self_field", None)
    _require(
        _canonical_sha(unsigned_gap) == supplied_gap_hash,
        "capability gap self binding is invalid",
    )
    _require(
        capability_gap.get("evidence_absence_claimed") is False
        and capability_gap.get("global_evidence_unavailability_claimed") is False,
        "capability specification cannot inherit an evidence-absence claim",
    )
    _require(
        capability_gap.get("execution_authority_granted") is False
        and capability_gap.get("network_authority_granted") is False
        and capability_gap.get("arbitrary_code_execution_granted") is False,
        "capability gap cannot pre-authorize implementation or execution",
    )
    action_class = _strict_text(
        capability_gap.get("requested_action_class"),
        "requested_action_class",
    )
    gap_class = _strict_text(capability_gap.get("gap_class"), "gap_class")
    _require(gap_class in _ALLOWED_GAP_CLASSES, "unsupported capability gap class")
    requirements = _action_requirements(action_class)

    specification: dict[str, Any] = {
        "schema_version": CAPABILITY_SPEC_SCHEMA_VERSION,
        "policy_version": CAPABILITY_EXPANSION_POLICY_VERSION,
        "artifact_type": "capability_specification",
        "requested_action_class": action_class,
        "gap_class": gap_class,
        "capability_gap_sha256": supplied_gap_hash,
        "predecessor_research_state_sha256": capability_gap.get(
            "predecessor_research_state_sha256"
        ),
        **requirements,
        "allowed_implementation_mechanisms": [
            "reuse_verified_capability",
            "compose_verified_primitives",
            "generate_declarative_adapter_instance",
        ],
        "forbidden_implementation_mechanisms": [
            "arbitrary_shell_generation",
            "arbitrary_python_eval_or_exec",
            "self_modifying_runtime_code",
            "unreviewed_network_host_expansion",
            "candidate_self_promotion",
        ],
        "verification_requirements": [
            "deterministic_contract_tests",
            "adversarial_authority_and_provenance_tests",
            "fixture_replay",
            "real_source_smoke_test_when_network_evidence_is_required",
            "epistemic_boundary_test",
            "exact_spec_implementation_and_verifier_byte_bindings",
        ],
        "promotion_policy": {
            "candidate_may_self_promote": False,
            "independent_verifier_required": True,
            "verified_registry_predecessor_required": True,
            "scientific_truth_promotion_authorized": False,
        },
        "authority_policy": {
            "may_synthesize_new_network_hosts": False,
            "may_synthesize_arbitrary_urls": False,
            "may_execute_physical_instrument": False,
            "may_promote_literature_to_row_level_measurement": False,
        },
    }
    specification["capability_specification_sha256_without_self_field"] = _canonical_sha(
        specification
    )
    return specification


__all__ = [
    "CAPABILITY_EXPANSION_POLICY_VERSION",
    "CAPABILITY_GAP_SCHEMA_VERSION",
    "CAPABILITY_SPEC_SCHEMA_VERSION",
    "CapabilityExpansionError",
    "build_capability_gap",
    "build_capability_specification",
    "classify_capability_gap",
]
