from __future__ import annotations

import pytest

from platform_core.battery_intelligence.nasa_review_evidence import (
    _bind_import_content,
    build_nasa_review_evidence_table,
)
from nasa_review_evidence_queue_fixture import _queue
from nasa_review_evidence_source_fixtures import (
    _excluded,
    _inventory,
    _predictions,
    _protocol,
)


def test_review_evidence_links_source_and_model_rows_without_filtering() -> None:
    result = build_nasa_review_evidence_table(
        review_queue=_queue(),
        excluded_operations=_excluded(),
        validation_predictions=_predictions(),
        predictive_evidence_level="Unsupported",
    )
    table = result["table"].set_index("battery_id")
    summary = result["summary"]

    assert len(table) == 2
    assert summary["packet_count"] == 2
    assert summary["priority_battery_ids"] == ["A", "B"]
    assert summary["linked_excluded_operation_count"] == 1
    assert summary["linked_validation_prediction_count"] == 2
    assert table.loc["A", "excluded_cycle_indices"] == "3"
    assert table.loc["A", "excluded_capacity_issue_counts"] == "nonpositive:1"
    assert "row=3" in table.loc["A", "top_ridge_error_rows"]
    assert table.loc["A", "recommended_action_class"] == (
        "source_quality_and_error_influence_review"
    )
    assert table.loc["B", "recommended_action_class"] == (
        "evaluation_coverage_review"
    )
    assert bool(table.loc["A", "battery_removal_authorized"]) is False
    assert bool(table.loc["A", "data_repair_authorized"]) is False
    assert summary["predictive_evidence_level"] == "Unsupported"


def test_review_evidence_rejects_prediction_count_mismatch() -> None:
    queue = _queue()
    queue.loc[queue["battery_id"] == "A", "prediction_count"] = 3
    with pytest.raises(ValueError, match="prediction counts"):
        build_nasa_review_evidence_table(
            review_queue=queue,
            excluded_operations=_excluded(),
            validation_predictions=_predictions(),
            predictive_evidence_level="Unsupported",
        )


def test_review_evidence_rejects_import_content_mismatch() -> None:
    protocol = _protocol()
    protocol.loc[protocol["battery_id"] == "A", "ambient_temperature_median_c"] = 40.0
    with pytest.raises(ValueError, match="content mismatch"):
        _bind_import_content(_queue(), protocol, _inventory())
