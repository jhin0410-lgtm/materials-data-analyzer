"""Conservative eligibility gates for advanced statistical analysis.

The module decides which model families are scientifically eligible from declared
physical lineage.  It does not infer missing grouping variables and does not treat rows as
independent experimental units by default.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .experimental_lineage import ObservationLineage, effective_independent_unit
from .kernel import ResearchLoopError

ADVANCED_STATISTICS_GATE_VERSION = "1.0"


class AdvancedStatisticsGateError(ResearchLoopError):
    """Raised when statistical eligibility inputs are malformed."""


def assess_statistical_model_eligibility(
    lineages: Sequence[ObservationLineage],
    *,
    fixed_effects_declared: bool,
    repeated_measurements_expected: bool,
) -> dict[str, Any]:
    if not lineages:
        raise AdvancedStatisticsGateError("lineages must not be empty")
    if not isinstance(fixed_effects_declared, bool):
        raise AdvancedStatisticsGateError("fixed_effects_declared must be boolean")
    if not isinstance(repeated_measurements_expected, bool):
        raise AdvancedStatisticsGateError("repeated_measurements_expected must be boolean")

    counts = effective_independent_unit(list(lineages))
    builds = counts["unique_builds_or_syntheses"]
    lots = counts["unique_material_lots"]
    labs = counts["unique_labs"]
    specimens = counts["unique_specimens"]
    acquisitions = counts["unique_acquisitions"]
    blockers: list[str] = []
    if counts["missing_lineage_prevents_inference"]:
        blockers.append("incomplete_physical_lineage")
    if not fixed_effects_declared:
        blockers.append("fixed_effect_semantics_not_declared")

    has_repeated_measurement_structure = acquisitions > specimens or counts["unique_measurements"] > acquisitions
    mixed_effects = (
        not blockers
        and fixed_effects_declared
        and specimens >= 2
        and (repeated_measurements_expected or has_repeated_measurement_structure)
    )
    variance_components = (
        not counts["missing_lineage_prevents_inference"]
        and isinstance(builds, int)
        and isinstance(lots, int)
        and builds >= 2
        and lots >= 1
        and specimens >= 2
    )
    hierarchical = (
        variance_components
        and isinstance(labs, int)
        and labs >= 2
        and isinstance(lots, int)
        and lots >= 2
    )
    naive_independent_rows = (
        counts["row_count"] == counts["unique_measurements"]
        == counts["unique_acquisitions"]
        == counts["unique_specimens"]
        and not counts["missing_lineage_prevents_inference"]
    )
    return {
        "policy_version": ADVANCED_STATISTICS_GATE_VERSION,
        "physical_counts": counts,
        "descriptive_analysis_eligible": True,
        "naive_independent_row_model_eligible": naive_independent_rows,
        "fixed_effect_model_eligible": fixed_effects_declared and not blockers,
        "mixed_effect_model_eligible": mixed_effects,
        "variance_components_eligible": variance_components,
        "hierarchical_model_eligible": hierarchical,
        "blocker_codes": blockers,
        "row_count_used_as_independence_without_lineage": False,
        "scientific_status_changed": False,
    }


def propagate_independent_standard_uncertainty(
    *,
    sensitivities: Sequence[float],
    standard_uncertainties: Sequence[float],
    independence_explicitly_established: bool,
) -> dict[str, Any]:
    """First-order RSS propagation only when independence is explicitly established."""
    if len(sensitivities) != len(standard_uncertainties) or not sensitivities:
        raise AdvancedStatisticsGateError(
            "sensitivities and standard_uncertainties must have equal non-zero length"
        )
    if not isinstance(independence_explicitly_established, bool):
        raise AdvancedStatisticsGateError(
            "independence_explicitly_established must be boolean"
        )
    terms: list[float] = []
    for sensitivity, uncertainty in zip(sensitivities, standard_uncertainties, strict=True):
        if isinstance(sensitivity, bool) or not isinstance(sensitivity, (int, float)):
            raise AdvancedStatisticsGateError("sensitivities must be numeric")
        if isinstance(uncertainty, bool) or not isinstance(uncertainty, (int, float)):
            raise AdvancedStatisticsGateError("standard_uncertainties must be numeric")
        if not math.isfinite(float(sensitivity)) or not math.isfinite(float(uncertainty)):
            raise AdvancedStatisticsGateError("uncertainty inputs must be finite")
        if uncertainty < 0:
            raise AdvancedStatisticsGateError("standard_uncertainties must be non-negative")
        terms.append((float(sensitivity) * float(uncertainty)) ** 2)
    if not independence_explicitly_established:
        return {
            "policy_version": ADVANCED_STATISTICS_GATE_VERSION,
            "eligible": False,
            "combined_standard_uncertainty": None,
            "reason": "covariance_or_independence_not_established",
            "scientific_status_changed": False,
        }
    return {
        "policy_version": ADVANCED_STATISTICS_GATE_VERSION,
        "eligible": True,
        "combined_standard_uncertainty": math.sqrt(sum(terms)),
        "reason": "independent_first_order_rss",
        "scientific_status_changed": False,
    }


__all__ = [
    "ADVANCED_STATISTICS_GATE_VERSION",
    "AdvancedStatisticsGateError",
    "assess_statistical_model_eligibility",
    "propagate_independent_standard_uncertainty",
]
