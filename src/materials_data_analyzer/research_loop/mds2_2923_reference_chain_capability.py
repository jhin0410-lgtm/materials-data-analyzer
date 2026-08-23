"""Bounded capability descriptor for mds2-2923 experiment-identity assessment.

The descriptor names only primitives that were already exercised by predecessor production
capabilities.  Naderi claim extraction and reference-graph construction are implementation
responsibilities that must pass this capability's independent verifier; they are deliberately
not listed as pre-verified primitives.
"""
from __future__ import annotations

from .nist_mds2_2923_reference_chain_policy import ACTION_CLASS

FACTORY_ID = "bounded-provenance-reference-graph-v1"
IMPLEMENTATION_ID = "mds2-2923-experiment-identity-reference-chain-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "exact_allowlisted_source_acquisition",
    "provenance_bound_calibration_intake",
    "provenance_bound_bridge_frontier_evaluation",
)
MECHANISM = "compose_verified_primitives"

__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "MECHANISM",
    "REQUIRED_VERIFIED_PRIMITIVES",
]
