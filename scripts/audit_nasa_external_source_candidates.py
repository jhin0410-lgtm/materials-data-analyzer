"""Audit registered external battery-source candidates against a requirement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from materials_data_analyzer.research_loop.nasa_external_source_audit import (
    audit_external_source_candidates,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit external battery-source candidates without downloading data or "
            "upgrading scientific evidence."
        )
    )
    parser.add_argument("--requirement", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = audit_external_source_candidates(args.requirement, args.registry)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
