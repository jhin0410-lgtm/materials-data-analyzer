"""Resolve verified capabilities or discover bounded declarative/reuse candidates."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import calibration_protocol_bridge_capability as bridge
from .capability_registry import (
    build_capability_candidate,
    resolve_verified_capability,
)

CAPABILITY_RESOLVER_SCHEMA_VERSION = "1.0"
CAPABILITY_RESOLVER_POLICY_VERSION = "1.0"


class CapabilityResolverError(ValueError):
    """Raised when capability resolution would widen the declared action space."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityResolverError(message)


def resolve_or_discover_capability(
    *,
    registry: Mapping[str, Any],
    capability_specification: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
) -> dict[str, Any]:
    """Prefer a verified capability, otherwise search only the finite trusted factory catalogue."""
    action_class = capability_specification.get("requested_action_class")
    _require(isinstance(action_class, str) and action_class, "requested action class missing")
    resolution = resolve_verified_capability(
        registry=registry,
        action_class=action_class,
    )
    if resolution["resolved"] is True:
        return {
            "schema_version": CAPABILITY_RESOLVER_SCHEMA_VERSION,
            "policy_version": CAPABILITY_RESOLVER_POLICY_VERSION,
            "resolution_status": "verified_capability_resolved",
            "action_class": action_class,
            "registry_sha256": resolution["registry_sha256"],
            "implementation_id": resolution["implementation_id"],
            "candidate": None,
            "unrestricted_discovery_performed": False,
            "arbitrary_code_generation_performed": False,
        }

    primitives = set(available_verified_primitives)
    if action_class == bridge.ACTION_CLASS and set(
        bridge.REQUIRED_VERIFIED_PRIMITIVES
    ).issubset(primitives):
        candidate = build_capability_candidate(
            capability_specification=capability_specification,
            factory_id=bridge.FACTORY_ID,
            implementation_id=bridge.IMPLEMENTATION_ID,
            mechanism="compose_verified_primitives",
            required_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
        )
        return {
            "schema_version": CAPABILITY_RESOLVER_SCHEMA_VERSION,
            "policy_version": CAPABILITY_RESOLVER_POLICY_VERSION,
            "resolution_status": "bounded_candidate_discovered",
            "action_class": action_class,
            "registry_sha256": resolution["registry_sha256"],
            "implementation_id": None,
            "candidate": candidate,
            "factory_id": bridge.FACTORY_ID,
            "unrestricted_discovery_performed": False,
            "arbitrary_code_generation_performed": False,
        }

    return {
        "schema_version": CAPABILITY_RESOLVER_SCHEMA_VERSION,
        "policy_version": CAPABILITY_RESOLVER_POLICY_VERSION,
        "resolution_status": "no_bounded_candidate_available",
        "action_class": action_class,
        "registry_sha256": resolution["registry_sha256"],
        "implementation_id": None,
        "candidate": None,
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }


__all__ = [
    "CAPABILITY_RESOLVER_POLICY_VERSION",
    "CAPABILITY_RESOLVER_SCHEMA_VERSION",
    "CapabilityResolverError",
    "resolve_or_discover_capability",
]
