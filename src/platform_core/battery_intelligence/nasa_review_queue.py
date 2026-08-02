"""Focused review queue for an existing NASA PCoE protocol audit.

This module intersects explicit source-quality, trajectory-continuity,
evaluation-coverage, and model-error-influence diagnostics. It does not infer a
causal failure mechanism, remove batteries, alter targets, refit models, or
replace the declared battery-disjoint validation result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256

_REQUIRED_PROFILE_COLUMNS = {
    "battery_id",
    "is_evaluated",
    "prediction_count",
    "reference_start_context_flag",
    "reference_context_only",
    "source_quality_issue",
    "trajectory_continuity_issue",
    "evaluation_coverage_issue",
    "structural_or_coverage_issue",
    "disproportionate_error_influence",
    "context_reasons",
    "structural_review_reasons",
    "influence_review_reasons",
    "persistence_mae",
    "ridge_mae",
    "ridge_minus_persistence_mae",
}

_SUMMARY_COUNT_COLUMNS = {
    "battery_count": None,
    "evaluated_battery_count": "is_evaluated",
    "unevaluated_battery_count": "evaluation_coverage_issue",
    "reference_start_context_battery_count": "reference_start_context_flag",
    "reference_context_only_battery_count": "reference_context_only",
    "source_quality_issue_battery_count": "source_quality_issue",
    "trajectory_continuity_issue_battery_count": "trajectory_continuity_issue",
    "structural_or_coverage_issue_battery_count": "structural_or_coverage_issue",
    "disproportionate_error_influence_battery_count": (
        "disproportionate_error_influence"
    ),
}

_REVIEW_TIER_LABELS = {
    1: "evaluation_coverage",
    2: "source_quality_plus_error_influence",
    3: "trajectory_continuity_plus_error_influence",
    4: "error_influence_without_structural_or_coverage_flag",
    5: "source_quality_without_disproportionate_error_influence",
    6: "trajectory_continuity_without_disproportionate_error_influence",
    7: "rated_reference_context_only",
    8: "no_current_review_flag",
}

_SOURCE_ARTIFACT_PATHS = {
    "tables/nasa_protocol_battery_profile.csv": "battery_profile",
    "reports/nasa_protocol_audit.json": "protocol_audit",
}

_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}


def _require_columns(frame: pd.DataFrame, required: set[str], *, context: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")


def _normalized_ids(frame: pd.DataFrame, *, context: str) -> pd.Series:
    if frame["battery_id"].isna().any():
        raise ValueError(f"{context} battery_id may not be missing")
    values = frame["battery_id"].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"{context} battery_id may not be blank")
    if values.duplicated().any():
        duplicates = sorted(values[values.duplicated(keep=False)].unique())
        raise ValueError(
            f"{context} contains duplicate battery_id values: {', '.join(duplicates)}"
        )
    return values


def _as_bool(series: pd.Series, *, context: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{context} contains missing boolean values")
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.casefold()
    allowed = _TRUE_TOKENS | _FALSE_TOKENS
    invalid = ~normalized.isin(allowed)
    if invalid.any():
        values = sorted({repr(value) for value in series.loc[invalid].tolist()})
        raise ValueError(
            f"{context} contains invalid boolean values: {', '.join(values)}"
        )
    return normalized.isin(_TRUE_TOKENS)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _validated_profile(profile: pd.DataFrame) -> pd.DataFrame:
    context = "NASA protocol battery profile"
    _require_columns(profile, _REQUIRED_PROFILE_COLUMNS, context=context)
    result = profile.copy()
    result["battery_id"] = _normalized_ids(result, context=context)
    boolean_columns = {
        column
        for column in _REQUIRED_PROFILE_COLUMNS
        if column.endswith("_flag")
        or column.endswith("_only")
        or column.endswith("_issue")
        or column in {"is_evaluated", "disproportionate_error_influence"}
    }
    for column in boolean_columns:
        result[column] = _as_bool(
            result[column],
            context=f"{context}.{column}",
        )
    result["prediction_count"] = (
        _numeric(result["prediction_count"]).fillna(0).astype(int)
    )
    if (result["prediction_count"] < 0).any():
        raise ValueError(
            "NASA protocol battery profile prediction_count may not be negative"
        )
    if (
        result["is_evaluated"]
        != ~result["evaluation_coverage_issue"]
    ).any():
        raise ValueError(
            "NASA protocol battery profile evaluation flags are internally inconsistent"
        )
    if (
        result["is_evaluated"]
        != (result["prediction_count"] > 0)
    ).any():
        raise ValueError(
            "NASA protocol battery profile evaluation status conflicts with prediction_count"
        )
    expected_structural = (
        result["source_quality_issue"]
        | result["trajectory_continuity_issue"]
        | result["evaluation_coverage_issue"]
    )
    if (result["structural_or_coverage_issue"] != expected_structural).any():
        raise ValueError(
            "NASA protocol battery profile structural_or_coverage_issue is inconsistent"
        )
    for column in ("persistence_mae", "ridge_mae", "ridge_minus_persistence_mae"):
        result[column] = _numeric(result[column])
    evaluated = result["is_evaluated"]
    if result.loc[evaluated, ["persistence_mae", "ridge_mae"]].isna().any().any():
        raise ValueError(
            "evaluated NASA protocol batteries require persistence_mae and ridge_mae"
        )
    if not np.isfinite(
        result.loc[evaluated, ["persistence_mae", "ridge_mae"]].to_numpy(
            dtype=float
        )
    ).all():
        raise ValueError("evaluated NASA protocol battery MAE values must be finite")
    expected_difference = result["ridge_mae"] - result["persistence_mae"]
    difference_mismatch = evaluated & ~np.isclose(
        result["ridge_minus_persistence_mae"].to_numpy(dtype=float),
        expected_difference.to_numpy(dtype=float),
        rtol=1e-9,
        atol=1e-9,
        equal_nan=True,
    )
    if difference_mismatch.any():
        raise ValueError(
            "NASA protocol battery profile ridge-minus-persistence MAE is inconsistent"
        )
    return result


def _validate_summary(profile: pd.DataFrame, summary: Mapping[str, Any]) -> None:
    for field, column in _SUMMARY_COUNT_COLUMNS.items():
        if field not in summary:
            raise ValueError(f"NASA protocol audit summary missing required field: {field}")
        expected = len(profile) if column is None else int(profile[column].sum())
        observed = int(summary[field])
        if observed != expected:
            raise ValueError(
                "NASA protocol audit summary/profile count mismatch for "
                f"{field}: summary={observed}, profile={expected}"
            )


def _validate_source_binding(
    *,
    output: Path,
    profile_path: Path,
    protocol_audit_path: Path,
    protocol_summary: Mapping[str, Any],
) -> dict[str, str]:
    manifest_path = output / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "NASA focused review queue requires run_manifest.json to bind source "
            "artifacts to one audited run"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_summary = manifest.get("nasa_protocol_aware_posthoc_audit")
    if not isinstance(manifest_summary, Mapping):
        raise ValueError(
            "run_manifest.json is missing nasa_protocol_aware_posthoc_audit"
        )
    if dict(manifest_summary) != dict(protocol_summary):
        raise ValueError(
            "run_manifest.json protocol audit summary does not match "
            "reports/nasa_protocol_audit.json"
        )
    checksums = manifest.get("artifact_checksums")
    if not isinstance(checksums, Mapping):
        raise ValueError("run_manifest.json is missing artifact_checksums")
    paths = {
        "tables/nasa_protocol_battery_profile.csv": profile_path,
        "reports/nasa_protocol_audit.json": protocol_audit_path,
    }
    verified: dict[str, str] = {}
    for relative_path, path in paths.items():
        expected = checksums.get(relative_path)
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError(
                "run_manifest.json is missing source artifact checksum: "
                f"{relative_path}"
            )
        observed = file_sha256(path)
        if observed.lower() != expected.strip().lower():
            raise ValueError(
                "NASA focused review queue source artifact checksum mismatch: "
                f"{relative_path}"
            )
        verified[relative_path] = observed
    return verified


def _review_dimensions(row: pd.Series) -> str:
    pairs = (
        ("source_quality_issue", "source_quality"),
        ("trajectory_continuity_issue", "trajectory_continuity"),
        ("evaluation_coverage_issue", "evaluation_coverage"),
        ("disproportionate_error_influence", "error_influence"),
        ("reference_start_context_flag", "rated_reference_context"),
    )
    return ";".join(label for column, label in pairs if bool(row[column]))


def _review_tier(row: pd.Series) -> int:
    if bool(row["evaluation_coverage_issue"]):
        return 1
    if bool(row["source_quality_issue"]) and bool(
        row["disproportionate_error_influence"]
    ):
        return 2
    if bool(row["trajectory_continuity_issue"]) and bool(
        row["disproportionate_error_influence"]
    ):
        return 3
    if bool(row["disproportionate_error_influence"]):
        return 4
    if bool(row["source_quality_issue"]):
        return 5
    if bool(row["trajectory_continuity_issue"]):
        return 6
    if bool(row["reference_context_only"]):
        return 7
    return 8


def _error_pattern(row: pd.Series) -> str:
    if not bool(row["is_evaluated"]):
        return "unevaluated"
    difference = float(row["ridge_minus_persistence_mae"])
    if difference < 0:
        return "ridge_better_for_this_battery"
    if difference > 0:
        return "persistence_better_for_this_battery"
    return "equal_battery_mae"


def _id_list(frame: pd.DataFrame, mask: pd.Series) -> list[str]:
    return sorted(frame.loc[mask, "battery_id"].astype(str).tolist())


def build_nasa_focused_review_queue(
    *,
    battery_profile: pd.DataFrame,
    protocol_audit_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an operational review queue from an existing protocol audit.

    The queue orders review work but does not assign causal mechanisms or alter
    the declared validation evidence.
    """
    profile = _validated_profile(battery_profile)
    _validate_summary(profile, protocol_audit_summary)

    queue = profile.copy()
    queue["review_dimensions"] = queue.apply(_review_dimensions, axis=1)
    queue["review_tier"] = queue.apply(_review_tier, axis=1).astype(int)
    queue["review_tier_label"] = queue["review_tier"].map(_REVIEW_TIER_LABELS)
    queue["error_pattern"] = queue.apply(_error_pattern, axis=1)
    queue["maximum_model_mae"] = queue[["persistence_mae", "ridge_mae"]].max(
        axis=1, skipna=True
    )
    queue["causal_attribution_established"] = False
    queue["battery_removal_authorized"] = False
    queue["interpretation_boundary"] = (
        "Operational review ordering only. Intersections identify observed audit "
        "dimensions, not causal degradation mechanisms, and do not authorize "
        "battery deletion, cohort reassignment, target repair, or replacement of "
        "the declared battery-disjoint validation result."
    )
    queue = queue.sort_values(
        ["review_tier", "maximum_model_mae", "battery_id"],
        ascending=[True, False, True],
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    queue["review_order"] = np.arange(1, len(queue) + 1)

    influence = queue["disproportionate_error_influence"]
    structural = queue["structural_or_coverage_issue"]
    source = queue["source_quality_issue"]
    continuity = queue["trajectory_continuity_issue"]
    coverage = queue["evaluation_coverage_issue"]

    tier_counts = {
        str(tier): int((queue["review_tier"] == tier).sum())
        for tier in sorted(_REVIEW_TIER_LABELS)
    }
    summary = {
        "schema_version": "1.0",
        "review_status": "Diagnostic",
        "battery_count": int(len(queue)),
        "evaluated_battery_count": int(queue["is_evaluated"].sum()),
        "unevaluated_battery_count": int(coverage.sum()),
        "disproportionate_error_influence_battery_count": int(influence.sum()),
        "influence_with_source_quality_count": int((influence & source).sum()),
        "influence_with_trajectory_continuity_count": int(
            (influence & continuity).sum()
        ),
        "influence_with_structural_or_coverage_count": int(
            (influence & structural).sum()
        ),
        "influence_without_structural_or_coverage_count": int(
            (influence & ~structural).sum()
        ),
        "structural_or_coverage_without_influence_count": int(
            (structural & ~influence).sum()
        ),
        "review_tier_counts": tier_counts,
        "unevaluated_battery_ids": _id_list(queue, coverage),
        "source_quality_plus_influence_battery_ids": _id_list(
            queue, source & influence
        ),
        "trajectory_continuity_plus_influence_battery_ids": _id_list(
            queue, continuity & influence
        ),
        "influence_without_structural_or_coverage_battery_ids": _id_list(
            queue, influence & ~structural
        ),
        "predictive_evidence_level": str(
            protocol_audit_summary.get("predictive_evidence_level", "Inconclusive")
        ),
        "causal_attribution_established": False,
        "battery_removal_authorized": False,
        "scientific_boundary": (
            "The queue is a deterministic review order derived from existing "
            "post-hoc diagnostics. Co-occurrence of source-quality, continuity, "
            "coverage, and error-influence flags does not establish causality. No "
            "battery, row, target, feature, or prediction is removed or recomputed."
        ),
    }
    return {"review_queue": queue, "summary": summary}


def _markdown(summary: Mapping[str, Any]) -> str:
    def render_ids(field: str) -> str:
        values = list(summary[field])
        return ", ".join(values) if values else "none"

    return "\n".join(
        [
            "# NASA PCoE Focused Review Queue",
            "",
            "## Result",
            "",
            f"- Status: `{summary['review_status']}`",
            f"- Preserved predictive evidence: `{summary['predictive_evidence_level']}`",
            f"- Batteries: `{summary['battery_count']}`",
            f"- Unevaluated batteries: `{summary['unevaluated_battery_count']}`",
            f"- Disproportionate-error batteries: `{summary['disproportionate_error_influence_battery_count']}`",
            f"- Error influence with source-quality flags: `{summary['influence_with_source_quality_count']}`",
            f"- Error influence with trajectory-continuity flags: `{summary['influence_with_trajectory_continuity_count']}`",
            f"- Error influence without structural/coverage flags: `{summary['influence_without_structural_or_coverage_count']}`",
            f"- Structural/coverage flags without disproportionate influence: `{summary['structural_or_coverage_without_influence_count']}`",
            "",
            "## Highest-priority identities",
            "",
            f"- Unevaluated: {render_ids('unevaluated_battery_ids')}",
            "- Source quality + error influence: "
            + render_ids("source_quality_plus_influence_battery_ids"),
            "- Trajectory continuity + error influence: "
            + render_ids("trajectory_continuity_plus_influence_battery_ids"),
            "- Error influence without structural/coverage flag: "
            + render_ids(
                "influence_without_structural_or_coverage_battery_ids"
            ),
            "",
            "## Scientific boundary",
            "",
            str(summary["scientific_boundary"]),
            "",
        ]
    )


def audit_nasa_focused_review_queue(
    *,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Persist a focused review queue from one manifest-bound protocol audit."""
    output = Path(analysis_output)
    tables = output / "tables"
    reports = output / "reports"
    profile_path = tables / "nasa_protocol_battery_profile.csv"
    protocol_audit_path = reports / "nasa_protocol_audit.json"
    missing = [
        name
        for name, path in {
            "battery_profile": profile_path,
            "protocol_audit": protocol_audit_path,
        }.items()
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "NASA focused review queue missing required artifacts: "
            + ", ".join(missing)
        )

    protocol_summary = json.loads(protocol_audit_path.read_text(encoding="utf-8"))
    verified_source_checksums = _validate_source_binding(
        output=output,
        profile_path=profile_path,
        protocol_audit_path=protocol_audit_path,
        protocol_summary=protocol_summary,
    )
    result = build_nasa_focused_review_queue(
        battery_profile=pd.read_csv(profile_path),
        protocol_audit_summary=protocol_summary,
    )
    result["summary"]["source_run_manifest"] = "run_manifest.json"
    result["summary"]["source_artifact_checksums"] = verified_source_checksums

    queue_path = tables / "nasa_protocol_review_queue.csv"
    report_path = reports / "nasa_protocol_review_queue.json"
    markdown_path = reports / "nasa_protocol_review_queue.md"
    result["review_queue"].to_csv(queue_path, index=False, lineterminator="\n")
    report_path.write_text(canonical_json(result["summary"]), encoding="utf-8")
    markdown_path.write_text(_markdown(result["summary"]), encoding="utf-8")

    manifest_path = output / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["nasa_focused_review_queue"] = result["summary"]
    paths = [queue_path, report_path, markdown_path]
    relative = [path.relative_to(output).as_posix() for path in paths]
    manifest["artifact_paths"] = sorted(
        set(manifest.get("artifact_paths", [])) | set(relative)
    )
    checksums = dict(manifest.get("artifact_checksums", {}))
    for path, name in zip(paths, relative, strict=True):
        checksums[name] = file_sha256(path)
    manifest["artifact_checksums"] = checksums
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    return {
        "summary": result["summary"],
        "outputs": {
            "review_queue": str(queue_path),
            "review_report": str(report_path),
            "review_markdown": str(markdown_path),
        },
    }
