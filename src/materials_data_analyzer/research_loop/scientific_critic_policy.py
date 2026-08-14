"""Conservative policy overlay for the deterministic scientific critic.

This wrapper deliberately refuses three shortcuts that a structural graph alone cannot
justify:

1. distinct support nodes/artifacts are *not* treated as independent replication unless
   a future explicit independence contract proves that property;
2. mission-program evidence requirements are preserved at workstream scope and are not
   silently attributed to an epistemic target without an explicit target↔workstream
   provenance mapping;
3. an empirical or mixed target is not assumed to have empirical support merely because
   a supporting source node is something other than a simulation. Empirical inference
   scope must be recoverable from the exact bound domain-verification decision.
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
    build_scientific_critic_report as _build_base_report,
)

SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION = "1.2"

_EMPIRICAL_TARGET_SCOPES = {"empirical", "mixed"}
_INFERENCE_SCOPES = {"structural", "computational", "empirical_derived", "empirical_direct"}
_EMPIRICAL_INFERENCE_SCOPES = {"empirical_derived", "empirical_direct"}


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
            if not isinstance(requirement, str) or not requirement.strip():
                raise ScientificCriticError(
                    f"generated goal evidence_requirements[{index}] must be non-empty text"
                )
            text = requirement.strip()
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

        # Direct artifact identity is useful provenance, but it is not an independence
        # certificate. Remove the narrower concentration-only finding/action and replace
        # it with the conservative statement that independence is not established.
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


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScientificCriticError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


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
    path = Path(path_value).expanduser().resolve(strict=True)
    raw = path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise ScientificCriticError(
            "epistemic graph changed after the base critic bound its exact bytes"
        )
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificCriticError("bound epistemic graph is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScientificCriticError("bound epistemic graph root must be an object")
    return value


def _bound_domain_verification_scope(
    edge: Mapping[str, Any], *, artifact_root: Path
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
    path = path.resolve(strict=True)
    raw = path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise ScientificCriticError(
            "domain verification decision changed after graph verification"
        )
    try:
        decision = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificCriticError(
            "domain verification decision must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(decision, Mapping):
        raise ScientificCriticError("domain verification decision root must be an object")
    expected_pairs = {
        "result_node_id": edge.get("source_node_id"),
        "target_node_id": edge.get("target_node_id"),
        "relation": edge.get("relation"),
    }
    if decision.get("schema_version") != "1.0" or decision.get("domain_verified") is not True:
        raise ScientificCriticError("bound domain verification decision is not a verified v1.0 decision")
    for field, expected in expected_pairs.items():
        if decision.get(field) != expected:
            raise ScientificCriticError(
                f"domain verification decision {field} does not match its graph edge"
            )
    scope = decision.get("inference_scope")
    if not isinstance(scope, str) or scope not in _INFERENCE_SCOPES:
        raise ScientificCriticError("domain verification decision inference_scope is unsupported")
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

    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
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
            scope = _bound_domain_verification_scope(edge, artifact_root=artifacts)
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
                    "verification decisions do not establish any empirical_derived or empirical_direct "
                    "inference scope."
                ),
                "rationale": (
                    "A domain-verified support edge remains domain verified, but node type alone cannot "
                    "show whether an analysis is computational or empirically derived. The critic therefore "
                    f"does not infer empirical evidence from source type. Observed bound scopes: {observed_scope_text}; "
                    f"support edges without a recognized domain-verification-decision scope: {unresolved_text}."
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
                    "Reconstruct the positive-support verification provenance and bind an explicit "
                    "empirical_derived or empirical_direct inference scope when justified; if no such "
                    "support exists, plan independent empirical validation."
                ),
                "rationale": (
                    "The critic must distinguish computational support from empirical evidence using "
                    "checksum-bound verifier provenance rather than source-node labels."
                ),
                "execution_mode": "plan_only",
                "information_gain_priority": "high",
                "information_gain_is_calibrated_probability": False,
                "expected_discrimination": (
                    "Determines whether the current positive support actually includes an empirically "
                    "verified inference scope without changing the existing scientific status automatically."
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
            "program_evidence_requirements_target_attributed_without_mapping": False,
            "program_evidence_acquisition_authorized": False,
        }
    )
    return report


__all__ = [
    "SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION",
    "build_policy_hardened_scientific_critic_report",
]
