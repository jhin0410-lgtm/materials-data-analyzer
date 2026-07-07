"""Tests for Battery Archive connector skeleton."""

from __future__ import annotations

from connectors.battery_archive_connector import BatteryArchiveConnector


def test_battery_archive_missing_endpoint_returns_warning(monkeypatch) -> None:
    monkeypatch.delenv("BATTERY_ARCHIVE_ENDPOINT", raising=False)
    monkeypatch.delenv("BATTERY_ARCHIVE_BASE_URL", raising=False)

    result = BatteryArchiveConnector().probe(limit=5)

    assert result.source_name == "battery_archive"
    assert result.raw_paths == []
    assert result.processed_paths == []
    assert "endpoint is not configured" in result.warnings[0]
