"""Mission-pinned standing authorization for bounded trusted-source discovery.

The self-directed planner intentionally continues to label external evidence search as
``explicit_authorization_required``. This module does not bypass or weaken that gate.
Instead it proves that the exact mission pins an exact trusted-source discovery policy
whose provider and safety boundaries match the executable implementation. Only then can
one selected external-evidence-search action be handed to the bounded evidence loop.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .autonomous_evidence_loop import run_autonomous_evidence_loop
from .kernel import ResearchLoopError
from .trusted_source_discovery import (
    AUTO,
    NIST_RMM_HOST,
    NIST_RMM_SEARCH_ENDPOINT,
    trusted_provider_authorization,
)

TRUSTED_DISCOVERY_AUTHORIZATION_SCHEMA_VERSION = "1.0"
TRUSTED_DISCOVERY_AUTHORIZATION_POLICY_VERSION = "1.0"


class TrustedDiscoveryAuthorizationError(ResearchLoopError):
    """Raised when standing trusted-source authorization cannot be authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrustedDiscoveryAuthorizationError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise TrustedDiscoveryAuthorizationError(f"{field} must be exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustedDiscoveryAuthorizationError(
            f"{field} must contain valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise TrustedDiscoveryAuthorizationError(f"{field} root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TrustedDiscoveryAuthorizationError(
            f"{field} must be non-empty text without surrounding whitespace"
        )
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustedDiscoveryAuthorizationError(f"{field} must be an object")
    return value


def _policy_pin(program_state: Mapping[str, Any], policy_id: str) -> str:
    mission = _mapping(program_state.get("mission"), "program_state.mission")
    autonomy = _mapping(mission.get("autonomy_policy"), "mission.autonomy_policy")
    if autonomy.get("network_evidence_search") != "explicit_authorization":
        raise TrustedDiscoveryAuthorizationError(
            "mission does not require the explicit network-evidence authorization gate"
        )
    pins = mission.get("source_trust_policy_pins")
    if not isinstance(pins, list) or not pins:
        raise TrustedDiscoveryAuthorizationError(
            "mission must pin at least one source-trust policy"
        )
    matches: list[str] = []
    for index, raw in enumerate(pins):
        if not isinstance(raw, Mapping):
            raise TrustedDiscoveryAuthorizationError(
                f"source_trust_policy_pins[{index}] must be an object"
            )
        if raw.get("policy_id") != policy_id:
            continue
        sha = raw.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64 or any(
            char not in "0123456789abcdef" for char in sha
        ):
            raise TrustedDiscoveryAuthorizationError(
                f"source-trust pin for {policy_id!r} has an invalid SHA-256"
            )
        matches.append(sha)
    if len(matches) != 1:
        raise TrustedDiscoveryAuthorizationError(
            f"mission must contain exactly one source-trust pin for {policy_id!r}"
        )
    return matches[0]


def _validate_policy_document(policy: Mapping[str, Any], *, provider: str) -> dict[str, Any]:
    if policy.get("schema_version") != "1.0":
        raise TrustedDiscoveryAuthorizationError(
            "unsupported trusted-source discovery policy schema_version"
        )
    policy_id = _strict_text(policy.get("policy_id"), "policy_id")
    providers = policy.get("providers")
    if not isinstance(providers, list) or not providers:
        raise TrustedDiscoveryAuthorizationError("policy.providers must be a non-empty list")
    provider_matches = [
        item
        for item in providers
        if isinstance(item, Mapping) and item.get("provider_id") == provider
    ]
    if len(provider_matches) != 1:
        raise TrustedDiscoveryAuthorizationError(
            f"policy must contain exactly one provider entry for {provider!r}"
        )
    entry = provider_matches[0]
    if provider == "nist_rmm":
        if entry.get("base_endpoint") != NIST_RMM_SEARCH_ENDPOINT:
            raise TrustedDiscoveryAuthorizationError(
                "pinned NIST provider endpoint does not match the executable endpoint"
            )
        if entry.get("allowed_hosts") != [NIST_RMM_HOST]:
            raise TrustedDiscoveryAuthorizationError(
                "pinned NIST provider hosts do not match the executable allow-list"
            )
        if entry.get("authorization_scope") != "public_catalog_search_only":
            raise TrustedDiscoveryAuthorizationError(
                "NIST provider authorization scope is not public_catalog_search_only"
            )
        if entry.get("human_review_mode") != "exception_only":
            raise TrustedDiscoveryAuthorizationError(
                "NIST provider must use exception_only human review"
            )

    boundaries = _mapping(policy.get("boundaries"), "policy.boundaries")
    required_false = (
        "authentication_allowed",
        "interactive_terms_allowed",
        "arbitrary_web_crawling_allowed",
        "scientific_status_upgrade_allowed",
        "physical_experiment_execution_allowed",
        "network_failure_counts_as_negative_scientific_evidence",
    )
    for field in required_false:
        if boundaries.get(field) is not False:
            raise TrustedDiscoveryAuthorizationError(
                f"policy boundary {field} must be exactly false"
            )
    provider_decision = trusted_provider_authorization(provider)
    if provider_decision["decision"] != AUTO:
        raise TrustedDiscoveryAuthorizationError(
            f"provider {provider!r} is not executable under trusted discovery policy"
        )
    if provider_decision["human_approval_required"] is not False:
        raise TrustedDiscoveryAuthorizationError(
            f"provider {provider!r} still requires human approval"
        )
    return {
        "policy_id": policy_id,
        "provider": provider,
        "provider_entry": dict(entry),
        "boundaries": dict(boundaries),
    }


def authorize_mission_pinned_trusted_discovery(
    program_state: Mapping[str, Any],
    *,
    trusted_policy_bytes: bytes,
    provider: str = "nist_rmm",
) -> dict[str, Any]:
    """Authenticate standing authorization from exact mission-pinned policy bytes."""
    if not isinstance(program_state, Mapping):
        raise TrustedDiscoveryAuthorizationError("program_state must be an object")
    policy = _json_object(trusted_policy_bytes, field="trusted_policy_bytes")
    policy_id = _strict_text(policy.get("policy_id"), "policy_id")
    expected_sha = _policy_pin(program_state, policy_id)
    observed_sha = hashlib.sha256(trusted_policy_bytes).hexdigest()
    if observed_sha != expected_sha:
        raise TrustedDiscoveryAuthorizationError(
            "trusted-source policy bytes do not match the exact mission pin"
        )
    validated = _validate_policy_document(policy, provider=provider)
    return {
        "schema_version": TRUSTED_DISCOVERY_AUTHORIZATION_SCHEMA_VERSION,
        "policy_version": TRUSTED_DISCOVERY_AUTHORIZATION_POLICY_VERSION,
        "decision": AUTO,
        "human_approval_required": False,
        "authorization_basis": "mission_pinned_standing_trusted_source_policy",
        "mission_pin": {
            "policy_id": validated["policy_id"],
            "sha256": observed_sha,
        },
        "provider": provider,
        "provider_entry": validated["provider_entry"],
        "planner_explicit_authorization_gate_satisfied": True,
        "planner_gate_bypassed": False,
        "scientific_status_upgrade_authorized": False,
        "physical_experiment_execution_authorized": False,
    }


def compile_trusted_discovery_handoff(
    program_state: Mapping[str, Any],
    self_directed_plan: Mapping[str, Any],
    *,
    trusted_policy_bytes: bytes,
    provider: str = "nist_rmm",
) -> dict[str, Any]:
    """Bind one planner-selected search action to the standing policy authorization."""
    if not isinstance(self_directed_plan, Mapping):
        raise TrustedDiscoveryAuthorizationError("self_directed_plan must be an object")
    action = self_directed_plan.get("selected_next_action")
    if not isinstance(action, Mapping):
        raise TrustedDiscoveryAuthorizationError(
            "self_directed_plan has no selected_next_action to authorize"
        )
    if action.get("action_class") != "external_evidence_search":
        raise TrustedDiscoveryAuthorizationError(
            "standing trusted discovery can authorize only external_evidence_search"
        )
    if action.get("execution_mode") != "explicit_authorization_required":
        raise TrustedDiscoveryAuthorizationError(
            "selected search action must retain explicit_authorization_required mode"
        )
    required_evidence = action.get("required_evidence")
    if not isinstance(required_evidence, list) or not required_evidence:
        raise TrustedDiscoveryAuthorizationError(
            "selected search action must declare required_evidence"
        )
    authorization = authorize_mission_pinned_trusted_discovery(
        program_state,
        trusted_policy_bytes=trusted_policy_bytes,
        provider=provider,
    )
    evidence_gap: object
    if len(required_evidence) == 1:
        evidence_gap = required_evidence[0]
    else:
        evidence_gap = {"evidence_requirements": list(required_evidence)}
    return {
        "schema_version": TRUSTED_DISCOVERY_AUTHORIZATION_SCHEMA_VERSION,
        "action_id": action.get("action_id"),
        "action_class": "external_evidence_search",
        "execution_mode": "explicit_authorization_required",
        "authorization": authorization,
        "evidence_gap": evidence_gap,
        "planner_gate_bypassed": False,
        "planner_gate_satisfied_by_pinned_policy": True,
        "scientific_status_changed": False,
    }


def run_mission_authorized_evidence_loop(
    program_state: Mapping[str, Any],
    self_directed_plan: Mapping[str, Any],
    *,
    trusted_policy_bytes: bytes,
    output_root: str | Path,
    provider: str = "nist_rmm",
    **loop_kwargs: Any,
) -> dict[str, Any]:
    """Compile the trusted handoff and run the bounded external-evidence loop."""
    handoff = compile_trusted_discovery_handoff(
        program_state,
        self_directed_plan,
        trusted_policy_bytes=trusted_policy_bytes,
        provider=provider,
    )
    result = run_autonomous_evidence_loop(
        handoff["evidence_gap"],
        output_root=output_root,
        **loop_kwargs,
    )
    return {
        "schema_version": TRUSTED_DISCOVERY_AUTHORIZATION_SCHEMA_VERSION,
        "handoff": handoff,
        "evidence_loop": result,
        "planner_gate_bypassed": False,
        "physical_experiment_execution_authorized": False,
    }


__all__ = [
    "TRUSTED_DISCOVERY_AUTHORIZATION_POLICY_VERSION",
    "TRUSTED_DISCOVERY_AUTHORIZATION_SCHEMA_VERSION",
    "TrustedDiscoveryAuthorizationError",
    "authorize_mission_pinned_trusted_discovery",
    "compile_trusted_discovery_handoff",
    "run_mission_authorized_evidence_loop",
]
