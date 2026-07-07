"""Kaggle dataset ingestion connector."""

from __future__ import annotations

import re
from pathlib import Path

from connectors.base import BaseConnector, IngestionResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "kaggle"


def safe_dataset_name(dataset_slug: str) -> str:
    """Return a filesystem-safe Kaggle dataset folder name."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_slug).strip("_")


class KaggleConnector(BaseConnector):
    """Kaggle raw-file download connector.

    Processed conversion is intentionally delegated to dataset-specific loaders
    because Kaggle dataset file structures vary.
    """

    source_name = "kaggle"

    def __init__(self, dataset_slug: str) -> None:
        self.dataset_slug = dataset_slug

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Download Kaggle dataset files into a raw-data folder."""
        del limit
        if not self.dataset_slug:
            raise ValueError("A Kaggle dataset slug is required, for example owner/name.")

        try:
            from kaggle.api.kaggle_api_extended import KaggleApi
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The kaggle package is required for Kaggle ingestion.\n"
                "Install it with: pip install kaggle\n"
                "Configure credentials outside this repository."
            ) from exc

        raw_dir = RAW_ROOT / safe_dataset_name(self.dataset_slug)
        raw_dir.mkdir(parents=True, exist_ok=True)

        api = KaggleApi()
        try:
            api.authenticate()
        except Exception as exc:
            raise RuntimeError(
                "Kaggle credentials are not configured or could not be used. "
                "Configure them outside this repository; do not commit keys."
            ) from exc

        api.dataset_download_files(
            self.dataset_slug,
            path=str(raw_dir),
            unzip=full,
            quiet=False,
        )

        raw_paths = [path for path in raw_dir.rglob("*") if path.is_file()]
        return IngestionResult(
            source_name=self.source_name,
            raw_paths=raw_paths,
            processed_paths=[],
            row_count=0,
            column_count=0,
            warnings=[
                "Kaggle raw files were downloaded only. Inspect the file "
                "structure and run a dataset-specific loader, such as the "
                "battery loader, to create processed CSV files."
            ],
        )
