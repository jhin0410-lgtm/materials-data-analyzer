"""Strict public facade for the canonical ResearchRun architecture contract."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import canonical_research_run_impl as _impl

RESEARCH_RUN_SCHEMA_VERSION = _impl.RESEARCH_RUN_SCHEMA_VERSION
RESEARCH_RUN_POLICY_VERSION = _impl.RESEARCH_RUN_POLICY_VERSION
RESEARCH_RUN_SECTIONS = _impl.RESEARCH_RUN_SECTIONS
SCIENTIFIC_STATE_COLLECTIONS = _impl.SCIENTIFIC_STATE_COLLECTIONS
GOVERNANCE_STATE_COLLECTIONS = _impl.GOVERNANCE_STATE_COLLECTIONS
RUN_LIFECYCLE_STATES = _impl.RUN_LIFECYCLE_STATES
SCIENTIFIC_STOP_DISPOSITIONS = _impl.SCIENTIFIC_STOP_DISPOSITIONS
DERIVED_PROJECTIONS = _impl.DERIVED_PROJECTIONS
ScientificEntityAuthoritySource = _impl.ScientificEntityAuthoritySource
SCIENTIFIC_ENTITY_AUTHORITY_SOURCES = _impl.SCIENTIFIC_ENTITY_AUTHORITY_SOURCES
CanonicalResearchRunError = _impl.CanonicalResearchRunError


def _typed_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return type(observed) is bool and observed is expected
    if isinstance(expected, int):
        return type(observed) is int and observed == expected
    if expected is None or isinstance(expected, str):
        return type(observed) is type(expected) and observed == expected
    if isinstance(expected, list):
        return isinstance(observed, list) and len(observed) == len(expected) and all(
            _typed_equal(left, right) for left, right in zip(observed, expected, strict=True)
        )
    if isinstance(expected, Mapping):
        if not isinstance(observed, Mapping) or set(observed) != set(expected):
            return False
        return all(_typed_equal(observed[key], expected[key]) for key in expected)
    return type(observed) is type(expected) and observed == expected


def build_canonical_research_run_contract() -> dict[str, Any]:
    return _impl.build_canonical_research_run_contract()


def validate_canonical_research_run_contract(value: object) -> dict[str, Any]:
    """Validate all nested values with exact JSON/Python scalar types."""
    if not isinstance(value, Mapping):
        raise CanonicalResearchRunError("canonical ResearchRun contract must be an object")
    missing = sorted(_impl._REQUIRED_KEYS - set(value))
    unknown = sorted(set(value) - _impl._REQUIRED_KEYS)
    if missing or unknown:
        raise CanonicalResearchRunError(
            f"canonical ResearchRun contract must use exact keys; unknown={unknown}, missing={missing}"
        )
    expected = build_canonical_research_run_contract()
    if not _typed_equal(value, expected):
        raise CanonicalResearchRunError("canonical ResearchRun contract drifted")
    return expected


__all__ = [
    "CanonicalResearchRunError",
    "DERIVED_PROJECTIONS",
    "GOVERNANCE_STATE_COLLECTIONS",
    "RESEARCH_RUN_POLICY_VERSION",
    "RESEARCH_RUN_SCHEMA_VERSION",
    "RESEARCH_RUN_SECTIONS",
    "RUN_LIFECYCLE_STATES",
    "SCIENTIFIC_ENTITY_AUTHORITY_SOURCES",
    "SCIENTIFIC_STATE_COLLECTIONS",
    "SCIENTIFIC_STOP_DISPOSITIONS",
    "ScientificEntityAuthoritySource",
    "build_canonical_research_run_contract",
    "validate_canonical_research_run_contract",
]
