"""Build the source-disjoint Materials Project external-evidence requirement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from materials_data_analyzer.research_loop.materials_project_external_evidence_requirement import (  # noqa: E402
    MaterialsProjectExternalEvidenceRequirementError,
    build_materials_project_external_evidence_requirement,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a completed target-blind Materials Project same-source readiness result "
            "with zero new IDs into an exact source-disjoint external-evidence requirement. "
            "This command does not search, download, query candidate targets, or fit models."
        )
    )
    parser.add_argument(
        "--readiness",
        type=Path,
        default=Path(
            "outputs/materials_project_independent_source_readiness_v1/"
            "independent_source_readiness.json"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "configs/research/materials_project_external_evidence_requirement.v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/materials_project_external_evidence_requirement_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_materials_project_external_evidence_requirement(
            readiness_path=args.readiness,
            config_path=args.config,
            output_dir=args.output,
            overwrite=args.overwrite,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ValueError,
        MaterialsProjectExternalEvidenceRequirementError,
    ) as exc:
        print(f"Materials Project external evidence requirement failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
