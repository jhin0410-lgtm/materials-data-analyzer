"""CLI for exact-SHA scientific review requests and releases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .research_loop.scientific_review_release import (
    build_review_decision,
    build_review_request,
    verify_review_release,
)


def _read_object(path: str) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write(path: str, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mda-scientific-review")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create an exact-byte review request")
    prepare.add_argument("--candidate-id", required=True)
    prepare.add_argument("--evidence-sha256", required=True)
    prepare.add_argument("--semantic-contract-sha256", required=True)
    prepare.add_argument("--lineage-sha256", required=True)
    prepare.add_argument("--intake-sha256")
    prepare.add_argument("--requested-use", action="append", required=True)
    prepare.add_argument("--output", required=True)

    decide = sub.add_parser("decide", help="Record one human review decision")
    decide.add_argument("--request", required=True)
    decide.add_argument("--reviewer-id", required=True)
    decide.add_argument("--decision", choices=["approved", "rejected"], required=True)
    decide.add_argument("--allow-use", action="append", default=[])
    decide.add_argument("--exclude-use", action="append", default=[])
    decide.add_argument("--notes", required=True)
    decide.add_argument("--output", required=True)

    verify = sub.add_parser("verify", help="Verify release against current exact bytes")
    verify.add_argument("--request", required=True)
    verify.add_argument("--decision", required=True)
    verify.add_argument("--candidate-id", required=True)
    verify.add_argument("--evidence-sha256", required=True)
    verify.add_argument("--semantic-contract-sha256", required=True)
    verify.add_argument("--lineage-sha256", required=True)
    verify.add_argument("--intake-sha256")
    verify.add_argument("--downstream-use", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        request = build_review_request(
            candidate_id=args.candidate_id,
            evidence_artifact_sha256=args.evidence_sha256,
            semantic_contract_sha256=args.semantic_contract_sha256,
            lineage_sha256=args.lineage_sha256,
            intake_artifact_sha256=args.intake_sha256,
            requested_uses=args.requested_use,
        )
        _write(args.output, request)
        print(json.dumps(request, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "decide":
        decision = build_review_decision(
            _read_object(args.request),
            reviewer_id=args.reviewer_id,
            decision=args.decision,
            allowed_uses=args.allow_use,
            excluded_uses=args.exclude_use,
            review_notes=args.notes,
        )
        _write(args.output, decision)
        print(json.dumps(decision, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    verified = verify_review_release(
        request=_read_object(args.request),
        decision=_read_object(args.decision),
        candidate_id=args.candidate_id,
        evidence_artifact_sha256=args.evidence_sha256,
        semantic_contract_sha256=args.semantic_contract_sha256,
        lineage_sha256=args.lineage_sha256,
        intake_artifact_sha256=args.intake_sha256,
        downstream_use=args.downstream_use,
    )
    print(json.dumps(verified, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if verified["human_review_blocker_released"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
