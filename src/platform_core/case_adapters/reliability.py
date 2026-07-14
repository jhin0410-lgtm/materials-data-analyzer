"""Reliability trust verify adapter.

This adapter verifies existing tracked compact reliability trust artifacts. It
does not execute the v1.5 trust script, read raw/local-only files, fit models,
or rewrite canonical tracked outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..artifact_resolver import calculate_sha256
from ..execution_runtime import AdapterExecutionResult, ExecutionContext


REQUIRED_READS = (
    "reliability_v1_5_classification_metrics",
    "reliability_v1_5_model_eligibility",
    "reliability_v1_5_validation_stability_summary",
    "reliability_v1_5_trust_summary",
    "reliability_v1_5_claim_boundary",
    "reliability_v1_5_closeout_conclusion",
)


def execute_reliability_trust_verify(context: ExecutionContext) -> AdapterExecutionResult:
    resolved = {
        artifact_id: context.artifact_resolver.resolve(
            artifact_id,
            require_exists=True,
            allow_local_only=False,
            allow_raw=False,
        )
        for artifact_id in REQUIRED_READS
    }
    frames = {
        artifact_id: pd.read_csv(resolved_artifact.path)
        for artifact_id, resolved_artifact in resolved.items()
    }
    checks = _verify_trust_outputs(frames)
    report = {
        "adapter_id": context.adapter_id,
        "run_id": context.run_id,
        "status": "success" if checks["error_count"] == 0 else "failed",
        "checks": checks,
        "input_artifacts": {
            artifact_id: resolved_artifact.to_dict()
            for artifact_id, resolved_artifact in sorted(resolved.items())
        },
        "canonical_comparison": "not_comparable_verify_mode",
        "execution_boundary": {
            "mode": context.execution_mode,
            "raw_data_read": False,
            "model_training": False,
            "canonical_overwrite": False,
        },
    }
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = context.artifacts_dir / "reliability_trust_verification_report.json"
    _write_json_atomic(report, report_path)
    output_sha = calculate_sha256(report_path)
    relative_report = report_path.resolve().relative_to(context.repository_root.resolve()).as_posix()
    return AdapterExecutionResult(
        status=str(report["status"]),
        produced_files=(relative_report,),
        warnings=tuple(checks["warnings"]),
        metrics_summary={
            "verification_status": report["status"],
            "error_count": checks["error_count"],
            "warning_count": len(checks["warnings"]),
            "canonical_comparison": "not_comparable_verify_mode",
            "representative_model": checks["representative_model"],
            "shap_status": checks["shap_status"],
            "survival_model_status": checks["survival_model_status"],
            "rul_model_status": checks["rul_model_status"],
        },
        claim_boundary=checks["claim_boundary"],
        input_checksums={
            artifact_id: str(resolved_artifact.sha256)
            for artifact_id, resolved_artifact in sorted(resolved.items())
            if resolved_artifact.sha256
        },
        output_checksums={relative_report: output_sha},
        side_effect_summary={},
        errors=tuple(checks["errors"]),
    )


def _verify_trust_outputs(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    trust = _field_value_map(frames["reliability_v1_5_trust_summary"])
    closeout = _field_value_map(frames["reliability_v1_5_closeout_conclusion"])
    eligibility = frames["reliability_v1_5_model_eligibility"]
    claims = frames["reliability_v1_5_claim_boundary"]

    representative_model = closeout.get("representative_model")
    if representative_model != "none_selected":
        errors.append("representative_model must remain none_selected")
    if trust.get("representative_model_selected") != "false":
        errors.append("trust_summary representative_model_selected must be false")
    if trust.get("shap_status") != "deferred_not_justified":
        errors.append("SHAP must remain deferred_not_justified")
    if trust.get("survival_model_status") != "deferred_not_ready":
        errors.append("survival model must remain deferred_not_ready")
    if trust.get("rul_model_status") != "deferred_not_ready":
        errors.append("RUL model must remain deferred_not_ready")
    if "representative_model_selected" in eligibility.columns and eligibility[
        "representative_model_selected"
    ].astype(str).str.lower().eq("true").any():
        errors.append("model eligibility cannot select a representative model")
    if "eligibility_status" in eligibility.columns and eligibility[
        "eligibility_status"
    ].astype(str).str.lower().eq("production_ready").any():
        errors.append("production_ready status is prohibited")
    required_claims = {
        "production-ready failure prediction",
        "calibrated 7-day failure probability",
        "survival probability or RUL estimate",
    }
    if {"claim", "status"}.issubset(claims.columns):
        prohibited_claims = set(
            claims.loc[claims["status"].astype(str).eq("prohibited"), "claim"].astype(str)
        )
        missing = sorted(required_claims - prohibited_claims)
        if missing:
            errors.append("missing prohibited claim(s): " + ", ".join(missing))
    else:
        errors.append("claim boundary missing claim/status columns")

    for artifact_id, frame in frames.items():
        text = frame.to_csv(index=False).lower()
        if "serial_number" in text:
            errors.append(f"raw serial identifier leaked in {artifact_id}")
        if any(marker in text for marker in ("password=", "secret=", "token=", "api_key=", "kaggle_key=")):
            errors.append(f"credential-like content found in {artifact_id}")
        if "c:/" in text or "c:\\" in text:
            errors.append(f"absolute Windows path found in {artifact_id}")

    if trust.get("combined_top_1_lift") and trust.get("combined_top_1_precision"):
        warnings.append("top-risk lift is verified only with absolute precision boundary")
    return {
        "error_count": len(errors),
        "errors": errors,
        "warnings": warnings,
        "representative_model": representative_model,
        "shap_status": trust.get("shap_status"),
        "survival_model_status": trust.get("survival_model_status"),
        "rul_model_status": trust.get("rul_model_status"),
        "claim_boundary": {
            "production_claim_allowed": False,
            "calibrated_probability_claim_allowed": False,
            "representative_model_status": "none_selected",
            "shap_status": trust.get("shap_status"),
            "survival_model_status": trust.get("survival_model_status"),
            "rul_model_status": trust.get("rul_model_status"),
        },
    }


def _field_value_map(frame: pd.DataFrame) -> dict[str, str]:
    if {"field", "value"}.issubset(frame.columns):
        return {str(row["field"]): str(row["value"]) for _, row in frame.iterrows()}
    return {}


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
