#!/usr/bin/env python3
"""Validate source-bound cross-source IN625 physical records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    load_registry,
)
from materials_data_analyzer.research_loop.in625_external_physical_evidence_intake import (
    validate_physical_evidence_records,
)

DEFAULT_REGISTRY = Path(
    "configs/research/in625_single_track_external_source_candidates.v1.json"
)
DEFAULT_RECORDS = Path(
    "data/reference/in625_external_physical_evidence/"
    "ghosh_2018_figure1_records.v1.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate provenance-stratified IN625 physical evidence records."
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--intake-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    registry = load_registry(args.registry)
    record_set = json.loads(args.records.read_text(encoding="utf-8"))
    records = record_set.get("records")
    validated, audit = validate_physical_evidence_records(
        records, registry, args.intake_root
    )
    result = {
        "record_set_id": record_set.get("record_set_id"),
        "source_reference": record_set.get("source_reference"),
        "validated_records": validated,
        "audit": audit,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
