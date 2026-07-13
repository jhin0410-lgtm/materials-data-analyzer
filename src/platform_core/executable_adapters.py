"""Approved adapter callable mapping."""

from __future__ import annotations

from .case_adapters.reliability import execute_reliability_trust_verify
from .execution_runtime import AdapterCallable


def build_approved_adapter_callables() -> dict[str, AdapterCallable]:
    """Return the explicit callable allowlist.

    The keys are adapter IDs from the adapter registry. No callable path comes
    from user config.
    """

    return {
        "reliability_trust_closeout": execute_reliability_trust_verify,
    }
