#!/usr/bin/env python
"""Prepare a compact exact-byte review packet from one live IN625 episode output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from materials_data_analyzer.research_loop.in625_zenodo_review_preparation import (
    prepare_in625_zenodo_review_packet,
)
from materials_data_analyzer.research_loop.safe_archive_member_reader import (
    read_verified_text_members,
)


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _selected_witness_paths(inventory: dict) -> list[str]:
    members = inventory.get("members")
    if not isinstance(members, list):
        raise ValueError("archive inventory members must be a list")
    verified = [
        item
        for item in members
        if isinstance(item, dict)
        and item.get("text_hash_status") == "hashed_within_budget"
        and item.get("utf8_decodable") is True
        and isinstance(item.get("path"), str)
    ]
    readmes = sorted(
        item["path"]
        for item in verified
        if "readme" in Path(item["path"]).name.lower()
    )
    data_candidates = sorted(
        item["path"]
        for item in verified
        if str(item.get("suffix", "")).lower() in {".dat", ".csv", ".tsv"}
    )
    selected = list(readmes)
    if data_candidates:
        selected.append(data_candidates[0])
    if not selected:
        raise ValueError("no bounded UTF-8 review witnesses are available")
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.episode_output)
    summary = _read_json(root / "live_in625_evidence_summary.json")
    if summary.get("status") != "acquired_pending_semantic_lineage_and_review_intake":
        result = {
            "schema_version": "1.0",
            "review_packet_prepared": False,
            "reason": "live_episode_did_not_reach_acquired_review_preparation_state",
            "live_episode_status": summary.get("status"),
            "scientific_negative_evidence": False,
            "scientific_status_changed": False,
            "human_review_decision_created": False,
        }
        _write_json(root / "review_preparation_summary.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    inventory = _read_json(root / "archive_inventory.json")
    candidate = _read_json(root / "federated_evidence_candidate.json")
    ceiling = _read_json(root / "federated_evidence_use_ceiling.json")
    archive_path = root / "acquisition" / "files" / "Dataset.zip"
    selected_paths = _selected_witness_paths(inventory)
    readout = read_verified_text_members(
        archive_path,
        inventory,
        selected_paths,
        max_member_bytes=4 * 1024 * 1024,
        max_total_bytes=8 * 1024 * 1024,
    )
    packet = prepare_in625_zenodo_review_packet(
        candidate=candidate,
        use_ceiling=ceiling,
        live_summary=summary,
        archive_inventory=inventory,
        selected_text_readout=readout,
    )
    _write_json(root / "selected_review_text_witnesses.json", readout)
    _write_json(root / "scientific_review_preparation_packet.json", packet)
    result = {
        "schema_version": "1.0",
        "review_packet_prepared": True,
        "review_packet_sha256": packet["review_packet_sha256"],
        "review_request_id": packet["review_request"]["review_request_id"],
        "selected_witness_count": readout["selected_member_count"],
        "selected_witness_paths": selected_paths,
        "human_review_decision_created": False,
        "human_review_blocker_released": False,
        "scientific_status_changed": False,
        "scientific_support_established": False,
        "issue_76_eligible": False,
    }
    _write_json(root / "review_preparation_summary.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
