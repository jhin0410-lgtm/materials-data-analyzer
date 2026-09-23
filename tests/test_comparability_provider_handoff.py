from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest

from materials_data_analyzer.research_loop.comparability_engine import (
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    UNKNOWN,
    AuthenticatedEvidenceInput,
    ComparabilityEngineError,
    DEFAULT_RULE_REGISTRY,
    assess_comparability,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    canonical_sha256,
    finalize_evidence_packet,
)
from materials_data_analyzer.research_loop.evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    EvidenceProviderContractError,
    adapt_verified_comparability_provider_state,
    aggregate_provider_requirements,
    verify_comparability_provider_state,
)
from materials_data_analyzer.research_loop.evidence_provider_planning import (
    build_provider_planner_program_state,
)
from materials_data_analyzer.research_loop.self_directed_research import (
    build_self_directed_research_plan,
)
from materials_data_analyzer.research_loop import public_recursive_api


def _attribute(
    name: str,
    value: object,
    *,
    unit: str | None = None,
) -> dict[str, object]:
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    else:
        value_type = "text"
    return {
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit_state": "specified" if unit is not None else "not_applicable",
        "unit": unit,
        "source_binding_ids": ["source-1"],
    }


def _packet(
    *,
    evidence_id: str,
    artifact: bytes,
    process_route: str = "LPBF",
    material: str = "IN625",
    sample: str = "sample-1",
    source_family_id: str = "family-1",
    dataset_parent_id: str = "dataset-1",
    unit: str = "MPa",
) -> dict[str, Any]:
    unsigned: dict[str, Any] = {
        "schema_version": "1.0",
        "packet_type": "evidence_packet",
        "evidence_id": evidence_id,
        "evidence_kind": "measurement",
        "provider": {
            "provider_id": "comparability-handoff-test-provider",
            "contract_version": "1.0",
            "schema_version": "1.0",
            "adapter_id": "comparability-handoff-test-adapter",
        },
        "subject": {
            "subject_type": "material_measurement",
            "identities": [
                {"namespace": "material", "value": material, "role": "material"},
                {"namespace": "sample", "value": sample, "role": "sample"},
            ],
            "material_scope": "bounded-comparability-handoff-test",
            "description": "Provider-handoff integration fixture.",
        },
        "contexts": {
            "process": {
                "status": "applicable",
                "attributes": [_attribute("process_route", process_route)],
            },
            "sample": {"status": "applicable", "attributes": []},
            "method": {"status": "applicable", "attributes": []},
            "measurement": {
                "status": "applicable",
                "attributes": [
                    _attribute(
                        "reference_convention",
                        "declared_scalar_quantity_convention",
                    )
                ],
            },
        },
        "results": [
            {
                "result_id": "result-1",
                "result_kind": "ultimate_tensile_strength",
                "value_state": "observed",
                "value": 950.0,
                "value_type": "number",
                "unit_state": "specified",
                "unit": unit,
                "source_binding_ids": ["source-1"],
                "derivation_ids": [],
                "uncertainty_ids": ["uncertainty-1"],
                "qualifiers": ["integration-fixture"],
            }
        ],
        "uncertainty": [
            {
                "uncertainty_id": "uncertainty-1",
                "status": "unknown",
                "kind": "measurement_uncertainty",
                "value": None,
                "unit": None,
                "distribution": None,
                "confidence_level": None,
                "source_binding_ids": ["source-1"],
                "notes": "Uncertainty is intentionally not quantified.",
            }
        ],
        "calibration": {"status": "unknown", "records": []},
        "source_bindings": [
            {
                "binding_id": "source-1",
                "role": "measurement_source",
                "artifact_id": evidence_id + "-artifact",
                "locator": f"artifacts/{evidence_id}.bin",
                "sha256": hashlib.sha256(artifact).hexdigest(),
                "byte_size": len(artifact),
                "media_type": "application/octet-stream",
            }
        ],
        "derivation_lineage": [],
        "independence": {
            "source_family_id": source_family_id,
            "dataset_parent_id": dataset_parent_id,
            "sample_parent_ids": [sample],
            "acquisition_parent_ids": [sample + "-acquisition"],
            "development_family_id": None,
            "overlap_status": "unknown",
            "overlap_with": [],
            "independence_claim_status": "not_assessed",
        },
        "scientific_validity": {
            "domain_verifier_id": "comparability-handoff-test-verifier",
            "verification_status": "limited",
            "validated_scope": ["source bytes", "fixture context"],
            "excluded_scope": ["causality", "prediction", "engineering use"],
            "assumptions": [],
            "scientific_status_promoted": False,
        },
        "comparability": {
            "status": "not_assessed",
            "requirements": ["separate Comparability Engine assessment required"],
            "limitations": ["packet itself grants no cross-source comparability"],
            "comparison_performed": False,
            "comparable_claimed": False,
        },
        "limitations": ["Integration fixture grants descriptive evidence only."],
        "authority": {
            "empirical_evidence_created": True,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "planning_metadata_only": False,
            "row_level_measurement_authority": True,
            "authority_source": "domain_verifier",
        },
    }
    return finalize_evidence_packet(unsigned)


def _expectations(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": packet["provider"]["provider_id"],
        "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
        "source_bindings": copy.deepcopy(packet["source_bindings"]),
        "result_units": {
            result["result_id"]: result["unit"] for result in packet["results"]
        },
        "calibration_status": packet["calibration"]["status"],
        "uncertainty_status_by_id": {
            item["uncertainty_id"]: item["status"] for item in packet["uncertainty"]
        },
        "existing_source_family_ids": [],
        "packet_sha256": packet["packet_sha256"],
    }


def _input(packet: dict[str, Any], artifact: bytes) -> AuthenticatedEvidenceInput:
    expected = _expectations(packet)
    return AuthenticatedEvidenceInput(
        packet=packet,
        artifacts={"source-1": artifact},
        expected=expected,
        trusted_expectation_sha256=canonical_sha256(expected),
    )


def _claim(
    *required: str,
    allowed_transformations: tuple[str, ...] = (),
) -> dict[str, Any]:
    dimensions = [rule.dimension for rule in DEFAULT_RULE_REGISTRY]
    required_set = set(required)
    return {
        "claim_id": "comparability-handoff-claim",
        "claim_type": "declared_cross_source_comparison",
        "required_dimensions": [
            dimension for dimension in dimensions if dimension in required_set
        ],
        "irrelevant_dimensions": [
            dimension for dimension in dimensions if dimension not in required_set
        ],
        "allowed_transformations": list(allowed_transformations),
        "requires_independent_replication": False,
        "maximum_downstream_use_requested": "comparative",
    }


def _assessment(
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    claim: dict[str, Any],
) -> dict[str, Any]:
    return assess_comparability(
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )


def _base_program() -> dict[str, Any]:
    return {
        "mission": {
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            }
        },
        "generated_goals": [],
    }


def _rehash_provider(value: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value.pop("provider_state_sha256", None)
    value["provider_state_sha256"] = canonical_sha256(value)
    return value


def _rehash_assessment(value: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value.pop("assessment_sha256", None)
    value["assessment_sha256"] = canonical_sha256(value)
    return value


def test_unknown_calibration_becomes_authenticated_gap_then_multiple_candidate_actions() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("instrument_state_calibration")
    assessment = _assessment(left, right, claim)
    assert assessment["assessment_status"] == UNKNOWN

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    assert provider["readiness"]["status"] == "blocked"
    assert provider["readiness"]["first_blocker"] == (
        "comparability-context:instrument_state_calibration"
    )
    assert len(provider["unresolved_requirements"]) == 1
    requirement = provider["unresolved_requirements"][0]
    assert requirement["action_class"] == "evidence_acquisition"
    assert "instrument_state_calibration" in requirement["description"]
    assert provider["authority_boundary"]["execution_authorized"] is False

    program = build_provider_planner_program_state(
        _base_program(),
        [
            AuthenticatedProviderStateInput(
                state=provider,
                trusted_provider_state_sha256=provider["provider_state_sha256"],
            )
        ],
    )
    provider_goal = next(
        item
        for item in program["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    )
    assert provider_goal["action_frontier"] == []

    plan = build_self_directed_research_plan(program)
    generated = {
        item["action_class"] for item in plan["self_generated_gap_actions"]
    }
    assert {"external_evidence_search", "physical_experiment_design"} <= generated
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["automatic_execution_authorized"] is False
    assert plan["handoff"]["execution_performed"] is False


def test_verified_conflict_is_blocker_not_acquisition_gap() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        process_route="LPBF",
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        process_route="casting",
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("process_route")
    assessment = _assessment(left, right, claim)
    assert assessment["assessment_status"] == NOT_COMPARABLE

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    assert provider["readiness"]["status"] == "blocked"
    assert provider["readiness"]["first_blocker"] == (
        "comparability-conflict:process_route"
    )
    assert provider["unresolved_requirements"] == []


def test_conflict_suppresses_coexisting_missing_context_as_actionable_gap() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        process_route="LPBF",
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        process_route="casting",
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("process_route", "instrument_state_calibration")
    assessment = _assessment(left, right, claim)

    assert assessment["assessment_status"] == NOT_COMPARABLE
    assert assessment["conflicting_dimensions"] == ["process_route"]
    assert assessment["missing_context"] == ["instrument_state_calibration"]
    assert assessment["planner_evidence_gaps"]

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    assert provider["readiness"]["status"] == "blocked"
    assert provider["readiness"]["first_blocker"] == (
        "comparability-conflict:process_route"
    )
    assert provider["unresolved_requirements"] == []


def test_conditional_unit_normalization_is_limited_not_missing_evidence() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        unit="MPa",
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        unit="kPa",
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim(
        "units_reference_conventions",
        allowed_transformations=("units_reference_conventions",),
    )
    assessment = _assessment(left, right, claim)
    assert assessment["assessment_status"] == CONDITIONALLY_COMPARABLE

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    assert provider["readiness"]["status"] == "limited"
    assert provider["readiness"]["first_blocker"] == (
        "comparability-normalization-required:units_reference_conventions"
    )
    assert provider["unresolved_requirements"] == []


def test_comparable_assessment_is_ready_without_false_gap() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim(
        "material_identity",
        "process_route",
        "target_response_semantics",
        "units_reference_conventions",
    )
    assessment = _assessment(left, right, claim)

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    assert provider["readiness"]["status"] == "ready"
    assert provider["readiness"]["first_blocker"] is None
    assert provider["unresolved_requirements"] == []


def test_rehashed_conflict_to_missing_rewrite_fails_authenticated_recomputation() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        process_route="LPBF",
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        process_route="casting",
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("process_route")
    forged = _assessment(left, right, claim)
    forged["assessment_status"] = UNKNOWN
    forged["conflicting_dimensions"] = []
    forged["missing_context"] = ["process_route"]
    forged["planner_evidence_gaps"] = [
        {
            "requirement_id": "comparability-context:process_route",
            "dimension": "process_route",
            "requirement_status": "missing_context",
            "action_class": "evidence_acquisition",
            "scientific_status_promoted": False,
        }
    ]
    forged = _rehash_assessment(forged)

    with pytest.raises(
        ComparabilityEngineError,
        match="authenticated recomputation",
    ):
        adapt_verified_comparability_provider_state(
            forged,
            left,
            right,
            claim_scope=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
        )


def test_claim_substitution_fails_original_claim_trust_root() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("instrument_state_calibration")
    assessment = _assessment(left, right, claim)
    trusted = canonical_sha256(claim)
    weakened = _claim("material_identity")

    with pytest.raises(ComparabilityEngineError, match="external trust-root"):
        adapt_verified_comparability_provider_state(
            assessment,
            left,
            right,
            claim_scope=weakened,
            trusted_claim_scope_sha256=trusted,
        )


def test_assessment_packet_binding_substitution_fails_recomputation() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("instrument_state_calibration")
    forged = _assessment(left, right, claim)
    forged["left_packet"]["source_bindings"][0]["sha256"] = "f" * 64
    forged = _rehash_assessment(forged)

    with pytest.raises(
        ComparabilityEngineError,
        match="authenticated recomputation",
    ):
        adapt_verified_comparability_provider_state(
            forged,
            left,
            right,
            claim_scope=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
        )


def test_rehashed_provider_tamper_fails_comparability_recomputation() -> None:
    left_raw = b"left-source\n"
    right_raw = b"right-source\n"
    left_packet = _packet(
        evidence_id="left",
        artifact=left_raw,
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right",
        artifact=right_raw,
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("instrument_state_calibration")
    assessment = _assessment(left, right, claim)
    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )

    forged = copy.deepcopy(provider)
    forged["unresolved_requirements"][0]["action_class"] = "analysis"
    forged["unresolved_requirements"][0]["requirement_class"] = "analysis"
    forged = _rehash_provider(forged)

    with pytest.raises(
        EvidenceProviderContractError,
        match="authenticated assessment recomputation",
    ):
        verify_comparability_provider_state(
            forged,
            assessment,
            left,
            right,
            claim_scope=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
        )



def test_two_comparability_assessments_have_distinct_stable_provider_identities() -> None:
    claim = _claim("instrument_state_calibration")

    left_a_raw = b"left-a\n"
    right_a_raw = b"right-a\n"
    left_a = _input(
        _packet(evidence_id="left-a", artifact=left_a_raw, sample="left-a-sample"),
        left_a_raw,
    )
    right_a = _input(
        _packet(
            evidence_id="right-a",
            artifact=right_a_raw,
            sample="right-a-sample",
            source_family_id="family-a2",
            dataset_parent_id="dataset-a2",
        ),
        right_a_raw,
    )
    assessment_a = _assessment(left_a, right_a, claim)
    provider_a = adapt_verified_comparability_provider_state(
        assessment_a,
        left_a,
        right_a,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )

    left_b_raw = b"left-b\n"
    right_b_raw = b"right-b\n"
    left_b = _input(
        _packet(evidence_id="left-b", artifact=left_b_raw, sample="left-b-sample"),
        left_b_raw,
    )
    right_b = _input(
        _packet(
            evidence_id="right-b",
            artifact=right_b_raw,
            sample="right-b-sample",
            source_family_id="family-b2",
            dataset_parent_id="dataset-b2",
        ),
        right_b_raw,
    )
    assessment_b = _assessment(left_b, right_b, claim)
    provider_b = adapt_verified_comparability_provider_state(
        assessment_b,
        left_b,
        right_b,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )

    assert provider_a["provider"]["provider_id"] != provider_b["provider"]["provider_id"]
    assert provider_a["provider"]["provider_id"].startswith(
        "provenance-aware-comparability-engine:"
    )
    aggregate = aggregate_provider_requirements(
        [
            AuthenticatedProviderStateInput(
                state=provider_a,
                trusted_provider_state_sha256=provider_a["provider_state_sha256"],
            ),
            AuthenticatedProviderStateInput(
                state=provider_b,
                trusted_provider_state_sha256=provider_b["provider_state_sha256"],
            ),
        ]
    )
    assert len(aggregate["provider_state_sha256s"]) == 2


def test_asymmetric_missing_context_names_the_missing_evidence_target() -> None:
    left_raw = b"left-complete\n"
    right_raw = b"right-missing\n"
    left_packet = _packet(
        evidence_id="left-complete",
        artifact=left_raw,
        process_route="LPBF",
        sample="left-sample",
    )
    right_packet = _packet(
        evidence_id="right-missing",
        artifact=right_raw,
        process_route="LPBF",
        sample="right-sample",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
    )
    right_packet["contexts"]["process"]["attributes"] = []
    right_packet.pop("packet_sha256", None)
    right_packet["packet_sha256"] = canonical_sha256(right_packet)

    left = _input(left_packet, left_raw)
    right = _input(right_packet, right_raw)
    claim = _claim("process_route")
    assessment = _assessment(left, right, claim)
    assert assessment["assessment_status"] == UNKNOWN

    provider = adapt_verified_comparability_provider_state(
        assessment,
        left,
        right,
        claim_scope=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    requirement = provider["unresolved_requirements"][0]
    assert "Missing/affected evidence target(s): right-missing." in requirement["description"]
    assert "left-complete" not in requirement["description"].split(
        "Missing/affected evidence target(s):", 1
    )[1].split(".", 1)[0]


def test_public_recursive_facade_exports_comparability_provider_handoff() -> None:
    assert (
        public_recursive_api.adapt_verified_comparability_provider_state
        is adapt_verified_comparability_provider_state
    )
    assert (
        public_recursive_api.verify_comparability_provider_state
        is verify_comparability_provider_state
    )
