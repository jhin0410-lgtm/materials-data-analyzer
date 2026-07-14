"""Registry-backed policy diagnostics for platform runs.

This module evaluates deterministic metadata rules only. It does not execute
adapters, import user-provided modules, read raw datasets, retrain models, or
recompute scientific results.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .artifacts import validate_relative_path
from .case_study_registry import build_default_case_study_registry
from .claim_diagnostics import CLAIM_ALIASES, evaluate_claim_id
from .diagnostic_rules import (
    RULE_SET_VERSION,
    DiagnosticContext,
    DiagnosticRule,
    build_default_diagnostic_rules,
)
from .diagnostics import DiagnosticFinding, EvidenceGap, RunDiagnosticReport
from .evidence_graph import build_evidence_graph
from .registry import build_default_plugin_registry
from .adapter_registry import build_default_adapter_registry
from .artifacts import build_default_artifact_registry
from .run_registry import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_REGISTRY_PATH,
    assert_no_sensitive_strings,
    canonical_json_sha256,
    compare_diagnostic_evaluations,
    get_claim_evaluation,
    get_run,
    initialize_registry,
    latest_diagnostic_evaluation,
    list_diagnostic_findings,
    list_evidence_gaps,
    reproducibility_status,
    resolve_registry_path,
    store_diagnostic_evaluation,
)
from .trust_registry import build_default_trust_policy_registry
from .validation_registry import build_default_validation_policy_registry


SUPPORTED_RULE_SETS = (RULE_SET_VERSION,)
DEFAULT_CLAIMS = tuple(sorted(CLAIM_ALIASES))
DIAGNOSTIC_EXPORT_DIR = f"{DEFAULT_EXPORT_DIR}/diagnostics"


class DiagnosticError(RuntimeError):
    """Base error for diagnostic service operations."""


class UnsupportedRuleSet(DiagnosticError):
    """Raised when a requested rule set is not registered in code."""


class DiagnosticSchemaError(DiagnosticError):
    """Raised when persisted diagnostic records are inconsistent."""


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    case_study_registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    return artifact_registry, validation_registry, trust_registry, case_study_registry


def _hash_for_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _policy_ids_for_run(run: dict[str, Any]) -> tuple[str | None, str | None]:
    _, _, _, case_study_registry = _registries()
    case_study_id = run.get("case_study_id") or run.get("plugin_id")
    try:
        case_study = case_study_registry.get(str(case_study_id))
    except KeyError:
        return None, None
    return case_study.validation_policy_id, case_study.trust_policy_id


def _policies_for_run(run: dict[str, Any]):
    _, validation_registry, trust_registry, _ = _registries()
    validation_policy_id, trust_policy_id = _policy_ids_for_run(run)
    validation_policy = None
    trust_policy = None
    if validation_policy_id:
        validation_policy = validation_registry.get(validation_policy_id)
    if trust_policy_id:
        trust_policy = trust_registry.get(trust_policy_id)
    return validation_policy, trust_policy


def _source_manifest_hash(run_payload: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {
            "run": run_payload["run"],
            "artifacts": run_payload["artifacts"],
            "warnings": run_payload["warnings"],
        }
    )


def _evaluation_id(run_id: str, rule_set: str, source_hash: str) -> str:
    return f"diag-{_hash_for_id(run_id, rule_set, source_hash)}"


def _artifact_evidence(artifacts: list[dict[str, Any]]) -> tuple[str, ...]:
    evidence: set[str] = set()
    artifact_ids = {str(artifact["artifact_id"]) for artifact in artifacts}
    if any(artifact.get("checksum_sha256") for artifact in artifacts if artifact["role"] == "input"):
        evidence.add("input_checksums")
    if any(artifact.get("checksum_sha256") for artifact in artifacts if artifact["role"] == "output"):
        evidence.add("output_checksums")
    if any("trust_summary" in artifact_id for artifact_id in artifact_ids):
        evidence.add("trust_summary")
    if any("classification_metrics" in artifact_id or "validation_metrics" in artifact_id for artifact_id in artifact_ids):
        evidence.add("metrics_summary")
    if any("model_eligibility" in artifact_id for artifact_id in artifact_ids):
        evidence.add("model_eligibility")
    if any("claim_boundary" in artifact_id for artifact_id in artifact_ids):
        evidence.add("claim_boundary_summary")
    if any("validation_stability" in artifact_id for artifact_id in artifact_ids):
        evidence.add("validation_stability_summary")
    return tuple(sorted(evidence))


def _available_evidence(
    *,
    run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    validation_policy: Any | None,
    trust_policy: Any | None,
    reproducibility: dict[str, Any],
    findings: tuple[DiagnosticFinding, ...],
) -> tuple[str, ...]:
    evidence = set(_artifact_evidence(artifacts))
    if run.get("code_commit"):
        evidence.add("code_commit")
    if run.get("config_sha256"):
        evidence.add("config_sha")
    if reproducibility.get("status") == "reproducible_verified":
        evidence.add("reproducible_verified")
    if validation_policy is not None:
        evidence.update(validation_policy.primary_evidence)
        if "asset_disjoint" in validation_policy.primary_evidence:
            evidence.add("asset_disjoint_metrics")
        if "time_aware" in validation_policy.primary_evidence or "chronological_holdout" in validation_policy.primary_evidence:
            evidence.add("time_aware_metrics")
        if "combined_asset_time" in validation_policy.primary_evidence:
            evidence.add("combined_metrics")
        if "group_disjoint_split" in validation_policy.primary_evidence:
            evidence.add("group_disjoint_validation")
    if trust_policy is not None and run.get("claim_boundary_ref"):
        evidence.add("claim_boundary_summary")
    for finding in findings:
        if finding.status == "satisfied":
            evidence.add(f"rule:{finding.deterministic_rule_id}")
    return tuple(sorted(evidence))


def _gap_id(run_id: str, gap_code: str) -> str:
    return f"gap-{_hash_for_id(run_id, gap_code)}"


def _gaps_from_findings(run_id: str, findings: tuple[DiagnosticFinding, ...]) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []
    for finding in findings:
        if finding.status not in {"violated", "unavailable", "partially_satisfied"}:
            continue
        priority = "P0" if finding.severity == "blocker" else "P1" if finding.severity == "error" else "P2"
        gaps.append(
            EvidenceGap(
                gap_id=_gap_id(run_id, f"rule:{finding.deterministic_rule_id}"),
                gap_code=f"rule:{finding.deterministic_rule_id}",
                required_for=finding.diagnostic_type,
                current_status=finding.status,
                missing_evidence=tuple(finding.evidence_refs),
                effect_on_claim=finding.claim_impact,
                recommended_next_step=finding.remediation_code,
                priority=priority,
            )
        )
    return gaps


def _gaps_from_required_evidence(
    *,
    run_id: str,
    trust_policy: Any | None,
    available_evidence: tuple[str, ...],
) -> list[EvidenceGap]:
    if trust_policy is None:
        return []
    available = set(available_evidence)
    gaps: list[EvidenceGap] = []
    for required in trust_policy.required_evidence:
        if required in available:
            continue
        gaps.append(
            EvidenceGap(
                gap_id=_gap_id(run_id, f"required:{required}"),
                gap_code=f"missing_required_evidence:{required}",
                required_for=trust_policy.policy_id,
                current_status="missing",
                missing_evidence=(required,),
                effect_on_claim="narrow_claim",
                recommended_next_step=f"provide_{required}",
                priority="P1",
            )
        )
    return gaps


def _promotion_status(findings: tuple[DiagnosticFinding, ...], gaps: tuple[EvidenceGap, ...]) -> tuple[str, str]:
    policy_blockers = [
        finding
        for finding in findings
        if finding.status == "violated" and finding.claim_impact in {"block_execution", "block_promotion"}
    ]
    missing_errors = [
        finding
        for finding in findings
        if finding.status in {"unavailable", "violated"} and finding.severity in {"error", "blocker"}
    ]
    if policy_blockers:
        return "blocked", "blocked_by_policy"
    if missing_errors or gaps:
        return "warning", "missing_evidence"
    return "passed", "diagnostic_only"


def _rules_for(rule_set: str) -> tuple[DiagnosticRule, ...]:
    if rule_set != RULE_SET_VERSION:
        raise UnsupportedRuleSet(f"unsupported diagnostic rule set: {rule_set}")
    return build_default_diagnostic_rules()


def diagnose_run(
    run_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    rule_set: str = RULE_SET_VERSION,
    persist: bool = True,
    claim_ids: tuple[str, ...] = DEFAULT_CLAIMS,
    check_files: bool = False,
) -> RunDiagnosticReport:
    rules = _rules_for(rule_set)
    run_payload = get_run(run_id, repo_root=repo_root, registry_path=registry_path)
    run = run_payload["run"]
    artifacts = run_payload["artifacts"]
    warnings = run_payload["warnings"]
    validation_policy, trust_policy = _policies_for_run(run)
    reproducibility = reproducibility_status(
        run_id,
        repo_root=repo_root,
        registry_path=registry_path,
        check_files=check_files,
    )
    context = DiagnosticContext(
        run=run,
        artifacts=tuple(artifacts),
        warnings=tuple(warnings),
        validation_policy=validation_policy,
        trust_policy=trust_policy,
        reproducibility=reproducibility,
    )
    findings = tuple(rule.evaluator(context, rule) for rule in rules if rule.applies_to(context))
    available = _available_evidence(
        run=run,
        artifacts=artifacts,
        validation_policy=validation_policy,
        trust_policy=trust_policy,
        reproducibility=reproducibility,
        findings=findings,
    )
    gaps = tuple(
        sorted(
            [*_gaps_from_findings(run_id, findings), *_gaps_from_required_evidence(run_id=run_id, trust_policy=trust_policy, available_evidence=available)],
            key=lambda gap: (gap.priority, gap.gap_code),
        )
    )
    if trust_policy is None:
        claim_evaluations = tuple(
            evaluate_claim_id(claim_id, allowed_claims=(), prohibited_claims=(), available_evidence=available)
            for claim_id in claim_ids
        )
        trust_policy_id = None
    else:
        claim_evaluations = tuple(
            evaluate_claim_id(
                claim_id,
                allowed_claims=trust_policy.allowed_claims,
                prohibited_claims=trust_policy.prohibited_claims,
                available_evidence=available,
            )
            for claim_id in claim_ids
        )
        trust_policy_id = trust_policy.policy_id
    source_hash = _source_manifest_hash(run_payload)
    overall_status, promotion_status = _promotion_status(findings, gaps)
    report = RunDiagnosticReport(
        run_id=run_id,
        evaluation_id=_evaluation_id(run_id, rule_set, source_hash),
        evaluated_at=str(run.get("created_at") or "unavailable"),
        rule_set_version=rule_set,
        overall_status=overall_status,
        promotion_status=promotion_status,
        findings=tuple(sorted(findings, key=lambda item: item.deterministic_rule_id)),
        evidence_gaps=gaps,
        claim_evaluations=tuple(sorted(claim_evaluations, key=lambda item: item.claim_id)),
        evidence_graph=build_evidence_graph(
            run=run,
            artifacts=artifacts,
            validation_policy_id=validation_policy.policy_id if validation_policy else None,
            trust_policy_id=trust_policy_id,
            claim_ids=claim_ids,
        ),
        source_manifest_hash=source_hash,
    )
    assert_no_sensitive_strings(report.to_dict())
    if persist:
        store_diagnostic_evaluation(report.to_persistence_dict(), repo_root=repo_root, registry_path=registry_path)
    return report


def show_diagnostics(
    run_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    return latest_diagnostic_evaluation(run_id, repo_root=repo_root, registry_path=registry_path)


def evaluate_claim(
    run_id: str,
    claim_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    rule_set: str = RULE_SET_VERSION,
    persist: bool = True,
) -> dict[str, Any]:
    if claim_id not in CLAIM_ALIASES:
        raise KeyError(f"unknown registered claim_id: {claim_id}")
    if persist:
        try:
            payload = show_diagnostics(run_id, repo_root=repo_root, registry_path=registry_path)
        except KeyError:
            payload = diagnose_run(
                run_id,
                repo_root=repo_root,
                registry_path=registry_path,
                rule_set=rule_set,
                persist=True,
            ).to_persistence_dict()
        for claim in payload["claim_evaluations"]:
            if claim["claim_id"] == claim_id:
                return claim
        raise KeyError(f"claim_id not evaluated for run {run_id}: {claim_id}")
    report = diagnose_run(
        run_id,
        repo_root=repo_root,
        registry_path=registry_path,
        rule_set=rule_set,
        persist=False,
        claim_ids=(claim_id,),
    )
    return report.claim_evaluations[0].to_dict()


def diagnostics_validate(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    path = initialize_registry(repo_root, registry_path)
    errors: list[str] = []
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        errors.extend(f"foreign_key:{dict(row)}" for row in fk)
        for row in connection.execute("SELECT evaluation_id, overall_status, promotion_status FROM diagnostic_evaluations"):
            if row["overall_status"] not in {"passed", "warning", "blocked"}:
                errors.append(f"unsupported overall_status:{row['evaluation_id']}")
            if row["promotion_status"] == "production_ready":
                errors.append(f"production_ready is prohibited:{row['evaluation_id']}")
        for row in connection.execute("SELECT finding_id, evidence_refs_json FROM diagnostic_findings"):
            try:
                json.loads(row["evidence_refs_json"])
            except json.JSONDecodeError:
                errors.append(f"invalid finding evidence JSON:{row['finding_id']}")
    return {"valid": not errors, "errors": errors, "registry_path": str(registry_path)}


def export_diagnostics(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    export_dir: str = DIAGNOSTIC_EXPORT_DIR,
    overwrite: bool = False,
) -> dict[str, Any]:
    validate_relative_path(export_dir)
    normalized = export_dir.replace("\\", "/")
    if not normalized.startswith(DIAGNOSTIC_EXPORT_DIR):
        raise ValueError("diagnostics export must be under outputs/platform_registry/exports/diagnostics")
    root = Path(repo_root).resolve()
    target = (root / normalized).resolve()
    if root != target and root not in target.parents:
        raise ValueError("diagnostics export escapes repository root")
    target.mkdir(parents=True, exist_ok=True)
    registry_db = resolve_registry_path(root, registry_path)
    snapshot: dict[str, Any] = {
        "export_type": "platform_diagnostics",
        "registry_path": registry_path,
        "evaluations": [],
        "findings": [],
        "evidence_gaps": [],
        "claim_evaluations": [],
    }
    if registry_db.exists():
        with sqlite3.connect(registry_db) as connection:
            connection.row_factory = sqlite3.Row
            snapshot["evaluations"] = [dict(row) for row in connection.execute("SELECT * FROM diagnostic_evaluations ORDER BY run_id, evaluation_id")]
            snapshot["findings"] = [dict(row) for row in connection.execute("SELECT * FROM diagnostic_findings ORDER BY evaluation_id, rule_id")]
            snapshot["evidence_gaps"] = [dict(row) for row in connection.execute("SELECT * FROM evidence_gaps ORDER BY evaluation_id, gap_code")]
            snapshot["claim_evaluations"] = [dict(row) for row in connection.execute("SELECT * FROM claim_evaluations ORDER BY evaluation_id, claim_id")]
    assert_no_sensitive_strings(snapshot)
    json_path = target / "diagnostics_snapshot.json"
    if json_path.exists() and not overwrite:
        raise FileExistsError(f"diagnostics export already exists: {json_path.relative_to(root).as_posix()}")
    temp = json_path.with_name(f".{json_path.name}.tmp")
    try:
        temp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(json_path)
    finally:
        temp.unlink(missing_ok=True)
    csv_path = target / "diagnostic_findings.csv"
    if csv_path.exists() and not overwrite:
        raise FileExistsError(f"diagnostics export already exists: {csv_path.relative_to(root).as_posix()}")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["evaluation_id", "rule_id", "category", "severity", "status", "claim_impact", "remediation_code"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for finding in snapshot["findings"]:
            writer.writerow({field: finding.get(field) for field in fieldnames})
    return {
        "status": "exported",
        "json_path": json_path.relative_to(root).as_posix(),
        "csv_path": csv_path.relative_to(root).as_posix(),
        "evaluation_count": len(snapshot["evaluations"]),
        "finding_count": len(snapshot["findings"]),
    }


def diagnostic_summary_exit_status(report: RunDiagnosticReport | dict[str, Any]) -> int:
    payload = report.to_dict() if isinstance(report, RunDiagnosticReport) else report
    evaluation = payload["evaluation"]
    if evaluation["overall_status"] == "blocked":
        return 11
    if evaluation["overall_status"] == "warning":
        return 10
    return 0


__all__ = [
    "DEFAULT_CLAIMS",
    "DIAGNOSTIC_EXPORT_DIR",
    "DiagnosticError",
    "DiagnosticSchemaError",
    "UnsupportedRuleSet",
    "compare_diagnostic_evaluations",
    "diagnose_run",
    "diagnostic_summary_exit_status",
    "diagnostics_validate",
    "evaluate_claim",
    "export_diagnostics",
    "get_claim_evaluation",
    "list_diagnostic_findings",
    "list_evidence_gaps",
    "show_diagnostics",
]
