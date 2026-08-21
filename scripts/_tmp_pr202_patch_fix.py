from __future__ import annotations

from pathlib import Path

EVIDENCE = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_evidence.py")
REDIAGNOSIS = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_rediagnosis.py")
TEST_ADAPTER = Path("tests/test_recursive_authenticated_transition_adapter.py")


def require_once(text: str, needle: str, replacement: str, *, label: str) -> str:
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(needle, replacement, 1)


# The primary patch replaces the evidence body against a branch that already had
# authenticated-transition imports. Add the new authoritative dependencies explicitly
# instead of relying on the older import-layout anchor.
evidence = EVIDENCE.read_text(encoding="utf-8")
consumer_block = '''from .authenticated_transition_consumer import (
    AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION,
    AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION,
    authenticate_transition_bundle,
)
'''
consumer_replacement = '''from .authenticated_transition_consumer import (
    AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION,
    AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION,
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
from .autonomous_inquiry import AUTONOMOUS_INQUIRY_POLICY_VERSION
from .epistemic_graph import EpistemicGraphError, evaluate_epistemic_graph
'''
evidence = require_once(
    evidence,
    consumer_block,
    consumer_replacement,
    label="evidence authenticated-transition imports",
)
portfolio_block = '''from .hypothesis_portfolio import (
    HYPOTHESIS_PORTFOLIO_POLICY_VERSION,
    HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION,
)
'''
portfolio_replacement = '''from .hypothesis_portfolio import (
    HYPOTHESIS_PORTFOLIO_POLICY_VERSION,
    HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION,
    HypothesisPortfolioError,
    build_hypothesis_portfolio,
)
'''
evidence = require_once(
    evidence,
    portfolio_block,
    portfolio_replacement,
    label="evidence hypothesis-portfolio imports",
)
evidence = evidence.replace(
    '    "build_epistemic_transition_record_from_authenticated_bundle",\n',
    "",
)
EVIDENCE.write_text(evidence, encoding="utf-8")


# The branch already formatted/hardened this function before the primary patch was
# authored, so replace the post-signature bridge by semantic anchors rather than an
# exact older formatting snapshot.
rediagnosis = REDIAGNOSIS.read_text(encoding="utf-8")
start = rediagnosis.index('    graph = _mapping(evaluated_graph, "evaluated_graph")')
end = rediagnosis.index('    previous_report_sha = _embedded_sha(', start)
bridge = '''    graph = _mapping(evaluated_graph, "evaluated_graph")

    checkpoint_sha, source_target, expected_previous_report_sha = (
        _authorization_checkpoint(checkpoint)
    )
    progression_sha, target, portfolio = _progression(
        progress,
        checkpoint_sha=checkpoint_sha,
        source_target=source_target,
        evaluated_graph=graph,
    )
'''
rediagnosis = rediagnosis[:start] + bridge + rediagnosis[end:]

verified_anchor = '''    verified = validate_physics_hardened_model_evidence_discrepancy_report(
        current,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
        previous_report=previous,
    )
'''
verified_replacement = '''    previous_target = _mapping(
        previous.get("target"), "previous_discrepancy_report.target"
    )
    if previous_target != source_target:
        raise RecursiveResearchRediagnosisError(
            "previous discrepancy report target differs from checkpoint source target"
        )
    verified = validate_physics_hardened_model_evidence_discrepancy_report(
        current,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
        previous_report=previous,
    )
'''
rediagnosis = require_once(
    rediagnosis,
    verified_anchor,
    verified_replacement,
    label="rediagnosis hardened validator",
)
REDIAGNOSIS.write_text(rediagnosis, encoding="utf-8")


# The hardened evidence path deliberately removes the old self-certifying transition
# record builder. Repoint the focused adapter regression at the real authenticated
# consumer bridge used by progression.
TEST_ADAPTER.write_text(
    '''from __future__ import annotations

import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
)


def _execution() -> dict:
    return {
        "action_id": "planner:analysis",
        "action_type": "analysis",
        "action_version": "1.0",
        "result_sha256": "d" * 64,
    }


def _source_target() -> dict:
    return {
        "graph_id": "g-1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "H",
    }


def _evaluated_graph() -> dict:
    return {
        "graph_id": "g-2",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "H",
            }
        ],
        "assessments": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "status": "inconclusive",
            }
        ],
    }


def _write_bundle(tmp_path):
    graph = {
        "graph_id": "g-2",
        "nodes": [{"node_id": "h-1", "node_type": "hypothesis", "statement": "H"}],
        "edges": [],
    }
    graph_bytes = json.dumps(graph, ensure_ascii=False, sort_keys=True).encode("utf-8")
    graph_path = tmp_path / "epistemic_graph.json"
    graph_path.write_bytes(graph_bytes)
    proposal = {
        "transition_id": "transition-1",
        "base_graph_id": "g-1",
        "new_graph_id": "g-2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": "planner:analysis",
            "action_class": "analysis",
            "action_version": "1.0",
        },
        "result_node": {
            "artifact_bindings": [{"role": "result", "sha256": "d" * 64}]
        },
    }
    proposal_bytes = json.dumps(proposal, ensure_ascii=False, sort_keys=True).encode("utf-8")
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_bytes(proposal_bytes)
    report = {
        "bundle_root": str(tmp_path.resolve()),
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": "transition-1",
        "target_node_id": "h-1",
        "inference_edge_id": "edge-1",
        "relation": "supports",
        "inference_scope": "computational",
        "proposal_binding": {
            "path": "proposal.json",
            "sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        },
        "graph_binding": {
            "path": "epistemic_graph.json",
            "sha256": hashlib.sha256(graph_bytes).hexdigest(),
        },
    }
    return report, graph_path


def test_adapter_executes_consumer_binds_execution_and_evaluates_successor(
    monkeypatch, tmp_path
) -> None:
    report, _graph_path = _write_bundle(tmp_path)
    calls: list[object] = []

    def fake_consumer(root):
        calls.append(root)
        return report

    evaluated = _evaluated_graph()
    monkeypatch.setattr(evidence, "authenticate_transition_bundle", fake_consumer)
    monkeypatch.setattr(
        evidence,
        "evaluate_epistemic_graph",
        lambda graph, *, program_state, artifact_root: evaluated,
    )

    (
        report_sha,
        transition,
        actual_evaluated,
        evaluated_sha,
        target,
        assessment,
    ) = evidence._authenticated_transition(
        bundle_root=tmp_path,
        execution=_execution(),
        source_target=_source_target(),
        program_state={"workstreams": []},
    )

    assert calls == [tmp_path]
    assert report_sha == evidence._canonical_sha256(report)
    assert transition["transition_id"] == "transition-1"
    assert transition["current_transition_exact_provenance_authenticated"] is True
    assert transition["execution_completion_treated_as_scientific_support"] is False
    assert actual_evaluated == evaluated
    assert evaluated_sha == evidence._canonical_sha256(evaluated)
    assert target["graph_id"] == "g-2"
    assert assessment["status"] == "inconclusive"


def test_adapter_rejects_graph_bytes_changed_after_consumer_verification(
    monkeypatch, tmp_path
) -> None:
    report, graph_path = _write_bundle(tmp_path)
    monkeypatch.setattr(evidence, "authenticate_transition_bundle", lambda root: report)
    graph_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RecursiveResearchEvidenceError, match="changed after authenticated"):
        evidence._authenticated_transition(
            bundle_root=tmp_path,
            execution=_execution(),
            source_target=_source_target(),
            program_state={"workstreams": []},
        )
''',
    encoding="utf-8",
)
