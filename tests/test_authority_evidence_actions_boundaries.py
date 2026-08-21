from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.authority_evidence_actions import (
    AuthorityEvidenceActionError,
    assess_resolution_authority_gaps,
    build_external_authority_route,
    build_local_text_authority_route,
    plan_authority_evidence_action,
    run_local_authority_evidence_loop,
)
from test_authority_evidence_actions_loop import (
    claim_values,
    companion,
    metadata,
    resolution,
)


def test_automated_public_route_is_ranked_before_human_and_delegated():
    assessment = assess_resolution_authority_gaps(resolution_contract=resolution())
    public = build_external_authority_route(
        route_id="route:repository-api",
        action_class="query_authoritative_repository_record",
        resolvable_claims=["unit", "method"],
        authorization_ref="authorization:repository-api",
        provenance_ref="source-registry:repository-api",
        provenance_quality_score=95,
        expected_bytes=4096,
        cost_units=2,
    )
    human = build_external_authority_route(
        route_id="route:source-owner",
        action_class="request_human_source_owner_evidence",
        resolvable_claims=["unit", "method"],
        authorization_ref="authorization:human-request",
        provenance_ref="contact-registry:source-owner",
        provenance_quality_score=100,
        expected_bytes=0,
        cost_units=8,
    )
    request = plan_authority_evidence_action(
        assessment=assessment,
        routes=[human, public],
        allow_human_fallback=True,
    )
    assert request["action_class"] == "query_authoritative_repository_record"
    assert request["network_performed_by_planner"] is False

    loop = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        external_routes=[human, public],
        allow_human_fallback=True,
    )
    assert loop["status"] == "action_required"
    assert loop["stop_reason"] == "authorized_external_executor_required"
    assert loop["next_action_request"]["action_class"] == "query_authoritative_repository_record"


def test_human_fallback_requires_explicit_permission():
    assessment = assess_resolution_authority_gaps(resolution_contract=resolution())
    human = build_external_authority_route(
        route_id="route:source-owner-only",
        action_class="request_human_source_owner_evidence",
        resolvable_claims=["unit"],
        authorization_ref="authorization:human-request",
        provenance_ref="contact-registry:source-owner",
        provenance_quality_score=100,
        expected_bytes=0,
        cost_units=8,
    )
    assert plan_authority_evidence_action(
        assessment=assessment,
        routes=[human],
        allow_human_fallback=False,
    ) is None
    allowed = plan_authority_evidence_action(
        assessment=assessment,
        routes=[human],
        allow_human_fallback=True,
    )
    assert allowed["action_class"] == "request_human_source_owner_evidence"


def test_exact_route_and_result_provenance_fail_on_mutation():
    readme = metadata(*tuple(claim_values()))
    route = build_local_text_authority_route(
        artifact_label="README.txt",
        artifact_bytes=readme,
        provenance_ref="archive-member:README.txt",
        authorization_ref="upstream-acquisition-boundary:fixture",
    )
    mutated_route = copy.deepcopy(route)
    mutated_route["artifact_label"] = "renamed-after-plan.txt"
    with pytest.raises(AuthorityEvidenceActionError, match="route SHA"):
        plan_authority_evidence_action(
            assessment=assess_resolution_authority_gaps(
                resolution_contract=resolution()
            ),
            routes=[mutated_route],
        )

    completed = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[companion("README.txt", readme)],
    )
    mutated_result = copy.deepcopy(completed["action_results"][0])
    mutated_result["negative_claims"] = ["unit"]
    with pytest.raises(AuthorityEvidenceActionError, match="result SHA"):
        run_local_authority_evidence_loop(
            resolution_contract=resolution(),
            companion_artifacts=[companion("README.txt", readme)],
            prior_action_results=[mutated_result],
        )


def test_budget_boundary_preserves_partial_evidence():
    claims = list(claim_values())
    result = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[
            companion("README-primary.txt", metadata(*claims[:6])),
            companion("README-secondary.txt", metadata(*claims[6:])),
        ],
        maximum_cost_units=1,
    )
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "policy_budget_boundary"
    assert result["spent_cost_units"] == 1
    assert set(result["authority_gap_assessment"]["missing_required_authority"]) == set(
        claims[6:]
    )


def test_canonical_directives_are_required_not_filename_or_free_text_heuristics():
    with pytest.raises(AuthorityEvidenceActionError, match="canonical JSON"):
        build_local_text_authority_route(
            artifact_label="README-unit-MPa.txt",
            artifact_bytes=b'resolution-authority:unit= "MPa"\n',
            provenance_ref="archive-member:README-unit-MPa.txt",
            authorization_ref="upstream-acquisition-boundary:fixture",
        )

    route = build_local_text_authority_route(
        artifact_label="unit-MPa-method-tensile.txt",
        artifact_bytes=b"unit=MPa; method=tensile; instrument=machine-7\n",
        provenance_ref="archive-member:free-text",
        authorization_ref="upstream-acquisition-boundary:fixture",
    )
    assert route["declared_claims"] == []
    assert route["semantic_inference_performed"] is False
