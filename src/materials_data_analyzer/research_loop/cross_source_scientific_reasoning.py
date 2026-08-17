"""Fail-closed cross-source comparability, uncertainty, contradiction, and analysis routing."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.0"


class CrossSourceReasoningError(ResearchLoopError):
    """Raised when cross-source reasoning would require an undeclared assumption."""


def _text(value: str | None, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CrossSourceReasoningError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class ComparabilityContext:
    material_id: str
    property_name: str
    unit: str
    process_signature: str | None
    instrument_model: str | None
    calibration_id: str | None
    source_id: str
    independence_group: str | None = None

    def __post_init__(self) -> None:
        for field in ("material_id", "property_name", "unit", "source_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in (
            "process_signature",
            "instrument_model",
            "calibration_id",
            "independence_group",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, optional=True),
            )


@dataclass(frozen=True)
class ComparabilityDecision:
    comparable: bool
    reasons: tuple[str, ...]
    right_to_left_unit_factor: float | None


def assess_comparability(
    left: ComparabilityContext,
    right: ComparabilityContext,
    *,
    explicit_unit_conversions: Mapping[tuple[str, str], float] | None = None,
    require_process_match: bool = True,
    require_instrument_match: bool = False,
    require_calibration_match: bool = False,
    require_independence: bool = False,
) -> ComparabilityDecision:
    reasons: list[str] = []
    if left.material_id != right.material_id:
        reasons.append("material_mismatch")
    if left.property_name != right.property_name:
        reasons.append("property_mismatch")
    if require_process_match and left.process_signature != right.process_signature:
        reasons.append("process_signature_mismatch")
    if require_instrument_match and left.instrument_model != right.instrument_model:
        reasons.append("instrument_model_mismatch")
    if require_calibration_match and left.calibration_id != right.calibration_id:
        reasons.append("calibration_mismatch")
    if require_independence:
        if left.source_id == right.source_id:
            reasons.append("independent_source_not_demonstrated")
        if left.independence_group is None or right.independence_group is None:
            reasons.append("independence_group_missing")
        elif left.independence_group == right.independence_group:
            reasons.append("independence_not_demonstrated")

    factor: float | None = 1.0
    if left.unit != right.unit:
        factor = (explicit_unit_conversions or {}).get((right.unit, left.unit))
        if factor is None or not math.isfinite(float(factor)) or float(factor) == 0:
            factor = None
            reasons.append("unit_conversion_not_explicitly_declared")
        else:
            factor = float(factor)
    return ComparabilityDecision(not reasons, tuple(reasons), factor)


@dataclass(frozen=True)
class UncertaintyComponent:
    category: str
    standard_uncertainty: float
    source: str

    def __post_init__(self) -> None:
        if self.category not in {
            "measurement",
            "model",
            "sampling",
            "extrapolation",
            "provenance",
        }:
            raise CrossSourceReasoningError("unsupported uncertainty category")
        if not self.source.strip():
            raise CrossSourceReasoningError("uncertainty source must be non-empty")
        if (
            not math.isfinite(self.standard_uncertainty)
            or self.standard_uncertainty < 0
        ):
            raise CrossSourceReasoningError(
                "standard uncertainty must be finite and non-negative"
            )


def combine_uncertainty(
    components: tuple[UncertaintyComponent, ...],
    *,
    independence_explicitly_established: bool,
) -> float:
    if not components:
        raise CrossSourceReasoningError(
            "at least one uncertainty component is required"
        )
    values = [item.standard_uncertainty for item in components]
    if independence_explicitly_established:
        return math.sqrt(sum(value * value for value in values))
    return sum(values)


@dataclass(frozen=True)
class EffectEstimate:
    context: ComparabilityContext
    effect: float
    standard_uncertainty: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.effect):
            raise CrossSourceReasoningError("effect must be finite")
        if (
            not math.isfinite(self.standard_uncertainty)
            or self.standard_uncertainty < 0
        ):
            raise CrossSourceReasoningError(
                "effect uncertainty must be finite and non-negative"
            )


def detect_verified_directional_contradiction(
    left: EffectEstimate,
    right: EffectEstimate,
    *,
    explicit_unit_conversions: Mapping[tuple[str, str], float] | None = None,
    interval_multiplier: float = 1.96,
) -> tuple[bool, ComparabilityDecision]:
    """Detect only confidently opposite effects from comparable independent evidence."""
    if interval_multiplier <= 0 or not math.isfinite(interval_multiplier):
        raise CrossSourceReasoningError(
            "interval_multiplier must be finite and positive"
        )
    decision = assess_comparability(
        left.context,
        right.context,
        explicit_unit_conversions=explicit_unit_conversions,
        require_independence=True,
    )
    if not decision.comparable:
        return False, decision
    factor = decision.right_to_left_unit_factor or 1.0
    left_low = left.effect - interval_multiplier * left.standard_uncertainty
    left_high = left.effect + interval_multiplier * left.standard_uncertainty
    right_effect = right.effect * factor
    right_uncertainty = right.standard_uncertainty * abs(factor)
    right_low = right_effect - interval_multiplier * right_uncertainty
    right_high = right_effect + interval_multiplier * right_uncertainty
    contradiction = (left_low > 0 and right_high < 0) or (
        left_high < 0 and right_low > 0
    )
    return contradiction, decision


@dataclass(frozen=True)
class AnalysisTraits:
    n_samples: int
    n_numeric_predictors: int
    target_kind: str
    group_count: int = 0
    repeated_measure_groups: int = 0

    def __post_init__(self) -> None:
        for field in (
            "n_samples",
            "n_numeric_predictors",
            "group_count",
            "repeated_measure_groups",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CrossSourceReasoningError(
                    "analysis trait counts must be non-negative integers"
                )
        if self.target_kind not in {"continuous", "categorical", "none"}:
            raise CrossSourceReasoningError("unsupported target_kind")


@dataclass(frozen=True)
class AnalysisRecommendation:
    action_class: str
    analysis_type: str
    executable: bool
    rationale: tuple[str, ...]


def select_next_analysis(traits: AnalysisTraits) -> AnalysisRecommendation:
    """Select one analysis contract; execution stays in the existing typed-action layer."""
    if traits.repeated_measure_groups >= 2 and traits.n_samples >= 6:
        return AnalysisRecommendation(
            "existing_data_reanalysis",
            "group_aware_repeated_measure_analysis",
            True,
            ("repeated_measure_structure_detected", "group_aware_split_required"),
        )
    if (
        traits.target_kind == "continuous"
        and traits.n_numeric_predictors >= 1
        and traits.n_samples >= 8
    ):
        return AnalysisRecommendation(
            "existing_data_reanalysis",
            "bounded_regression",
            True,
            (
                "continuous_target",
                "numeric_predictor_available",
                "minimum_sample_contract_met",
            ),
        )
    if (
        traits.target_kind == "continuous"
        and traits.group_count >= 2
        and traits.n_samples >= 6
    ):
        return AnalysisRecommendation(
            "existing_data_reanalysis",
            "bounded_group_comparison",
            True,
            (
                "continuous_target",
                "multiple_groups",
                "minimum_sample_contract_met",
            ),
        )
    if traits.n_numeric_predictors >= 2 and traits.n_samples >= 5:
        return AnalysisRecommendation(
            "existing_data_reanalysis",
            "exploratory_structure_analysis",
            True,
            ("multiple_numeric_variables", "exploratory_only"),
        )
    return AnalysisRecommendation(
        "review",
        "insufficient_analysis_preconditions",
        False,
        ("no_registered_analysis_contract_has_satisfied_preconditions",),
    )


__all__ = [
    "AnalysisRecommendation",
    "AnalysisTraits",
    "ComparabilityContext",
    "ComparabilityDecision",
    "CrossSourceReasoningError",
    "EffectEstimate",
    "SCHEMA_VERSION",
    "UncertaintyComponent",
    "assess_comparability",
    "combine_uncertainty",
    "detect_verified_directional_contradiction",
    "select_next_analysis",
]
