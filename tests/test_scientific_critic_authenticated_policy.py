from __future__ import annotations

import copy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    scientific_critic_authenticated_policy as module,
)


def _consumer(*, relation: str = "contradicts", scope: str = "structural") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "consumer_policy_version": "1.0",
        "bundle_root": "/bundle",
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": "transition-1",
        "inference_edge_id": "inference-1",
        "result_node_id": "result-1",
        "target_node_id": "hypothesis-1",
        "relation": relation,
        "inference_scope": scope,
        "graph_binding": {"path": "epistemic_graph.json", "sha256": "a" * 64},
        "authority_boundary": {
            "scientific_authority_applied": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "positive_closeout_granted": False,
            "verifier_identity_or_credential_authenticated": False,
            "support_independence_established": False,
            "empirical_origin_independently_established": False,
        },
    }


def _base_report(*, include_target: bool = True) -> dict[str, object]:
    targets: list[dict[str, object]] = []
    if include_target:
        targets.append(
            {
                "target_node_id": "hypothesis-1",
                "epistemic_assessment": {
                    "status": "inconclusive",
                    "verified_support_edges": [],
                    "verified_contradiction_edges": [],
                    "verified_falsification_edges": [],
                    "confidence_score": None,
                    "final_positive_support_granted": False,
                },
                "critic_findings": [
                    {
                        "finding_id": "critic:hypothesis-1:counterevidence-gap",
                        "code": "NO_DOMAIN_VERIFIED_COUNTEREVIDENCE",
                    }
                ],
                "methodological_alternatives": [],
                "discriminating_actions": [],
                "stop_recommendation": {
                    "recommendation": "continue_bounded_research",
                    "automatic_stop_authorized": False,
                    "positive_scientific_closeout_granted": False,
                },
            }
        )
    return {
        "target_reports": targets,
        "summary": {
            "findings": sum(len(item["critic_findings"]) for item in targets),
            "methodological_alternatives": 0,
            "discriminating_actions": 0,
        },
        "autonomy_boundary": {},
    }


def _wire(monkeypatch: pytest.MonkeyPatch, *, consumer: dict[str, object], base: dict[str, object]) -> list[Path]:
    observed: list[Path] = []

    def fake_consume(bundle_root: str | Path) -> dict[str, object]:
        observed.append(Path(bundle_root))
        return copy.deepcopy(consumer)

    monkeypatch.setattr(module, "authenticate_transition_bundle", fake_consume)
    monkeypatch.setattr(module, "_sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(
        module,
        "build_policy_hardened_scientific_critic_report",
        lambda *args, **kwargs: copy.deepcopy(base),
    )
    return observed


def test_negative_authenticated_advisory_preserves_evaluator_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _base_report()
    original_assessment = copy.deepcopy(base["target_reports"][0]["epistemic_assessment"])
    observed = _wire(monkeypatch, consumer=_consumer(relation="contradicts"), base=base)

    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle",
        program_state={"generated_goals": []},
    )

    assert observed == [tmp_path / "bundle"]
    target = result["target_reports"][0]
    assert target["epistemic_assessment"] == original_assessment
    advisory = target["authenticated_directional_assessment"]
    assert advisory["relation"] == "contradicts"
    assert advisory["persistent_graph_or_evaluator_status_changed"] is False
    assert advisory["scientific_status_promotion_authorized"] is False
    assert target["stop_recommendation"]["recommendation"] == "continue_bounded_research"
    advisory_stop = target["authenticated_stop_advisory"]
    assert advisory_stop["recommendation"] == (
        "reassess_or_narrow_authenticated_contradicted_scope"
    )
    assert advisory_stop["base_critic_stop_recommendation_preserved"] is True
    assert advisory_stop["automatic_stop_authorized"] is False
    assert advisory_stop["positive_scientific_closeout_granted"] is False
    codes = {item["code"] for item in target["critic_findings"]}
    assert "AUTHENTICATED_DIRECTIONAL_CONTRADICTION_PRESENT" in codes
    assert (
        result["autonomy_boundary"][
            "authenticated_directional_advisory_may_inform_manual_reframe"
        ]
        is True
    )


def test_authenticated_falsification_allows_manual_reframe_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _wire(
        monkeypatch,
        consumer=_consumer(relation="falsifies"),
        base=_base_report(),
    )
    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle", program_state={"generated_goals": []}
    )
    assert observed == [tmp_path / "bundle"]
    target = result["target_reports"][0]
    assert target["stop_recommendation"]["recommendation"] == "continue_bounded_research"
    assert target["authenticated_stop_advisory"]["recommendation"] == (
        "reframe_or_narrow_authenticated_falsified_scope"
    )
    action = next(
        item
        for item in target["discriminating_actions"]
        if item["action_id"].endswith("reframe-authenticated-falsified-scope")
    )
    assert action["execution_mode"] == "plan_only"
    assert action["automatic_execution_authorized"] is False
    assert action["availability_asserted"] is False


def test_authenticated_support_does_not_grant_independence_or_positive_closeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _base_report()
    original_assessment = copy.deepcopy(base["target_reports"][0]["epistemic_assessment"])
    _wire(monkeypatch, consumer=_consumer(relation="supports"), base=base)

    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle", program_state={"generated_goals": []}
    )
    target = result["target_reports"][0]
    assert target["epistemic_assessment"] == original_assessment
    advisory = target["authenticated_directional_assessment"]
    assert advisory["support_independence_established"] is False
    assert advisory["calibrated_confidence_established"] is False
    assert advisory["positive_closeout_granted"] is False
    assert target["stop_recommendation"]["recommendation"] == "continue_bounded_research"
    assert (
        result["autonomy_boundary"][
            "support_independence_established_by_exact_edge_provenance"
        ]
        is False
    )
    assert (
        result["autonomy_boundary"][
            "authenticated_directional_advisory_may_inform_manual_reframe"
        ]
        is False
    )


def test_requested_target_filter_can_exclude_authenticated_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(
        monkeypatch,
        consumer=_consumer(relation="contradicts"),
        base=_base_report(include_target=False),
    )
    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle",
        program_state={"generated_goals": []},
        target_node_ids=["different-target"],
    )
    assert result["target_reports"] == []
    assert (
        result["authenticated_transition_consumer"][
            "advisory_applied_to_requested_target_set"
        ]
        is False
    )
    assert result["summary"]["authenticated_directional_advisories"] == 0
    assert (
        result["autonomy_boundary"][
            "authenticated_directional_advisory_may_inform_manual_reframe"
        ]
        is False
    )


def test_adapter_api_accepts_bundle_not_caller_supplied_consumer_report() -> None:
    parameters = module.build_authenticated_scientific_critic_report.__annotations__
    assert "bundle_root" in parameters
    assert "consumer_report" not in parameters


def test_adapter_boundary_never_authorizes_execution_or_closeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(monkeypatch, consumer=_consumer(relation="contradicts"), base=_base_report())
    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle", program_state={"generated_goals": []}
    )
    boundary = result["autonomy_boundary"]
    assert boundary["authenticated_bundle_re_read_by_critic_adapter"] is True
    assert boundary["caller_supplied_consumer_report_accepted"] is False
    assert boundary["persistent_graph_promoted_by_authenticated_advisory"] is False
    assert boundary["evaluator_status_changed_by_authenticated_advisory"] is False
    assert boundary["authenticated_directional_advisory_authorizes_automatic_stop"] is False
    assert boundary["authenticated_directional_advisory_authorizes_execution"] is False
    assert boundary["authenticated_directional_advisory_grants_positive_closeout"] is False
    assert boundary["empirical_derived_authority_enabled_without_evidence_origin_contract"] is False



def test_adapter_rejects_empirical_derived_even_if_consumer_regresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(
        monkeypatch,
        consumer=_consumer(relation="supports", scope="empirical_derived"),
        base=_base_report(),
    )
    with pytest.raises(
        module.ScientificCriticError,
        match="evidence-origin contract",
    ):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_consumer_authority_escalation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = _consumer(relation="supports")
    boundary = consumer["authority_boundary"]
    assert isinstance(boundary, dict)
    boundary["scientific_authority_applied"] = True
    _wire(monkeypatch, consumer=consumer, base=_base_report())
    with pytest.raises(
        module.ScientificCriticError,
        match="scientific_authority_applied=false",
    ):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_empirical_direct_even_if_consumer_regresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(
        monkeypatch,
        consumer=_consumer(relation="supports", scope="empirical_direct"),
        base=_base_report(),
    )
    with pytest.raises(module.ScientificCriticError, match="evidence-origin contract"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_unknown_consumer_contract_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = _consumer()
    consumer["consumer_policy_version"] = "2.0"
    _wire(monkeypatch, consumer=consumer, base=_base_report())
    with pytest.raises(module.ScientificCriticError, match="schema/policy 1.0"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_consumer_scientific_status_escalation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = _consumer(relation="supports")
    boundary = consumer["authority_boundary"]
    assert isinstance(boundary, dict)
    boundary["scientific_status_changed"] = True
    _wire(monkeypatch, consumer=consumer, base=_base_report())
    with pytest.raises(module.ScientificCriticError, match="scientific_status_changed=false"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_authenticated_advisory_never_downgrades_existing_base_stop_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _base_report()
    target = base["target_reports"][0]
    target["stop_recommendation"] = {
        "recommendation": "stop_and_reframe_current_target",
        "rationale": "Existing verified falsification elsewhere in the graph.",
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }
    _wire(
        monkeypatch,
        consumer=_consumer(relation="contradicts"),
        base=base,
    )
    result = module.build_authenticated_scientific_critic_report(
        tmp_path / "bundle", program_state={"generated_goals": []}
    )
    target_result = result["target_reports"][0]
    assert target_result["stop_recommendation"] == target["stop_recommendation"]
    assert target_result["authenticated_stop_advisory"]["recommendation"] == (
        "reassess_or_narrow_authenticated_contradicted_scope"
    )


def test_adapter_rejects_graph_change_between_consumer_and_base_critic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(monkeypatch, consumer=_consumer(), base=_base_report())
    monkeypatch.setattr(module, "_sha256_file", lambda _path: "b" * 64)
    with pytest.raises(module.ScientificCriticError, match="before critic evaluation"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_graph_change_during_base_critic_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(monkeypatch, consumer=_consumer(), base=_base_report())
    digests = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(module, "_sha256_file", lambda _path: next(digests))
    with pytest.raises(module.ScientificCriticError, match="while the base critic report"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_alternate_consumer_graph_binding_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = _consumer()
    graph_binding = consumer["graph_binding"]
    assert isinstance(graph_binding, dict)
    graph_binding["path"] = "other-graph.json"
    _wire(monkeypatch, consumer=consumer, base=_base_report())
    with pytest.raises(module.ScientificCriticError, match="fixed epistemic_graph.json"):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )
