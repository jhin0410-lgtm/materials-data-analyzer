"""Resolve verified capabilities or discover bounded declarative/reuse candidates."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import calibration_protocol_bridge_capability as bridge
from . import nist_ammt_calibration_source_discovery as discovery
from .capability_registry import (
    build_capability_candidate,
    resolve_verified_capability,
)

CAPABILITY_RESOLVER_SCHEMA_VERSION = "1.1"
CAPABILITY_RESOLVER_POLICY_VERSION = "1.1"


class CapabilityResolverError(ValueError):
    """Raised when capability resolution would widen the declared action space."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityResolverError(message)


def _bounded_factory(
    action_class: str,
    primitives: set[str],
) -> tuple[object, str] | None:
    if action_class == bridge.ACTION_CLASS and set(
        bridge.REQUIRED_VERIFIED_PRIMITIVES
    ).issubset(primitives):
        return bridge, "compose_verified_primitives"
    if action_class == discovery.ACTION_CLASS and set(
        discovery.REQUIRED_VERIFIED_PRIMITIVES
    ).issubset(primitives):
        return discovery, "generate_declarative_adapter_instance"
    return None


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
    factory = _bounded_factory(action_class, primitives)
    if factory is not None:
        module, mechanism = factory
        required = getattr(module, "REQUIRED_VERIFIED_PRIMITIVES")
        factory_id = getattr(module, "FACTORY_ID")
        implementation_id = getattr(module, "IMPLEMENTATION_ID")
        candidate = build_capability_candidate(
            capability_specification=capability_specification,
            factory_id=factory_id,
            implementation_id=implementation_id,
            mechanism=mechanism,
            required_verified_primitives=required,
        )
        return {
            "schema_version": CAPABILITY_RESOLVER_SCHEMA_VERSION,
            "policy_version": CAPABILITY_RESOLVER_POLICY_VERSION,
            "resolution_status": "bounded_candidate_discovered",
            "action_class": action_class,
            "registry_sha256": resolution["registry_sha256"],
            "implementation_id": None,
            "candidate": candidate,
            "factory_id": factory_id,
            "factory_catalogue_size": 2,
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
        "factory_catalogue_size": 2,
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }


__all__ = [
    "CAPABILITY_RESOLVER_POLICY_VERSION",
    "CAPABILITY_RESOLVER_SCHEMA_VERSION",
    "CapabilityResolverError",
    "resolve_or_discover_capability",
]
