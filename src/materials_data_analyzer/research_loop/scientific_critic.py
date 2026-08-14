"""Deterministic scientific-critic proposals over a verified epistemic graph.

The critic is intentionally non-authoritative. It audits the *structure* of current
scientific support, contradiction, falsification, testing, and provenance, then emits
methodological alternatives and discriminating next-action proposals. It never creates
new scientific evidence, upgrades an epistemic relation, executes an action, estimates
probabilities, or claims a domain mechanism.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .epistemic_graph import evaluate_epistemic_graph
from .kernel import ResearchLoopError

SCIENTIFIC_CRITIC_SCHEMA_VERSION = "1.0"
SCIENTIFIC_CRITIC_POLICY_VERSION = "1.0"

_TARGET_TYPES = {"hypothesis", "claim", "conclusion"}
_DIRECTIONAL_RELATIONS = {"supports", "contradicts", "falsifies"}
_EXECUTABLE_TYPES = {"analysis", "simulation", "experiment"}
_EMPIRICAL_SCOPES = {"empirical", "mixed"}


class ScientificCriticError(ResearchLoopError):
    """Raised when a scientific-critic proposal cannot preserve its evidence boundary."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScientificCriticError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _read_graph_snapshot(path: Path) -> tuple[dict[str, Any], str, int]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScientificCriticError(f"could not read epistemic graph: {path}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScientificCriticError("epistemic graph must be UTF-8 JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ScientificCriticError(f"invalid epistemic graph JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ScientificCriticError("epistemic graph root must be an object")
    return value, hashlib.sha256(raw).hexdigest(), len(raw)


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScientificCriticError("program state is not canonical-JSON serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificCriticError(f"{field} must be a non-empty string")
    return value.strip()


def _target_ids(values: Sequence[object] | None, available: Sequence[str]) -> list[str]:
    if values is None:
        return list(available)
    if isinstance(values, (str, bytes)):
        raise ScientificCriticError("target_node_ids must be a sequence of node IDs")
    result: list[str] = []
    for index, value in enumerate(values):
        node_id = _nonempty_text(value, f"target_node_ids[{index}]")
        if node_id in result:
            raise ScientificCriticError(f"duplicate target node ID: {node_id}")
        result.append(node_id)
    if not result:
        raise ScientificCriticError("target_node_ids must not be empty")
    unknown = sorted(set(result) - set(available))
    if unknown:
        raise ScientificCriticError(
            "scientific critic targets must be assessed hypothesis/claim/conclusion nodes: "
            + ", ".join(unknown)
        )
    return result


def _require_reasoning_policy(program_state: Mapping[str, Any]) -> None:
    mission = program_state.get("mission")
    if not isinstance(mission, Mapping):
        raise ScientificCriticError("program_state.mission is missing or malformed")
    policy = mission.get("autonomy_policy")
    if not isinstance(policy, Mapping):
        raise ScientificCriticError("program_state mission autonomy_policy is missing")
    if policy.get("reasoning_proposals") != "schema_validated":
        raise ScientificCriticError(
            "mission does not permit schema-validated scientific reasoning proposals"
        )


def _source_identity(node: Mapping[str, Any]) -> str:
    binding = node.get("evidence_binding")
    if isinstance(binding, Mapping):
        workstream_id = binding.get("workstream_id")
        role = binding.get("role")
        sha256 = binding.get("sha256")
        if all(isinstance(item, str) and item for item in (workstream_id, role, sha256)):
            return f"program:{workstream_id}:{role}:{sha256}"
    artifacts = node.get("artifact_bindings")
    if isinstance(artifacts, list) and artifacts:
        digests = sorted(
            str(item.get("sha256"))
            for item in artifacts
            if isinstance(item, Mapping) and isinstance(item.get("sha256"), str)
        )
        if digests:
            return "artifact:" + ":".join(digests)
    return f"node:{node.get('node_id')}"


def _claim_scope(node: Mapping[str, Any]) -> str | None:
    metadata = node.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("claim_scope")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _finding(
    *,
    finding_id: str,
    code: str,
    severity: str,
    statement: str,
    rationale: str,
    edge_ids: Sequence[str] = (),
    node_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "code": code,
        "severity": severity,
        "statement": statement,
        "rationale": rationale,
        "edge_ids": list(edge_ids),
        "node_ids": list(node_ids),
        "scientific_status_changed": False,
    }


def _alternative(
    target_id: str,
    suffix: str,
    statement: str,
    falsification_criteria: Sequence[str],
    discriminating_evidence: Sequence[str],
) -> dict[str, Any]:
    return {
        "alternative_id": f"critic:{target_id}:{suffix}",
        "alternative_type": "methodological_not_domain_mechanism",
        "statement": statement,
        "falsification_criteria": list(falsification_criteria),
        "discriminating_evidence": list(discriminating_evidence),
        "proposal_status": "proposed_not_evidence_upgraded",
        "scientific_mechanism_claim": False,
    }


def _action(
    target_id: str,
    suffix: str,
    *,
    action_class: str,
    description: str,
    rationale: str,
    execution_mode: str,
    priority: str,
    expected_discrimination: str,
) -> dict[str, Any]:
    return {
        "action_id": f"critic:{target_id}:{suffix}",
        "action_class": action_class,
        "description": description,
        "rationale": rationale,
        "execution_mode": execution_mode,
        "information_gain_priority": priority,
        "information_gain_is_calibrated_probability": False,
        "expected_discrimination": expected_discrimination,
        "automatic_execution_authorized": False,
        "availability_asserted": False,
    }


def _criticize_target(
    target_id: str,
    *,
    assessment: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    target = nodes_by_id[target_id]
    incoming = [
        edge
        for edge in edges
        if edge.get("active") is True and edge.get("target_node_id") == target_id
    ]

    # Reuse the evaluator's exact usable-source decision rather than reconstructing
    # domain-verified authority from the raw edge label. A planned/failed executable
    # result or unsupported evidence node may carry a syntactically domain-verified
    # edge, but evaluate_epistemic_graph intentionally excludes it from verified status.
    verified_edge_ids = {
        str(edge_id)
        for field in (
            "verified_support_edges",
            "verified_contradiction_edges",
            "verified_falsification_edges",
        )
        for edge_id in assessment.get(field, [])
        if isinstance(edge_id, str)
    }
    verified_directional = [
        edge
        for edge in incoming
        if isinstance(edge.get("edge_id"), str)
        and str(edge["edge_id"]) in verified_edge_ids
    ]
    diagnostic_directional = [
        edge
        for edge in incoming
        if edge.get("relation") in _DIRECTIONAL_RELATIONS
        and edge.get("assessment_level") != "domain_verified"
    ]

    # A tests edge is only a recorded scientific test after its executable source
    # actually completed. Planned/failed executions must not suppress the absence of a
    # discriminating test or masquerade as completed-but-uninterpreted evidence.
    tests = [
        edge
        for edge in incoming
        if edge.get("relation") == "tests"
        and isinstance(edge.get("source_node_id"), str)
        and str(edge["source_node_id"]) in nodes_by_id
        and nodes_by_id[str(edge["source_node_id"])].get("node_type") in _EXECUTABLE_TYPES
        and nodes_by_id[str(edge["source_node_id"])].get("execution_status") == "completed"
    ]

    supports = [edge for edge in verified_directional if edge.get("relation") == "supports"]
    contradicts = [
        edge for edge in verified_directional if edge.get("relation") == "contradicts"
    ]
    falsifies = [edge for edge in verified_directional if edge.get("relation") == "falsifies"]

    support_sources = [
        nodes_by_id[str(edge["source_node_id"])]
        for edge in supports
        if isinstance(edge.get("source_node_id"), str)
        and str(edge["source_node_id"]) in nodes_by_id
    ]
    support_identities = {_source_identity(node) for node in support_sources}
    support_types = {str(node.get("node_type")) for node in support_sources}

    test_source_ids = {
        str(edge["source_node_id"])
        for edge in tests
        if isinstance(edge.get("source_node_id"), str)
    }
    directional_source_ids = {
        str(edge["source_node_id"])
        for edge in incoming
        if edge.get("relation") in _DIRECTIONAL_RELATIONS
        and isinstance(edge.get("source_node_id"), str)
    }
    uninterpreted_tests = sorted(test_source_ids - directional_source_ids)

    findings: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    if falsifies:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:verified-falsification",
                code="VERIFIED_FALSIFICATION_PRESENT",
                severity="high",
                statement="The target is falsified within at least one domain-verified scope.",
                rationale=(
                    "A domain-verified falsification relation exists. Additional positive-result "
                    "seeking must not silently erase that scope-limited negative result."
                ),
                edge_ids=[str(edge["edge_id"]) for edge in falsifies],
            )
        )
        actions.append(
            _action(
                target_id,
                "reframe-falsified-scope",
                action_class="manual_review",
                description="Reframe or narrow the falsified target before further positive-claim work.",
                rationale="The verified falsification must be explicitly preserved in the next question.",
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Separates scope revision from unsupported rescue of the original claim.",
            )
        )

    if contradicts and not supports and not falsifies:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:verified-contradiction",
                code="VERIFIED_CONTRADICTION_PRESENT",
                severity="high",
                statement="The target is contradicted within at least one domain-verified scope.",
                rationale=(
                    "Usable domain-verified negative evidence exists without verified positive support. "
                    "The target must not fall through to a positive closeout-style review merely because "
                    "the negative relation is contradiction rather than falsification."
                ),
                edge_ids=[str(edge["edge_id"]) for edge in contradicts],
            )
        )
        actions.append(
            _action(
                target_id,
                "reassess-contradicted-scope",
                action_class="manual_review",
                description="Reassess, narrow, or reframe the contradicted target before positive-claim continuation.",
                rationale="The standalone verified contradiction is a scientific objection that must remain explicit.",
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Separates justified scope revision from unsupported continuation of the contradicted claim.",
            )
        )

    if supports and (contradicts or falsifies):
        conflict_edges = supports + contradicts + falsifies
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:verified-conflict",
                code="VERIFIED_EVIDENCE_CONFLICT",
                severity="high",
                statement="Domain-verified evidence is directionally conflicting for the target.",
                rationale=(
                    "Positive and negative verified relations coexist; aggregation into one scalar "
                    "confidence would hide scope, protocol, or population heterogeneity."
                ),
                edge_ids=[str(edge["edge_id"]) for edge in conflict_edges],
            )
        )
        alternatives.append(
            _alternative(
                target_id,
                "scope-heterogeneity",
                "The apparent disagreement may be scope-, protocol-, sample-, or condition-dependent rather than a single universal effect.",
                [
                    "A prespecified stratification eliminates the directional disagreement without selective exclusions.",
                    "Independent replication under matched conditions yields consistent direction across strata.",
                ],
                [
                    "Protocol- and condition-stratified reanalysis",
                    "Matched-condition independent replication",
                ],
            )
        )
        actions.append(
            _action(
                target_id,
                "resolve-verified-conflict",
                action_class="existing_data_reanalysis",
                description="Plan a stratification of the conflicting verified evidence by declared scope and protocol variables.",
                rationale=(
                    "A conflict should be localized before any stronger claim is attempted, but the critic "
                    "has not established that suitable data or a registered local action is available."
                ),
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Tests whether the conflict is reproducibly associated with declared strata if the required data and capability are later established.",
            )
        )

    if not contradicts and not falsifies:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:counterevidence-gap",
                code="NO_DOMAIN_VERIFIED_COUNTEREVIDENCE",
                severity="medium",
                statement="No domain-verified contradiction or falsification is currently represented for the target.",
                rationale=(
                    "Absence in the current graph is not evidence of absence. A serious positive claim "
                    "requires an explicit search for counterexamples or discriminating negative evidence."
                ),
            )
        )
        alternatives.append(
            _alternative(
                target_id,
                "artifact-or-selection",
                "The current apparent support may be explainable by measurement, preprocessing, selection, or analysis artifacts not yet discriminated in the graph.",
                [
                    "Prespecified robustness checks leave the direction unchanged across defensible preprocessing choices.",
                    "Independent data collected or curated without the original selection path reproduce the effect.",
                ],
                [
                    "Preprocessing and inclusion-rule sensitivity",
                    "Independent counterexample-oriented evidence",
                ],
            )
        )
        actions.extend(
            [
                _action(
                    target_id,
                    "robustness-sensitivity",
                    action_class="sensitivity_analysis",
                    description="Plan prespecified sensitivity checks over defensible preprocessing and inclusion choices.",
                    rationale=(
                        "This directly tests a generic artifact/selection alternative without asserting a domain "
                        "mechanism, but the critic has not established suitable local data or action capability."
                    ),
                    execution_mode="plan_only",
                    priority="high" if supports else "medium",
                    expected_discrimination="Determines whether the observed direction is robust to defensible analytic choices if the required evidence and capability are later established.",
                ),
                _action(
                    target_id,
                    "seek-counterexample-evidence",
                    action_class="external_evidence_search",
                    description="Seek independent evidence specifically capable of contradicting or falsifying the target.",
                    rationale="Counterexample-oriented search reduces confirmation bias in the current evidence graph.",
                    execution_mode="explicit_authorization_required",
                    priority="high" if supports else "medium",
                    expected_discrimination="Adds independent negative or null evidence, or documents a bounded search failure without treating that failure as support.",
                ),
            ]
        )

    if supports and len(support_identities) <= 1:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:support-concentration",
                code="SUPPORT_SOURCE_CONCENTRATION",
                severity="medium",
                statement="Verified positive support is concentrated in one direct provenance identity.",
                rationale=(
                    "Multiple edges from one source lineage do not establish independent replication. "
                    "The critic does not infer statistical independence from edge count."
                ),
                edge_ids=[str(edge["edge_id"]) for edge in supports],
                node_ids=[str(node["node_id"]) for node in support_sources],
            )
        )
        alternatives.append(
            _alternative(
                target_id,
                "shared-provenance",
                "The apparent multiplicity of support may reflect a shared provenance lineage rather than independent replication.",
                [
                    "A provenance-disjoint replication produces compatible evidence.",
                ],
                [
                    "Parent/source-disjoint replication",
                    "Independent instrument, dataset, or acquisition lineage where scientifically appropriate",
                ],
            )
        )
        actions.append(
            _action(
                target_id,
                "independent-replication",
                action_class="replication",
                description="Plan a provenance-disjoint replication of the positive result.",
                rationale=(
                    "Independent replication is more discriminating than another derivative analysis of the same "
                    "source, but no disjoint dataset or execution capability is inferred by the critic."
                ),
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Distinguishes reproducible support from shared-source dependence once genuinely disjoint evidence becomes available.",
            )
        )

    scope = _claim_scope(target)
    if supports and scope in _EMPIRICAL_SCOPES and support_types and support_types <= {"simulation"}:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:simulation-only-empirical-support",
                code="SIMULATION_ONLY_SUPPORT_FOR_EMPIRICAL_SCOPE",
                severity="high",
                statement="An empirical or mixed-scope target is positively supported only by simulation sources in the current verified graph.",
                rationale=(
                    "Computational or structural adequacy cannot by itself establish measurement truth, "
                    "material identity, calibration truth, or empirical generalization."
                ),
                edge_ids=[str(edge["edge_id"]) for edge in supports],
            )
        )
        actions.append(
            _action(
                target_id,
                "design-empirical-validation",
                action_class="physical_experiment_design",
                description="Design an independent empirical validation capable of testing the target without treating the simulation as ground truth.",
                rationale="The claim scope requires empirical evidence that is absent from the current positive-support lineage.",
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Separates computational structural support from empirical/material truth.",
            )
        )

    if diagnostic_directional:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:diagnostic-directional-relations",
                code="DIRECTIONAL_RELATIONS_NOT_DOMAIN_VERIFIED",
                severity="medium",
                statement="Directional proposal/diagnostic relations exist that do not have domain-verified authority.",
                rationale="They may motivate tests but must not be counted as verified scientific support or refutation.",
                edge_ids=[str(edge["edge_id"]) for edge in diagnostic_directional],
            )
        )

    if uninterpreted_tests:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:uninterpreted-tests",
                code="COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION",
                severity="medium",
                statement="One or more completed recorded tests have no active directional inference relation to the target.",
                rationale=(
                    "Execution success is not scientific interpretation. These results require a separate, "
                    "evidence-bound interpretation proposal and domain verification where applicable."
                ),
                node_ids=uninterpreted_tests,
            )
        )
        actions.append(
            _action(
                target_id,
                "interpret-recorded-tests",
                action_class="manual_review",
                description="Review the completed test artifacts and prepare a separate evidence-bound directional interpretation proposal if justified.",
                rationale="The graph intentionally separates executed tests from scientific support/contradiction/falsification.",
                execution_mode="plan_only",
                priority="high",
                expected_discrimination="Determines whether the completed tests justify any proposed directional relation without automatic status promotion.",
            )
        )

    if not tests and not verified_directional:
        findings.append(
            _finding(
                finding_id=f"critic:{target_id}:no-discriminating-test",
                code="NO_RECORDED_DISCRIMINATING_TEST",
                severity="high",
                statement="The target has neither a completed recorded test edge nor a usable domain-verified directional relation.",
                rationale="The target is presently a question/hypothesis state rather than an evidence-tested scientific claim.",
            )
        )

    dedup_actions: list[dict[str, Any]] = []
    seen_action_ids: set[str] = set()
    for action in actions:
        action_id = str(action["action_id"])
        if action_id not in seen_action_ids:
            seen_action_ids.add(action_id)
            dedup_actions.append(action)

    status = str(assessment.get("status"))
    if status == "falsified_within_verified_scope":
        recommendation = "stop_and_reframe_current_target"
        stop_rationale = (
            "The target is falsified within a verified scope; the critic recommends preserving "
            "that negative result and reframing before additional positive-claim work."
        )
    elif status == "contradicted_within_verified_scope":
        recommendation = "reassess_or_reframe_contradicted_target"
        stop_rationale = (
            "The target is contradicted within a verified scope; the negative result must remain an "
            "explicit scientific objection before positive-claim continuation."
        )
    elif findings:
        recommendation = "continue_discriminating_research"
        stop_rationale = (
            "Material methodological uncertainties or unresolved counterevidence obligations remain."
        )
    else:
        recommendation = "domain_closeout_review_required"
        stop_rationale = (
            "The deterministic critic found no structural objection, but positive scientific closeout "
            "still requires domain review and cannot be granted by this critic."
        )

    return {
        "target_node_id": target_id,
        "target_node_type": target.get("node_type"),
        "target_statement": target.get("statement"),
        "claim_scope": scope,
        "epistemic_assessment": dict(assessment),
        "critic_findings": findings,
        "methodological_alternatives": alternatives,
        "discriminating_actions": dedup_actions,
        "stop_recommendation": {
            "recommendation": recommendation,
            "rationale": stop_rationale,
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        },
    }


def _build_structural_scientific_critic_report(
    graph_path: str | Path,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    target_node_ids: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Audit graph structure before applying the public conservative policy overlay."""
    _require_reasoning_policy(program_state)
    graph_file = Path(graph_path).expanduser().resolve(strict=True)
    if not graph_file.is_file():
        raise ScientificCriticError(f"epistemic graph must be a regular file: {graph_file}")
    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    if not artifacts.is_dir():
        raise ScientificCriticError(f"artifact_root must be a directory: {artifacts}")

    graph, graph_sha256, graph_bytes = _read_graph_snapshot(graph_file)
    evaluation = evaluate_epistemic_graph(
        graph,
        program_state=program_state,
        artifact_root=artifacts,
    )
    raw_nodes = evaluation.get("nodes")
    raw_edges = evaluation.get("edges")
    raw_assessments = evaluation.get("assessments")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ScientificCriticError("epistemic evaluation omitted normalized nodes/edges")
    if not isinstance(raw_assessments, list):
        raise ScientificCriticError("epistemic evaluation assessments must be a list")

    nodes_by_id = {
        str(node["node_id"]): node
        for node in raw_nodes
        if isinstance(node, Mapping)
        and isinstance(node.get("node_id"), str)
        and node.get("node_type") in _TARGET_TYPES.union(_EXECUTABLE_TYPES).union({"evidence"})
    }
    assessments_by_id = {
        str(item["node_id"]): item
        for item in raw_assessments
        if isinstance(item, Mapping) and isinstance(item.get("node_id"), str)
    }
    available_targets = sorted(assessments_by_id)
    targets = _target_ids(target_node_ids, available_targets)
    edges = [edge for edge in raw_edges if isinstance(edge, Mapping)]

    target_reports = [
        _criticize_target(
            target_id,
            assessment=assessments_by_id[target_id],
            nodes_by_id=nodes_by_id,
            edges=edges,
        )
        for target_id in targets
    ]
    target_reports.sort(key=lambda item: str(item["target_node_id"]))

    mission_binding = program_state.get("mission_binding")
    context_binding = program_state.get("runtime_context_binding")
    return {
        "schema_version": SCIENTIFIC_CRITIC_SCHEMA_VERSION,
        "critic_policy_version": SCIENTIFIC_CRITIC_POLICY_VERSION,
        "critic_id": f"scientific-critic:{evaluation.get('graph_id')}:{graph_sha256[:16]}",
        "graph_binding": {
            "path": str(graph_file),
            "sha256": graph_sha256,
            "bytes": graph_bytes,
        },
        "program_state_sha256": _canonical_sha256(program_state),
        "mission_binding": dict(mission_binding) if isinstance(mission_binding, Mapping) else None,
        "runtime_context_binding": (
            dict(context_binding) if isinstance(context_binding, Mapping) else None
        ),
        "target_reports": target_reports,
        "summary": {
            "targets_reviewed": len(target_reports),
            "findings": sum(len(item["critic_findings"]) for item in target_reports),
            "methodological_alternatives": sum(
                len(item["methodological_alternatives"]) for item in target_reports
            ),
            "discriminating_actions": sum(
                len(item["discriminating_actions"]) for item in target_reports
            ),
        },
        "autonomy_boundary": {
            "deterministic_structural_critic_only": True,
            "domain_mechanism_invented": False,
            "scientific_evidence_created": False,
            "scientific_status_changed": False,
            "probability_or_confidence_estimated": False,
            "automatic_action_execution_authorized": False,
            "network_access_authorized": False,
            "physical_experiment_execution_authorized": False,
            "positive_scientific_closeout_granted": False,
        },
    }


def build_scientific_critic_report(
    graph_path: str | Path,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    target_node_ids: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Build the public policy-hardened scientific-critic report.

    The import is intentionally lazy so the conservative overlay can use the private
    structural builder without a module-import cycle. Direct imports from this module
    therefore preserve the same policy boundary as the package and installed CLI.
    """
    from .scientific_critic_policy import build_policy_hardened_scientific_critic_report

    return build_policy_hardened_scientific_critic_report(
        graph_path,
        program_state=program_state,
        artifact_root=artifact_root,
        target_node_ids=target_node_ids,
    )


__all__ = [
    "SCIENTIFIC_CRITIC_POLICY_VERSION",
    "SCIENTIFIC_CRITIC_SCHEMA_VERSION",
    "ScientificCriticError",
    "build_scientific_critic_report",
]
