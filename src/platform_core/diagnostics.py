"""Deterministic diagnostic data model for platform registry intelligence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


SEVERITIES = ("info", "warning", "error", "blocker")
FINDING_STATUSES = ("satisfied", "partially_satisfied", "violated", "unavailable", "not_applicable")
CLAIM_IMPACTS = ("none", "narrow_claim", "prohibit_claim", "block_promotion", "block_execution")
PROMOTION_STATUSES = (
    "metadata_only",
    "diagnostic_ready",
    "limited_validation_ready",
    "further_validation_candidate",
    "blocked_missing_evidence",
    "blocked_policy_violation",
    "missing_evidence",
    "blocked_by_policy",
    "diagnostic_only",
    "eligible_for_further_validation",
)


@dataclass(frozen=True)
class DiagnosticFinding:
    finding_id: str
    run_id: str
    diagnostic_type: str
    policy_id: str | None
    severity: str
    status: str
    evidence_refs: tuple[str, ...]
    message: str
    remediation_code: str
    claim_impact: str
    deterministic_rule_id: str
    category: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"unsupported severity: {self.severity}")
        if self.status not in FINDING_STATUSES:
            raise ValueError(f"unsupported finding status: {self.status}")
        if self.claim_impact not in CLAIM_IMPACTS:
            raise ValueError(f"unsupported claim impact: {self.claim_impact}")

    def to_persistence_dict(self, evaluation_id: str) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "evaluation_id": evaluation_id,
            "rule_id": self.deterministic_rule_id,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "remediation_code": self.remediation_code,
            "claim_impact": self.claim_impact,
            "evidence_refs_json": json.dumps(list(self.evidence_refs), sort_keys=True),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "run_id": self.run_id,
            "diagnostic_type": self.diagnostic_type,
            "policy_id": self.policy_id,
            "severity": self.severity,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "message": self.message,
            "remediation_code": self.remediation_code,
            "claim_impact": self.claim_impact,
            "deterministic_rule_id": self.deterministic_rule_id,
            "category": self.category,
        }


@dataclass(frozen=True)
class EvidenceGap:
    gap_id: str
    gap_code: str
    required_for: str
    current_status: str
    missing_evidence: tuple[str, ...]
    effect_on_claim: str
    recommended_next_step: str
    priority: str

    def to_persistence_dict(self, evaluation_id: str) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "evaluation_id": evaluation_id,
            "gap_code": self.gap_code,
            "required_for": self.required_for,
            "current_status": self.current_status,
            "impact": self.effect_on_claim,
            "remediation_code": self.recommended_next_step,
            "priority": self.priority,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "gap_code": self.gap_code,
            "required_for": self.required_for,
            "current_status": self.current_status,
            "missing_evidence": list(self.missing_evidence),
            "effect_on_claim": self.effect_on_claim,
            "recommended_next_step": self.recommended_next_step,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class ClaimEvaluation:
    claim_id: str
    status: str
    supporting_evidence: tuple[str, ...] = ()
    conflicting_evidence: tuple[str, ...] = ()
    reason_code: str = "not_evaluated"

    def to_persistence_dict(self, evaluation_id: str) -> dict[str, Any]:
        return {
            "claim_evaluation_id": f"{evaluation_id}:{self.claim_id}",
            "evaluation_id": evaluation_id,
            "claim_id": self.claim_id,
            "status": self.status,
            "supporting_evidence_json": json.dumps(list(self.supporting_evidence), sort_keys=True),
            "conflicting_evidence_json": json.dumps(list(self.conflicting_evidence), sort_keys=True),
            "reason_code": self.reason_code,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "supporting_evidence": list(self.supporting_evidence),
            "conflicting_evidence": list(self.conflicting_evidence),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    policy_id: str | None
    status: str
    findings: tuple[DiagnosticFinding, ...] = ()


@dataclass(frozen=True)
class RunDiagnosticReport:
    run_id: str
    evaluation_id: str
    evaluated_at: str
    rule_set_version: str
    overall_status: str
    promotion_status: str
    findings: tuple[DiagnosticFinding, ...]
    evidence_gaps: tuple[EvidenceGap, ...]
    claim_evaluations: tuple[ClaimEvaluation, ...]
    evidence_graph: dict[str, Any] = field(default_factory=dict)
    source_manifest_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation": {
                "evaluation_id": self.evaluation_id,
                "run_id": self.run_id,
                "evaluated_at": self.evaluated_at,
                "rule_set_version": self.rule_set_version,
                "overall_status": self.overall_status,
                "promotion_status": self.promotion_status,
                "finding_count": len(self.findings),
                "blocker_count": sum(1 for finding in self.findings if finding.severity == "blocker" and finding.status == "violated"),
                "source_manifest_hash": self.source_manifest_hash,
            },
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence_gaps": [gap.to_dict() for gap in self.evidence_gaps],
            "claim_evaluations": [claim.to_dict() for claim in self.claim_evaluations],
            "evidence_graph": self.evidence_graph,
        }

    def to_persistence_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        evaluation_id = self.evaluation_id
        payload["findings"] = [finding.to_persistence_dict(evaluation_id) for finding in self.findings]
        payload["evidence_gaps"] = [gap.to_persistence_dict(evaluation_id) for gap in self.evidence_gaps]
        payload["claim_evaluations"] = [claim.to_persistence_dict(evaluation_id) for claim in self.claim_evaluations]
        return payload
