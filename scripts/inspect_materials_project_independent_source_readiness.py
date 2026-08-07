"""Inspect whether Materials Project exposes a new ID-disjoint same-source cohort."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.materials_project_acquisition import (  # noqa: E402
    AcquisitionStopError,
    CredentialRequiredError,
)
from materials_data_analyzer.research_loop.materials_project_independent_source_readiness import (  # noqa: E402
    MaterialsProjectIndependentSourceReadinessError,
    run_materials_project_independent_source_readiness,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Query only current Materials Project identity fields under the frozen v1.3 scope, "
            "exclude all 838 benchmark-v1 material IDs using partition membership, and report "
            "whether a new ID-disjoint cohort exists within the same Materials Project source. "
            "This does not establish source-independent external validation. No target values, "
            "policies or models are used."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/research/materials_project_independent_source_readiness.v1.json"),
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("outputs/materials_project_retrospective_benchmark_v1"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/materials_project_independent_source_readiness_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_materials_project_independent_source_readiness(
            config_path=args.config,
            benchmark_dir=args.benchmark,
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
        AcquisitionStopError,
        CredentialRequiredError,
        MaterialsProjectIndependentSourceReadinessError,
    ) as exc:
        print(f"Materials Project same-source cohort readiness failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
