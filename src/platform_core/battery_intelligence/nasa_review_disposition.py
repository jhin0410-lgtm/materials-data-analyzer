"""Human-review disposition over manifest-bound NASA PCoE evidence packets.

This module never infers a scientific conclusion. It creates a reviewer-editable
worksheet and validates reviewer-supplied dispositions against the exact evidence
artifact from which the worksheet was derived.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .common import canonical_json, file_sha256

_REQUIRED_EVIDENCE_COLUMNS = {
    "review_order",
    "battery_id",
    "review_tier",
    "recommended_action_class",
    "review_check_codes",
    "predictive_evidence_level",
}
_IMMUTABLE_COLUMNS = (
    "source_evidence_sha256",
    "review_order",
    "battery_id",
    "review_tier",
    "recommended_action_class",
    "review_check_codes",
    "predictive_evidence_level",
)
_EDITABLE_COLUMNS = (
    "review_status",
    "conclusion_code",
    "reviewer",
    "reviewed_at_utc",
    "evidence_refs",
    "rationale",
    "follow_up_action",
)
_ALLOWED_STATUSES = {"pending", "completed", "follow_up_required"}
_ALLOWED_CONCLUSIONS = {
    "no_confirmed_issue",
    "source_quality_issue_confirmed",
    "trajectory_continuity_issue_confirmed",
    "evaluation_coverage_issue_confirmed",
    "model_or_protocol_mismatch_suspected",
    "inconclusive",
}
_EVIDENCE_REQUIRED_CONCLUSIONS = _ALLOWED_CONCLUSIONS - {
    "no_confirmed_issue",
    "inconclusive",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _load_bound_evidence(analysis_root: Path) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    evidence_path = analysis_root / "tables" / "nasa_protocol_review_evidence.csv"
    report_path = analysis_root / "reports" / "nasa_protocol_review_evidence.json"
    manifest_path = analysis_root / "run_manifest.json"
    missing = [
        str(path.relative_to(analysis_root))
        for path in (evidence_path, report_path, manifest_path)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "NASA review disposition missing required artifacts: " + ", ".join(missing)
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksums = manifest.get("artifact_checksums", {})
    if not isinstance(checksums, dict):
        raise ValueError("run manifest artifact_checksums must be an object")
    for relative, path in (
        ("tables/nasa_protocol_review_evidence.csv", evidence_path),
        ("reports/nasa_protocol_review_evidence.json", report_path),
    ):
        expected = checksums.get(relative)
        if not isinstance(expected, str) or not expected:
            raise ValueError(f"run manifest lacks checksum for {relative}")
        observed = file_sha256(path)
        if observed != expected:
            raise ValueError(f"artifact checksum mismatch for {relative}")

    frame = pd.read_csv(evidence_path, keep_default_na=False)
    missing_columns = sorted(_REQUIRED_EVIDENCE_COLUMNS - set(frame.columns))
    if missing_columns:
        raise ValueError(
            "NASA review evidence missing required columns: "
            + ", ".join(missing_columns)
        )
    if frame.empty:
        raise ValueError("NASA review evidence must contain at least one battery")
    frame["battery_id"] = frame["battery_id"].map(_text)
    if (frame["battery_id"] == "").any() or frame["battery_id"].duplicated().any():
        raise ValueError("NASA review evidence battery identities must be nonblank and unique")
    frame["review_order"] = pd.to_numeric(frame["review_order"], errors="raise").astype(int)
    if frame["review_order"].duplicated().any():
        raise ValueError("NASA review evidence review_order must be unique")
    frame = frame.sort_values("review_order", kind="mergesort").reset_index(drop=True)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        raise ValueError("NASA review evidence report summary must be an object")
    if int(summary.get("packet_count", -1)) != len(frame):
        raise ValueError("NASA review evidence packet count does not match CSV rows")
    return frame, file_sha256(evidence_path), manifest


def initialize_nasa_review_disposition(
    *, analysis_output: str | Path, overwrite: bool = False
) -> dict[str, Any]:
    """Create a reviewer-editable worksheet bound to the current evidence CSV."""
    root = Path(analysis_output)
    evidence, evidence_sha256, _ = _load_bound_evidence(root)
    output = root / "tables" / "nasa_protocol_review_disposition.csv"
    if output.exists() and not overwrite:
        raise FileExistsError(
            "review disposition worksheet already exists; use --overwrite only after "
            "preserving any manual review work"
        )

    worksheet = pd.DataFrame(
        {
            "source_evidence_sha256": evidence_sha256,
            "review_order": evidence["review_order"].astype(int),
            "battery_id": evidence["battery_id"].astype(str),
            "review_tier": pd.to_numeric(evidence["review_tier"], errors="raise").astype(int),
            "recommended_action_class": evidence["recommended_action_class"].astype(str),
            "review_check_codes": evidence["review_check_codes"].astype(str),
            "predictive_evidence_level": evidence["predictive_evidence_level"].astype(str),
            "review_status": "pending",
            "conclusion_code": "",
            "reviewer": "",
            "reviewed_at_utc": "",
            "evidence_refs": "",
            "rationale": "",
            "follow_up_action": "",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    worksheet.to_csv(output, index=False, lineterminator="\n")
    return {
        "summary": {
            "worksheet_status": "initialized",
            "battery_count": int(len(worksheet)),
            "priority_battery_count": int((worksheet["review_tier"] <= 4).sum()),
            "source_evidence_sha256": evidence_sha256,
            "scientific_claim_changed": False,
        },
        "outputs": {"review_disposition_worksheet": str(output)},
    }


def _validate_disposition(
    worksheet: pd.DataFrame, evidence: pd.DataFrame, evidence_sha256: str
) -> pd.DataFrame:
    required = set(_IMMUTABLE_COLUMNS) | set(_EDITABLE_COLUMNS)
    missing = sorted(required - set(worksheet.columns))
    if missing:
        raise ValueError("review disposition missing required columns: " + ", ".join(missing))
    if len(worksheet) != len(evidence):
        raise ValueError("review disposition row count does not match evidence packets")

    normalized = worksheet.copy()
    for column in required:
        normalized[column] = normalized[column].map(_text)
    normalized["review_order"] = pd.to_numeric(
        normalized["review_order"], errors="raise"
    ).astype(int)
    normalized["review_tier"] = pd.to_numeric(
        normalized["review_tier"], errors="raise"
    ).astype(int)
    normalized = normalized.sort_values("review_order", kind="mergesort").reset_index(drop=True)

    expected = pd.DataFrame(
        {
            "source_evidence_sha256": evidence_sha256,
            "review_order": evidence["review_order"].astype(int),
            "battery_id": evidence["battery_id"].astype(str),
            "review_tier": pd.to_numeric(evidence["review_tier"], errors="raise").astype(int),
            "recommended_action_class": evidence["recommended_action_class"].astype(str),
            "review_check_codes": evidence["review_check_codes"].astype(str),
            "predictive_evidence_level": evidence["predictive_evidence_level"].astype(str),
        }
    ).sort_values("review_order", kind="mergesort").reset_index(drop=True)
    for column in _IMMUTABLE_COLUMNS:
        if not normalized[column].equals(expected[column]):
            raise ValueError(f"review disposition immutable column changed: {column}")

    invalid_status = sorted(set(normalized["review_status"]) - _ALLOWED_STATUSES)
    if invalid_status:
        raise ValueError("invalid review_status values: " + ", ".join(invalid_status))

    for _, row in normalized.iterrows():
        battery_id = row["battery_id"]
        status = row["review_status"]
        conclusion = row["conclusion_code"]
        if status == "pending":
            if any(row[column] for column in _EDITABLE_COLUMNS if column != "review_status"):
                raise ValueError(f"{battery_id}: pending rows must not contain review conclusions")
            continue
        if conclusion not in _ALLOWED_CONCLUSIONS:
            raise ValueError(f"{battery_id}: completed review requires an allowed conclusion_code")
        for column in ("reviewer", "reviewed_at_utc", "rationale"):
            if not row[column]:
                raise ValueError(f"{battery_id}: {column} is required for reviewed rows")
        timestamp = pd.to_datetime(row["reviewed_at_utc"], utc=True, errors="coerce")
        if pd.isna(timestamp):
            raise ValueError(f"{battery_id}: reviewed_at_utc must be a valid timestamp")
        if conclusion in _EVIDENCE_REQUIRED_CONCLUSIONS and not row["evidence_refs"]:
            raise ValueError(f"{battery_id}: evidence_refs required for {conclusion}")
        if status == "follow_up_required" and not row["follow_up_action"]:
            raise ValueError(f"{battery_id}: follow_up_action required")
    return normalized


def _markdown(summary: dict[str, Any], table: pd.DataFrame) -> str:
    lines = [
        "# NASA PCoE Review Disposition",
        "",
        f"- Disposition status: **{summary['disposition_status']}**",
        f"- Reviewed batteries: **{summary['reviewed_battery_count']} / {summary['battery_count']}**",
        f"- Pending priority batteries: **{summary['pending_priority_battery_count']}**",
        f"- Predictive evidence level: **{summary['predictive_evidence_level']}**",
        "",
        "## Conclusion counts",
        "",
    ]
    for name, count in summary["conclusion_code_counts"].items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Priority review state", ""])
    priority = table[table["review_tier"] <= 4]
    lines.append("| Battery | Tier | Status | Conclusion | Follow-up |")
    lines.append("|---|---:|---|---|---|")
    for _, row in priority.iterrows():
        lines.append(
            f"| {row['battery_id']} | {row['review_tier']} | {row['review_status']} | "
            f"{row['conclusion_code'] or ''} | {row['follow_up_action'] or ''} |"
        )
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "These dispositions are reviewer records over diagnostic evidence packets. "
            "They do not refit a model, remove batteries, repair targets, establish "
            "causality, or upgrade the declared predictive evidence level.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_nasa_review_disposition(
    *, analysis_output: str | Path, disposition_input: str | Path | None = None
) -> dict[str, Any]:
    """Validate reviewer input and persist an immutable disposition snapshot."""
    root = Path(analysis_output)
    evidence, evidence_sha256, manifest = _load_bound_evidence(root)
    input_path = (
        Path(disposition_input)
        if disposition_input is not None
        else root / "tables" / "nasa_protocol_review_disposition.csv"
    )
    if not input_path.is_file():
        raise FileNotFoundError(f"review disposition worksheet not found: {input_path}")
    worksheet = pd.read_csv(input_path, keep_default_na=False)
    normalized = _validate_disposition(worksheet, evidence, evidence_sha256)

    reviewed = normalized[normalized["review_status"] != "pending"]
    pending_priority = normalized[
        (normalized["review_tier"] <= 4) & (normalized["review_status"] == "pending")
    ]["battery_id"].tolist()
    conclusion_counts = Counter(
        value for value in reviewed["conclusion_code"].tolist() if value
    )
    evidence_levels = sorted(set(normalized["predictive_evidence_level"]))
    if len(evidence_levels) != 1:
        raise ValueError("review disposition contains inconsistent predictive evidence levels")
    summary = {
        "schema_version": "1.0",
        "disposition_status": "complete" if len(reviewed) == len(normalized) else "in_progress",
        "battery_count": int(len(normalized)),
        "reviewed_battery_count": int(len(reviewed)),
        "pending_battery_count": int(len(normalized) - len(reviewed)),
        "priority_battery_count": int((normalized["review_tier"] <= 4).sum()),
        "pending_priority_battery_count": int(len(pending_priority)),
        "pending_priority_battery_ids": pending_priority,
        "review_status_counts": dict(sorted(Counter(normalized["review_status"]).items())),
        "conclusion_code_counts": dict(sorted(conclusion_counts.items())),
        "source_evidence_sha256": evidence_sha256,
        "predictive_evidence_level": evidence_levels[0],
        "scientific_claim_changed": False,
        "battery_removal_authorized": False,
        "data_repair_authorized": False,
        "causal_attribution_established": False,
        "scientific_boundary": (
            "Reviewer dispositions preserve the source evidence and predictive closeout. "
            "They do not establish causality, authorize filtering or repair, or replace "
            "battery-disjoint validation."
        ),
    }

    final_csv = root / "tables" / "nasa_protocol_review_disposition_final.csv"
    report_json = root / "reports" / "nasa_protocol_review_disposition.json"
    report_md = root / "reports" / "nasa_protocol_review_disposition.md"
    normalized.to_csv(final_csv, index=False, lineterminator="\n")
    report_json.write_text(
        canonical_json({"summary": summary, "batteries": normalized.to_dict(orient="records")}),
        encoding="utf-8",
    )
    report_md.write_text(_markdown(summary, normalized), encoding="utf-8")

    relative_paths = [path.relative_to(root).as_posix() for path in (final_csv, report_json, report_md)]
    manifest["nasa_protocol_review_disposition"] = summary
    manifest["artifact_paths"] = sorted(
        set(manifest.get("artifact_paths", [])) | set(relative_paths)
    )
    checksums = dict(manifest.get("artifact_checksums", {}))
    for relative, path in zip(relative_paths, (final_csv, report_json, report_md), strict=True):
        checksums[relative] = file_sha256(path)
    manifest["artifact_checksums"] = checksums
    (root / "run_manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return {
        "summary": summary,
        "outputs": {
            "review_disposition_final": str(final_csv),
            "review_disposition_report": str(report_json),
            "review_disposition_markdown": str(report_md),
        },
    }


__all__ = [
    "finalize_nasa_review_disposition",
    "initialize_nasa_review_disposition",
]
