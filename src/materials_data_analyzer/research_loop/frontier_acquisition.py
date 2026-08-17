"""Bridge machine-actionable research frontiers to bounded source acquisition.

A research planner should select a scientific candidate, not reconstruct download URLs
or ask a human to approve every public file. This bridge validates a candidate's exact
acquisition plan and dispatches it to a source adapter. Candidates without such a plan
remain discovery-only and cannot be silently executed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .nist_pdr_acquisition import acquire_nist_pdr_auto_candidates
from .public_data_acquisition import (
    DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    PublicFetcher,
    fetch_https_bytes,
)

FRONTIER_ACQUISITION_PLAN_SCHEMA_VERSION = "1.0"
_PLAN_KEYS = {
    "adapter",
    "product_id",
    "filepaths",
    "approval_mode",
    "human_review_is_exception_only",
}


class FrontierAcquisitionError(ResearchLoopError):
    """Raised when a research-frontier acquisition plan is missing or malformed."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrontierAcquisitionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_frontier(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrontierAcquisitionError("frontier must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise FrontierAcquisitionError("frontier root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrontierAcquisitionError(f"{field} must be non-empty text")
    if value != value.strip():
        raise FrontierAcquisitionError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _candidate(frontier: Mapping[str, Any], candidate_id: str) -> dict[str, Any]:
    requested = _strict_text(candidate_id, "candidate_id")
    candidates = frontier.get("candidates")
    if not isinstance(candidates, list):
        raise FrontierAcquisitionError("frontier candidates must be a list")
    matches = [
        item
        for item in candidates
        if isinstance(item, dict) and item.get("candidate_id") == requested
    ]
    if len(matches) != 1:
        raise FrontierAcquisitionError(
            f"candidate_id must resolve exactly once in frontier: {requested!r}"
        )
    return matches[0]


def normalize_frontier_acquisition_plan(
    frontier: Mapping[str, Any], candidate_id: str
) -> dict[str, Any]:
    """Return the exact machine-actionable acquisition plan for one candidate."""

    candidate = _candidate(frontier, candidate_id)
    raw = candidate.get("automatic_acquisition_plan")
    if not isinstance(raw, Mapping):
        raise FrontierAcquisitionError(
            "candidate is discovery-only; no automatic_acquisition_plan is declared"
        )
    missing = sorted(_PLAN_KEYS - set(raw))
    unknown = sorted(set(raw) - _PLAN_KEYS)
    if missing or unknown:
        raise FrontierAcquisitionError(
            "automatic_acquisition_plan must use the exact key set; "
            f"unknown={unknown}, missing={missing}"
        )
    adapter = _strict_text(raw["adapter"], "automatic_acquisition_plan.adapter")
    if adapter != "nist_pdr":
        raise FrontierAcquisitionError(
            f"unsupported automatic acquisition adapter: {adapter!r}"
        )
    product_id = _strict_text(
        raw["product_id"], "automatic_acquisition_plan.product_id"
    )
    filepaths = raw["filepaths"]
    if not isinstance(filepaths, list) or not filepaths:
        raise FrontierAcquisitionError(
            "automatic_acquisition_plan.filepaths must be a non-empty list"
        )
    normalized_paths: list[str] = []
    for index, value in enumerate(filepaths):
        text = _strict_text(value, f"automatic_acquisition_plan.filepaths[{index}]")
        if text in normalized_paths:
            raise FrontierAcquisitionError(
                "automatic_acquisition_plan.filepaths must not contain duplicates"
            )
        normalized_paths.append(text)
    approval_mode = _strict_text(
        raw["approval_mode"], "automatic_acquisition_plan.approval_mode"
    )
    if approval_mode != "automatic_when_public_checksum_bound_policy_passes":
        raise FrontierAcquisitionError(
            "automatic_acquisition_plan approval_mode is not executable"
        )
    if raw["human_review_is_exception_only"] is not True:
        raise FrontierAcquisitionError(
            "automatic acquisition requires human_review_is_exception_only=true"
        )
    return {
        "schema_version": FRONTIER_ACQUISITION_PLAN_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "adapter": adapter,
        "product_id": product_id,
        "filepaths": normalized_paths,
        "approval_mode": approval_mode,
        "human_review_is_exception_only": True,
    }


def load_frontier_acquisition_plan(
    frontier_path: str | Path, candidate_id: str
) -> dict[str, Any]:
    """Load and validate a frontier acquisition plan from exact local JSON bytes."""

    frontier = _load_frontier(frontier_path)
    return normalize_frontier_acquisition_plan(frontier, candidate_id)


def acquire_frontier_candidate(
    *,
    frontier_path: str | Path,
    candidate_id: str,
    output_root: str | Path,
    fetcher: PublicFetcher = fetch_https_bytes,
    overwrite: bool = False,
    timeout_seconds: float = 60.0,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Execute the declared AUTO acquisition path for one scientific candidate."""

    plan = load_frontier_acquisition_plan(frontier_path, candidate_id)
    if plan["adapter"] == "nist_pdr":
        result = acquire_nist_pdr_auto_candidates(
            product_id=plan["product_id"],
            output_root=output_root,
            filepaths=plan["filepaths"],
            fetcher=fetcher,
            overwrite=overwrite,
            timeout_seconds=timeout_seconds,
            max_auto_bytes=max_auto_bytes,
        )
    else:  # pragma: no cover - normalize_frontier_acquisition_plan is fail-closed.
        raise FrontierAcquisitionError(
            f"unsupported automatic acquisition adapter: {plan['adapter']!r}"
        )
    return {
        "schema_version": FRONTIER_ACQUISITION_PLAN_SCHEMA_VERSION,
        "frontier_candidate_id": plan["candidate_id"],
        "adapter": plan["adapter"],
        "approval_mode": plan["approval_mode"],
        "human_review_is_exception_only": True,
        "acquisition": result,
        "scientific_status_changed": False,
        "requires_scientific_intake": True,
    }


__all__ = [
    "FRONTIER_ACQUISITION_PLAN_SCHEMA_VERSION",
    "FrontierAcquisitionError",
    "acquire_frontier_candidate",
    "load_frontier_acquisition_plan",
    "normalize_frontier_acquisition_plan",
]
