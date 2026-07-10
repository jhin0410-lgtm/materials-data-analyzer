"""Battery Archive connector and raw zip inventory helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
import zipfile

import pandas as pd

from connectors.base import BaseConnector, IngestionResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "battery_archive"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "battery_archive_records.csv"
BATTERY_ARCHIVE_INVENTORY_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "file_type",
    "uncompressed_size_bytes",
    "compressed_size_bytes",
    "crc32",
]


def _list_zip_paths(raw_dir: str | Path) -> list[Path]:
    """Return sorted Battery Archive zip paths from a local raw directory."""
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Battery Archive raw directory was not found: {raw_path}"
        )
    if not raw_path.is_dir():
        raise ValueError(f"Battery Archive raw path is not a directory: {raw_path}")

    zip_paths = sorted(raw_path.glob("*.zip"), key=lambda path: path.name.casefold())
    if not zip_paths:
        raise FileNotFoundError(
            f"No Battery Archive zip files were found in raw directory: {raw_path}"
        )
    return zip_paths


def _is_cycle_data_entry(zip_info: zipfile.ZipInfo) -> bool:
    """Return whether a zip entry is a Battery Archive cycle_data CSV file."""
    if zip_info.is_dir():
        return False

    internal_path = zip_info.filename.replace("\\", "/")
    path_parts = [part for part in internal_path.split("/") if part]
    if not path_parts:
        return False
    if "__MACOSX" in path_parts:
        return False

    file_name = path_parts[-1]
    if file_name.startswith(".") or file_name.startswith("._"):
        return False

    return file_name.casefold().endswith("_cycle_data.csv")


def discover_cycle_files(raw_dir: str | Path) -> list[dict[str, object]]:
    """Discover Battery Archive cycle_data CSV entries without extracting zips."""
    records: list[dict[str, object]] = []
    for zip_path in _list_zip_paths(raw_dir):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for zip_info in archive.infolist():
                    if not _is_cycle_data_entry(zip_info):
                        continue
                    internal_csv_path = zip_info.filename.replace("\\", "/")
                    records.append(
                        {
                            "zip_file": zip_path.name,
                            "internal_csv_path": internal_csv_path,
                            "file_name": PurePosixPath(internal_csv_path).name,
                            "file_type": "cycle_data",
                            "uncompressed_size_bytes": int(zip_info.file_size),
                            "compressed_size_bytes": int(zip_info.compress_size),
                            "crc32": f"{zip_info.CRC:08x}",
                        }
                    )
        except zipfile.BadZipFile as exc:
            raise ValueError(
                f"Could not read Battery Archive zip file: {zip_path.name}"
            ) from exc

    return sorted(
        records,
        key=lambda record: (
            str(record["zip_file"]).casefold(),
            str(record["internal_csv_path"]).casefold(),
        ),
    )


def build_cycle_file_inventory(raw_dir: str | Path) -> pd.DataFrame:
    """Build a deterministic cycle_data file inventory DataFrame."""
    records = discover_cycle_files(raw_dir)
    if not records:
        raise ValueError(
            f"No Battery Archive cycle_data CSV files were found in: {Path(raw_dir)}"
        )

    inventory_df = pd.DataFrame(records, columns=BATTERY_ARCHIVE_INVENTORY_COLUMNS)
    duplicate_mask = inventory_df.duplicated(
        subset=["zip_file", "internal_csv_path"],
        keep=False,
    )
    if duplicate_mask.any():
        duplicates = inventory_df.loc[
            duplicate_mask, ["zip_file", "internal_csv_path"]
        ]
        raise ValueError(
            "Duplicate Battery Archive cycle file records were found: "
            f"{duplicates.to_dict(orient='records')}"
        )

    return inventory_df.sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)


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
