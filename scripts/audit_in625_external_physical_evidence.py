#!/usr/bin/env python3
"""Audit the provenance-stratified IN625 external physical-evidence registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    build_support_matrix,
    load_registry,
    registry_audit,
)

DEFAULT_REGISTRY = Path(
    "configs/research/in625_single_track_external_source_candidates.v1.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit cross-source IN625 physical evidence without promoting "
            "non-AMMT experiments into the frozen AMB2018-02 Stage 1 contract."
        )
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to the provenance-stratified source registry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON audit output. Nothing is written when omitted.",
    )
    parser.add_argument(
        "--support-matrix-output",
        type=Path,
        help="Optional JSON output containing only the source/process support matrix.",
    )
    args = parser.parse_args()

    registry = load_registry(args.registry)
    audit = registry_audit(registry)
    rendered = json.dumps(audit, indent=2, sort_keys=True)
    print(rendered)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.support_matrix_output is not None:
        args.support_matrix_output.parent.mkdir(parents=True, exist_ok=True)
        matrix = build_support_matrix(registry)
        args.support_matrix_output.write_text(
            json.dumps(matrix, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
