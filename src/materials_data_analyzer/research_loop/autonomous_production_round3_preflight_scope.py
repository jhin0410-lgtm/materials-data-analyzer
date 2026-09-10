"""Scope the round-3 duplicate-key preflight to syntactically valid JSON.

A bounded typed transport stop may retain partial source metadata bytes at a historical
``*.json`` locator before a complete JSON document exists.  Those bytes are not parsed as a
provenance JSON object by the accepted transport-stop path and remain non-reusable.  This
adapter therefore rejects duplicate keys whenever a persisted file is syntactically valid
JSON, while leaving non-JSON partial source bytes to the existing lifecycle-specific verifier.
It never converts an existing verifier failure into success.
"""
from __future__ import annotations

import json
from pathlib import Path

from .autonomous_production_exact_head_p2_round3 import (
    AutonomousProductionExactHeadRound3Error,
    _duplicate_rejecting_object,
)


def verify_round3_duplicate_key_preflight(output_root: str | Path) -> None:
    """Reject duplicate keys without treating partial source bytes as completed JSON."""
    root = Path(output_root).expanduser().resolve(strict=True)
    for path in sorted(root.rglob("*.json")):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise AutonomousProductionExactHeadRound3Error(
                "persisted provenance JSON path or UTF-8 bytes are invalid"
            ) from exc
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
