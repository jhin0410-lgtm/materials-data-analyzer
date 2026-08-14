"""Conservative policy overlay for the deterministic scientific critic.

The overlay refuses to infer scientific authority from artifact multiplicity, source-node
labels, incomplete verifier provenance, workstream proximity, or action proposal shape.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .scientific_critic import (
    SCIENTIFIC_CRITIC_POLICY_VERSION,
    ScientificCriticError,
    _build_structural_scientific_critic_report as _build_base_report,
)

SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION = "1.5"

_EMPIRICAL_TARGET_SCOPES = {"empirical", "mixed"}
_INFERENCE_SCOPES = {"structural", "computational", "empirical_derived", "empirical_direct"}
_EMPIRICAL_INFERENCE_SCOPES = {"empirical_derived", "empirical_direct"}
_DIRECTIONAL_RELATIONS = {"supports", "contradicts", "falsifies"}
_VERIFICATION_DECISION_KEYS = {
    "schema_version",
    "decision_id",
    "transition_id",
    "proposal_sha256",
    "base_graph_sha256",
    "result_node_id",
    "target_node_id",
    "relation",
    "inference_scope",
    "verifier_id",
    "rationale",
    "limitations",
    "domain_verified",
}


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificCriticError(f"{field} must be non-empty text")
    return value.strip()


def _program_evidence_gaps(program_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    goals = program_state.get("generated_goals")
    if not isinstance(goals, list):
        raise ScientificCriticError("program_state.generated_goals must be a list")

    gaps: list[dict[str, Any]] = []
    for raw in goals:
        if not isinstance(raw, Mapping):
            continue
        workstream_id = raw.get("workstream_id")
        goal_id = raw.get("goal_id")
        status = raw.get("status")
        gap_status = raw.get("evidence_gap_status")
        requirements = raw.get("evidence_requirements")
        if not isinstance(workstream_id, str) or not workstream_id.strip():
            continue
        if not isinstance(goal_id, str) or not goal_id.strip():
            continue
        if not isinstance(requirements, list):
            raise ScientificCriticError(
                f"generated goal evidence_requirements are malformed: {goal_id}"
            )
        normalized: list[str] = []
        for index, requirement in enumerate(requirements):
            text = _nonempty_text(
                requirement, f"generated goal evidence_requirements[{index}]"
            )
            if text not in normalized:
                normalized.append(text)
        if not normalized or status == "scope_exhausted":
            continue
        gaps.append(
            {
                "goal_id": goal_id.strip(),
                "workstream_id": workstream_id.strip(),
                "goal_status": status,
                "evidence_gap_status": gap_status,
                "evidence_requirements": normalized,
                "target_attribution": "not_inferred",
                "automatic_acquisition_authorized": False,
            }
        )
    gaps.sort(key=lambda item: (str(item["workstream_id"]), str(item["goal_id"])))
    return gaps


def _replace_independence_assumption(report: dict[str, Any]) -> None:
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise ScientificCriticError("critic report target_reports are malformed")

    for raw in target_reports:
        if not isinstance(raw, dict):
            raise ScientificCriticError("critic target report is malformed")
        assessment = raw.get("epistemic_assessment")
        if not isinstance(assessment, Mapping):
            raise ScientificCriticError("critic target assessment is malformed")
        support_edges = assessment.get("verified_support_edges")
        if not isinstance(support_edges, list):
            raise ScientificCriticError("verified_support_edges must be a list")
        if not support_edges:
            continue

        findings = raw.get("critic_findings")
        alternatives = raw.get("methodological_alternatives")
        actions = raw.get("discriminating_actions")
        if (
            not isinstance(findings, list)
            or not isinstance(alternatives, list)
            or not isinstance(actions, list)
        ):
            raise ScientificCriticError("critic target proposal collections are malformed")

        findings[:] = [
            item
            for item in findings
            if not (
                isinstance(item, Mapping)
                and item.get("code") == "SUPPORT_SOURCE_CONCENTRATION"
            )
        ]
        alternatives[:] = [
            item
            for item in alternatives
            if not (
                isinstance(item, Mapping)
                and str(item.get("alternative_id", "")).endswith(":shared-provenance")
            )
        ]
        actions[:] = [
            item
            for item in actions
            if not (
                isinstance(item, Mapping)
                and str(item.get("action_id", "")).endswith(":independent-replication")
            )
        ]

        target_id = str(raw.get("target_node_id"))
        findings.append(
            {
                "finding_id": f"critic:{target_id}:support-independence-unproven",
                "code": "SUPPORT_INDEPENDENCE_NOT_ESTABLISHED",
                "severity": "medium",
                "statement": (
                    "The current graph does not contain an explicit contract proving that the "
                    "positive-support lineages are statistically or experimentally independent."
                ),
                "rationale": (
                    "Different node IDs, files, checksums, instruments, or derivative analyses do "
                    "not by themselves prove parent-, sample-, acquisition-, or experimental "
                    "independence. Independence must be established by a separate provenance "
                    "contract before replication language is used as scientific support."
                ),
                "edge_ids": [str(item) for item in support_edges],
                "node_ids": [],
                "scientific_status_changed": False,
            }
        )
        alternatives.append(
            {
                "alternative_id": f"critic:{target_id}:shared-or-dependent-lineage",
                "alternative_type": "methodological_not_domain_mechanism",
                "statement": (
                    "The positive-support observations may share parent samples, source data, "
                    "acquisition conditions, preprocessing lineage, or another dependence that is "
                    "not represented by the current graph contract."
                ),
                "falsification_criteria": [
                    "A separately verified provenance contract establishes the required independence dimensions.",
                    "A provenance-disjoint replication produces compatible evidence under a prespecified protocol.",
                ],
                "discriminating_evidence": [
                    "Explicit parent/sample/acquisition lineage mapping",
                    "Prespecified provenance-disjoint replication",
                ],
                "proposal_status": "proposed_not_evidence_upgraded",
                "scientific_mechanism_claim": False,
            }
        )
        actions.append(
            {
                "action_id": f"critic:{target_id}:establish-support-independence",
                "action_class": "replication",
                "description": (
                    "Establish an explicit provenance-disjointness contract and, when suitable "
                    "data or an external experiment actually exists, test replication under that "
                    "contract."
                ),
                "rationale": (
                    "The critic cannot infer independence or local replication availability from "
                    "distinct artifacts alone."
                ),
                "execution_mode": "explicit_authorization_required",
                "information_gain_priority": "high",
                "information_gain_is_calibrated_probability": False,
                "expected_discrimination": (
                    "Separates genuinely independent replication from repeated analysis of "
                    "shared provenance."
                ),
                "automatic_execution_authorized": False,
                "availability_asserted": False,
            }
        )


def _mark_action_availability_unproven(report: dict[str, Any]) -> None:
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise ScientificCriticError("critic report target_reports are malformed")
    for raw in target_reports:
        if not isinstance(raw, Mapping):
            raise ScientificCriticError("critic target report is malformed")
        actions = raw.get("discriminating_actions")
        if not isinstance(actions, list):
            raise ScientificCriticError("critic target discriminating_actions are malformed")
        for action in actions:
            if not isinstance(action, dict):
                raise ScientificCriticError("critic discriminating action is malformed")
            action["availability_asserted"] = False


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScientificCriticError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _read_json_snapshot(path: Path, *, field: str) -> tuple[dict[str, Any], bytes, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScientificCriticError(f"could not read {field}: {path}") from exc
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificCriticError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScientificCriticError(f"{field} root must be an object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _load_bound_graph(report: Mapping[str, Any]) -> dict[str, Any]:
    binding = report.get("graph_binding")
    if not isinstance(binding, Mapping):
        raise ScientificCriticError("critic report graph_binding is malformed")
    path_value = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ScientificCriticError("critic report graph_binding.path is malformed")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        raise ScientificCriticError("critic report graph_binding.sha256 is malformed")
    try:
        path = Path(path_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ScientificCriticError("bound epistemic graph is no longer readable") from exc
    value, _, actual_sha = _read_json_snapshot(path, field="bound epistemic graph")
    if actual_sha != expected_sha:
        raise ScientificCriticError(
            "epistemic graph changed after the base critic bound its exact bytes"
        )
    return value


def _graph_nodes_by_id(graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ScientificCriticError("bound epistemic graph nodes must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("node_id"), str):
            continue
        node_id = str(raw["node_id"])
        if node_id in result:
            raise ScientificCriticError(f"duplicate epistemic node ID: {node_id}")
        result[node_id] = raw
    return result


def _transition_lineage_by_id(graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    metadata = graph.get("metadata")
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ScientificCriticError("bound epistemic graph metadata must be an object")
    lineage = metadata.get("transition_lineage")
    if lineage is None:
        return {}
    if not isinstance(lineage, list):
        raise ScientificCriticError("bound graph metadata.transition_lineage must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(lineage):
        if not isinstance(raw, Mapping):
            raise ScientificCriticError(
                f"bound graph transition_lineage[{index}] must be an object"
            )
        transition_id = raw.get("transition_id")
        if not isinstance(transition_id, str) or not transition_id.strip():
            raise ScientificCriticError(
                f"bound graph transition_lineage[{index}].transition_id is malformed"
            )
        if transition_id in result:
            raise ScientificCriticError(f"duplicate transition lineage ID: {transition_id}")
        result[transition_id] = raw
    return result


def _validate_verification_decision_contract(decision: Mapping[str, Any]) -> str:
    keys = set(decision)
    missing = sorted(_VERIFICATION_DECISION_KEYS - keys)
    unknown = sorted(keys - _VERIFICATION_DECISION_KEYS)
    if missing:
        raise ScientificCriticError(
            "domain verification decision is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise ScientificCriticError(
            "domain verification decision has unknown keys: " + ", ".join(unknown)
        )
    if decision.get("schema_version") != "1.0":
        raise ScientificCriticError("bound domain verification decision is not schema v1.0")
    if decision.get("domain_verified") is not True:
        raise ScientificCriticError("domain verification decision must set domain_verified=true")

    for field in (
        "decision_id",
        "transition_id",
        "proposal_sha256",
        "base_graph_sha256",
        "result_node_id",
        "target_node_id",
        "verifier_id",
        "rationale",
    ):
        _nonempty_text(decision.get(field), f"domain verification decision {field}")

    relation = _nonempty_text(
        decision.get("relation"), "domain verification decision relation"
    )
    if relation not in _DIRECTIONAL_RELATIONS:
        raise ScientificCriticError("domain verification decision relation is unsupported")
    scope = _nonempty_text(
        decision.get("inference_scope"), "domain verification decision inference_scope"
    )
    if scope not in _INFERENCE_SCOPES:
        raise ScientificCriticError("domain verification decision inference_scope is unsupported")

    limitations = decision.get("limitations")
    if not isinstance(limitations, list):
        raise ScientificCriticError("domain verification decision limitations must be a list")
    seen: set[str] = set()
    for index, value in enumerate(limitations):
        text = _nonempty_text(
            value, f"domain verification decision limitations[{index}]"
        )
        if text in seen:
            raise ScientificCriticError(
                "domain verification decision limitations must not contain duplicates"
            )
        seen.add(text)
    return scope


def _validate_empirical_scope_source(
    *, scope: str, source_node: Mapping[str, Any]
) -> bool:
    """Return whether the graph contract can establish the requested empirical scope.

    `empirical_derived` cannot currently be established from the graph because its
    `input_evidence_bindings` identify workstream/role/checksum only; they do not carry
    a provenance-bound empirical-vs-computational origin classification. The critic must
    therefore keep that scope unestablished until a first-class evidence-origin contract
    exists. `empirical_direct` can be established from an external physical experiment.
    """
    if scope not in _EMPIRICAL_INFERENCE_SCOPES:
        return True

    node_type = source_node.get("node_type")
    metadata = source_node.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ScientificCriticError(
            "empirical verifier scope requires transition metadata on its source node"
        )
    result_origin = metadata.get("result_origin")
    input_evidence = metadata.get("input_evidence_bindings")

    if scope == "empirical_direct":
        if node_type != "experiment" or result_origin != "external_physical_experiment":
            raise ScientificCriticError(
                "empirical_direct verifier scope is incompatible with its source-node provenance"
            )
        return True

    if not isinstance(input_evidence, list) or not input_evidence:
        raise ScientificCriticError(
            "empirical_derived verifier scope requires bound input evidence on its source node"
        )
    if node_type == "simulation":
        raise ScientificCriticError("simulation source cannot carry empirical_derived verifier scope")
    if node_type == "experiment" and result_origin != "data_experiment":
        raise ScientificCriticError(
            "empirical_derived experiment scope requires data_experiment provenance"
        )
    if node_type == "analysis" and result_origin not in {
        "authorized_local_analysis",
        "external_analysis",
    }:
        raise ScientificCriticError(
            "empirical_derived analysis scope has incompatible result_origin provenance"
        )
    if node_type not in {"analysis", "experiment"}:
        raise ScientificCriticError(
            "empirical_derived verifier scope requires analysis or data-experiment provenance"
        )

    # The current binding object has no empirical-origin classification, so presence of
    # input bindings alone cannot prove that this is empirical-derived evidence.
    return False


def _bound_domain_verification_scope(
    edge: Mapping[str, Any],
    *,
    artifact_root: Path,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    lineage_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    binding = edge.get("verification_artifact")
    if not isinstance(binding, Mapping):
        return None
    if binding.get("role") != "domain_verification_decision":
        return None
    path_value = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ScientificCriticError("domain verification decision path is malformed")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        raise ScientificCriticError("domain verification decision checksum is malformed")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise ScientificCriticError("domain verification decision is no longer readable") from exc
    decision, _, actual_sha = _read_json_snapshot(
        path, field="domain verification decision"
    )
    if actual_sha != expected_sha:
        raise ScientificCriticError(
            "domain verification decision changed after graph verification"
        )

    scope = _validate_verification_decision_contract(decision)
    expected_pairs = {
        "result_node_id": edge.get("source_node_id"),
        "target_node_id": edge.get("target_node_id"),
        "relation": edge.get("relation"),
    }
    for field, expected in expected_pairs.items():
        if decision.get(field) != expected:
            raise ScientificCriticError(
                f"domain verification decision {field} does not match its graph edge"
            )

    source_node_id = edge.get("source_node_id")
    if not isinstance(source_node_id, str) or source_node_id not in nodes_by_id:
        raise ScientificCriticError("verified support source node is absent from the bound graph")
    source_node = nodes_by_id[source_node_id]
    source_metadata = source_node.get("metadata")
    if not isinstance(source_metadata, Mapping):
        raise ScientificCriticError(
            "domain verification decision source node lacks transition metadata"
        )
    transition_id = decision.get("transition_id")
    if source_metadata.get("transition_id") != transition_id:
        raise ScientificCriticError(
            "domain verification decision transition_id does not match source-node provenance"
        )
    lineage = lineage_by_id.get(str(transition_id))
    if not isinstance(lineage, Mapping):
        raise ScientificCriticError(
            "domain verification decision is not bound by graph transition_lineage"
        )
    lineage_pairs = {
        "result_node_id": source_node_id,
        "proposal_sha256": decision.get("proposal_sha256"),
        "parent_graph_sha256": decision.get("base_graph_sha256"),
        "verification_decision_sha256": expected_sha,
    }
    for field, expected in lineage_pairs.items():
        if not isinstance(expected, str) or not expected:
            raise ScientificCriticError(
                f"domain verification decision {field} provenance is malformed"
            )
        if lineage.get(field) != expected:
            raise ScientificCriticError(
                f"domain verification decision {field} does not match graph transition_lineage"
            )

    # The merged transition-lineage v1.0 contract does not record inference_edge_id.
    # Without that exact identity, a verifier for one same-triple edge could be attached
    # to another. Missing identity therefore leaves scope unestablished; an explicit but
    # conflicting identity is a provenance error and fails closed.
    lineage_edge_id = lineage.get("inference_edge_id")
    if lineage_edge_id is None:
        return None
    if not isinstance(lineage_edge_id, str) or not lineage_edge_id.strip():
        raise ScientificCriticError("transition lineage inference_edge_id is malformed")
    if lineage_edge_id != edge.get("edge_id"):
        raise ScientificCriticError(
            "domain verification decision does not match the exact inference edge identity"
        )

    if not _validate_empirical_scope_source(scope=scope, source_node=source_node):
        return None
    return scope


def _add_empirical_support_scope_obligation(
    report: dict[str, Any], *, artifact_root: str | Path
) -> None:
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise ScientificCriticError("critic report target_reports are malformed")

    relevant: list[tuple[dict[str, Any], list[str]]] = []
    for raw in target_reports:
        if not isinstance(raw, dict):
            raise ScientificCriticError("critic target report is malformed")
        if raw.get("claim_scope") not in _EMPIRICAL_TARGET_SCOPES:
            continue
        assessment = raw.get("epistemic_assessment")
        if not isinstance(assessment, Mapping):
            raise ScientificCriticError("critic target assessment is malformed")
        support_edges = assessment.get("verified_support_edges")
        if not isinstance(support_edges, list):
            raise ScientificCriticError("verified_support_edges must be a list")
        normalized = [str(item) for item in support_edges]
        if normalized:
            relevant.append((raw, normalized))
    if not relevant:
        return

    graph = _load_bound_graph(report)
    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        raise ScientificCriticError("bound epistemic graph edges must be a list")
    edges_by_id: dict[str, Mapping[str, Any]] = {}
    for edge in raw_edges:
        if not isinstance(edge, Mapping) or not isinstance(edge.get("edge_id"), str):
            continue
        edge_id = str(edge["edge_id"])
        if edge_id in edges_by_id:
            raise ScientificCriticError(f"duplicate epistemic edge ID: {edge_id}")
        edges_by_id[edge_id] = edge
    nodes_by_id = _graph_nodes_by_id(graph)
    lineage_by_id = _transition_lineage_by_id(graph)

    try:
        artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ScientificCriticError("artifact_root is no longer readable") from exc
    if not artifacts.is_dir():
        raise ScientificCriticError(f"artifact_root must be a directory: {artifacts}")

    for raw, support_edge_ids in relevant:
        scopes: list[str] = []
        unscoped_edge_ids: list[str] = []
        source_node_ids: list[str] = []
        for edge_id in support_edge_ids:
            edge = edges_by_id.get(edge_id)
            if not isinstance(edge, Mapping):
                raise ScientificCriticError(
                    f"verified support edge is absent from the exact bound graph: {edge_id}"
                )
            source_node_id = edge.get("source_node_id")
            if isinstance(source_node_id, str) and source_node_id not in source_node_ids:
                source_node_ids.append(source_node_id)
            scope = _bound_domain_verification_scope(
                edge,
                artifact_root=artifacts,
                nodes_by_id=nodes_by_id,
                lineage_by_id=lineage_by_id,
            )
            if scope is None:
                unscoped_edge_ids.append(edge_id)
            else:
                scopes.append(scope)

        if any(scope in _EMPIRICAL_INFERENCE_SCOPES for scope in scopes):
            continue

        findings = raw.get("critic_findings")
        actions = raw.get("discriminating_actions")
        if not isinstance(findings, list) or not isinstance(actions, list):
            raise ScientificCriticError("critic target proposal collections are malformed")
        target_id = str(raw.get("target_node_id"))
        observed_scope_text = ", ".join(sorted(set(scopes))) if scopes else "none"
        unresolved_text = ", ".join(unscoped_edge_ids) if unscoped_edge_ids else "none"
        findings.append(
            {
                "finding_id": f"critic:{target_id}:empirical-support-scope-unproven",
                "code": "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED",
                "severity": "high",
                "statement": (
                    "The target is empirical or mixed in scope, but the exact bound positive-support "
                    "verification provenance does not establish any empirical_derived or empirical_direct "
                    "inference scope."
                ),
                "rationale": (
                    "A domain-verified support edge remains domain verified, but the critic requires a "
                    "complete verifier contract, exact transition/inference-edge identity, and provenance-"
                    "bound empirical origin before treating support as empirical. Current transition lineage "
                    "does not prove inference-edge identity, and empirical_derived input bindings do not yet "
                    f"classify empirical origin. Observed established scopes: {observed_scope_text}; unresolved "
                    f"support edges: {unresolved_text}."
                ),
                "edge_ids": list(support_edge_ids),
                "node_ids": source_node_ids,
                "scientific_status_changed": False,
            }
        )
        actions.append(
            {
                "action_id": f"critic:{target_id}:bind-empirical-support-scope",
                "action_class": "manual_review",
                "description": (
                    "Strengthen verifier/transition provenance with exact inference-edge identity and "
                    "first-class empirical input-origin classification where applicable; if no empirical "
                    "support exists, plan independent empirical validation."
                ),
                "rationale": (
                    "The critic must distinguish computational support from empirical evidence without "
                    "inferring authority from source labels or generic evidence bindings."
                ),
                "execution_mode": "plan_only",
                "information_gain_priority": "high",
                "information_gain_is_calibrated_probability": False,
                "expected_discrimination": (
                    "Determines whether positive support has provenance sufficient to establish empirical "
                    "scope without changing existing scientific status automatically."
                ),
                "automatic_execution_authorized": False,
                "availability_asserted": False,
            }
        )


def build_policy_hardened_scientific_critic_report(
    graph_path: str | Path,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    target_node_ids: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Build the critic report with conservative provenance/evidence-gap policy."""
    base = _build_base_report(
        graph_path,
        program_state=program_state,
        artifact_root=artifact_root,
        target_node_ids=target_node_ids,
    )
    report = copy.deepcopy(base)
    _replace_independence_assumption(report)
    _add_empirical_support_scope_obligation(report, artifact_root=artifact_root)
    _mark_action_availability_unproven(report)
    gaps = _program_evidence_gaps(program_state)
    report["critic_policy_version"] = (
        f"{SCIENTIFIC_CRITIC_POLICY_VERSION}+hardening-"
        f"{SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION}"
    )
    report["program_evidence_gaps"] = gaps
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ScientificCriticError("critic report summary is malformed")
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise ScientificCriticError("critic report target_reports are malformed")
    summary["findings"] = sum(
        len(item.get("critic_findings", []))
        for item in target_reports
        if isinstance(item, Mapping)
    )
    summary["methodological_alternatives"] = sum(
        len(item.get("methodological_alternatives", []))
        for item in target_reports
        if isinstance(item, Mapping)
    )
    summary["discriminating_actions"] = sum(
        len(item.get("discriminating_actions", []))
        for item in target_reports
        if isinstance(item, Mapping)
    )
    summary["program_evidence_gaps"] = len(gaps)
    boundary = report.get("autonomy_boundary")
    if not isinstance(boundary, dict):
        raise ScientificCriticError("critic report autonomy boundary is malformed")
    boundary.update(
        {
            "support_independence_inferred_from_artifact_identity": False,
            "empirical_support_scope_inferred_from_source_node_type": False,
            "empirical_support_scope_accepted_without_transition_lineage": False,
            "empirical_support_scope_accepted_without_exact_inference_edge_identity": False,
            "empirical_derived_scope_inferred_from_unclassified_input_bindings": False,
            "action_availability_inferred": False,
            "program_evidence_requirements_target_attributed_without_mapping": False,
            "program_evidence_acquisition_authorized": False,
        }
    )
    return report


__all__ = [
    "SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION",
    "build_policy_hardened_scientific_critic_report",
]
