from __future__ import annotations

from pathlib import Path

EVIDENCE = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_evidence.py")
REDIAGNOSIS = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_rediagnosis.py")


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
