"""Transitive byte-binding facade for the Weaver 2021 capability verifier.

The implementation performs the scientific and replay checks.  This facade additionally binds
all executable Weaver verifier/acquisition/policy layers so a stable facade cannot hide a changed
implementation module.  It also preserves the explicit fetch seam used by deterministic tests.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import capability_smoke_replay_evidence as smoke_replay
from . import weaver_2021_full_text_acquisition as acquisition
from . import weaver_2021_full_text_acquisition_impl as acquisition_impl
from . import weaver_2021_full_text_capability_verifier_impl as _impl
from . import weaver_2021_full_text_policy as policy
from . import weaver_2021_full_text_policy_impl as policy_impl
from .in625_geometry_condition_source_acquisition import fetch_exact_source

VERIFIER_SCHEMA_VERSION = "2.0"
VERIFIER_POLICY_VERSION = "2.0"
Weaver2021FullTextCapabilityVerifierError = _impl.Weaver2021FullTextCapabilityVerifierError


class Weaver2021VerifierByteBindingError(Weaver2021FullTextCapabilityVerifierError):
    """Raised when a transitive Weaver code-byte binding cannot be authenticated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Weaver2021VerifierByteBindingError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _module_sha(module: object, field: str) -> str:
    raw_path = getattr(module, "__file__", None)
    _require(isinstance(raw_path, str) and raw_path, f"{field} module path missing")
    return hashlib.sha256(Path(raw_path).resolve(strict=True).read_bytes()).hexdigest()


def _authenticate_inner_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    supplied = value.get("capability_verification_sha256_without_self_field")
    _require(
        isinstance(supplied, str) and len(supplied) == 64,
        "inner Weaver verification self binding is missing",
    )
    unsigned = dict(value)
    unsigned.pop("capability_verification_sha256_without_self_field", None)
    _require(
        _canonical_sha(unsigned) == supplied,
        "inner Weaver verification self binding is invalid",
    )
    return unsigned


def verify_weaver_2021_full_text_capability_candidate(
    *,
    capability_specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    verification_context: Mapping[str, Any] | None,
    perform_real_source_smoke: bool = True,
    retained_smoke_replay_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the Weaver verifier and bind every transitive executable module into its receipt."""

    original_fetcher = _impl.fetch_exact_source
    _impl.fetch_exact_source = fetch_exact_source
    try:
        inner = _impl.verify_weaver_2021_full_text_capability_candidate(
            capability_specification=capability_specification,
            candidate=candidate,
            available_verified_primitives=available_verified_primitives,
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
            verification_context=verification_context,
            perform_real_source_smoke=perform_real_source_smoke,
            retained_smoke_replay_evidence=retained_smoke_replay_evidence,
        )
    finally:
        _impl.fetch_exact_source = original_fetcher

    unsigned = _authenticate_inner_receipt(inner)
    components = {
        "capability_descriptor_sha256": unsigned.get(
            "implementation_component_sha256", {}
        ).get("capability_descriptor_sha256"),
        "acquisition_facade_sha256": _module_sha(acquisition, "acquisition facade"),
        "acquisition_implementation_sha256": _module_sha(
            acquisition_impl,
            "acquisition implementation",
        ),
        "policy_facade_sha256": _module_sha(policy, "policy facade"),
        "policy_implementation_sha256": _module_sha(policy_impl, "policy implementation"),
        "smoke_replay_helper_sha256": _module_sha(smoke_replay, "smoke replay helper"),
        "verifier_implementation_sha256": _module_sha(_impl, "verifier implementation"),
    }
    _require(
        all(isinstance(value, str) and len(value) == 64 for value in components.values()),
        "transitive Weaver implementation SHA-256 binding is incomplete",
    )
    facade_sha = hashlib.sha256(Path(__file__).resolve(strict=True).read_bytes()).hexdigest()
    unsigned.update(
        {
            "verifier_schema_version": VERIFIER_SCHEMA_VERSION,
            "verifier_policy_version": VERIFIER_POLICY_VERSION,
            "implementation_component_sha256": components,
            "implementation_sha256": _canonical_sha(components),
            "verifier_implementation_sha256": components[
                "verifier_implementation_sha256"
            ],
            "verifier_facade_sha256": facade_sha,
            "verifier_sha256": facade_sha,
            "complete_transitive_byte_binding_verified": True,
        }
    )
    verification_results = unsigned.get("verification_results")
    _require(
        isinstance(verification_results, Mapping)
        and verification_results.get(
            "exact_spec_implementation_and_verifier_byte_bindings"
        )
        is True,
        "inner Weaver byte-binding verification did not pass",
    )
    unsigned["capability_verification_sha256_without_self_field"] = _canonical_sha(unsigned)
    return unsigned


__all__ = [
    "VERIFIER_POLICY_VERSION",
    "VERIFIER_SCHEMA_VERSION",
    "Weaver2021FullTextCapabilityVerifierError",
    "Weaver2021VerifierByteBindingError",
    "verify_weaver_2021_full_text_capability_candidate",
]
