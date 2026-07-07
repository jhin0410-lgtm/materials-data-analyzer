"""Base classes for external data ingestion connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IngestionResult:
    """Summary of raw and processed files produced by one ingestion run."""

    source_name: str
    raw_paths: list[Path] = field(default_factory=list)
    processed_paths: list[Path] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    warnings: list[str] = field(default_factory=list)


class BaseConnector:
    """Common interface for small probe and explicit full ingestion runs."""

    source_name: str = "base"

    def probe(self, limit: int = 50) -> IngestionResult:
        """Fetch a small source preview."""
        return self.fetch(limit=limit, full=False)

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Fetch source data and return raw/processed output paths."""
        raise NotImplementedError
