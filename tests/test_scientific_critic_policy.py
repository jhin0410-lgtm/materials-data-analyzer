from __future__ import annotations

from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import scientific_critic_policy as module
from materials_data_analyzer.research_loop.scientific_critic import ScientificCriticError


def _base_report(*, supports: bool = True) -> dict[str, object]:
    support_edges = ["support-1", "support-2"] if supports else []
    findings = (
        [
            {
                "finding_id": "critic:h1:support-concentration",
                "code": "SUPPORT_SOURCE_CONCENTRATION",
            }
        ]
        if supports
        else []
    )
    alternatives = (
        [{"alternative_id": "critic:h1:shared-provenance"}] if supports else []
    )
    actions = (
        [{"action_id": "critic:h1:independent-replication"}] if supports else []
    )
    return {
        "critic_policy_version": "1.0",
        "target_reports": [
            {
                "target_node_id": "h1",
                "epistemic_assessment": {
                    "status": "provisionally_supported" if supports else "inconclusive",
                    "verified_support_edges": support_edges,
                    "verified_contradiction_edges": [],
                    "verified_falsification_edges": [],
                },
                "critic_findings": findings,
                "methodological_alternatives": alternatives,
                "discriminating_actions": actions,
            }
        ],
        "summary": {
            "findings": len(findings),
            "methodological_alternatives": len(alternatives),
            "discriminating_actions": len(actions),
        },
        "autonomy_boundary": {},
    }


def _program() -> dict[str, object]:
    return {
        "generated_goals": [
            {
                "goal_id": "mission:nist:resolve-current-blocker",
                "workstream_id": "nist",
                "status": "active",
                "evidence_gap_status": "missing",
                "evidence_requirements": [
                    "Three independent traces at the missing design condition",
                    "Checksum-bound acquisition provenance",
                ],
            },
            {
                "goal_id": "mission:tem:resolve-current-blocker",
                "workstream_id": "tem",
                "status": "active",
                "evidence_gap_status": "external_validation_missing",
                "evidence_requirements": [
                    "Independent parent-disjoint validation data",
                ],
            },
        ]
    }


def test_positive_support_never_implies_independence_from_distinct_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: _base_report())
    monkeypatch.setattr(
        module,
        "_apply_directional_provenance_policy",
        lambda *args, **kwargs: None,
    )
    result = module.build_policy_hardened_scientific_critic_report(
        tmp_path / "unused.json",
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = result["target_reports"][0]
    codes = {item["code"] for item in report["critic_findings"]}
    assert "SUPPORT_SOURCE_CONCENTRATION" not in codes
    assert "SUPPORT_INDEPENDENCE_NOT_ESTABLISHED" in codes
    action = next(
        item
        for item in report["discriminating_actions"]
        if item["action_id"].endswith("establish-support-independence")
    )
    assert action["execution_mode"] == "plan_only"
    assert action["automatic_execution_authorized"] is False
    assert action["availability_asserted"] is False
    assert (
        result["autonomy_boundary"][
            "support_independence_inferred_from_artifact_identity"
        ]
        is False
    )


def test_program_requirements_remain_workstream_scoped_not_target_attributed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        module,
        "_build_base_report",
        lambda *args, **kwargs: _base_report(supports=False),
    )
    result = module.build_policy_hardened_scientific_critic_report(
        tmp_path / "unused.json",
        program_state=_program(),
        artifact_root=tmp_path,
    )
    gaps = result["program_evidence_gaps"]
    assert [item["workstream_id"] for item in gaps] == ["nist", "tem"]
    assert gaps[0]["evidence_requirements"] == [
        "Three independent traces at the missing design condition",
        "Checksum-bound acquisition provenance",
    ]
    assert all(item["target_attribution"] == "not_inferred" for item in gaps)
    assert all(item["automatic_acquisition_authorized"] is False for item in gaps)
    assert (
        result["autonomy_boundary"][
            "program_evidence_requirements_target_attributed_without_mapping"
        ]
        is False
    )


def test_scope_exhausted_program_requirement_is_not_reported_as_open_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        module,
        "_build_base_report",
        lambda *args, **kwargs: _base_report(supports=False),
    )
    program = _program()
    program["generated_goals"][0]["status"] = "scope_exhausted"
    result = module.build_policy_hardened_scientific_critic_report(
        tmp_path / "unused.json",
        program_state=program,
        artifact_root=tmp_path,
    )
    assert [item["workstream_id"] for item in result["program_evidence_gaps"]] == [
        "tem"
    ]


def test_malformed_program_requirement_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        module,
        "_build_base_report",
        lambda *args, **kwargs: _base_report(supports=False),
    )
    program = _program()
    program["generated_goals"][0]["evidence_requirements"] = [""]
    with pytest.raises(ScientificCriticError, match="must be non-empty text"):
        module.build_policy_hardened_scientific_critic_report(
            tmp_path / "unused.json",
            program_state=program,
            artifact_root=tmp_path,
        )
