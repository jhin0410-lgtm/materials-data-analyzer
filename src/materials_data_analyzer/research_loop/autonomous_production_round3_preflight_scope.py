"""Scope the round-3 duplicate-key preflight to syntactically valid JSON.

A bounded typed transport stop may retain partial source metadata bytes at a historical
``*.json`` locator before a complete JSON document exists. Those bytes are not parsed as a
provenance JSON object by the accepted transport-stop path and remain non-reusable. This
adapter therefore rejects duplicate keys whenever a persisted file is syntactically valid
JSON, while leaving non-JSON partial source bytes to the existing lifecycle-specific verifier.
It also bounds every untrusted ``*.json`` read before parsing. The ceiling is derived from the
largest legitimate retained multisource payload (base64 expansion of the total source-byte
budget) plus fixed JSON/provenance overhead, so exported evidence cannot turn verification
into an unbounded-memory read. It never converts an existing verifier failure into success.
"""
from __future__ import annotations

import json
from pathlib import Path

from .autonomous_production_exact_head_p2_round3 import (
    AutonomousProductionExactHeadRound3Error,
    _duplicate_rejecting_object,
)
from .in625_geometry_condition_multisource_policy import MAX_TOTAL_BYTES

# Cycle-4 may legitimately retain every authorized source body in base64. Base64 uses at most
# 4*ceil(n/3) bytes; 16 MiB leaves ample deterministic room for JSON structure, source metadata,
# claim receipts, and future bounded fields without making the verifier accept arbitrary files.
_MAX_PERSISTED_JSON_BYTES = (
    4 * ((MAX_TOTAL_BYTES + 2) // 3) + 16 * 1024 * 1024
)


def _bounded_utf8_text(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AutonomousProductionExactHeadRound3Error(
            "persisted provenance JSON could not be stat-ed"
        ) from exc
    if size < 0 or size > _MAX_PERSISTED_JSON_BYTES:
        raise AutonomousProductionExactHeadRound3Error(
            "persisted provenance JSON exceeds bounded verifier budget"
        )
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_PERSISTED_JSON_BYTES + 1)
    except OSError as exc:
        raise AutonomousProductionExactHeadRound3Error(
            "persisted provenance JSON could not be read"
        ) from exc
    if len(raw) > _MAX_PERSISTED_JSON_BYTES:
        # Also catches growth between stat() and read().
        raise AutonomousProductionExactHeadRound3Error(
            "persisted provenance JSON exceeds bounded verifier budget"
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AutonomousProductionExactHeadRound3Error(
            "persisted provenance JSON path or UTF-8 bytes are invalid"
        ) from exc


def verify_round3_duplicate_key_preflight(output_root: str | Path) -> None:
    """Reject oversized/duplicate JSON before any downstream persisted-artifact parser."""
    root = Path(output_root).expanduser().resolve(strict=True)
    for path in sorted(root.rglob("*.json")):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise AutonomousProductionExactHeadRound3Error(
                "persisted provenance JSON path or UTF-8 bytes are invalid"
            ) from exc
        text = _bounded_utf8_text(resolved)
        try:
            json.loads(text, object_pairs_hook=_duplicate_rejecting_object)
        except AutonomousProductionExactHeadRound3Error:
            raise
        except json.JSONDecodeError:
            # A typed transport stop may retain incomplete raw source metadata under its
            # eventual JSON filename. Existing lifecycle-specific verification determines
            # whether such partial output is allowed and always denies reuse.
            continue


__all__ = ["verify_round3_duplicate_key_preflight"]
