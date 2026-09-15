"""Bind persisted authority artifacts to canonical trusted-replay producer outputs.

Mutable provider pages may legitimately change in non-authority bytes or visible text.  Those
observations are not allowed to sever the binding between a trusted replay and the persisted
scientific/provenance artifact that downstream cycles consume.  This module compares canonical
producer projections and excludes only fields that are direct fingerprints of mutable candidate-page
HTML; exact derived routes, the static primary PDF, extracted page digests, claim receipts, lineage,
policy identity, and fail-closed scientific authority remain bound.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_exact_head_p2_round8 as _round8
from . import autonomous_production_merge_gate_hardening as _merge_gate

AutonomousProductionTrustedReplayArtifactBindingError = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionTrustedReplayArtifactBindingError(message)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _candidate_acquisition_authority_projection(
    report: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    """Return all acquisition semantics except mutable candidate-page fingerprints."""

    projected = dict(report)
    projected.pop("report_sha256_without_self_field", None)
    candidate_page = projected.get("candidate_page")
    _require(isinstance(candidate_page, Mapping), f"{label} candidate_page is missing")
    normalized_page = dict(candidate_page)
    for field in (
        "source_sha256",
        "source_size_bytes",
        "http_content_type",
        "visible_text_sha256",
        "visible_text_utf8_bytes",
    ):
        normalized_page.pop(field, None)
    projected["candidate_page"] = normalized_page
    return projected


def _bind_persisted_candidate_acquisition_to_trusted_replay(root: Path) -> None:
    trusted_smoke = _round8._trusted_smoke_receipt(root, step=3)
    _merge_gate._verify_self_hash(
        trusted_smoke,
        "report_sha256_without_self_field",
        label="trusted promotion-3 replay receipt",
    )
    trusted_acquisition = trusted_smoke.get("acquisition_receipt")
    _require(
        isinstance(trusted_acquisition, Mapping),
        "trusted promotion-3 replay omitted canonical acquisition receipt",
    )
    _merge_gate._verify_self_hash(
        trusted_acquisition,
        "report_sha256_without_self_field",
        label="trusted promotion-3 acquisition replay",
    )

    persisted = _merge_gate._load(
        root,
        "nist-ammt-calibration-candidate-acquisition.json",
    )
    _merge_gate._verify_self_hash(
        persisted,
        "report_sha256_without_self_field",
        label="persisted NIST AMMT calibration candidate acquisition",
    )

    trusted_projection = _candidate_acquisition_authority_projection(
        trusted_acquisition,
        label="trusted promotion-3 acquisition replay",
    )
    persisted_projection = _candidate_acquisition_authority_projection(
        persisted,
        label="persisted NIST AMMT calibration candidate acquisition",
    )
    _require(
        _canonical_bytes(persisted_projection) == _canonical_bytes(trusted_projection),
        "persisted NIST AMMT candidate acquisition authority projection drifted from trusted promotion-3 replay",
    )


def verify_trusted_replay_artifact_bindings(output_root: str | Path) -> None:
    """Verify persisted artifacts that must equal trusted producer replay semantics."""

    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")

    # Promotion 3 is the candidate-acquisition capability.  Earlier lifecycles do not yet
    # persist this authority artifact and are outside this binding's scope.
    if len(cycles) >= _round6._PROMOTIONS[2][3]:
        _bind_persisted_candidate_acquisition_to_trusted_replay(root)


__all__ = [
    "AutonomousProductionTrustedReplayArtifactBindingError",
    "verify_trusted_replay_artifact_bindings",
]
