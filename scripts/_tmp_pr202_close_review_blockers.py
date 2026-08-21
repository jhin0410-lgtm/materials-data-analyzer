from __future__ import annotations

from pathlib import Path

CONTROLLER = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_controller.py")
EVIDENCE = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_evidence.py")
REDIAGNOSIS = Path("src/materials_data_analyzer/research_loop/recursive_research_cycle_rediagnosis.py")
TEST_CONTROLLER = Path("tests/test_recursive_research_cycle_controller.py")
TEST_EVIDENCE = Path("tests/test_recursive_research_cycle_evidence.py")
TEST_REDIAGNOSIS = Path("tests/test_recursive_research_cycle_rediagnosis.py")
TEST_INTEGRATION = Path("tests/test_recursive_research_cycle_integration.py")


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement.rstrip() + "\n\n" + text[j:]


# ---------------------------------------------------------------------------
# Controller: bind successor discrepancy ancestry to the previous checkpoint.
# Planner policy + stop-decision hardening already landed on this branch; keep it.
# ---------------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")
old = '''def _verify_handoff(\n    handoff: Mapping[str, Any],\n) -> tuple[str, dict[str, Any], list[dict[str, Any]], bool]:'''
new = '''def _verify_handoff(\n    handoff: Mapping[str, Any],\n) -> tuple[str, dict[str, Any], list[dict[str, Any]], str | None]:'''
if old not in controller:
    raise SystemExit("controller _verify_handoff signature anchor missing")
controller = controller.replace(old, new, 1)
old = '''    previous_report_sha = source_ancestry.get("previous_discrepancy_report_sha256")\n    successor_handoff = previous_report_sha is not None\n    if successor_handoff:\n        _sha(\n            previous_report_sha,\n            "planning_handoff.source_ancestry.previous_discrepancy_report_sha256",\n        )\n    return handoff_sha, target, objectives, successor_handoff\n'''
new = '''    previous_report_sha = source_ancestry.get("previous_discrepancy_report_sha256")\n    if previous_report_sha is not None:\n        previous_report_sha = _sha(\n            previous_report_sha,\n            "planning_handoff.source_ancestry.previous_discrepancy_report_sha256",\n        )\n    return handoff_sha, target, objectives, previous_report_sha\n'''
if old not in controller:
    raise SystemExit("controller handoff ancestry anchor missing")
controller = controller.replace(old, new, 1)
old = '''def _previous_checkpoint(\n    previous: Mapping[str, Any] | None,\n    *,\n    target: Mapping[str, Any],\n    current_plan_sha: str,\n    successor_handoff: bool,\n) -> tuple[str | None, int]:\n    if previous is None:\n        if successor_handoff:\n            raise RecursiveResearchCycleError(\n                "successor discrepancy handoff requires previous recursive checkpoint ancestry"\n            )\n        return None, 1\n'''
new = '''def _previous_checkpoint(\n    previous: Mapping[str, Any] | None,\n    *,\n    target: Mapping[str, Any],\n    current_plan_sha: str,\n    previous_discrepancy_report_sha256: str | None,\n) -> tuple[str | None, int]:\n    if previous is None:\n        if previous_discrepancy_report_sha256 is not None:\n            raise RecursiveResearchCycleError(\n                "successor discrepancy handoff requires previous recursive checkpoint ancestry"\n            )\n        return None, 1\n'''
if old not in controller:
    raise SystemExit("controller previous checkpoint signature anchor missing")
controller = controller.replace(old, new, 1)
old = '''    previous_target = _mapping(\n        previous.get("target"), "previous_checkpoint.target"\n    )\n    for field in ("graph_id", "node_id", "node_type", "statement"):\n        if previous_target.get(field) != target.get(field):\n            raise RecursiveResearchCycleError(\n                f"recursive cycle target identity changed across checkpoints: {field}"\n            )\n    ancestry = _mapping(\n        previous.get("ancestry"), "previous_checkpoint.ancestry"\n    )\n'''
new = '''    previous_target = _mapping(\n        previous.get("target"), "previous_checkpoint.target"\n    )\n    # A verified epistemic transition is allowed to advance graph_id, but it may not\n    # silently change the stable hypothesis/claim identity under the recursive cycle.\n    for field in ("node_id", "node_type", "statement"):\n        if previous_target.get(field) != target.get(field):\n            raise RecursiveResearchCycleError(\n                f"recursive cycle target identity changed across checkpoints: {field}"\n            )\n    if (\n        previous_discrepancy_report_sha256 is None\n        and previous_target.get("graph_id") != target.get("graph_id")\n    ):\n        raise RecursiveResearchCycleError(\n            "recursive cycle graph identity changed without successor discrepancy ancestry"\n        )\n    ancestry = _mapping(\n        previous.get("ancestry"), "previous_checkpoint.ancestry"\n    )\n    if previous_discrepancy_report_sha256 is not None:\n        previous_source_report_sha = _sha(\n            ancestry.get("source_discrepancy_report_sha256"),\n            "previous_checkpoint.ancestry.source_discrepancy_report_sha256",\n        )\n        if previous_source_report_sha != previous_discrepancy_report_sha256:\n            raise RecursiveResearchCycleError(\n                "successor discrepancy ancestry does not descend from the previous checkpoint report"\n            )\n'''
if old not in controller:
    raise SystemExit("controller target ancestry anchor missing")
controller = controller.replace(old, new, 1)
old = '''    handoff_sha, target, objectives, successor_handoff = _verify_handoff(handoff)\n    plan_sha, ranked, selected, stop_decision = _verify_plan(plan)\n    previous_sha, cycle_index = _previous_checkpoint(\n        previous_checkpoint,\n        target=target,\n        current_plan_sha=plan_sha,\n        successor_handoff=successor_handoff,\n    )\n'''
new = '''    handoff_sha, target, objectives, previous_report_sha = _verify_handoff(handoff)\n    plan_sha, ranked, selected, stop_decision = _verify_plan(plan)\n    previous_sha, cycle_index = _previous_checkpoint(\n        previous_checkpoint,\n        target=target,\n        current_plan_sha=plan_sha,\n        previous_discrepancy_report_sha256=previous_report_sha,\n    )\n'''
if old not in controller:
    raise SystemExit("controller build ancestry anchor missing")
controller = controller.replace(old, new, 1)
CONTROLLER.write_text(controller, encoding="utf-8")


# ---------------------------------------------------------------------------
# Evidence progression: consume the real authenticated transition bundle,
# bind the executed action to both the selected planner action and proposal,
# independently evaluate the exact authenticated successor graph, and build the
# hypothesis portfolio from the authoritative portfolio builder.
# ---------------------------------------------------------------------------
evidence = EVIDENCE.read_text(encoding="utf-8")
evidence = evidence.replace(
    "from collections.abc import Mapping, Sequence\nfrom typing import Any\n\nfrom .kernel import ResearchLoopError\n",
    "from collections.abc import Mapping, Sequence\nfrom pathlib import Path\nfrom typing import Any\n\nfrom .authenticated_transition_consumer import (\n    AuthenticatedTransitionConsumerError,\n    authenticate_transition_bundle,\n)\nfrom .autonomous_inquiry import AUTONOMOUS_INQUIRY_POLICY_VERSION\nfrom .epistemic_graph import EpistemicGraphError, evaluate_epistemic_graph\nfrom .hypothesis_portfolio import HypothesisPortfolioError, build_hypothesis_portfolio\nfrom .kernel import ResearchLoopError\n",
    1,
)
evidence = evidence.replace('EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION = "1.0"\n', "", 1)
start = evidence.index("def _checkpoint(")
end = evidence.index("\n\n__all__ = [", start)
new_evidence_body = r'''def _checkpoint(
    value: Mapping[str, Any],
) -> tuple[str, dict[str, Any], str, str, str]:
    if value.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint schema_version"
        )
    if value.get("policy_version") != RECURSIVE_CYCLE_POLICY_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint policy_version"
        )
    digest = _embedded_sha(
        value,
        field="checkpoint",
        sha_field="checkpoint_sha256",
    )
    if value.get("checkpoint_status") != "explicit_authorization_required":
        raise RecursiveResearchEvidenceError(
            "post-execution progression requires an explicit_authorization_required checkpoint"
        )
    boundary = _mapping(value.get("autonomy_boundary"), "checkpoint.autonomy_boundary")
    if boundary.get("authorization_granted") is not False:
        raise RecursiveResearchEvidenceError(
            "planning checkpoint must not have self-granted authorization"
        )
    target = dict(_mapping(value.get("target"), "checkpoint.target"))
    for field in ("graph_id", "node_id", "node_type", "statement"):
        _text(target.get(field), f"checkpoint.target.{field}")

    candidate = _mapping(value.get("candidate_match"), "checkpoint.candidate_match")
    action_id = _text(
        candidate.get("candidate_action_id"),
        "checkpoint.candidate_match.candidate_action_id",
    )
    action_class = _text(
        candidate.get("candidate_action_class"),
        "checkpoint.candidate_match.candidate_action_class",
    )
    planner_state = _mapping(
        value.get("fresh_planner_state"), "checkpoint.fresh_planner_state"
    )
    if planner_state.get("selected_candidate_id") != action_id:
        raise RecursiveResearchEvidenceError(
            "checkpoint selected candidate and candidate-match action_id diverge"
        )
    ancestry = _mapping(value.get("ancestry"), "checkpoint.ancestry")
    plan_sha = _sha(
        ancestry.get("fresh_plan_sha256"),
        "checkpoint.ancestry.fresh_plan_sha256",
    )
    return digest, target, action_id, action_class, plan_sha


def _execution_record(
    value: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    expected_action_id: str,
    expected_action_type: str,
) -> tuple[str, dict[str, Any]]:
    if value.get("schema_version") != VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported verified execution record schema_version"
        )
    digest = _embedded_sha(
        value,
        field="verified_execution_record",
        sha_field="verification_record_sha256",
    )
    if value.get("source_checkpoint_sha256") != checkpoint_sha:
        raise RecursiveResearchEvidenceError(
            "verified execution record is bound to a different recursive checkpoint"
        )
    if (
        value.get("authorization_status")
        != "explicit_request_authorized_by_existing_chain"
    ):
        raise RecursiveResearchEvidenceError(
            "execution record does not attest existing-chain explicit authorization"
        )
    if value.get("independent_verification_status") != "verified_by_existing_chain":
        raise RecursiveResearchEvidenceError(
            "execution record is not marked as independently verified by the existing chain"
        )
    action_id = _text(value.get("action_id"), "verified_execution_record.action_id")
    action_type = _text(value.get("action_type"), "verified_execution_record.action_type")
    action_version = _text(
        value.get("action_version"), "verified_execution_record.action_version"
    )
    if action_id != expected_action_id:
        raise RecursiveResearchEvidenceError(
            "verified execution action_id does not match the planner-selected checkpoint action"
        )
    if action_type != expected_action_type:
        raise RecursiveResearchEvidenceError(
            "verified execution action_type does not match the checkpoint candidate action class"
        )
    for field in ("request_sha256", "registry_sha256", "result_sha256"):
        _sha(value.get(field), f"verified_execution_record.{field}")
    outcome = _text(
        value.get("execution_outcome"),
        "verified_execution_record.execution_outcome",
    )
    if outcome not in {"completed", "rejected", "failed"}:
        raise RecursiveResearchEvidenceError("unsupported verified execution outcome")
    success = value.get("execution_success")
    if not isinstance(success, bool):
        raise RecursiveResearchEvidenceError(
            "verified_execution_record.execution_success must be boolean"
        )
    if success != (outcome == "completed"):
        raise RecursiveResearchEvidenceError(
            "rejected/failed execution cannot be represented as verified execution success"
        )
    if value.get("scientific_evidence_upgraded") is not False:
        raise RecursiveResearchEvidenceError(
            "execution verification cannot itself upgrade scientific evidence"
        )
    return digest, {
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "request_sha256": value["request_sha256"],
        "registry_sha256": value["registry_sha256"],
        "result_sha256": value["result_sha256"],
        "execution_outcome": outcome,
        "execution_success": success,
    }


def _fresh_plan(value: Mapping[str, Any], *, expected_sha: str) -> tuple[dict[str, Any], str]:
    plan = dict(_mapping(value, "fresh_plan"))
    if plan.get("schema_version") != "1.0":
        raise RecursiveResearchEvidenceError("unsupported fresh plan schema_version")
    if plan.get("policy_version") != AUTONOMOUS_INQUIRY_POLICY_VERSION:
        raise RecursiveResearchEvidenceError("unsupported fresh plan policy_version")
    digest = _embedded_sha(plan, field="fresh_plan", sha_field="plan_sha256")
    if digest != expected_sha:
        raise RecursiveResearchEvidenceError(
            "fresh plan is not the exact plan bound into the authorization checkpoint"
        )
    return plan, digest


def _read_bound_json(
    bundle_root: Path,
    binding_value: object,
    *,
    field: str,
) -> dict[str, Any]:
    binding = _mapping(binding_value, field)
    path_text = _text(binding.get("path"), f"{field}.path")
    expected_sha = _sha(binding.get("sha256"), f"{field}.sha256")
    candidate = bundle_root / path_text
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(bundle_root)
    except (OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            f"{field} escaped or disappeared after authenticated transition verification"
        ) from exc
    if not resolved.is_file():
        raise RecursiveResearchEvidenceError(f"{field} must remain a regular file")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise RecursiveResearchEvidenceError(
            f"{field} changed after authenticated transition verification"
        )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecursiveResearchEvidenceError(f"{field} is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise RecursiveResearchEvidenceError(f"{field} root must be an object")
    return parsed


def _target_assessment(
    evaluated_graph: Mapping[str, Any],
    *,
    source_target: Mapping[str, Any],
    successor_graph_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = _sequence(evaluated_graph.get("nodes"), "evaluated_graph.nodes")
    matches = [
        item
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id") == source_target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target must resolve to exactly one authenticated successor graph node"
        )
    node = matches[0]
    for field in ("node_type", "statement"):
        if node.get(field) != source_target[field]:
            raise RecursiveResearchEvidenceError(
                f"authenticated successor graph target identity drifted: {field}"
            )
    assessments = _sequence(
        evaluated_graph.get("assessments"), "evaluated_graph.assessments"
    )
    assessed = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == source_target["node_id"]
    ]
    if len(assessed) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target requires exactly one evaluated epistemic assessment"
        )
    assessment = dict(assessed[0])
    _text(assessment.get("status"), "evaluated_graph target assessment.status")
    current_target = dict(source_target)
    current_target["graph_id"] = successor_graph_id
    return current_target, assessment


def _authenticated_transition(
    *,
    bundle_root: str | Path,
    execution: Mapping[str, Any],
    source_target: Mapping[str, Any],
    program_state: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    try:
        report = authenticate_transition_bundle(bundle_root)
    except (AuthenticatedTransitionConsumerError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated transition bundle failed independent consumer verification"
        ) from exc
    if report.get("current_transition_exact_provenance_authenticated") is not True:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer did not establish exact current-transition provenance"
        )
    root = Path(_text(report.get("bundle_root"), "transition_consumer.bundle_root"))
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated transition bundle root disappeared after verification"
        ) from exc

    proposal = _read_bound_json(
        root,
        report.get("proposal_binding"),
        field="transition_consumer.proposal_binding",
    )
    graph = _read_bound_json(
        root,
        report.get("graph_binding"),
        field="transition_consumer.graph_binding",
    )
    source_action = _mapping(proposal.get("source_action"), "transition proposal.source_action")
    if source_action.get("action_id") != execution["action_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_id differs from verified execution"
        )
    if source_action.get("action_class") != execution["action_type"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_class differs from verified execution"
        )
    if source_action.get("action_version") != execution["action_version"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_version differs from verified execution"
        )
    if proposal.get("base_graph_id") != source_target["graph_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition base_graph_id differs from recursive checkpoint graph"
        )
    if proposal.get("target_node_id") != source_target["node_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition target differs from recursive checkpoint target"
        )
    if report.get("target_node_id") != source_target["node_id"]:
        raise RecursiveResearchEvidenceError(
            "transition consumer target differs from recursive checkpoint target"
        )
    if report.get("transition_id") != proposal.get("transition_id"):
        raise RecursiveResearchEvidenceError(
            "transition consumer transition_id differs from exact proposal"
        )
    successor_graph_id = _text(proposal.get("new_graph_id"), "transition proposal.new_graph_id")
    if graph.get("graph_id") != successor_graph_id:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph_id differs from exact transition proposal"
        )
    result_node = _mapping(proposal.get("result_node"), "transition proposal.result_node")
    result_bindings = _sequence(
        result_node.get("artifact_bindings"),
        "transition proposal.result_node.artifact_bindings",
    )
    result_shas = {
        item.get("sha256")
        for item in result_bindings
        if isinstance(item, Mapping) and isinstance(item.get("sha256"), str)
    }
    if execution["result_sha256"] not in result_shas:
        raise RecursiveResearchEvidenceError(
            "verified execution result SHA is absent from the authenticated transition result artifacts"
        )

    try:
        evaluated_graph = evaluate_epistemic_graph(
            graph,
            program_state=program_state,
            artifact_root=root,
        )
    except (EpistemicGraphError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph could not be independently evaluated"
        ) from exc
    evaluated_sha = _canonical_sha256(evaluated_graph)
    current_target, assessment = _target_assessment(
        evaluated_graph,
        source_target=source_target,
        successor_graph_id=successor_graph_id,
    )
    report_sha = _canonical_sha256(report)
    graph_binding = _mapping(report.get("graph_binding"), "transition_consumer.graph_binding")
    transition = {
        "transition_id": report["transition_id"],
        "base_graph_id": proposal["base_graph_id"],
        "new_graph_id": successor_graph_id,
        "target_node_id": report["target_node_id"],
        "inference_edge_id": report.get("inference_edge_id"),
        "relation": report.get("relation"),
        "inference_scope": report.get("inference_scope"),
        "authenticated_successor_graph_sha256": _sha(
            graph_binding.get("sha256"),
            "transition_consumer.graph_binding.sha256",
        ),
        "transition_consumer_report_sha256": report_sha,
        "current_transition_exact_provenance_authenticated": True,
        "execution_completion_treated_as_scientific_support": False,
        "scientific_authority_applied_by_recursive_controller": False,
    }
    return (
        report_sha,
        transition,
        evaluated_graph,
        evaluated_sha,
        current_target,
        assessment,
    )


def _authoritative_portfolio(
    *,
    evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    target: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    try:
        portfolio = build_hypothesis_portfolio(
            evaluated_graph,
            plan=fresh_plan,
            previous_portfolio=None,
        )
    except HypothesisPortfolioError as exc:
        raise RecursiveResearchEvidenceError(
            "authoritative hypothesis portfolio refresh failed"
        ) from exc
    digest = _sha(
        portfolio.get("portfolio_sha256"),
        "authoritative_hypothesis_portfolio.portfolio_sha256",
    )
    if target["node_type"] != "hypothesis":
        return portfolio, digest, None
    records = _sequence(portfolio.get("hypotheses"), "hypothesis_portfolio.hypotheses")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping) and item.get("hypothesis_id") == target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "target hypothesis must resolve to exactly one authoritative portfolio record"
        )
    record = dict(matches[0])
    if record.get("statement") != target["statement"]:
        raise RecursiveResearchEvidenceError(
            "authoritative portfolio hypothesis statement drifted"
        )
    if record.get("epistemic_status") != assessment.get("status"):
        raise RecursiveResearchEvidenceError(
            "authoritative portfolio status differs from evaluated graph assessment"
        )
    return portfolio, digest, record


def advance_recursive_cycle_after_verified_transition(
    *,
    authorization_checkpoint: Mapping[str, Any],
    verified_execution_record: Mapping[str, Any],
    transition_bundle_root: str | Path,
    fresh_plan: Mapping[str, Any],
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind verified execution -> authenticated transition -> authoritative portfolio."""
    checkpoint = _mapping(authorization_checkpoint, "authorization_checkpoint")
    (
        checkpoint_sha,
        source_target,
        expected_action_id,
        expected_action_type,
        expected_plan_sha,
    ) = _checkpoint(checkpoint)
    plan, plan_sha = _fresh_plan(
        _mapping(fresh_plan, "fresh_plan"),
        expected_sha=expected_plan_sha,
    )
    execution_sha, execution = _execution_record(
        _mapping(verified_execution_record, "verified_execution_record"),
        checkpoint_sha=checkpoint_sha,
        expected_action_id=expected_action_id,
        expected_action_type=expected_action_type,
    )
    (
        transition_report_sha,
        transition,
        evaluated_graph,
        graph_sha,
        current_target,
        assessment,
    ) = _authenticated_transition(
        bundle_root=transition_bundle_root,
        execution=execution,
        source_target=source_target,
        program_state=_mapping(program_state, "program_state"),
    )
    portfolio, portfolio_sha, portfolio_state = _authoritative_portfolio(
        evaluated_graph=evaluated_graph,
        fresh_plan=plan,
        target=current_target,
        assessment=assessment,
    )

    previous_sha = None
    if previous_progression is not None:
        previous = _mapping(previous_progression, "previous_progression")
        previous_sha = _embedded_sha(
            previous,
            field="previous_progression",
            sha_field="progression_sha256",
        )
        previous_target = _mapping(previous.get("target"), "previous_progression.target")
        for field in ("node_id", "node_type", "statement"):
            if previous_target.get(field) != current_target.get(field):
                raise RecursiveResearchEvidenceError(
                    f"recursive progression target changed across iterations: {field}"
                )
        prior_ancestry = _mapping(
            previous.get("ancestry"), "previous_progression.ancestry"
        )
        if prior_ancestry.get("evaluated_graph_canonical_sha256") == graph_sha:
            raise RecursiveResearchEvidenceError(
                "recursive cycle produced no new evaluated graph information state"
            )

    portfolio_state_name = (
        portfolio_state.get("portfolio_state") if portfolio_state is not None else None
    )
    if portfolio_state_name == "retired_falsified_within_verified_scope":
        status = "bounded_stop_hypothesis_retired"
        re_diagnosis_required = False
        stop_reason = "Target hypothesis remains retired/falsified within verified scope."
    elif portfolio_state_name == "positive_closeout_required":
        status = "bounded_stop_domain_closeout_required"
        re_diagnosis_required = False
        stop_reason = "Positive scientific closeout requires separate domain review."
    else:
        status = "re_diagnosis_required"
        re_diagnosis_required = True
        stop_reason = None

    result: dict[str, Any] = {
        "schema_version": RECURSIVE_CYCLE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_EVIDENCE_POLICY_VERSION,
        "cycle_id": checkpoint.get("cycle_id"),
        "cycle_index": checkpoint.get("cycle_index"),
        "progression_status": status,
        "source_target": dict(source_target),
        "target": dict(current_target),
        "ancestry": {
            "previous_progression_sha256": previous_sha,
            "authorization_checkpoint_sha256": checkpoint_sha,
            "fresh_plan_sha256": plan_sha,
            "verified_execution_record_sha256": execution_sha,
            "authenticated_transition_consumer_report_sha256": transition_report_sha,
            "authenticated_successor_graph_sha256": transition[
                "authenticated_successor_graph_sha256"
            ],
            "evaluated_graph_canonical_sha256": graph_sha,
            "hypothesis_portfolio_sha256": portfolio_sha,
        },
        "verified_execution": execution,
        "verified_epistemic_transition": transition,
        "target_epistemic_assessment": dict(assessment),
        "hypothesis_portfolio": portfolio,
        "target_hypothesis_portfolio_state": portfolio_state,
        "re_diagnosis": {
            "required": re_diagnosis_required,
            "performed": False,
            "previous_discrepancy_report_reuse_authorized": False,
        },
        "bounded_stop": {
            "stopped": not re_diagnosis_required,
            "reason": stop_reason,
        },
        "autonomy_boundary": {
            "verification_authority_created_by_controller": False,
            "authorization_created_by_controller": False,
            "execution_performed_by_controller": False,
            "epistemic_interpretation_created_by_controller": False,
            "epistemic_edge_created_by_controller": False,
            "hypothesis_state_invented_by_controller": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed_by_controller": False,
        },
    }
    result["progression_sha256"] = _canonical_sha256(result)
    return result'''
evidence = evidence[:start] + new_evidence_body + evidence[end:]
evidence = evidence.replace('    "EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION",\n', "", 1)
EVIDENCE.write_text(evidence, encoding="utf-8")


# ---------------------------------------------------------------------------
# Re-diagnosis: use only physics/provenance-hardened public boundaries and
# consume the authoritative portfolio already bound into progression.
# ---------------------------------------------------------------------------
rediagnosis = REDIAGNOSIS.read_text(encoding="utf-8")
rediagnosis = rediagnosis.replace(
    "from .discrepancy_planning_handoff import build_discrepancy_planning_handoff\nfrom .kernel import ResearchLoopError\nfrom .model_evidence_discrepancy import validate_model_evidence_discrepancy_report\n",
    "from .discrepancy_planning_handoff import DiscrepancyPlanningHandoffError\nfrom .discrepancy_planning_handoff_policy import (\n    build_policy_hardened_discrepancy_planning_handoff,\n)\nfrom .kernel import ResearchLoopError\nfrom .model_evidence_discrepancy_physics_policy import (\n    ModelEvidenceDiscrepancyPhysicsPolicyError,\n    validate_physics_hardened_model_evidence_discrepancy_report,\n)\n",
    1,
)
start = rediagnosis.index("def _progression(")
end = rediagnosis.index("\n\ndef complete_recursive_cycle_with_rediagnosis", start)
new_progression = r'''def _progression(
    progression: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    source_target: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    if progression.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchRediagnosisError("unsupported progression schema_version")
    if progression.get("policy_version") != RECURSIVE_EVIDENCE_POLICY_VERSION:
        raise RecursiveResearchRediagnosisError("unsupported progression policy_version")
    digest = _embedded_sha(
        progression,
        field="progression",
        sha_field="progression_sha256",
    )
    if progression.get("progression_status") != "re_diagnosis_required":
        raise RecursiveResearchRediagnosisError(
            "progression does not require another discrepancy diagnosis"
        )
    if progression.get("source_target") != source_target:
        raise RecursiveResearchRediagnosisError(
            "progression source target differs from authorization checkpoint target"
        )
    target = _mapping(progression.get("target"), "progression.target")
    for field in ("node_id", "node_type", "statement"):
        if target.get(field) != source_target.get(field):
            raise RecursiveResearchRediagnosisError(
                f"progression target identity drifted across authenticated graph transition: {field}"
            )
    _text(target.get("graph_id"), "progression.target.graph_id")
    ancestry = _mapping(progression.get("ancestry"), "progression.ancestry")
    if ancestry.get("authorization_checkpoint_sha256") != checkpoint_sha:
        raise RecursiveResearchRediagnosisError(
            "progression is bound to a different authorization checkpoint"
        )
    graph_sha = _canonical_sha256(evaluated_graph)
    if ancestry.get("evaluated_graph_canonical_sha256") != graph_sha:
        raise RecursiveResearchRediagnosisError(
            "progression is bound to a different evaluated graph"
        )
    portfolio = _mapping(
        progression.get("hypothesis_portfolio"),
        "progression.hypothesis_portfolio",
    )
    portfolio_sha = _embedded_sha(
        portfolio,
        field="progression.hypothesis_portfolio",
        sha_field="portfolio_sha256",
    )
    if ancestry.get("hypothesis_portfolio_sha256") != portfolio_sha:
        raise RecursiveResearchRediagnosisError(
            "progression portfolio binding differs from its authoritative embedded portfolio"
        )
    return digest, target, portfolio'''
rediagnosis = rediagnosis[:start] + new_progression + rediagnosis[end:]
rediagnosis = rediagnosis.replace(
    '''    evaluated_graph: Mapping[str, Any],\n    hypothesis_portfolio: Mapping[str, Any],\n) -> dict[str, Any]:''',
    '''    evaluated_graph: Mapping[str, Any],\n) -> dict[str, Any]:''',
    1,
)
rediagnosis = rediagnosis.replace(
    '''    graph = _mapping(evaluated_graph, "evaluated_graph")\n    portfolio = _mapping(hypothesis_portfolio, "hypothesis_portfolio")\n\n    checkpoint_sha, target, expected_previous_report_sha = _authorization_checkpoint(checkpoint)\n    progression_sha = _progression(\n        progress,\n        checkpoint_sha=checkpoint_sha,\n        target=target,\n        evaluated_graph=graph,\n        hypothesis_portfolio=portfolio,\n    )\n''',
    '''    graph = _mapping(evaluated_graph, "evaluated_graph")\n\n    checkpoint_sha, source_target, expected_previous_report_sha = _authorization_checkpoint(checkpoint)\n    progression_sha, target, portfolio = _progression(\n        progress,\n        checkpoint_sha=checkpoint_sha,\n        source_target=source_target,\n        evaluated_graph=graph,\n    )\n''',
    1,
)
rediagnosis = rediagnosis.replace(
    '''    verified = validate_model_evidence_discrepancy_report(\n        current,\n        evaluated_graph=graph,\n        hypothesis_portfolio=portfolio,\n        previous_report=previous,\n    )\n''',
    '''    previous_target = _mapping(\n        previous.get("target"), "previous_discrepancy_report.target"\n    )\n    if previous_target != source_target:\n        raise RecursiveResearchRediagnosisError(\n            "previous discrepancy report target differs from checkpoint source target"\n        )\n    try:\n        verified = validate_physics_hardened_model_evidence_discrepancy_report(\n            current,\n            evaluated_graph=graph,\n            hypothesis_portfolio=portfolio,\n            previous_report=previous,\n        )\n    except ModelEvidenceDiscrepancyPhysicsPolicyError as exc:\n        raise RecursiveResearchRediagnosisError(\n            "current discrepancy report failed physics/provenance-hardened validation"\n        ) from exc\n''',
    1,
)
rediagnosis = rediagnosis.replace(
    '''    next_handoff = build_discrepancy_planning_handoff(\n        current,\n        evaluated_graph=graph,\n        hypothesis_portfolio=portfolio,\n        previous_discrepancy_report=previous,\n    )\n''',
    '''    try:\n        next_handoff = build_policy_hardened_discrepancy_planning_handoff(\n            current,\n            evaluated_graph=graph,\n            hypothesis_portfolio=portfolio,\n            previous_discrepancy_report=previous,\n        )\n    except (\n        DiscrepancyPlanningHandoffError,\n        ModelEvidenceDiscrepancyPhysicsPolicyError,\n    ) as exc:\n        raise RecursiveResearchRediagnosisError(\n            "current discrepancy report could not enter the policy-hardened planning handoff"\n        ) from exc\n''',
    1,
)
REDIAGNOSIS.write_text(rediagnosis, encoding="utf-8")


# ---------------------------------------------------------------------------
# Focused regression tests. Use a real authenticated transition bundle for the
# evidence progression and end-to-end integration; mock only the expensive
# discrepancy re-diagnosis payload construction while asserting hardened entry points.
# ---------------------------------------------------------------------------
TEST_EVIDENCE.write_text(r'''from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
    advance_recursive_cycle_after_verified_transition,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _plan(action_id: str = "planner:sensitivity") -> dict:
    selected = {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "action_kind": "analysis",
        "description": "Run bounded sensitivity analysis.",
        "rationale": "Discriminate the bounded target.",
        "required_evidence": [],
        "expected_outcome": "A bounded verified result.",
        "execution_mode": "plan_only",
        "origin": "verified_goal_frontier",
        "expected_information_score": 0.8,
        "hypothesis_discrimination_score": 0.8,
        "feasibility_score": 0.9,
        "cost_units": 1.0,
        "risk_penalty": 0.0,
        "utility_score": 0.576,
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "program_binding": {"canonical_sha256": "a" * 64},
        "critic_binding": None,
        "reasoning_proposal_binding": None,
        "planning_budget": {
            "budget_units": 8.0,
            "minimum_utility": 0.01,
            "score_semantics": "deterministic_nonprobabilistic_planning_heuristic",
        },
        "research_objectives": [],
        "evidence_gaps": [],
        "candidate_hypotheses": [],
        "ranked_actions": [selected],
        "selected_next_action": dict(selected),
        "stop_decision": {
            "stop": False,
            "reason": "informative_action_available",
            "next_mode": "request_existing_authorization_chain",
        },
        "objective_revision": None,
        "handoff": {
            "required_for_selected_action": True,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
        "autonomy_boundary": {
            "bounded_goal_derivation_performed": True,
            "methodological_rival_hypotheses_generated": False,
            "domain_mechanism_truth_invented": False,
            "empirical_evidence_created": False,
            "calibrated_probability_claimed": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    value["plan_sha256"] = _sha(value)
    return value


def _checkpoint(plan: dict) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:graph-v1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": {
            "graph_id": "graph-v1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The bounded target remains under discrimination.",
        },
        "ancestry": {
            "previous_checkpoint_sha256": None,
            "source_discrepancy_report_sha256": "b" * 64,
            "planning_handoff_sha256": "c" * 64,
            "fresh_plan_sha256": plan["plan_sha256"],
        },
        "fresh_planner_state": {
            "ranked_candidate_count": 1,
            "selected_candidate_id": "planner:sensitivity",
            "stop_decision": dict(plan["stop_decision"]),
        },
        "matched_objective": {"objective_id": "planning-objective:1"},
        "candidate_match": {
            "candidate_action_id": "planner:sensitivity",
            "candidate_action_class": "sensitivity_analysis",
        },
        "authorization_handoff": {
            "required": True,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
        },
        "epistemic_handoff": {
            "execution_result_verified": False,
            "epistemic_interpretation_performed": False,
            "epistemic_transition_verified": False,
            "hypothesis_portfolio_refreshed": False,
            "re_diagnosis_performed": False,
        },
        "bounded_stop": {"stopped": False, "reason": None, "reopen_condition": None},
        "autonomy_boundary": {
            "critic_proposal_executed_directly": False,
            "planner_candidate_injected": False,
            "action_type_synthesized": False,
            "registry_synthesized": False,
            "availability_promoted": False,
            "authorization_granted": False,
            "automatic_execution_authorized": False,
            "execution_performed": False,
            "network_access_performed": False,
            "physical_experiment_executed": False,
            "empirical_evidence_created": False,
            "epistemic_edge_created": False,
            "scientific_status_changed": False,
        },
    }
    value["checkpoint_sha256"] = _sha(value)
    return value


def _bundle(tmp_path: Path, *, source_action_id: str = "planner:sensitivity", falsified: bool = False) -> tuple[Path, str]:
    result = tmp_path / "result.json"
    result_sha = _write_json(result, {"sensitivity": 0.25})
    prior_result_sha = _write_json(tmp_path / "prior-result.json", {"prior": True})
    prior_verifier_sha = _write_json(tmp_path / "prior-verifier.json", {"verified": True})
    nodes: list[dict] = [
        {
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The bounded target remains under discrimination.",
            "metadata": {"claim_scope": "structural"},
        }
    ]
    edges: list[dict] = []
    if falsified:
        nodes.append(
            {
                "node_id": "prior-analysis",
                "node_type": "analysis",
                "statement": "Prior verified analysis falsified the target in scope.",
                "execution_status": "completed",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": "prior-result.json",
                        "sha256": prior_result_sha,
                    }
                ],
                "metadata": {"result_origin": "authorized_local_analysis"},
            }
        )
        edges.append(
            {
                "edge_id": "prior-falsification",
                "source_node_id": "prior-analysis",
                "target_node_id": "h-1",
                "relation": "falsifies",
                "assessment_level": "domain_verified",
                "rationale": "Prior exact verifier established falsification in scope.",
                "active": True,
                "verification_artifact": {
                    "role": "domain_verification_decision",
                    "path": "prior-verifier.json",
                    "sha256": prior_verifier_sha,
                },
            }
        )
    base_graph = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "recursive evidence regression",
        "nodes": nodes,
        "edges": edges,
    }
    base = tmp_path / "base.json"
    base_sha = _write_json(base, base_graph)
    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": source_action_id,
            "action_class": "sensitivity_analysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "A bounded sensitivity analysis completed.",
            "artifact_bindings": [
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The result is diagnostic for the structural target.",
        },
        "limitations": ["No positive scientific closeout is granted."],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_path, proposal)
    verification = {
        "schema_version": "1.1",
        "decision_id": "verification-1",
        "transition_id": "transition-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": "inference-1",
        "result_node_id": "result-1",
        "target_node_id": "h-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "bounded-domain-verifier-v1.1",
        "rationale": "Exact edge verification is structural only.",
        "limitations": ["No positive closeout is granted."],
        "domain_verified": True,
    }
    verification_path = tmp_path / "verification.json"
    _write_json(verification_path, verification)
    output = tmp_path / "bundle"
    apply_authenticated_epistemic_transition_files(
        base_graph_path=base,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    return output, result_sha


def _execution(checkpoint: dict, result_sha: str, *, action_id: str = "planner:sensitivity") -> dict:
    value = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": action_id,
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "d" * 64,
        "registry_sha256": "e" * 64,
        "result_sha256": result_sha,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    value["verification_record_sha256"] = _sha(value)
    return value


def test_real_authenticated_transition_refreshes_authoritative_portfolio(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=_execution(checkpoint, result_sha),
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert result["progression_status"] == "re_diagnosis_required"
    assert result["source_target"]["graph_id"] == "graph-v1"
    assert result["target"]["graph_id"] == "graph-v2"
    assert result["verified_epistemic_transition"][
        "current_transition_exact_provenance_authenticated"
    ] is True
    assert result["target_hypothesis_portfolio_state"]["portfolio_state"] == (
        "active_discrimination_required"
    )
    assert result["autonomy_boundary"]["scientific_status_changed_by_controller"] is False


def test_executed_action_must_equal_planner_selected_checkpoint_action(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    with pytest.raises(RecursiveResearchEvidenceError, match="action_id does not match"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=_execution(
                checkpoint, result_sha, action_id="different-action"
            ),
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
        )


def test_authenticated_transition_action_must_equal_verified_execution(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path, source_action_id="different-action")
    with pytest.raises(RecursiveResearchEvidenceError, match="proposal action_id differs"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=_execution(checkpoint, result_sha),
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
        )


def test_falsified_state_is_derived_and_stops_without_caller_portfolio(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path, falsified=True)
    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=_execution(checkpoint, result_sha),
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert result["progression_status"] == "bounded_stop_hypothesis_retired"
    assert result["target_epistemic_assessment"]["status"] == (
        "falsified_within_verified_scope"
    )
    assert result["target_hypothesis_portfolio_state"]["portfolio_state"] == (
        "retired_falsified_within_verified_scope"
    )


def test_repeated_authenticated_successor_graph_is_no_new_information(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    execution = _execution(checkpoint, result_sha)
    first = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    with pytest.raises(RecursiveResearchEvidenceError, match="no new evaluated graph"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
            previous_progression=first,
        )
''', encoding="utf-8")

# Add controller regression coverage for the already-landed stop/policy fixes plus exact
# successor-report ancestry binding.
controller_tests = TEST_CONTROLLER.read_text(encoding="utf-8")
if "def test_planner_stop_decision_blocks_authorization_even_with_candidate" not in controller_tests:
    controller_tests += r'''


def test_planner_stop_decision_blocks_authorization_even_with_candidate() -> None:
    handoff = _handoff()
    plan = _plan()
    plan.pop("plan_sha256")
    plan["stop_decision"] = {
        "stop": True,
        "reason": "budget_exhausted",
        "next_mode": "bounded_stop",
    }
    plan["selected_next_action"] = None
    plan["handoff"]["required_for_selected_action"] = False
    plan["plan_sha256"] = _canonical_sha(plan)
    with pytest.raises(RecursiveResearchCycleError, match="candidate match supplied"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=_match(handoff, plan),
        )


def test_future_autonomous_plan_policy_is_rejected() -> None:
    handoff = _handoff()
    plan = _plan()
    plan.pop("plan_sha256")
    plan["policy_version"] = "999.0"
    plan["plan_sha256"] = _canonical_sha(plan)
    with pytest.raises(RecursiveResearchCycleError, match="policy_version"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=None,
        )


def test_successor_handoff_requires_and_binds_previous_checkpoint_report() -> None:
    handoff = _handoff()
    plan = _plan()
    match = _match(handoff, plan)
    first = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    successor = copy.deepcopy(handoff)
    successor.pop("handoff_sha256")
    successor["source_discrepancy_report_sha256"] = "d" * 64
    successor["source_ancestry"]["previous_discrepancy_report_sha256"] = "a" * 64
    successor["target"]["graph_id"] = "g-2"
    successor["handoff_sha256"] = _canonical_sha(successor)
    next_plan = _plan(action_id="planner:sensitivity-2")
    next_match = _match(successor, next_plan)
    next_match["handoff_sha256"] = successor["handoff_sha256"]
    next_match["fresh_plan_sha256"] = next_plan["plan_sha256"]
    next_match["candidate_action_id"] = "planner:sensitivity-2"

    with pytest.raises(RecursiveResearchCycleError, match="requires previous"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=successor,
            fresh_plan=next_plan,
            candidate_match=next_match,
        )

    forged_first = copy.deepcopy(first)
    forged_first.pop("checkpoint_sha256")
    forged_first["ancestry"]["source_discrepancy_report_sha256"] = "f" * 64
    forged_first["checkpoint_sha256"] = _canonical_sha(forged_first)
    with pytest.raises(RecursiveResearchCycleError, match="does not descend"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=successor,
            fresh_plan=next_plan,
            candidate_match=next_match,
            previous_checkpoint=forged_first,
        )

    second = build_recursive_research_cycle_checkpoint(
        planning_handoff=successor,
        fresh_plan=next_plan,
        candidate_match=next_match,
        previous_checkpoint=first,
    )
    assert second["cycle_index"] == 2
    assert second["target"]["graph_id"] == "g-2"
    assert second["ancestry"]["previous_checkpoint_sha256"] == first["checkpoint_sha256"]
'''
TEST_CONTROLLER.write_text(controller_tests, encoding="utf-8")

TEST_REDIAGNOSIS.write_text(r'''from __future__ import annotations

import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.model_evidence_discrepancy_physics_policy import (
    ModelEvidenceDiscrepancyPhysicsPolicyError,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis import (
    RecursiveResearchRediagnosisError,
    complete_recursive_cycle_with_rediagnosis,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _state() -> tuple[dict, dict, dict, dict]:
    source_target = {
        "graph_id": "graph-v1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "Bounded target statement.",
    }
    current_target = dict(source_target)
    current_target["graph_id"] = "graph-v2"
    previous = {"schema_version": "1.0", "policy_version": "1.0", "target": source_target}
    previous["report_sha256"] = _sha(previous)
    checkpoint = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:graph-v1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": source_target,
        "ancestry": {"source_discrepancy_report_sha256": previous["report_sha256"]},
    }
    checkpoint["checkpoint_sha256"] = _sha(checkpoint)
    graph = {
        "graph_id": "graph-v2",
        "research_scope": "recursive re-diagnosis",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "Bounded target statement.",
            }
        ],
        "edges": [],
        "assessments": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "status": "inconclusive",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "confidence_score": None,
            }
        ],
    }
    portfolio = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "graph_id": "graph-v2",
        "research_scope": "recursive re-diagnosis",
        "evaluated_graph_binding": {"canonical_sha256": _sha(graph)},
        "plan_binding": {"plan_sha256": "1" * 64},
        "previous_portfolio_sha256": None,
        "hypothesis_count": 1,
        "state_counts": {"active_discrimination_required": 1},
        "portfolio_directive": "continue_bounded_discrimination",
        "hypotheses": [
            {
                "hypothesis_id": "h-1",
                "statement": "Bounded target statement.",
                "epistemic_status": "inconclusive",
                "portfolio_state": "active_discrimination_required",
                "research_directive": "continue_discriminating_research",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "confidence_score": None,
                "transition": "entered_from_current_verified_graph",
            }
        ],
        "autonomy_boundary": {
            "numeric_belief_probability_assigned": False,
            "final_positive_support_granted": False,
            "empirical_evidence_created": False,
            "domain_mechanism_invented": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "physical_experiment_executed": False,
        },
    }
    portfolio["portfolio_sha256"] = _sha(portfolio)
    progression = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": checkpoint["cycle_id"],
        "cycle_index": 1,
        "progression_status": "re_diagnosis_required",
        "source_target": source_target,
        "target": current_target,
        "ancestry": {
            "authorization_checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "evaluated_graph_canonical_sha256": _sha(graph),
            "hypothesis_portfolio_sha256": portfolio["portfolio_sha256"],
        },
        "hypothesis_portfolio": portfolio,
    }
    progression["progression_sha256"] = _sha(progression)
    return previous, checkpoint, graph, progression


def _current(previous: dict, target: dict) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(target),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous["report_sha256"],
            }
        },
    }


def _handoff(current_sha: str, target: dict, previous_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": current_sha,
        "target": dict(target),
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "source_ancestry": {"previous_discrepancy_report_sha256": previous_sha},
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    value["handoff_sha256"] = _sha(value)
    return value


def test_rediagnosis_uses_physics_hardened_validator_and_handoff(monkeypatch) -> None:
    previous, checkpoint, graph, progression = _state()
    target = progression["target"]
    current = _current(previous, target)
    current_sha = "e" * 64
    calls = {"physics": 0, "handoff": 0}

    def verify(*args, **kwargs):
        calls["physics"] += 1
        return {
            "report_sha256": current_sha,
            "iteration_index": 2,
            "diagnosis_types": ["parameter_or_property_uncertainty"],
        }

    def build(*args, **kwargs):
        calls["handoff"] += 1
        return _handoff(current_sha, target, previous["report_sha256"])

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        verify,
    )
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        build,
    )
    result = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current,
        previous_discrepancy_report=previous,
        evaluated_graph=graph,
    )
    assert calls == {"physics": 1, "handoff": 1}
    assert result["completion_status"] == "next_planning_handoff_ready"
    assert result["target"]["graph_id"] == "graph-v2"
    assert result["autonomy_boundary"]["authorization_granted"] is False


def test_physics_policy_rejection_blocks_recursive_reentry(monkeypatch) -> None:
    previous, checkpoint, graph, progression = _state()
    current = _current(previous, progression["target"])

    def reject(*args, **kwargs):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError("physics contract failed")

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        reject,
    )
    with pytest.raises(RecursiveResearchRediagnosisError, match="physics/provenance"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
        )
''', encoding="utf-8")

TEST_INTEGRATION.write_text(r'''from __future__ import annotations

import hashlib
import json
from pathlib import Path

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (
    build_recursive_research_cycle_checkpoint,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    advance_recursive_cycle_after_verified_transition,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis import (
    complete_recursive_cycle_with_rediagnosis,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_real_transition_bundle_closes_one_recursive_cycle(tmp_path: Path, monkeypatch) -> None:
    target = {
        "graph_id": "graph-v1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "A bounded hypothesis remains under discrimination.",
    }
    previous_report = {"schema_version": "1.0", "policy_version": "1.0", "target": target}
    previous_report["report_sha256"] = _sha(previous_report)
    handoff = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": previous_report["report_sha256"],
        "target": target,
        "research_objectives": [
            {
                "objective_id": "planning-objective:sensitivity",
                "source_proposal_id": "model-evidence:sensitivity",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "planner_candidate_required": True,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
        "source_ancestry": {
            "previous_discrepancy_report_sha256": None,
            "prior_diagnosis_types": [],
            "current_diagnosis_types": ["parameter_or_property_uncertainty"],
        },
        "planner_boundary": {
            "current_planner_frontier_modified": False,
            "current_selected_action_modified": False,
            "executable_candidate_created": False,
            "candidate_availability_verified": False,
            "candidate_registry_binding_created": False,
            "fresh_planner_candidate_matching_required": True,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    handoff["handoff_sha256"] = _sha(handoff)
    candidate = {
        "action_id": "planner:sensitivity",
        "action_class": "sensitivity_analysis",
        "action_kind": "analysis",
        "description": "Run bounded sensitivity analysis.",
        "rationale": "Discriminate the bounded target.",
        "required_evidence": [],
        "expected_outcome": "A bounded verified result.",
        "execution_mode": "plan_only",
        "origin": "verified_goal_frontier",
        "expected_information_score": 0.8,
        "hypothesis_discrimination_score": 0.8,
        "feasibility_score": 0.9,
        "cost_units": 1.0,
        "risk_penalty": 0.0,
        "utility_score": 0.576,
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }
    plan = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "program_binding": {"canonical_sha256": "a" * 64},
        "critic_binding": None,
        "reasoning_proposal_binding": None,
        "planning_budget": {
            "budget_units": 8.0,
            "minimum_utility": 0.01,
            "score_semantics": "deterministic_nonprobabilistic_planning_heuristic",
        },
        "research_objectives": [],
        "evidence_gaps": [],
        "candidate_hypotheses": [],
        "ranked_actions": [candidate],
        "selected_next_action": dict(candidate),
        "stop_decision": {
            "stop": False,
            "reason": "informative_action_available",
            "next_mode": "request_existing_authorization_chain",
        },
        "objective_revision": None,
        "handoff": {
            "required_for_selected_action": True,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
        "autonomy_boundary": {
            "bounded_goal_derivation_performed": True,
            "methodological_rival_hypotheses_generated": False,
            "domain_mechanism_truth_invented": False,
            "empirical_evidence_created": False,
            "calibrated_probability_claimed": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    plan["plan_sha256"] = _sha(plan)
    match = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": "planning-objective:sensitivity",
        "source_proposal_id": "model-evidence:sensitivity",
        "source_rank": 1,
        "candidate_action_id": "planner:sensitivity",
        "candidate_action_class": "sensitivity_analysis",
        "candidate_execution_mode": "plan_only",
        "match_rationale": "Fresh planner selected the same bounded action class.",
    }
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    result_path = tmp_path / "result.json"
    result_sha = _write_json(result_path, {"sensitivity": 0.25})
    base_path = tmp_path / "base.json"
    base_sha = _write_json(
        base_path,
        {
            "schema_version": "1.0",
            "graph_id": "graph-v1",
            "research_scope": "recursive integration",
            "nodes": [
                {
                    "node_id": "h-1",
                    "node_type": "hypothesis",
                    "statement": target["statement"],
                    "metadata": {"claim_scope": "structural"},
                }
            ],
            "edges": [],
        },
    )
    proposal_path = tmp_path / "proposal.json"
    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": "planner:sensitivity",
            "action_class": "sensitivity_analysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "A bounded sensitivity result completed.",
            "artifact_bindings": [
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The bounded result is diagnostic for the target.",
        },
        "limitations": ["No automatic scientific closeout."],
    }
    proposal_sha = _write_json(proposal_path, proposal)
    verification_path = tmp_path / "verification.json"
    _write_json(
        verification_path,
        {
            "schema_version": "1.1",
            "decision_id": "verification-1",
            "transition_id": "transition-1",
            "proposal_sha256": proposal_sha,
            "base_graph_sha256": base_sha,
            "inference_edge_id": "inference-1",
            "result_node_id": "result-1",
            "target_node_id": "h-1",
            "relation": "supports",
            "inference_scope": "structural",
            "verifier_id": "bounded-domain-verifier-v1.1",
            "rationale": "Exact edge is verified in structural scope only.",
            "limitations": ["No positive closeout."],
            "domain_verified": True,
        },
    )
    bundle = tmp_path / "bundle"
    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_path,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=bundle,
    )
    execution = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": "planner:sensitivity",
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "1" * 64,
        "registry_sha256": "2" * 64,
        "result_sha256": result_sha,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    execution["verification_record_sha256"] = _sha(execution)
    progression = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert progression["target"]["graph_id"] == "graph-v2"
    assert progression["progression_status"] == "re_diagnosis_required"

    current_target = progression["target"]
    current_report = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(current_target),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous_report["report_sha256"],
            }
        },
    }
    current_report_sha = "5" * 64
    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": current_report_sha,
            "iteration_index": 2,
            "diagnosis_types": ["empirical_model_discrepancy"],
        },
    )
    next_handoff = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": current_report_sha,
        "target": dict(current_target),
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "source_ancestry": {
            "previous_discrepancy_report_sha256": previous_report["report_sha256"]
        },
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    next_handoff["handoff_sha256"] = _sha(next_handoff)
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        lambda *args, **kwargs: next_handoff,
    )
    graph_sha = progression["ancestry"]["evaluated_graph_canonical_sha256"]
    # Re-evaluate through the same exact bundle by reusing the internally produced graph.
    # The authoritative portfolio embeds the exact evaluated graph binding; construct the
    # same evaluated representation from the transition bundle for the re-diagnosis step.
    from materials_data_analyzer.research_loop.epistemic_graph import evaluate_epistemic_graph

    raw_graph = json.loads((bundle / "epistemic_graph.json").read_text(encoding="utf-8"))
    evaluated_graph = evaluate_epistemic_graph(
        raw_graph,
        program_state={"workstreams": []},
        artifact_root=bundle,
    )
    assert _sha(evaluated_graph) == graph_sha
    completed = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current_report,
        previous_discrepancy_report=previous_report,
        evaluated_graph=evaluated_graph,
    )
    assert completed["completion_status"] == "next_planning_handoff_ready"
    assert completed["target"]["graph_id"] == "graph-v2"
    assert completed["ancestry"]["previous_discrepancy_report_sha256"] == (
        previous_report["report_sha256"]
    )
    assert completed["autonomy_boundary"]["authorization_granted"] is False
    assert completed["autonomy_boundary"]["execution_performed"] is False
    assert completed["autonomy_boundary"]["scientific_status_changed"] is False
''', encoding="utf-8")
