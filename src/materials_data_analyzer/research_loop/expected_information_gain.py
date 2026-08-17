"""Expected-information-gain utilities with an explicit probabilistic-model gate."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

EXPECTED_INFORMATION_GAIN_POLICY_VERSION = "1.0"


class ExpectedInformationGainError(ResearchLoopError):
    """Raised when probabilistic EIG inputs violate their declared contract."""


def _probabilities(values: Sequence[float], field: str) -> list[float]:
    if not values:
        raise ExpectedInformationGainError(f"{field} must not be empty")
    normalized: list[float] = []
    for raw in values:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ExpectedInformationGainError(f"{field} must be numeric")
        value = float(raw)
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            raise ExpectedInformationGainError(f"{field} values must be probabilities")
        normalized.append(value)
    if not math.isclose(sum(normalized), 1.0, rel_tol=0.0, abs_tol=1e-10):
        raise ExpectedInformationGainError(f"{field} probabilities must sum to 1")
    return normalized


def entropy_bits(probabilities: Sequence[float]) -> float:
    values = _probabilities(probabilities, "probabilities")
    return -sum(value * math.log2(value) for value in values if value > 0.0)


def expected_information_gain(
    *,
    prior_hypothesis_probabilities: Sequence[float],
    outcome_probabilities: Sequence[float],
    posterior_probabilities_by_outcome: Sequence[Sequence[float]],
    probabilistic_model_validated: bool,
    model_artifact_sha256: str | None,
    action_cost_units: float = 1.0,
) -> dict[str, Any]:
    """Compute Shannon EIG only for a separately validated probabilistic model."""
    if not isinstance(probabilistic_model_validated, bool):
        raise ExpectedInformationGainError("probabilistic_model_validated must be boolean")
    if isinstance(action_cost_units, bool) or not isinstance(action_cost_units, (int, float)):
        raise ExpectedInformationGainError("action_cost_units must be numeric")
    cost = float(action_cost_units)
    if not math.isfinite(cost) or cost <= 0:
        raise ExpectedInformationGainError("action_cost_units must be positive and finite")
    if not probabilistic_model_validated:
        return {
            "policy_version": EXPECTED_INFORMATION_GAIN_POLICY_VERSION,
            "mode": "structural_proxy_only",
            "eig_bits": None,
            "eig_per_cost_unit": None,
            "reason": "validated_probabilistic_model_not_available",
            "scientific_status_changed": False,
        }
    if not isinstance(model_artifact_sha256, str) or len(model_artifact_sha256) != 64:
        raise ExpectedInformationGainError(
            "validated probabilistic EIG requires a SHA-256 model artifact binding"
        )
    digest = model_artifact_sha256.lower()
    if any(char not in "0123456789abcdef" for char in digest):
        raise ExpectedInformationGainError("model_artifact_sha256 must be lowercase SHA-256")
    prior = _probabilities(prior_hypothesis_probabilities, "prior_hypothesis_probabilities")
    outcomes = _probabilities(outcome_probabilities, "outcome_probabilities")
    if len(outcomes) != len(posterior_probabilities_by_outcome):
        raise ExpectedInformationGainError(
            "one posterior distribution is required for each outcome probability"
        )
    posteriors = [
        _probabilities(values, f"posterior_probabilities_by_outcome[{index}]")
        for index, values in enumerate(posterior_probabilities_by_outcome)
    ]
    if any(len(values) != len(prior) for values in posteriors):
        raise ExpectedInformationGainError(
            "posterior and prior hypothesis dimensions must match"
        )
    prior_entropy = entropy_bits(prior)
    expected_posterior_entropy = sum(
        probability * entropy_bits(posterior)
        for probability, posterior in zip(outcomes, posteriors, strict=True)
    )
    eig = prior_entropy - expected_posterior_entropy
    if eig < -1e-10:
        raise ExpectedInformationGainError(
            "declared predictive/posterior distributions produce negative EIG"
        )
    eig = max(0.0, eig)
    return {
        "policy_version": EXPECTED_INFORMATION_GAIN_POLICY_VERSION,
        "mode": "probabilistic_eig",
        "model_artifact_sha256": digest,
        "prior_entropy_bits": prior_entropy,
        "expected_posterior_entropy_bits": expected_posterior_entropy,
        "eig_bits": eig,
        "action_cost_units": cost,
        "eig_per_cost_unit": eig / cost,
        "scientific_status_changed": False,
    }


def rank_actions_by_eig(results: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank only true probabilistic-EIG results; structural proxies stay unranked."""
    ranked: list[dict[str, Any]] = []
    for action_id, result in results.items():
        if result.get("mode") != "probabilistic_eig":
            continue
        value = result.get("eig_per_cost_unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExpectedInformationGainError("invalid eig_per_cost_unit")
        ranked.append({"action_id": str(action_id), "eig_per_cost_unit": float(value)})
    ranked.sort(key=lambda item: (-item["eig_per_cost_unit"], item["action_id"]))
    return ranked


__all__ = [
    "EXPECTED_INFORMATION_GAIN_POLICY_VERSION",
    "ExpectedInformationGainError",
    "entropy_bits",
    "expected_information_gain",
    "rank_actions_by_eig",
]
