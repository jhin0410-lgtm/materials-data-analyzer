"""Audit registered Materials Project external-evidence candidates without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from materials_data_analyzer.research_loop.external_evidence_registry import (
    ExternalEvidenceRegistryError,
    audit_external_evidence_registry,
)

DEFAULT_REGISTRY = Path("configs/research/materials_project_external_source_candidates.v1.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate registered external-source candidates against an already generated "
            "Materials Project external-evidence requirement. No network access or target "
            "retrieval is performed."
        )
    )
    parser.add_argument("--requirement", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = audit_external_evidence_registry(
            requirement_path=args.requirement,
            registry_path=args.registry,
            output_dir=args.output,
            overwrite=args.overwrite,
        )
    except (ExternalEvidenceRegistryError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
