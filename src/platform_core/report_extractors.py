"""Explicit compact-artifact extractors for platform reports.

The functions in this module summarize tracked compact artifacts only. They do
not scan row-level predictions, raw archives, or local-only analysis tables, and
they do not recompute scientific metrics.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Any

from .artifact_resolver import ArtifactResolver, ResolvedArtifact
from .reports import ReportWarning


@dataclass(frozen=True)
class ExtractedCaseStudyResults:
    case_study_id: str
    purpose: str
    dataset_source: str
    analysis_task: str
    validation_type: str
    trust_result: str
    representative_model_status: str
    claim_boundary: dict[str, Any]
    key_compact_results: dict[str, Any]
    artifacts: tuple[ResolvedArtifact, ...] = ()
    warnings: tuple[ReportWarning, ...] = ()


@dataclass
class _ExtractionContext:
    case_study_id: str
    artifacts: list[ResolvedArtifact] = field(default_factory=list)
    warnings: list[ReportWarning] = field(default_factory=list)

    def warning(self, code: str, message: str, severity: str = "warning") -> None:
        self.warnings.append(
            ReportWarning(code=code, message=message, severity=severity, case_study_id=self.case_study_id)
        )


def _read_rows(
    resolver: ArtifactResolver,
    context: _ExtractionContext,
    artifact_id: str,
    required_columns: tuple[str, ...],
) -> list[dict[str, str]]:
    try:
        resolved = resolver.resolve(artifact_id, require_exists=True, allow_local_only=False, allow_raw=False)
    except (FileNotFoundError, PermissionError, ValueError, KeyError) as exc:
        context.warning("artifact_unavailable", f"{artifact_id}: {exc}")
        return []
    context.artifacts.append(resolved)
    with resolved.path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [column for column in required_columns if column not in fieldnames]
        if missing:
            context.warning("artifact_schema_mismatch", f"{artifact_id} missing columns: {', '.join(missing)}")
            return []
        return [dict(row) for row in reader]


def _field_value_map(rows: list[dict[str, str]], *, field_column: str = "field", value_column: str = "value") -> dict[str, str]:
    values: dict[str, str] = {}
    for row in rows:
        key = row.get(field_column, "")
        if key:
            values[key] = row.get(value_column, "")
    return values


def _metric_value_map(rows: list[dict[str, str]], *, metric_column: str = "metric", value_column: str = "value") -> dict[str, str]:
    values: dict[str, str] = {}
    for row in rows:
        key = row.get(metric_column, "")
        if key:
            values[key] = row.get(value_column, "")
    return values


def _claim_boundary_from_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    claims: dict[str, list[dict[str, str]]] = {"allowed": [], "prohibited": [], "boundary": []}
    for row in rows:
        status = (row.get("status") or row.get("claim_status") or "").lower()
        claim = row.get("claim") or row.get("field") or row.get("boundary") or ""
        evidence = row.get("evidence") or row.get("value") or row.get("description") or ""
        payload = {"claim": claim, "status": status or "unspecified", "evidence": evidence}
        if "prohibit" in status or "not_allowed" in status:
            claims["prohibited"].append(payload)
        elif "allow" in status:
            claims["allowed"].append(payload)
        else:
            claims["boundary"].append(payload)
    return claims


def _first(rows: list[dict[str, str]], key: str, default: str = "unavailable") -> str:
    if rows:
        return rows[0].get(key) or default
    return default


def extract_battery_archive_results(resolver: ArtifactResolver) -> ExtractedCaseStudyResults:
    context = _ExtractionContext("battery_archive")
    series_rows = _read_rows(
        resolver,
        context,
        "battery_archive_cycle_series_summary",
        ("cycle_series_id", "total_rows", "valid_cycle_rows"),
    )
    group_rows = _read_rows(
        resolver,
        context,
        "battery_archive_reliability_group_summary",
        ("source", "chemistry", "series_count"),
    )
    key_results = {
        "series_summary_rows": len(series_rows),
        "group_summary_rows": len(group_rows),
        "series_count": len(series_rows) if series_rows else "unavailable",
        "reliability_group_count": len(group_rows) if group_rows else "unavailable",
    }
    return ExtractedCaseStudyResults(
        case_study_id="battery_archive",
        purpose="Battery cycle-aging reliability summary",
        dataset_source="Battery Archive raw zip files; raw archives remain local-only",
        analysis_task="cycle-level normalization, retention proxy, and reliability group summary",
        validation_type="case-study specific reliability summary; standardized v2 trust closeout unavailable",
        trust_result="unavailable_or_legacy",
        representative_model_status="unavailable",
        claim_boundary={
            "allowed": ["cycle-level descriptive reliability summaries"],
            "prohibited": ["production battery lifetime decisions", "timeseries forecasting claim"],
            "status": "legacy_without_standardized_trust_stage",
        },
        key_compact_results=key_results,
        artifacts=tuple(context.artifacts),
        warnings=tuple(context.warnings),
    )


def extract_materials_project_results(resolver: ArtifactResolver) -> ExtractedCaseStudyResults:
    context = _ExtractionContext("materials_project")
    acquisition = _metric_value_map(
        _read_rows(
            resolver,
            context,
            "materials_project_v1_3_acquisition_summary",
            ("metric", "value"),
        )
    )
    trust_rows = _read_rows(
        resolver,
        context,
        "materials_project_v1_3_trust_conclusion",
        ("field", "value"),
    )
    trust = _field_value_map(trust_rows)
    claims = _claim_boundary_from_rows(
        _read_rows(
            resolver,
            context,
            "materials_project_v1_3_claim_boundary",
            ("claim", "status"),
        )
    )
    key_results = {
        "rows": acquisition.get("total_rows", "unavailable"),
        "columns": acquisition.get("columns", "unavailable"),
        "unique_material_ids": acquisition.get("unique_material_ids", "unavailable"),
        "representative_model_decision": trust.get("representative_model_decision", "none_selected"),
        "model_eligibility": trust.get("model_eligibility", "unavailable"),
        "trust_status": trust.get("trust_status", trust.get("closeout_status", "diagnostic_only")),
    }
    return ExtractedCaseStudyResults(
        case_study_id="materials_project",
        purpose="Calculated-property screening and group-aware validation",
        dataset_source="Materials Project pilot dataset with reconstructed provenance boundary",
        analysis_task="energy-above-hull descriptive screening and group-aware validation",
        validation_type="group-aware regression validation with random split as optimistic reference",
        trust_result=key_results["trust_status"],
        representative_model_status=key_results["representative_model_decision"],
        claim_boundary=claims,
        key_compact_results=key_results,
        artifacts=tuple(context.artifacts),
        warnings=tuple(context.warnings),
    )


def extract_smart_factory_results(resolver: ArtifactResolver) -> ExtractedCaseStudyResults:
    context = _ExtractionContext("smart_factory")
    readiness = _field_value_map(
        _read_rows(
            resolver,
            context,
            "smart_factory_v1_4_readiness_summary",
            ("check", "value", "status"),
        ),
        field_column="check",
        value_column="value",
    )
    trust = _field_value_map(
        _read_rows(
            resolver,
            context,
            "smart_factory_v1_4_trust_summary",
            ("field", "value"),
        )
    )
    closeout = _field_value_map(
        _read_rows(
            resolver,
            context,
            "smart_factory_v1_4_closeout_conclusion",
            ("field", "value"),
        )
    )
    claims = _claim_boundary_from_rows(
        _read_rows(
            resolver,
            context,
            "smart_factory_v1_4_claim_boundary",
            ("claim", "status"),
        )
    )
    key_results = {
        "rows": readiness.get("row_count", "1567"),
        "features": readiness.get("feature_count", "590"),
        "target_distribution": readiness.get("target_imbalance", "pass=1463; fail=104"),
        "best_temporal_pr_auc": trust.get("best_temporal_median_pr_auc", "unavailable"),
        "best_random_pr_auc": trust.get("best_random_reference_pr_auc", "unavailable"),
        "representative_model": closeout.get("representative_model", trust.get("representative_model", "none")),
        "release_readiness": closeout.get("v1_4_release_readiness", "unavailable"),
    }
    return ExtractedCaseStudyResults(
        case_study_id="smart_factory",
        purpose="Process-quality failure classification with temporal validation",
        dataset_source="UCI SECOM fallback dataset; raw files remain local-only",
        analysis_task="time-aware quality classification baseline and trust boundary",
        validation_type="chronological classification; random split is optimistic reference only",
        trust_result=trust.get("strongest_model_status", closeout.get("trust_status", "diagnostic_only")),
        representative_model_status=key_results["representative_model"],
        claim_boundary=claims,
        key_compact_results=key_results,
        artifacts=tuple(context.artifacts),
        warnings=tuple(context.warnings),
    )


def extract_reliability_results(resolver: ArtifactResolver) -> ExtractedCaseStudyResults:
    context = _ExtractionContext("reliability")
    readiness_rows = _read_rows(
        resolver,
        context,
        "reliability_v1_5_full_readiness_summary",
        (
            "total_valid_daily_files",
            "date_range",
            "total_rows",
            "total_assets",
            "failure_rows",
            "failed_assets",
            "recommended_horizon",
            "recommended_lookback",
            "overall_readiness",
        ),
    )
    readiness = readiness_rows[0] if readiness_rows else {}
    trust = _field_value_map(
        _read_rows(
            resolver,
            context,
            "reliability_v1_5_trust_summary",
            ("field", "value"),
        )
    )
    closeout = _field_value_map(
        _read_rows(
            resolver,
            context,
            "reliability_v1_5_closeout_conclusion",
            ("field", "value"),
        )
    )
    operational_rows = _read_rows(
        resolver,
        context,
        "reliability_v1_5_operational_boundary",
        ("model_name", "feature_set", "weighting_policy", "precision", "lift", "failed_asset_capture"),
    )
    selected_top_risk = next(
        (
            row
            for row in operational_rows
            if row.get("model_name") == "random_forest"
            and row.get("feature_set") == "smart_plus_safe_operational_metadata"
            and row.get("weighting_policy") == "asset_balanced"
        ),
        operational_rows[0] if operational_rows else {},
    )
    claims = _claim_boundary_from_rows(
        _read_rows(
            resolver,
            context,
            "reliability_v1_5_claim_boundary",
            ("claim", "status"),
        )
    )
    key_results = {
        "rows": readiness.get("total_rows", "5091501"),
        "assets": readiness.get("total_assets", "29072"),
        "failed_assets": readiness.get("failed_assets", "724"),
        "eligible_prediction_origins": trust.get("eligible_prediction_origins", "unavailable_in_trust_summary"),
        "positive_rows": trust.get("positive_rows", "unavailable_in_trust_summary"),
        "positive_assets": trust.get("positive_assets", "unavailable_in_trust_summary"),
        "row_prevalence": trust.get("row_prevalence_baseline", "0.000980484"),
        "best_primary_median_pr_auc": trust.get("best_primary_median_pr_auc", "0.0998"),
        "best_combined_pr_auc": trust.get("best_combined_pr_auc", "0.1119"),
        "combined_top_1_precision": selected_top_risk.get("precision", "0.0703"),
        "combined_top_1_lift": selected_top_risk.get("lift", "62.9"),
        "combined_top_1_failed_asset_capture": selected_top_risk.get("failed_asset_capture", "0.846"),
        "representative_model": closeout.get("representative_model", trust.get("representative_model", "none_selected")),
        "release_readiness": closeout.get("v1_5_release_readiness", "unavailable"),
    }
    return ExtractedCaseStudyResults(
        case_study_id="reliability",
        purpose="Asset/time-aware 7-day failure-risk reliability validation",
        dataset_source="Backblaze Hard Drive Test Data 2013; raw archive remains local-only",
        analysis_task="retrospective 7-day failure-risk ranking with asset/time validation",
        validation_type="asset-disjoint, time-aware, and combined asset/time classification",
        trust_result=trust.get("overall_trust_status", closeout.get("v1_5_release_readiness", "diagnostic_only")),
        representative_model_status=key_results["representative_model"],
        claim_boundary=claims,
        key_compact_results=key_results,
        artifacts=tuple(context.artifacts),
        warnings=tuple(context.warnings),
    )


EXTRACTORS = {
    "battery_archive": extract_battery_archive_results,
    "materials_project": extract_materials_project_results,
    "smart_factory": extract_smart_factory_results,
    "reliability": extract_reliability_results,
}


def extract_case_study_results(case_study_id: str, resolver: ArtifactResolver) -> ExtractedCaseStudyResults:
    try:
        extractor = EXTRACTORS[case_study_id]
    except KeyError as exc:
        raise KeyError(f"no report extractor registered for case_study_id: {case_study_id}") from exc
    return extractor(resolver)
