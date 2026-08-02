"""Serialization and Markdown rendering for NASA PCoE review evidence."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        record: dict[str, Any] = {}
        for key, value in row.items():
            if value is None or (isinstance(value, float) and not np.isfinite(value)):
                record[key] = None
            elif isinstance(value, (np.bool_, bool)):
                record[key] = bool(value)
            elif isinstance(value, (np.integer, int)):
                record[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                record[key] = float(value)
            else:
                record[key] = str(value)
        records.append(record)
    return records


def _markdown(summary: Mapping[str, Any], table: pd.DataFrame) -> str:
    lines = [
        "# NASA PCoE Battery Review Evidence",
        "",
        "## Result",
        "",
        f"- Status: `{summary['review_status']}`",
        f"- Preserved predictive evidence: `{summary['predictive_evidence_level']}`",
        f"- Battery packets: `{summary['packet_count']}`",
        f"- Priority packets (tiers 1-4): `{summary['priority_packet_count']}`",
        f"- Linked excluded operations: `{summary['linked_excluded_operation_count']}`",
        f"- Linked validation rows: `{summary['linked_validation_prediction_count']}`",
        f"- Retrieval receipt verified: `{summary['retrieval_receipt_verified']}`",
        "",
        "## Scientific boundary",
        "",
        str(summary["scientific_boundary"]),
        "",
        "## Battery packets",
        "",
    ]
    for _, row in table.iterrows():
        lines.extend(
            [
                f"### {int(row['review_order'])}. {row['battery_id']}",
                "",
                f"- Tier: `{int(row['review_tier'])}` / `{row['review_tier_label']}`",
                f"- Dimensions: `{row['review_dimensions'] or 'none'}`",
                f"- Action: `{row['recommended_action_class']}`",
                f"- Structural reasons: `{row['structural_review_reasons'] or 'none'}`",
                f"- Excluded operations: `{int(row['excluded_operation_count'])}`",
                f"- Excluded cycles: `{row['excluded_cycle_indices'] or 'none'}`",
                f"- Capacity issues: `{row['excluded_capacity_issue_counts'] or 'none'}`",
                f"- Source locations: `{row['excluded_source_locations'] or 'none'}`",
                f"- Source operation indices: `{row['excluded_source_operation_indices'] or 'none'}`",
                f"- Cycle gaps: `{int(row['cycle_gap_count'])}`",
                f"- Exact-horizon rows: `{int(row['prediction_count'])}`",
                f"- Persistence MAE: `{row['persistence_mae']}`",
                f"- Ridge MAE: `{row['ridge_mae']}`",
                f"- Highest persistence-error rows: `{row['top_persistence_error_rows'] or 'none'}`",
                f"- Highest Ridge-error rows: `{row['top_ridge_error_rows'] or 'none'}`",
                f"- Review checks: `{row['review_check_codes']}`",
                "- Boundary: no causal attribution, battery removal, or data repair is authorized.",
                "",
            ]
        )
    return "\n".join(lines)
