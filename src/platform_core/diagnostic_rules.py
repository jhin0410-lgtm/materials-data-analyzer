"""Code-registered deterministic diagnostic rules.

Rules are static Python objects built by this module. User configs cannot
define rules, callables, imports, or filesystem discovery paths.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from .diagnostics import DiagnosticFinding, EvidenceGap


RULE_SET_VERSION = "diagnostic_rules_v1"


@dataclass(frozen=True)
class DiagnosticRule:
    rule_id: str
    category: str
    applicable_plugins: tuple[str, ...]
    applicable_stages: tuple[str, ...]
    required_fields: tuple[str, ...]
    severity: str
    evaluator: Callable[["DiagnosticContext", "DiagnosticRule"], DiagnosticFinding]
    remediation_code: str
    description: str

    def applies_to(self, context: "DiagnosticContext") -> bool:
        plugin_match = "*" in self.applicable_plugins or context.plugin_id in self.applicable_plugins
        stage_match = "*" in self.applicable_stages or context.stage in self.applicable_stages
        return plugin_match and stage_match


@dataclass(frozen=True)
class DiagnosticContext:
    run: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    warnings: tuple[dict[str, Any], ...]
    validation_policy: Any | None
    trust_policy: Any | None
    reproducibility: dict[str, Any]

    @property
    def run_id(self) -> str:
        return str(self.run["run_id"])

    @property
    def plugin_id(self) -> str:
        return str(self.run["plugin_id"])

    @property
    def stage(self) -> str:
        return str(self.run["stage"])


def _finding_id(run_id: str, rule_id: str) -> str:
    return hashlib.sha256(f"{run_id}:{rule_id}".encode("utf-8")).hexdigest()[:24]


def _finding(
    context: DiagnosticContext,
    rule: DiagnosticRule,
    *,
    status: str,
    message: str,
    severity: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    claim_impact: str = "none",
) -> DiagnosticFinding:
    return DiagnosticFinding(
        finding_id=_finding_id(context.run_id, rule.rule_id),
        run_id=context.run_id,
        diagnostic_type=rule.category,
        policy_id=(context.trust_policy.policy_id if context.trust_policy and rule.category in {"trust", "claim_boundary"} else None)
        or (context.validation_policy.policy_id if context.validation_policy and rule.category in {"validation", "preprocessing"} else None),
        severity=severity or rule.severity,
        status=status,
        evidence_refs=evidence_refs,
        message=message,
        remediation_code=rule.remediation_code,
        claim_impact=claim_impact,
        deterministic_rule_id=rule.rule_id,
        category=rule.category,
    )


def _require_run_field(field: str, label: str):
    def evaluator(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
        if context.run.get(field):
            return _finding(
                context,
                rule,
                status="satisfied",
                message=f"{label} is present.",
                severity="info",
                evidence_refs=(f"run.{field}",),
            )
        return _finding(
            context,
            rule,
            status="unavailable",
            message=f"{label} is missing from run metadata.",
            evidence_refs=(f"run.{field}",),
            claim_impact="block_promotion",
        )

    return evaluator


def _input_checksum_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    input_records = [artifact for artifact in context.artifacts if artifact["role"] == "input"]
    if not input_records:
        return _finding(context, rule, status="unavailable", message="No input artifact records are registered.", claim_impact="block_promotion")
    missing = [artifact["artifact_id"] for artifact in input_records if not artifact.get("checksum_sha256")]
    if missing:
        return _finding(
            context,
            rule,
            status="unavailable",
            message="Input artifact checksum missing: " + ", ".join(sorted(missing)),
            evidence_refs=tuple(f"artifact:{item}" for item in sorted(missing)),
            claim_impact="block_promotion",
        )
    return _finding(context, rule, status="satisfied", message="Input artifact checksums are present.", severity="info")


def _output_checksum_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    output_records = [artifact for artifact in context.artifacts if artifact["role"] == "output"]
    if not output_records:
        return _finding(context, rule, status="unavailable", message="No output artifact records are registered.", claim_impact="narrow_claim")
    missing = [artifact["artifact_id"] for artifact in output_records if not artifact.get("checksum_sha256")]
    if missing:
        return _finding(
            context,
            rule,
            status="partially_satisfied",
            message="Output artifact checksum missing: " + ", ".join(sorted(missing)),
            evidence_refs=tuple(f"artifact:{item}" for item in sorted(missing)),
            claim_impact="narrow_claim",
        )
    return _finding(context, rule, status="satisfied", message="Output artifact checksums are present.", severity="info")


def _reproducibility_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    status = context.reproducibility.get("status")
    if status == "reproducible_verified":
        return _finding(context, rule, status="satisfied", message="Registry reproducibility status is verified.", severity="info")
    if status == "reproducible_partial":
        return _finding(context, rule, status="partially_satisfied", message="Registry reproducibility status is partial.", claim_impact="narrow_claim")
    return _finding(
        context,
        rule,
        status="unavailable",
        message=f"Registry reproducibility status is {status}.",
        claim_impact="block_promotion",
    )


def _artifact_policy_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    bad = [
        artifact["artifact_id"]
        for artifact in context.artifacts
        if (int(artifact["local_only"]) and artifact["tracked_policy"] in {"tracked", "generated_compact"})
        or (
            str(artifact["relative_path"]).replace("\\", "/").startswith("data/raw/")
            and artifact["tracked_policy"] in {"tracked", "generated_compact"}
        )
    ]
    if bad:
        return _finding(
            context,
            rule,
            status="violated",
            message="Artifact tracking policy conflict: " + ", ".join(sorted(bad)),
            evidence_refs=tuple(f"artifact:{item}" for item in sorted(bad)),
            claim_impact="block_execution",
        )
    return _finding(context, rule, status="satisfied", message="Artifact local/tracked policy is consistent.", severity="info")


def _validation_policy_present(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.validation_policy is None:
        return _finding(context, rule, status="unavailable", message="Validation policy is not registered for this run.", claim_impact="block_promotion")
    return _finding(
        context,
        rule,
        status="satisfied",
        message=f"Validation policy {context.validation_policy.policy_id} is registered.",
        severity="info",
        evidence_refs=(f"policy:{context.validation_policy.policy_id}",),
    )


def _train_only_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.validation_policy is None:
        return _finding(context, rule, status="unavailable", message="Cannot evaluate preprocessing scope without validation policy.", claim_impact="narrow_claim")
    if context.validation_policy.preprocessing_scope != "train_only":
        return _finding(context, rule, status="violated", message="Preprocessing scope is not train_only.", claim_impact="block_promotion")
    return _finding(context, rule, status="satisfied", message="Validation policy declares train-only preprocessing.", severity="info")


def _primary_not_random_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.validation_policy is None:
        return _finding(context, rule, status="unavailable", message="Cannot evaluate primary evidence without validation policy.", claim_impact="narrow_claim")
    if not context.validation_policy.primary_evidence and context.validation_policy.optimistic_reference:
        return _finding(context, rule, status="violated", message="Random/optimistic reference has no primary evidence.", claim_impact="block_promotion")
    return _finding(context, rule, status="satisfied", message="Primary evidence is distinct from optimistic reference.", severity="info")


def _required_group_or_time_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.validation_policy is None:
        return _finding(context, rule, status="unavailable", message="Validation policy unavailable.", claim_impact="narrow_claim")
    missing: list[str] = []
    if "group" in context.validation_policy.validation_type and not context.validation_policy.group_key:
        missing.append("group_key")
    if ("time" in context.validation_policy.validation_type or "chronological" in context.validation_policy.validation_type) and not context.validation_policy.time_key:
        missing.append("time_key")
    if missing:
        return _finding(context, rule, status="unavailable", message="Validation key missing: " + ", ".join(missing), claim_impact="block_promotion")
    return _finding(context, rule, status="satisfied", message="Required validation keys are declared.", severity="info")


def _trust_policy_present(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.trust_policy is None:
        if context.plugin_id == "battery_archive":
            return _finding(context, rule, status="unavailable", message="Battery Archive has legacy/partial trust metadata.", claim_impact="narrow_claim")
        return _finding(context, rule, status="unavailable", message="Trust policy is not registered for this run.", claim_impact="block_promotion")
    return _finding(
        context,
        rule,
        status="satisfied",
        message=f"Trust policy {context.trust_policy.policy_id} is registered.",
        severity="info",
        evidence_refs=(f"policy:{context.trust_policy.policy_id}",),
    )


def _production_claim_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.trust_policy is None:
        return _finding(context, rule, status="unavailable", message="Production-claim policy unavailable.", claim_impact="narrow_claim")
    if context.trust_policy.production_claim_allowed:
        return _finding(context, rule, status="violated", message="Production claim is allowed by policy, which is prohibited in v2 defaults.", claim_impact="block_promotion")
    return _finding(context, rule, status="satisfied", message="Production claims are prohibited by trust policy.", severity="info")


def _calibration_boundary_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.trust_policy is None:
        return _finding(context, rule, status="unavailable", message="Calibration boundary unavailable.", claim_impact="narrow_claim")
    boundary = context.trust_policy.calibration_boundary
    if "calibrated" in boundary and not (boundary.startswith("uncalibrated") or boundary.startswith("no_")):
        return _finding(context, rule, status="violated", message="Calibration boundary may permit calibrated claims.", claim_impact="prohibit_claim")
    return _finding(context, rule, status="satisfied", message="Calibration boundary prevents calibrated probability claims.", severity="info")


def _execution_boundary_rule(context: DiagnosticContext, rule: DiagnosticRule) -> DiagnosticFinding:
    if context.run.get("side_effect_status") in {None, "", "allowed_outputs_only", "local_only_report_generated"}:
        return _finding(context, rule, status="satisfied", message="Side-effect status is allowed.", severity="info")
    return _finding(
        context,
        rule,
        status="violated",
        message=f"Side-effect status is {context.run.get('side_effect_status')}.",
        claim_impact="block_execution",
    )


def build_default_diagnostic_rules() -> tuple[DiagnosticRule, ...]:
    return (
        DiagnosticRule("provenance.config_sha_present", "provenance", ("*",), ("*",), ("config_sha256",), "error", _require_run_field("config_sha256", "Config SHA"), "provide_config_sha", "Run metadata must include config SHA."),
        DiagnosticRule("provenance.code_commit_present", "provenance", ("*",), ("*",), ("code_commit",), "error", _require_run_field("code_commit", "Code commit"), "provide_code_commit", "Run metadata must include code commit."),
        DiagnosticRule("provenance.input_checksums_present", "provenance", ("*",), ("*",), ("artifacts",), "error", _input_checksum_rule, "record_input_checksums", "Input artifact checksums should be recorded."),
        DiagnosticRule("provenance.output_checksums_present", "provenance", ("*",), ("*",), ("artifacts",), "warning", _output_checksum_rule, "record_output_checksums", "Output artifact checksums should be recorded."),
        DiagnosticRule("reproducibility.registry_status", "reproducibility", ("*",), ("*",), ("reproducibility",), "warning", _reproducibility_rule, "resolve_reproducibility_gap", "Registry reproducibility status should support claim scope."),
        DiagnosticRule("artifact_policy.local_tracked_consistency", "artifact_policy", ("*",), ("*",), ("artifacts",), "blocker", _artifact_policy_rule, "fix_artifact_policy", "Local-only/raw artifacts must not be tracked compact outputs."),
        DiagnosticRule("validation.policy_present", "validation", ("*",), ("validation", "trust", "report"), ("validation_policy",), "error", _validation_policy_present, "register_validation_policy", "Run should be associated with a validation policy when applicable."),
        DiagnosticRule("validation.train_only_preprocessing", "preprocessing", ("*",), ("validation", "trust"), ("validation_policy",), "error", _train_only_rule, "declare_train_only_preprocessing", "Validation policy should declare train-only preprocessing."),
        DiagnosticRule("validation.primary_not_random", "validation", ("*",), ("validation", "trust"), ("validation_policy",), "error", _primary_not_random_rule, "provide_primary_validation", "Optimistic random reference cannot be primary evidence."),
        DiagnosticRule("validation.required_keys_declared", "validation", ("materials_project", "smart_factory", "reliability"), ("validation", "trust"), ("validation_policy",), "warning", _required_group_or_time_rule, "declare_validation_keys", "Required group/time keys should be declared by policy."),
        DiagnosticRule("trust.policy_present", "trust", ("*",), ("trust", "report"), ("trust_policy",), "error", _trust_policy_present, "register_trust_policy", "Trust policy should be associated with trust-stage runs."),
        DiagnosticRule("trust.production_claim_disallowed", "claim_boundary", ("*",), ("trust", "report"), ("trust_policy",), "blocker", _production_claim_rule, "prohibit_production_claims", "Production claims must not be allowed."),
        DiagnosticRule("trust.calibration_boundary", "claim_boundary", ("*",), ("trust", "report"), ("trust_policy",), "error", _calibration_boundary_rule, "document_calibration_boundary", "Calibrated probability claims require explicit evidence and are currently prohibited."),
        DiagnosticRule("execution.side_effect_status", "execution", ("*",), ("*",), ("side_effect_status",), "blocker", _execution_boundary_rule, "inspect_side_effects", "Side-effect status must be allowed."),
    )
