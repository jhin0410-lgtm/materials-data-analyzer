"""Exact mission/policy bindings shared by both accepted autonomous live outcomes.

A canonical self-hash proves only internal consistency.  This verifier anchors the persisted
NIST qualification and authorization to the exact mission and policy SHA-256 values used by
the audited production profile, then binds those values into cycle 3 and the final manifest.
It performs no network access and cannot promote scientific status.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACTION_CLASS,
    POLICY_ID as NIST_POLICY_ID,
)

EXPECTED_MISSION_SHA256 = (
    "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
)
EXPECTED_NIST_POLICY_SHA256 = (
    "4b19c64f4f2c764f5315971c5afba16000763a4d307929ec5e463f42ee1cbebf"
)


class AutonomousProductionAuthorityBindingError(ValueError):
    """Raised when persisted execution authority is only self-consistent, not exact-bound."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionAuthorityBindingError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionAuthorityBindingError(
            f"{name} must be valid persisted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{name} root must be an object")
    return value


def _self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    digest = value.get(field)
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        f"{label} {field} is missing or non-canonical",
    )
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{label} self-hash mismatch")
    return digest


def verify_exact_authority_bindings(output_root: str | Path) -> None:
    """Reject re-hashed mission/policy substitutions on transport and full-success outputs."""
    root = Path(output_root).expanduser().resolve(strict=True)
    qualification = _load(root, "nist-network-policy-qualification.json")
    authorization = _load(root, "nist-network-authorization.json")
    manifest = _load(root, "autonomous-production-manifest.json")

    _self_hash(
        qualification,
        "qualification_sha256",
        "NIST network policy qualification",
    )
    authorization_sha = _self_hash(
        authorization,
        "authorization_sha256",
        "NIST network authorization",
    )

    _require(
        qualification.get("mission_sha256") == EXPECTED_MISSION_SHA256
        and qualification.get("policy_id") == NIST_POLICY_ID
        and qualification.get("policy_sha256") == EXPECTED_NIST_POLICY_SHA256,
        "NIST qualification exact mission/policy binding drifted",
    )
    _require(
        authorization.get("mission_sha256") == EXPECTED_MISSION_SHA256
        and authorization.get("policy_id") == NIST_POLICY_ID
        and authorization.get("policy_sha256") == EXPECTED_NIST_POLICY_SHA256,
        "NIST authorization exact mission/policy binding drifted",
    )
    _require(
        manifest.get("mission_sha256") == EXPECTED_MISSION_SHA256
        and manifest.get("nist_mds2_2923_policy_sha256")
        == EXPECTED_NIST_POLICY_SHA256,
        "autonomous manifest exact mission/NIST-policy binding drifted",
    )

    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) >= 3, "NIST authority cycle history is incomplete")
    cycle3 = cycles[2]
    _require(isinstance(cycle3, Mapping), "NIST authority cycle 3 must be an object")
    _require(
        cycle3.get("selected_action_class") == NIST_ACTION_CLASS
        and cycle3.get("network_policy_id") == NIST_POLICY_ID
        and cycle3.get("network_policy_sha256") == EXPECTED_NIST_POLICY_SHA256
        and cycle3.get("network_authorization_sha256") == authorization_sha,
        "cycle-3 exact NIST authority binding drifted",
    )

    persisted_authorization_sha = manifest.get(
        "nist_mds2_2923_network_authorization_sha256"
    )
    if persisted_authorization_sha is not None:
        _require(
            persisted_authorization_sha == authorization_sha,
            "autonomous manifest NIST authorization binding drifted",
        )


__all__ = [
    "AutonomousProductionAuthorityBindingError",
    "EXPECTED_MISSION_SHA256",
    "EXPECTED_NIST_POLICY_SHA256",
    "verify_exact_authority_bindings",
]
