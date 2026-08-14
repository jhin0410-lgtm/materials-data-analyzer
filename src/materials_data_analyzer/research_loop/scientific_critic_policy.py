"""Conservative policy overlay for the deterministic scientific critic.

This wrapper deliberately refuses two shortcuts that a structural graph alone cannot
justify:

1. distinct support nodes/artifacts are *not* treated as independent replication unless
   a future explicit independence contract proves that property;
2. mission-program evidence requirements are preserved at workstream scope and are not
   silently attributed to an epistemic target without an explicit target↔workstream
   provenance mapping.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from .scientific_critic import (
    SCIENTIFIC_CRITIC_POLICY_VERSION,
    ScientificCriticError,
    build_scientific_critic_report as _build_base_report,
)

SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION = "1.1"


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


def build_policy_hardened_scientific_critic_report(
    graph_path: str | Path,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    target_node_ids: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Build the critic report with conservative independence/evidence-gap policy."""
    base = _build_base_report(
        graph_path,
        program_state=program_state,
        artifact_root=artifact_root,
        target_node_ids=target_node_ids,
    )
    report = copy.deepcopy(base)
    _replace_independence_assumption(report)
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
            "program_evidence_requirements_target_attributed_without_mapping": False,
            "program_evidence_acquisition_authorized": False,
        }
    )
    return report


__all__ = [
    "SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION",
    "build_policy_hardened_scientific_critic_report",
]
