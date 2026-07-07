"""Dataset metadata structures for real-data readiness."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetMetadata:
    """Record source and analysis metadata for a tabular engineering dataset."""

    dataset_id: str
    title: str
    source_url: str | None
    raw_path: str | None
    processed_path: str | None
    domain: str
    available_modes: list[str]
    target_candidates: list[str]
    notes: str | None = None
