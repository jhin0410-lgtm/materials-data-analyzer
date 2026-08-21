from __future__ import annotations

from pathlib import Path

EVIDENCE = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_evidence.py")
VALIDATED = Path("src/materials_data_analyzer/research_loop/validated_recursive_cycle_planning.py")
TEST_PLAN = Path("tests/test_autonomous_inquiry_plan_verifier.py")
TEST_HARDENING = Path("tests/test_recursive_research_cycle_review_hardening.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Evidence progression: a successor checkpoint must consume the exact preceding
# progression and bind that progression back to the checkpoint it descended from.
# This closes the no-new-information bypass created by omitting previous_progression.
# ---------------------------------------------------------------------------
evidence = EVIDENCE.read_text(encoding="utf-8")
anchor = '''    ) = _checkpoint(checkpoint)\n    plan, plan_sha = _fresh_plan(\n'''
replacement = '''    ) = _checkpoint(checkpoint)\n\n    cycle_index = checkpoint.get("cycle_index")\n    if (\n        isinstance(cycle_index, bool)\n        or not isinstance(cycle_index, int)\n        or cycle_index < 1\n    ):\n        raise RecursiveResearchEvidenceError(\n            "checkpoint.cycle_index must be an integer >= 1"\n        )\n    checkpoint_ancestry = _mapping(\n        checkpoint.get("ancestry"), "checkpoint.ancestry"\n    )\n    previous_checkpoint_sha = checkpoint_ancestry.get("previous_checkpoint_sha256")\n    previous_sha: str | None = None\n    previous_evaluated_graph_sha: str | None = None\n    if cycle_index == 1:\n        if previous_checkpoint_sha is not None:\n            raise RecursiveResearchEvidenceError(\n                "cycle-one checkpoint cannot carry previous checkpoint ancestry"\n            )\n        if previous_progression is not None:\n            raise RecursiveResearchEvidenceError(\n                "cycle-one progression cannot accept a predecessor progression"\n            )\n    else:\n        expected_previous_checkpoint_sha = _sha(\n            previous_checkpoint_sha,\n            "checkpoint.ancestry.previous_checkpoint_sha256",\n        )\n        if previous_progression is None:\n            raise RecursiveResearchEvidenceError(\n                "successor recursive cycle requires the exact previous progression"\n            )\n        previous = _mapping(previous_progression, "previous_progression")\n        if previous.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:\n            raise RecursiveResearchEvidenceError(\n                "previous progression schema_version drifted"\n            )\n        if previous.get("policy_version") != RECURSIVE_EVIDENCE_POLICY_VERSION:\n            raise RecursiveResearchEvidenceError(\n                "previous progression policy_version drifted"\n            )\n        previous_sha = _embedded_sha(\n            previous,\n            field="previous_progression",\n            sha_field="progression_sha256",\n        )\n        previous_cycle_index = previous.get("cycle_index")\n        if (\n            isinstance(previous_cycle_index, bool)\n            or not isinstance(previous_cycle_index, int)\n            or previous_cycle_index != cycle_index - 1\n        ):\n            raise RecursiveResearchEvidenceError(\n                "previous progression is not the immediately preceding cycle"\n            )\n        previous_target = _mapping(\n            previous.get("target"), "previous_progression.target"\n        )\n        for field in ("graph_id", "node_id", "node_type", "statement"):\n            if previous_target.get(field) != source_target.get(field):\n                raise RecursiveResearchEvidenceError(\n                    f"previous progression does not terminate at current checkpoint target: {field}"\n                )\n        prior_ancestry = _mapping(\n            previous.get("ancestry"), "previous_progression.ancestry"\n        )\n        if (\n            prior_ancestry.get("authorization_checkpoint_sha256")\n            != expected_previous_checkpoint_sha\n        ):\n            raise RecursiveResearchEvidenceError(\n                "previous progression is not bound to the checkpoint predecessor"\n            )\n        previous_evaluated_graph_sha = _sha(\n            prior_ancestry.get("evaluated_graph_canonical_sha256"),\n            "previous_progression.ancestry.evaluated_graph_canonical_sha256",\n        )\n\n    plan, plan_sha = _fresh_plan(\n'''
evidence = replace_once(evidence, anchor, replacement, label="evidence cycle ancestry insert")
old_previous = '''    previous_sha = None\n    if previous_progression is not None:\n        previous = _mapping(previous_progression, "previous_progression")\n        previous_sha = _embedded_sha(\n            previous,\n            field="previous_progression",\n            sha_field="progression_sha256",\n        )\n        previous_target = _mapping(previous.get("target"), "previous_progression.target")\n        for field in ("node_id", "node_type", "statement"):\n            if previous_target.get(field) != current_target.get(field):\n                raise RecursiveResearchEvidenceError(\n                    f"recursive progression target changed across iterations: {field}"\n                )\n        prior_ancestry = _mapping(\n            previous.get("ancestry"), "previous_progression.ancestry"\n        )\n        if prior_ancestry.get("evaluated_graph_canonical_sha256") == graph_sha:\n            raise RecursiveResearchEvidenceError(\n                "recursive cycle produced no new evaluated graph information state"\n            )\n'''
new_previous = '''    if previous_evaluated_graph_sha == graph_sha:\n        raise RecursiveResearchEvidenceError(\n            "recursive cycle produced no new evaluated graph information state"\n        )\n'''
evidence = replace_once(
    evidence,
    old_previous,
    new_previous,
    label="evidence previous progression replacement",
)
evidence = replace_once(
    evidence,
    '        "cycle_index": checkpoint.get("cycle_index"),\n',
    '        "cycle_index": cycle_index,\n',
    label="evidence canonical cycle index",
)
EVIDENCE.write_text(evidence, encoding="utf-8")


# ---------------------------------------------------------------------------
# Validated planning facade: planner reconstruction alone is insufficient. The
# discrepancy-to-planning handoff must itself be rebuilt from the exact hardened
# discrepancy context before the controller may publish an authorization checkpoint.
# ---------------------------------------------------------------------------
validated = VALIDATED.read_text(encoding="utf-8")
validated = replace_once(
    validated,
    'from .autonomous_inquiry_plan_verifier import validate_autonomous_inquiry_plan\nfrom .kernel import ResearchLoopError\n',
    'from .autonomous_inquiry_plan_verifier import validate_autonomous_inquiry_plan\nfrom .discrepancy_planning_handoff_policy import (\n    validate_policy_hardened_discrepancy_planning_handoff,\n)\nfrom .kernel import ResearchLoopError\n',
    label="validated imports",
)
old_signature = '''def build_validated_recursive_planning_checkpoint(\n    *,\n    planning_handoff: Mapping[str, Any],\n    fresh_plan: Mapping[str, Any],\n    planner_program_state: Mapping[str, Any],\n    candidate_match: Mapping[str, Any] | None = None,\n    planner_critic_report: Mapping[str, Any] | None = None,\n    planner_reasoning_proposal: Mapping[str, Any] | None = None,\n    budget_units: float = 8.0,\n    minimum_utility: float = 0.01,\n    previous_checkpoint: Mapping[str, Any] | None = None,\n) -> dict[str, Any]:\n    """Verify planner provenance and build a non-executing recursive checkpoint."""\n    verification = validate_autonomous_inquiry_plan(\n'''
new_signature = '''def build_validated_recursive_planning_checkpoint(\n    *,\n    planning_handoff: Mapping[str, Any],\n    source_discrepancy_report: Mapping[str, Any],\n    source_evaluated_graph: Mapping[str, Any],\n    fresh_plan: Mapping[str, Any],\n    planner_program_state: Mapping[str, Any],\n    source_hypothesis_portfolio: Mapping[str, Any] | None = None,\n    previous_discrepancy_report: Mapping[str, Any] | None = None,\n    candidate_match: Mapping[str, Any] | None = None,\n    planner_critic_report: Mapping[str, Any] | None = None,\n    planner_reasoning_proposal: Mapping[str, Any] | None = None,\n    budget_units: float = 8.0,\n    minimum_utility: float = 0.01,\n    previous_checkpoint: Mapping[str, Any] | None = None,\n) -> dict[str, Any]:\n    """Verify hardened discrepancy provenance and planner identity before publication."""\n    try:\n        handoff_verification = validate_policy_hardened_discrepancy_planning_handoff(\n            planning_handoff,\n            discrepancy_report=source_discrepancy_report,\n            evaluated_graph=source_evaluated_graph,\n            hypothesis_portfolio=source_hypothesis_portfolio,\n            previous_discrepancy_report=previous_discrepancy_report,\n        )\n    except ResearchLoopError as exc:\n        raise ValidatedRecursivePlanningError(\n            "planning handoff failed hardened discrepancy-source reconstruction"\n        ) from exc\n\n    verification = validate_autonomous_inquiry_plan(\n'''
validated = replace_once(
    validated,
    old_signature,
    new_signature,
    label="validated signature and source verification",
)
old_compare = '''    if verification["plan_sha256"] != checkpoint["ancestry"]["fresh_plan_sha256"]:\n        raise ValidatedRecursivePlanningError(\n            "verified planner SHA diverged before recursive checkpoint publication"\n        )\n    result: dict[str, Any] = {\n'''
new_compare = '''    if verification["plan_sha256"] != checkpoint["ancestry"]["fresh_plan_sha256"]:\n        raise ValidatedRecursivePlanningError(\n            "verified planner SHA diverged before recursive checkpoint publication"\n        )\n    if (\n        handoff_verification["handoff_sha256"]\n        != checkpoint["ancestry"]["planning_handoff_sha256"]\n    ):\n        raise ValidatedRecursivePlanningError(\n            "verified discrepancy handoff SHA diverged before recursive checkpoint publication"\n        )\n    result: dict[str, Any] = {\n'''
validated = replace_once(validated, old_compare, new_compare, label="validated SHA compare")
validated = replace_once(
    validated,
    '        "planner_verification": verification,\n        "recursive_checkpoint": checkpoint,\n',
    '        "handoff_verification": handoff_verification,\n        "planner_verification": verification,\n        "recursive_checkpoint": checkpoint,\n',
    label="validated result handoff verification",
)
validated = replace_once(
    validated,
    '            "planner_reconstruction_verified": True,\n',
    '            "source_discrepancy_hardening_verified": True,\n            "planner_reconstruction_verified": True,\n',
    label="validated autonomy source verification",
)
VALIDATED.write_text(validated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Update the existing validated-facade regression to assert that the hardened
# handoff validator is actually invoked with source context. The discrepancy policy
# itself is independently covered elsewhere, so this test uses a narrow monkeypatch.
# ---------------------------------------------------------------------------
plan_test = TEST_PLAN.read_text(encoding="utf-8")
plan_test = replace_once(
    plan_test,
    'import pytest\n\nfrom materials_data_analyzer.research_loop.autonomous_inquiry import (\n',
    'import pytest\n\nimport materials_data_analyzer.research_loop.validated_recursive_cycle_planning as validated_planning\nfrom materials_data_analyzer.research_loop.autonomous_inquiry import (\n',
    label="plan test module import",
)
plan_test = replace_once(
    plan_test,
    '        "schema_version": "1.0",\n        "source_discrepancy_report_sha256": previous_report_sha,\n',
    '        "schema_version": "1.0",\n        "policy_version": "1.0",\n        "source_discrepancy_report_sha256": previous_report_sha,\n',
    label="plan test handoff policy",
)
plan_test = replace_once(
    plan_test,
    '        "research_objectives": [\n',
    '        "source_ancestry": {\n            "previous_discrepancy_report_sha256": None,\n            "prior_diagnosis_types": [],\n            "current_diagnosis_types": ["parameter_or_property_uncertainty"],\n        },\n        "research_objectives": [\n',
    label="plan test handoff ancestry",
)
old_test_head = '''def test_validated_recursive_entry_binds_planner_reconstruction_and_still_grants_no_authority() -> None:\n    program = _program_state()\n    plan = build_autonomous_inquiry_plan(program)\n    handoff = _handoff("a" * 64)\n    match = _match(handoff, plan)\n\n    result = build_validated_recursive_planning_checkpoint(\n        planning_handoff=handoff,\n        fresh_plan=plan,\n        planner_program_state=program,\n        candidate_match=match,\n    )\n'''
new_test_head = '''def test_validated_recursive_entry_binds_planner_reconstruction_and_still_grants_no_authority(\n    monkeypatch,\n) -> None:\n    program = _program_state()\n    plan = build_autonomous_inquiry_plan(program)\n    handoff = _handoff("a" * 64)\n    match = _match(handoff, plan)\n    calls: list[dict] = []\n\n    def fake_handoff_validator(value, **kwargs):\n        calls.append({"handoff": value, **kwargs})\n        return {\n            "handoff_sha256": handoff["handoff_sha256"],\n            "source_discrepancy_hardening_verified": True,\n            "source_discrepancy_physics_hardening_verified": True,\n            "source_discrepancy_report_sha256": "a" * 64,\n        }\n\n    monkeypatch.setattr(\n        validated_planning,\n        "validate_policy_hardened_discrepancy_planning_handoff",\n        fake_handoff_validator,\n    )\n    source_report = {"report_sha256": "a" * 64}\n    source_graph = {"graph_id": "g-1"}\n    result = build_validated_recursive_planning_checkpoint(\n        planning_handoff=handoff,\n        source_discrepancy_report=source_report,\n        source_evaluated_graph=source_graph,\n        fresh_plan=plan,\n        planner_program_state=program,\n        candidate_match=match,\n    )\n    assert calls == [\n        {\n            "handoff": handoff,\n            "discrepancy_report": source_report,\n            "evaluated_graph": source_graph,\n            "hypothesis_portfolio": None,\n            "previous_discrepancy_report": None,\n        }\n    ]\n    assert result["handoff_verification"]["source_discrepancy_hardening_verified"] is True\n'''
plan_test = replace_once(
    plan_test,
    old_test_head,
    new_test_head,
    label="plan test validated facade",
)
TEST_PLAN.write_text(plan_test, encoding="utf-8")


# ---------------------------------------------------------------------------
# Add fail-closed regressions for successor progression presence and predecessor
# checkpoint binding. These fail before any bundle/execution work is attempted.
# ---------------------------------------------------------------------------
hardening = TEST_HARDENING.read_text(encoding="utf-8")
hardening = replace_once(
    hardening,
    'from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (\n    RecursiveResearchCycleError,\n    build_recursive_research_cycle_checkpoint,\n)\n',
    'from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (\n    RecursiveResearchCycleError,\n    build_recursive_research_cycle_checkpoint,\n)\nfrom materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (\n    RecursiveResearchEvidenceError,\n    advance_recursive_cycle_after_verified_transition,\n)\n',
    label="hardening evidence imports",
)
append = r'''


def _successor_checkpoint() -> tuple[dict, dict, dict]:
    first_handoff = _handoff(previous_report_sha=None)
    first_plan = _plan(action_id="planner:review-1")
    first = build_recursive_research_cycle_checkpoint(
        planning_handoff=first_handoff,
        fresh_plan=first_plan,
        candidate_match=_match(first_handoff, first_plan),
    )
    successor_handoff = _handoff(previous_report_sha="a" * 64)
    successor_plan = _plan(action_id="planner:review-2")
    successor = build_recursive_research_cycle_checkpoint(
        planning_handoff=successor_handoff,
        fresh_plan=successor_plan,
        candidate_match=_match(successor_handoff, successor_plan),
        previous_checkpoint=first,
    )
    return first, successor, successor_plan


def test_successor_evidence_progression_requires_exact_previous_progression() -> None:
    _first, successor, successor_plan = _successor_checkpoint()
    with pytest.raises(RecursiveResearchEvidenceError, match="requires the exact previous progression"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=successor,
            verified_execution_record={},
            transition_bundle_root="unused",
            fresh_plan=successor_plan,
            program_state={},
            previous_progression=None,
        )


def test_successor_progression_must_bind_checkpoint_predecessor() -> None:
    first, successor, successor_plan = _successor_checkpoint()
    forged_previous = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_index": 1,
        "target": dict(successor["target"]),
        "ancestry": {
            "authorization_checkpoint_sha256": "f" * 64,
            "evaluated_graph_canonical_sha256": "e" * 64,
        },
    }
    forged_previous["progression_sha256"] = _sha(forged_previous)
    assert successor["ancestry"]["previous_checkpoint_sha256"] == first["checkpoint_sha256"]
    with pytest.raises(RecursiveResearchEvidenceError, match="checkpoint predecessor"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=successor,
            verified_execution_record={},
            transition_bundle_root="unused",
            fresh_plan=successor_plan,
            program_state={},
            previous_progression=forged_previous,
        )
'''
if "test_successor_evidence_progression_requires_exact_previous_progression" in hardening:
    raise SystemExit("hardening successor progression tests already present")
hardening += append
TEST_HARDENING.write_text(hardening, encoding="utf-8")
