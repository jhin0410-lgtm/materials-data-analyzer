"""Canonical terminal capability-lineage closure for PR #233.

This additive verifier binds the terminal capability gap/specification/resolution to the
already authenticated cycle-12 reference graph and promoted registry.  Self-consistent
rehashing of the terminal artifacts therefore cannot substitute a different next action,
objective, predecessor state, available-action set, capability contract, or resolution.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from .capability_expansion import build_capability_gap, build_capability_specification
from .capability_resolver import resolve_or_discover_capability

AutonomousProductionExactHeadRound5Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound5Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _verified_action_classes(registry: Mapping[str, Any]) -> list[str]:
    records = registry.get("records")
    _require(isinstance(records, list), "terminal capability registry records must be a list")
    result: list[str] = []
    for index, raw_record in enumerate(records):
        record = _mapping(raw_record, label=f"terminal capability registry record {index}")
        if record.get("state") != "verified":
            continue
        action_class = record.get("action_class")
        _require(
            isinstance(action_class, str) and action_class,
            f"terminal verified registry action {index} is invalid",
        )
        result.append(action_class)
    _require(
        len(result) == len(set(result)),
        "terminal capability registry contains duplicate verified action classes",
    )
    return sorted(result)


def verify_exact_head_round5_boundaries(output_root: str | Path) -> None:
    """Canonically rebuild terminal capability artifacts from authenticated predecessors."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    if len(cycles) < 12:
        return

    cycle12 = _mapping(cycles[11], label="cycle 12")
    reference = _merge_gate._load(
        root,
        "mds2-2923-experiment-identity-reference-chain.json",
    )
    reference_sha = _merge_gate._verify_self_hash(
        reference,
        "report_sha256_without_self_field",
        label="terminal predecessor reference graph",
    )
    _require(
        cycle12.get("reference_graph_sha256") == reference_sha,
        "terminal predecessor reference graph is not bound to cycle 12",
    )
    next_action = _mapping(reference.get("next_action"), label="terminal predecessor next action")
    requested_action_class = next_action.get("action_class")
    _require(
        isinstance(requested_action_class, str) and requested_action_class,
        "terminal predecessor next action class is invalid",
    )
    _require(
        cycle12.get("output_next_action_class") == requested_action_class,
        "terminal capability action drifted from authenticated cycle 12",
    )

    registry = _merge_gate._load(root, "capability-registry-promoted-4.json")
    registry_sha = _merge_gate._verify_self_hash(
        registry,
        "capability_registry_sha256_without_self_field",
        label="terminal promoted capability registry",
    )
    _require(
        cycle12.get("promoted_registry_sha256") == registry_sha,
        "terminal promoted capability registry is not bound to cycle 12",
    )
    available_action_classes = _verified_action_classes(registry)

    expected_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=reference,
        available_action_classes=available_action_classes,
    )
    persisted_gap = _merge_gate._load(root, "capability-gap-5.json")
    _require(
        persisted_gap == expected_gap,
        "terminal capability gap drifted from the authenticated reference action",
    )

    expected_specification = build_capability_specification(expected_gap)
    persisted_specification = _merge_gate._load(root, "capability-specification-5.json")
    _require(
        persisted_specification == expected_specification,
        "terminal capability specification drifted from the canonical gap",
    )

    expected_resolution = resolve_or_discover_capability(
        registry=registry,
        capability_specification=expected_specification,
        available_verified_primitives=[],
    )
    persisted_resolution = _merge_gate._load(root, "capability-resolution-5.json")
    _require(
        persisted_resolution == expected_resolution,
        "terminal capability resolution drifted from the canonical bounded resolver",
    )


__all__ = [
    "AutonomousProductionExactHeadRound5Error",
    "verify_exact_head_round5_boundaries",
]
