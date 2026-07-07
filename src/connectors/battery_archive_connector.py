"""Battery Archive generic REST connector skeleton."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from connectors.base import BaseConnector, IngestionResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "battery_archive"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "battery_archive_records.csv"


class BatteryArchiveConnector(BaseConnector):
    """Generic skeleton for a future Battery Archive API endpoint."""

    source_name = "battery_archive"

    def __init__(self, base_url: str | None = None, endpoint: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("BATTERY_ARCHIVE_BASE_URL") or "").rstrip("/")
        self.api_key = os.getenv("BATTERY_ARCHIVE_API_KEY")
        self.endpoint = endpoint or os.getenv("BATTERY_ARCHIVE_ENDPOINT")

    def get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET JSON from a configured Battery Archive endpoint."""
        if not self.base_url:
            raise RuntimeError(
                "BATTERY_ARCHIVE_BASE_URL is not configured. Set it in the "
                "environment when an endpoint is available."
            )
        try:
            import requests
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The requests package is required for Battery Archive ingestion.\n"
                "Install it with: pip install requests"
            ) from exc

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Probe Battery Archive if endpoint details are configured."""
        del full
        if not self.endpoint:
            return IngestionResult(
                source_name=self.source_name,
                warnings=[
                    "Battery Archive endpoint is not configured yet. Set "
                    "BATTERY_ARCHIVE_ENDPOINT and BATTERY_ARCHIVE_BASE_URL when "
                    "API documentation is available."
                ],
            )

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        response_json = self.get_json(self.endpoint, params={"limit": limit})
        raw_path = RAW_DIR / "battery_archive_probe_raw.json"
        raw_path.write_text(json.dumps(response_json, indent=2), encoding="utf-8")

        return IngestionResult(
            source_name=self.source_name,
            raw_paths=[raw_path],
            processed_paths=[],
            warnings=[
                "Raw JSON was saved. Processed CSV conversion is pending until "
                "the Battery Archive response schema is finalized."
            ],
        )
