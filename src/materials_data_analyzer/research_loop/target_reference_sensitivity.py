"""Compatibility surface for the leakage-bounded target-reference analysis."""

from .target_reference_analysis import (
    REFERENCE_DEFINITIONS,
    SCHEMA_VERSION,
    TargetReferenceSensitivityError,
    build_target_reference_sensitivity,
)

__all__ = [
    "REFERENCE_DEFINITIONS",
    "SCHEMA_VERSION",
    "TargetReferenceSensitivityError",
    "build_target_reference_sensitivity",
]
