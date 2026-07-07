"""HTEM/NREL ingestion connector skeleton."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from connectors.base import BaseConnector, IngestionResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "htem"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "htem_sample_properties.csv"
DEFAULT_BASE_URLS = [
    "https://htem.nrel.gov",
    "https://htem-api.nrel.gov",
    "https://htem-api.nlr.gov",
]


class HTEMConnector(BaseConnector):
    """Connector for sample-level scalar HTEM properties."""

    source_name = "htem"

    def __init__(
        self,
        elements: list[str] | None = None,
        base_url: str | None = None,
    ) -> None:
        self.elements = ["Zn", "Sn"] if elements is None else elements
        self.base_url = (base_url or DEFAULT_BASE_URLS[0]).rstrip("/")

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET JSON from the configured HTEM endpoint."""
        try:
            import requests
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The requests package is required for HTEM ingestion.\n"
                "Install it with: pip install requests"
            ) from exc

        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def search_libraries_by_elements(
        self, elements: list[str], limit: int = 50
    ) -> Any:
        """Search HTEM libraries by element list."""
        return self.get_json(
            "/api/libraries",
            params={"elements": ",".join(elements), "limit": limit},
        )

    def fetch_library(self, library_id: str) -> Any:
        """Fetch one HTEM library JSON document."""
        return self.get_json(f"/api/libraries/{library_id}")

    def fetch_sample(self, sample_id: str) -> Any:
        """Fetch one HTEM sample JSON document."""
        return self.get_json(f"/api/samples/{sample_id}")

    def extract_scalar_fields(self, sample_json: dict[str, Any]) -> dict[str, Any]:
        """Keep only flat scalar sample fields and exclude nested spectra/arrays."""
        scalar_types = (str, int, float, bool, type(None))
        return {
            key: value
            for key, value in sample_json.items()
            if isinstance(value, scalar_types)
        }

    def build_sample_property_table(
        self,
        sample_ids: list[str],
        library_id: str | None = None,
        limit: int = 50,
    ) -> tuple[pd.DataFrame, list[Path]]:
        """Fetch sample JSON files and build a scalar-property table."""
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        raw_paths: list[Path] = []

        for sample_id in sample_ids[:limit]:
            sample_json = self.fetch_sample(str(sample_id))
            raw_path = RAW_DIR / f"sample_{sample_id}.json"
            raw_path.write_text(json.dumps(sample_json, indent=2), encoding="utf-8")
            raw_paths.append(raw_path)
            row = self.extract_scalar_fields(sample_json)
            row.setdefault("sample_id", sample_id)
            if library_id:
                row.setdefault("library_id", library_id)
            rows.append(row)

        return pd.DataFrame(rows), raw_paths

    def _extract_library_rows(self, search_json: Any) -> list[dict[str, Any]]:
        """Normalize search JSON into a list of library-like dictionaries."""
        if isinstance(search_json, list):
            return [item for item in search_json if isinstance(item, dict)]
        if isinstance(search_json, dict):
            for key in ("results", "libraries", "data"):
                value = search_json.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _extract_sample_ids(self, library_json: dict[str, Any]) -> list[str]:
        """Extract sample IDs from common library JSON shapes."""
        for key in ("sample_ids", "samples"):
            value = library_json.get(key)
            if isinstance(value, list):
                ids = []
                for item in value:
                    if isinstance(item, dict):
                        sample_id = item.get("sample_id") or item.get("id")
                    else:
                        sample_id = item
                    if sample_id is not None:
                        ids.append(str(sample_id))
                return ids
        return []

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Probe HTEM libraries and save sample-level scalar properties."""
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        query_limit = limit if not full else max(limit, 50)
        search_json = self.search_libraries_by_elements(self.elements, query_limit)
        search_path = RAW_DIR / "library_search_raw.json"
        search_path.write_text(json.dumps(search_json, indent=2), encoding="utf-8")

        libraries = self._extract_library_rows(search_json)
        if not libraries:
            return IngestionResult(
                source_name=self.source_name,
                raw_paths=[search_path],
                processed_paths=[],
                warnings=["No HTEM libraries were found in the search response."],
            )

        library = libraries[0]
        library_id = str(library.get("library_id") or library.get("id") or "unknown")
        sample_ids = self._extract_sample_ids(library)
        if not sample_ids and library_id != "unknown":
            library_json = self.fetch_library(library_id)
            library_path = RAW_DIR / f"library_{library_id}.json"
            library_path.write_text(json.dumps(library_json, indent=2), encoding="utf-8")
            sample_ids = self._extract_sample_ids(library_json)
            raw_paths = [search_path, library_path]
        else:
            raw_paths = [search_path]

        if not sample_ids:
            return IngestionResult(
                source_name=self.source_name,
                raw_paths=raw_paths,
                processed_paths=[],
                warnings=["No sample IDs were found; processed CSV was not created."],
            )

        table, sample_raw_paths = self.build_sample_property_table(
            sample_ids=sample_ids,
            library_id=library_id,
            limit=query_limit,
        )
        table.to_csv(PROCESSED_PATH, index=False)
        return IngestionResult(
            source_name=self.source_name,
            raw_paths=raw_paths + sample_raw_paths,
            processed_paths=[PROCESSED_PATH],
            row_count=len(table),
            column_count=len(table.columns),
            warnings=[
                "Sample-level scalar fields only; spectra are excluded in this "
                "first ingestion version."
            ],
        )
