"""Materials Project ingestion connector."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from connectors.base import BaseConnector, IngestionResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "materials_project"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "materials_project_fe_si.csv"
RAW_PATH = RAW_DIR / "mp_fe_si_raw.json"
MP_FIELDS = [
    "material_id",
    "formula_pretty",
    "band_gap",
    "formation_energy_per_atom",
    "energy_above_hull",
    "density",
    "volume",
]


def serialize_mp_doc(doc: Any) -> dict[str, Any]:
    """Convert Materials Project document objects to plain dictionaries."""
    if hasattr(doc, "model_dump"):
        return doc.model_dump()
    if hasattr(doc, "dict"):
        return doc.dict()
    if isinstance(doc, dict):
        return doc
    return {
        field: getattr(doc, field, None)
        for field in MP_FIELDS
    }


def build_materials_project_dataframe(docs: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the analyzer-ready Materials Project processed table."""
    rows = []
    for doc in docs:
        rows.append(
            {
                "material_id": str(doc.get("material_id", "")),
                "formula": doc.get("formula_pretty"),
                "band_gap_ev": doc.get("band_gap"),
                "formation_energy_ev_atom": doc.get("formation_energy_per_atom"),
                "energy_above_hull_ev_atom": doc.get("energy_above_hull"),
                "density_g_cm3": doc.get("density"),
                "volume_a3": doc.get("volume"),
            }
        )
    return pd.DataFrame(rows)


class MaterialsProjectConnector(BaseConnector):
    """Small Materials Project API probe connector."""

    source_name = "materials_project"

    def __init__(self, elements: list[str] | None = None) -> None:
        self.elements = ["Fe", "Si"] if elements is None else elements

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Fetch Materials Project summary docs and save raw JSON/processed CSV."""
        api_key = os.getenv("MP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MP_API_KEY is not set. Set it in your environment; do not store "
                "API keys in code, README files, source.md files, or tests."
            )

        try:
            from mp_api.client import MPRester
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The mp-api package is required for Materials Project ingestion.\n"
                "Install it with: pip install mp-api"
            ) from exc

        query_limit = limit if not full else max(limit, 50)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)

        with MPRester(api_key) as mpr:
            docs = mpr.materials.summary.search(
                elements=self.elements,
                fields=MP_FIELDS,
                num_chunks=1,
                chunk_size=query_limit,
            )

        plain_docs = [serialize_mp_doc(doc) for doc in docs[:query_limit]]
        RAW_PATH.write_text(
            json.dumps(plain_docs, indent=2, default=str),
            encoding="utf-8",
        )
        processed_df = build_materials_project_dataframe(plain_docs)
        processed_df.to_csv(PROCESSED_PATH, index=False)

        return IngestionResult(
            source_name=self.source_name,
            raw_paths=[RAW_PATH],
            processed_paths=[PROCESSED_PATH],
            row_count=len(processed_df),
            column_count=len(processed_df.columns),
            warnings=[
                "Materials Project values are computed materials properties, "
                "not direct experimental measurements."
            ],
        )
