"""Fail-closed downstream-use contract for characterization handoff bundles."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

POLICY_SCHEMA_VERSION = "1.0"
USE_LEVELS = (
    "display",
    "descriptive",
    "association",
    "predictive",
    "causal",
    "engineering",
)
FEATURE_STAGES = ("observable", "derived", "interpreted")
REVIEW_STATUSES = ("reviewed", "review_required", "unreviewed")
MEASUREMENT_TIMINGS = (
    "pre_outcome",
    "concurrent",
    "post_outcome",
    "unknown",
    "not_applicable",
)
EVIDENCE_LEVELS = ("Supported", "Diagnostic", "Inconclusive", "Unsupported")
ELIGIBILITY_FILE_NAME = "characterization_use_eligibility.json"
_POLICY_FIELDS = {
    "schema_version",
    "maximum_allowed_use",
    "feature_stage",
    "evidence_level",
    "review_status",
    "independence_group_field",
    "measurement_timing",
    "causal_design_validated",
    "operational_validation_validated",
    "limitations",
}


class CharacterizationUsePolicyError(ValueError):
    """Raised when policy content is malformed or the requested use is blocked."""


@dataclass(frozen=True)
class CharacterizationUseEligibility:
    requested_use: str
    allowed: bool
    maximum_allowed_use: str
    policy_source: str
    evidence_level: str
    feature_stage: str
    review_status: str
    independence_group_field: str | None
    split_group_field: str | None
    measurement_timing: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rank(value: str) -> int:
    try:
        return USE_LEVELS.index(value)
    except ValueError as exc:
        raise CharacterizationUsePolicyError(
            f"unsupported downstream use: {value!r}"
        ) from exc


def _text(policy: Mapping[str, object], field: str) -> str:
    value = policy.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationUsePolicyError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(policy: Mapping[str, object], field: str) -> str | None:
    value = policy.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationUsePolicyError(
            f"{field} must be null or a non-empty string"
        )
    return value.strip()


def _boolean(policy: Mapping[str, object], field: str) -> bool:
    value = policy.get(field)
    if not isinstance(value, bool):
        raise CharacterizationUsePolicyError(f"{field} must be a boolean")
    return value


def _string_list(policy: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = policy.get(field)
    if not isinstance(value, list):
        raise CharacterizationUsePolicyError(
            f"{field} must be a list of non-empty strings"
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CharacterizationUsePolicyError(
                f"{field} must contain only non-empty strings"
            )
        text = item.strip()
        if text in normalized:
            raise CharacterizationUsePolicyError(
                f"{field} must not contain duplicates"
            )
        normalized.append(text)
    return tuple(normalized)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharacterizationUsePolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_manifest_object(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(
            f"characterization bundle manifest not found or unsafe: {path}"
        )
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterizationUsePolicyError(
            f"could not read characterization bundle manifest: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise CharacterizationUsePolicyError("bundle manifest root must be an object")
    return payload


def _validate_policy(
    raw_policy: object,
    *,
    scientific_evidence_level: str,
) -> dict[str, Any]:
    if not isinstance(raw_policy, Mapping):
        raise CharacterizationUsePolicyError("downstream_use_policy must be an object")
    unknown = sorted(set(raw_policy) - _POLICY_FIELDS)
    missing = sorted(_POLICY_FIELDS - set(raw_policy))
    if unknown:
        raise CharacterizationUsePolicyError(
            f"downstream_use_policy contains unknown field: {unknown[0]}"
        )
    if missing:
        raise CharacterizationUsePolicyError(
            f"downstream_use_policy is missing field: {missing[0]}"
        )

    schema_version = _text(raw_policy, "schema_version")
    if schema_version != POLICY_SCHEMA_VERSION:
        raise CharacterizationUsePolicyError(
            "unsupported downstream_use_policy schema_version"
        )
    maximum_allowed_use = _text(raw_policy, "maximum_allowed_use")
    maximum_rank = _rank(maximum_allowed_use)
    feature_stage = _text(raw_policy, "feature_stage")
    if feature_stage not in FEATURE_STAGES:
        raise CharacterizationUsePolicyError(
            f"unsupported feature_stage: {feature_stage!r}"
        )
    evidence_level = _text(raw_policy, "evidence_level")
    if evidence_level not in EVIDENCE_LEVELS:
        raise CharacterizationUsePolicyError(
            f"unsupported evidence_level: {evidence_level!r}"
        )
    if evidence_level != scientific_evidence_level:
        raise CharacterizationUsePolicyError(
            "policy evidence_level must match scientific_closeout evidence_level"
        )
    review_status = _text(raw_policy, "review_status")
    if review_status not in REVIEW_STATUSES:
        raise CharacterizationUsePolicyError(
            f"unsupported review_status: {review_status!r}"
        )
    independence_group_field = _optional_text(
        raw_policy, "independence_group_field"
    )
    measurement_timing = _text(raw_policy, "measurement_timing")
    if measurement_timing not in MEASUREMENT_TIMINGS:
        raise CharacterizationUsePolicyError(
            f"unsupported measurement_timing: {measurement_timing!r}"
        )
    causal_validated = _boolean(raw_policy, "causal_design_validated")
    operational_validated = _boolean(
        raw_policy, "operational_validation_validated"
    )
    limitations = _string_list(raw_policy, "limitations")

    descriptive_rank = _rank("descriptive")
    association_rank = _rank("association")
    predictive_rank = _rank("predictive")
    causal_rank = _rank("causal")
    engineering_rank = _rank("engineering")

    if evidence_level in {"Inconclusive", "Unsupported"} and maximum_rank > descriptive_rank:
        raise CharacterizationUsePolicyError(
            f"{evidence_level} evidence cannot authorize use above descriptive"
        )
    if evidence_level == "Diagnostic" and maximum_rank > association_rank:
        raise CharacterizationUsePolicyError(
            "Diagnostic evidence cannot authorize use above association"
        )
    if (
        feature_stage == "interpreted"
        and review_status != "reviewed"
        and maximum_rank > descriptive_rank
    ):
        raise CharacterizationUsePolicyError(
            "unreviewed interpreted features cannot authorize use above descriptive"
        )
    if maximum_rank >= association_rank and independence_group_field is None:
        raise CharacterizationUsePolicyError(
            "association or stronger use requires independence_group_field"
        )
    if maximum_rank >= predictive_rank and measurement_timing != "pre_outcome":
        raise CharacterizationUsePolicyError(
            "predictive or stronger use requires pre_outcome measurement_timing"
        )
    if maximum_rank >= causal_rank and not causal_validated:
        raise CharacterizationUsePolicyError(
            "causal or stronger use requires causal_design_validated=true"
        )
    if maximum_rank >= engineering_rank and not operational_validated:
        raise CharacterizationUsePolicyError(
            "engineering use requires operational_validation_validated=true"
        )

    return {
        "maximum_allowed_use": maximum_allowed_use,
        "feature_stage": feature_stage,
        "evidence_level": evidence_level,
        "review_status": review_status,
        "independence_group_field": independence_group_field,
        "measurement_timing": measurement_timing,
        "limitations": limitations,
    }


def evaluate_characterization_use(
    manifest_path: str | Path,
    *,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> CharacterizationUseEligibility:
    """Evaluate one requested use before consumer outputs are generated."""
    requested_rank = _rank(requested_use)
    manifest = read_manifest_object(manifest_path)
    closeout = manifest.get("scientific_closeout")
    if not isinstance(closeout, Mapping):
        raise CharacterizationUsePolicyError("scientific_closeout must be an object")
    evidence_level = _text(closeout, "evidence_level")
    if evidence_level not in EVIDENCE_LEVELS:
        raise CharacterizationUsePolicyError(
            f"unsupported scientific_closeout evidence_level: {evidence_level!r}"
        )

    raw_policy = manifest.get("downstream_use_policy")
    warnings: list[str] = []
    if raw_policy is None:
        policy_source = "legacy_default"
        policy = {
            "maximum_allowed_use": "descriptive",
            "feature_stage": "derived",
            "evidence_level": evidence_level,
            "review_status": "review_required",
            "independence_group_field": None,
            "measurement_timing": "unknown",
            "limitations": (
                "Legacy bundle has no explicit downstream_use_policy; consumer default is descriptive-only.",
            ),
        }
        warnings.append(
            "Legacy bundle accepted with descriptive-only downstream-use default."
        )
    else:
        policy_source = "manifest"
        policy = _validate_policy(
            raw_policy,
            scientific_evidence_level=evidence_level,
        )

    reasons: list[str] = []
    maximum_allowed_use = str(policy["maximum_allowed_use"])
    if requested_rank > _rank(maximum_allowed_use):
        reasons.append(
            f"requested use {requested_use!r} exceeds maximum_allowed_use {maximum_allowed_use!r}"
        )

    independence_group_field = policy["independence_group_field"]
    if requested_rank >= _rank("association"):
        if split_group_field is None or not split_group_field.strip():
            reasons.append(
                "association or stronger use requires --split-group-field"
            )
        elif split_group_field.strip() != independence_group_field:
            reasons.append(
                "split_group_field must match the producer-declared independence_group_field"
            )
        context_record = manifest.get("sample_context")
        context_columns = (
            context_record.get("columns")
            if isinstance(context_record, Mapping)
            else None
        )
        if (
            not isinstance(context_columns, list)
            or independence_group_field not in context_columns
        ):
            reasons.append(
                "producer-declared independence_group_field is absent from sample_context columns"
            )

    return CharacterizationUseEligibility(
        requested_use=requested_use,
        allowed=not reasons,
        maximum_allowed_use=maximum_allowed_use,
        policy_source=policy_source,
        evidence_level=evidence_level,
        feature_stage=str(policy["feature_stage"]),
        review_status=str(policy["review_status"]),
        independence_group_field=(
            str(independence_group_field)
            if independence_group_field is not None
            else None
        ),
        split_group_field=(
            split_group_field.strip()
            if isinstance(split_group_field, str) and split_group_field.strip()
            else None
        ),
        measurement_timing=str(policy["measurement_timing"]),
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        limitations=tuple(str(item) for item in policy["limitations"]),
    )


def require_characterization_use(
    manifest_path: str | Path,
    *,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> CharacterizationUseEligibility:
    """Return an allowed decision or raise before downstream outputs are written."""
    decision = evaluate_characterization_use(
        manifest_path,
        requested_use=requested_use,
        split_group_field=split_group_field,
    )
    if not decision.allowed:
        raise CharacterizationUsePolicyError(
            "characterization downstream use blocked: "
            + "; ".join(decision.reasons)
        )
    return decision


def write_characterization_use_eligibility(
    output_dir: str | Path,
    decision: CharacterizationUseEligibility,
) -> Path:
    """Persist the exact gate decision beside successful consumer outputs."""
    output = Path(output_dir)
    if not output.is_dir() or output.is_symlink():
        raise ValueError("consumer output directory must be a real directory")
    path = output / ELIGIBILITY_FILE_NAME
    if path.exists():
        raise FileExistsError(f"refusing to overwrite eligibility artifact: {path}")
    payload = {
        "schema_version": "1.0",
        "status": "characterization_downstream_use_allowed",
        **decision.to_dict(),
        "scientific_boundary": (
            "This gate enforces declared eligibility and leakage prerequisites only; "
            "it does not establish comparability, predictive validity, causality, or "
            "engineering readiness."
        ),
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
