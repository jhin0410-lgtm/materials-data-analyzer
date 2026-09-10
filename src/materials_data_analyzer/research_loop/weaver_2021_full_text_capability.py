"""Bounded capability descriptor for Weaver 2021 derived full-text acquisition."""
from __future__ import annotations

from .weaver_2021_full_text_policy import ACTION_CLASS

FACTORY_ID = "bounded-derived-primary-full-text-acquisition-v1"
IMPLEMENTATION_ID = "weaver-2021-pmc-bioc-derived-full-text-acquisition-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
    "provenance_bound_calibration_intake",
)
MECHANISM = "compose_verified_primitives"

__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "MECHANISM",
    "REQUIRED_VERIFIED_PRIMITIVES",
]
