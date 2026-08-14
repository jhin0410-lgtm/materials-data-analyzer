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

SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION = "1.7"

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
_NEGATIVE_AUTHORITY_FINDING_CODES = {
    "VERIFIED_FALSIFICATION_PRESENT",
    "VERIFIED_CONTRADICTION_PRESENT",
    "VERIFIED_EVIDENCE_CONFLICT",
}
_NEGATIVE_AUTHORITY_ACTION_SUFFIXES = {
    ":reframe-falsified-scope",
    ":reassess-contradicted-scope",
    ":resolve-verified-conflict",
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
                    "independence. Independence requires a separate provenance contract."
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
                    "acquisition conditions, preprocessing lineage, or another unrepresented dependence."
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
                    "data or an external experiment actually exists, test replication under that contract."
                ),
                "rationale": (
                    "The critic cannot infer independence, suitable data, or local replication capability "
                    "from distinct artifacts alone."
                ),
                "execution_mode": "plan_only",
                "information_gain_priority": "high",
                "information_gain_is_calibrated_probability": False,
                "expected_discrimination": (
                    "Separates genuinely independent replication from repeated analysis of shared provenance."
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


def _read_json_snapshot(path: Path, *, field: str) -> tuple[dict[str, Any], str]:
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
    return value, hashlib.sha256(raw).hexdigest()


def _load_bound_graph(report: Mapping[str, Any]) -> dict[str, Any]:
    binding = report.get("graph_binding")
    if not isinstance(binding, Mapping):
        raise ScientificCriticError("critic report graph_binding is malformed")
    path_value = _nonempty_text(binding.get("path"), "critic report graph_binding.path")
    expected_sha = _nonempty_text(binding.get("sha256"), "critic report graph_binding.sha256")
    try:
        path = Path(path_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ScientificCriticError("bound epistemic graph is no longer readable") from exc
    value, actual_sha = _read_json_snapshot(path, field="bound epistemic graph")
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
        transition_id = _nonempty_text(
            raw.get("transition_id"), f"bound graph transition_lineage[{index}].transition_id"
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
    relation = _nonempty_text(decision.get("relation"), "domain verification decision relation")
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
        text = _nonempty_text(value, f"domain verification decision limitations[{index}]")
        if text in seen:
            raise ScientificCriticError(
                "domain verification decision limitations must not contain duplicates"
            )
        seen.add(text)
    return scope


def _validate_empirical_source_shape(*, scope: str, source_node: Mapping[str, Any]) -> None:
    if scope not in _EMPIRICAL_INFERENCE_SCOPES:
        return
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
        return
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


def _validate_current_verifier_provenance(
    edge: Mapping[str, Any],
    *,
    artifact_root: Path,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    lineage_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Validate the current verifier contract without granting exact-edge authority.

    Transition provenance v1.0 does not checksum-authenticate the exact proposed
    `inference_edge_id`. Graph metadata is extensible, so a manually inserted edge ID is
    not authoritative. This function validates everything that the current contract can
    prove and returns the verifier's declared scope for diagnostics only. The caller must
    not treat the return value as proof that this exact graph edge was independently
    verified.
    """
    binding = edge.get("verification_artifact")
    if not isinstance(binding, Mapping) or binding.get("role") != "domain_verification_decision":
        return None
    path_value = _nonempty_text(binding.get("path"), "domain verification decision path")
    expected_sha = _nonempty_text(binding.get("sha256"), "domain verification decision checksum")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise ScientificCriticError("domain verification decision is no longer readable") from exc
    decision, actual_sha = _read_json_snapshot(path, field="domain verification decision")
    if actual_sha != expected_sha:
        raise ScientificCriticError(
            "domain verification decision changed after graph verification"
        )

    scope = _validate_verification_decision_contract(decision)
    for field, expected in {
        "result_node_id": edge.get("source_node_id"),
        "target_node_id": edge.get("target_node_id"),
        "relation": edge.get("relation"),
    }.items():
        if decision.get(field) != expected:
            raise ScientificCriticError(
                f"domain verification decision {field} does not match its graph edge"
            )

    source_node_id = edge.get("source_node_id")
    if not isinstance(source_node_id, str) or source_node_id not in nodes_by_id:
        raise ScientificCriticError("verified directional source node is absent from the bound graph")
    source_node = nodes_by_id[source_node_id]
    source_metadata = source_node.get("metadata")
    if not isinstance(source_metadata, Mapping):
        raise ScientificCriticError(
            "domain verification decision source node lacks transition metadata"
        )
    transition_id = _nonempty_text(
        decision.get("transition_id"), "domain verification decision transition_id"
    )
    if source_metadata.get("transition_id") != transition_id:
        raise ScientificCriticError(
            "domain verification decision transition_id does not match source-node provenance"
        )
    lineage = lineage_by_id.get(transition_id)
    if not isinstance(lineage, Mapping):
        raise ScientificCriticError(
            "domain verification decision is not bound by graph transition_lineage"
        )
    for field, expected in {
        "result_node_id": source_node_id,
        "proposal_sha256": decision.get("proposal_sha256"),
        "parent_graph_sha256": decision.get("base_graph_sha256"),
        "verification_decision_sha256": expected_sha,
    }.items():
        if not isinstance(expected, str) or not expected:
            raise ScientificCriticError(
                f"domain verification decision {field} provenance is malformed"
            )
        if lineage.get(field) != expected:
            raise ScientificCriticError(
                f"domain verification decision {field} does not match graph transition_lineage"
            )

    _validate_empirical_source_shape(scope=scope, source_node=source_node)
    return scope


def _remove_negative_authority_claims(raw: dict[str, Any], *, target_id: str) -> None:
    findings = raw.get("critic_findings")
    actions = raw.get("discriminating_actions")
    if not isinstance(findings, list) or not isinstance(actions, list):
        raise ScientificCriticError("critic target proposal collections are malformed")

    findings[:] = [
        item
        for item in findings
        if not (
            isinstance(item, Mapping)
            and item.get("code") in _NEGATIVE_AUTHORITY_FINDING_CODES
        )
    ]
    actions[:] = [
        item
        for item in actions
        if not (
            isinstance(item, Mapping)
            and any(
                str(item.get("action_id", "")).endswith(suffix)
                for suffix in _NEGATIVE_AUTHORITY_ACTION_SUFFIXES
            )
        )
    ]
    findings.append(
        {
            "finding_id": f"critic:{target_id}:negative-directional-provenance-unproven",
            "code": "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED",
            "severity": "high",
            "statement": (
                "The evaluator reports one or more usable verified negative directional relations, "
                "but the critic cannot authenticate the exact inference-edge identity under the current "
                "transition-v1 provenance contract."
            ),
            "rationale": (
                "A contradiction or falsification must not drive critic stop/reframe authority when a verifier "
                "could be reused across same-source/target/relation edges and exact edge identity is not "
                "checksum-authenticated. The evaluator assessment is preserved unchanged; only critic authority "
                "is withheld pending stronger provenance."
            ),
            "edge_ids": [],
            "node_ids": [],
            "scientific_status_changed": False,
        }
    )
    actions.append(
        {
            "action_id": f"critic:{target_id}:verify-negative-directional-provenance",
            "action_class": "manual_review",
            "description": (
                "Verify the negative directional relation against a checksum-authenticated exact inference-edge "
                "contract before using it to stop, narrow, or reframe the scientific target."
            ),
            "rationale": (
                "Current transition-v1 provenance cannot prove which exact inference edge the verifier authorized."
            ),
            "execution_mode": "plan_only",
            "information_gain_priority": "high",
            "information_gain_is_calibrated_probability": False,
            "expected_discrimination": (
                "Separates authenticated negative scientific evidence from a reused or ambiguously bound verifier."
            ),
            "automatic_execution_authorized": False,
            "availability_asserted": False,
        }
    )
    raw["stop_recommendation"] = {
        "recommendation": "verify_directional_provenance_before_scientific_reframe",
        "rationale": (
            "The evaluator's negative status is preserved, but critic-level stop/reframe authority is withheld "
            "until exact directional provenance is authenticated."
        ),
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }


def _apply_directional_provenance_policy(
    report: dict[str, Any], *, artifact_root: str | Path
) -> None:
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise ScientificCriticError("critic report target_reports are malformed")

    relevant: list[dict[str, Any]] = []
    for raw in target_reports:
        if not isinstance(raw, dict):
            raise ScientificCriticError("critic target report is malformed")
        assessment = raw.get("epistemic_assessment")
        if not isinstance(assessment, Mapping):
            raise ScientificCriticError("critic target assessment is malformed")
        for field in (
            "verified_support_edges",
            "verified_contradiction_edges",
            "verified_falsification_edges",
        ):
            if not isinstance(assessment.get(field), list):
                raise ScientificCriticError(f"{field} must be a list")
        if (
            assessment.get("verified_support_edges")
            or assessment.get("verified_contradiction_edges")
            or assessment.get("verified_falsification_edges")
        ):
            relevant.append(raw)
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

    for raw in relevant:
        assessment = raw["epistemic_assessment"]
        target_id = str(raw.get("target_node_id"))
        support_ids = [str(item) for item in assessment["verified_support_edges"]]
        contradiction_ids = [str(item) for item in assessment["verified_contradiction_edges"]]
        falsification_ids = [str(item) for item in assessment["verified_falsification_edges"]]
        directional_ids = support_ids + contradiction_ids + falsification_ids
        declared_scopes: dict[str, str | None] = {}
        for edge_id in directional_ids:
            edge = edges_by_id.get(edge_id)
            if not isinstance(edge, Mapping):
                raise ScientificCriticError(
                    f"verified directional edge is absent from the exact bound graph: {edge_id}"
                )
            declared_scopes[edge_id] = _validate_current_verifier_provenance(
                edge,
                artifact_root=artifacts,
                nodes_by_id=nodes_by_id,
                lineage_by_id=lineage_by_id,
            )

        if contradiction_ids or falsification_ids:
            _remove_negative_authority_claims(raw, target_id=target_id)
            negative_finding = raw["critic_findings"][-1]
            negative_finding["edge_ids"] = contradiction_ids + falsification_ids

        if raw.get("claim_scope") in _EMPIRICAL_TARGET_SCOPES and support_ids:
            findings = raw.get("critic_findings")
            actions = raw.get("discriminating_actions")
            if not isinstance(findings, list) or not isinstance(actions, list):
                raise ScientificCriticError("critic target proposal collections are malformed")
            scopes = [
                declared_scopes[edge_id]
                for edge_id in support_ids
                if declared_scopes.get(edge_id) is not None
            ]
            findings.append(
                {
                    "finding_id": f"critic:{target_id}:empirical-support-scope-unproven",
                    "code": "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED",
                    "severity": "high",
                    "statement": (
                        "The target is empirical or mixed in scope, but the current provenance contract "
                        "does not establish empirical authority for its positive support."
                    ),
                    "rationale": (
                        "The critic validates current verifier bytes and lineage but transition-v1 cannot "
                        "checksum-authenticate exact inference-edge identity. Generic input bindings also do "
                        "not classify empirical origin for empirical_derived scope. Declared verifier scopes "
                        f"observed after current-contract validation: {', '.join(sorted(set(scopes))) if scopes else 'none'}."
                    ),
                    "edge_ids": list(support_ids),
                    "node_ids": [],
                    "scientific_status_changed": False,
                }
            )
            actions.append(
                {
                    "action_id": f"critic:{target_id}:bind-empirical-support-scope",
                    "action_class": "manual_review",
                    "description": (
                        "Strengthen transition/verifier provenance with checksum-authenticated exact inference-edge "
                        "identity and first-class empirical input-origin classification where applicable."
                    ),
                    "rationale": (
                        "The critic must not infer empirical authority from source labels, opaque graph metadata, "
                        "or generic input evidence bindings."
                    ),
                    "execution_mode": "plan_only",
                    "information_gain_priority": "high",
                    "information_gain_is_calibrated_probability": False,
                    "expected_discrimination": (
                        "Determines whether positive support has provenance sufficient for empirical scope without "
                        "changing existing scientific status automatically."
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
    _apply_directional_provenance_policy(report, artifact_root=artifact_root)
    _mark_action_availability_unproven(report)
    gaps = _program_evidence_gaps(program_state)
    report["critic_policy_version"] = (
        f"{SCIENTIFIC_CRITIC_POLICY_VERSION}+hardening-"
        f"{SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION}"
    )
    report["program_evidence_gaps"] = gaps

    target_reports = report.get("target_reports")
    summary = report.get("summary")
    if not isinstance(target_reports, list) or not isinstance(summary, dict):
        raise ScientificCriticError("critic report summary/target_reports are malformed")
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
            "empirical_support_scope_accepted_without_authenticated_inference_edge_identity": False,
            "empirical_derived_scope_inferred_from_unclassified_input_bindings": False,
            "negative_directional_authority_accepted_without_authenticated_inference_edge_identity": False,
            "opaque_graph_metadata_treated_as_scientific_authority": False,
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
