"""Backward-compatible facade for characterization downstream-use gating."""
from .characterization_use_contract import (
    ELIGIBILITY_FILE_NAME,
    EVIDENCE_LEVELS,
    FEATURE_STAGES,
    MEASUREMENT_TIMINGS,
    POLICY_SCHEMA_VERSION,
    REVIEW_STATUSES,
    USE_LEVELS,
    CharacterizationUseEligibility,
    CharacterizationUsePolicyError,
    evaluate_characterization_use,
    read_manifest_object,
    require_characterization_use,
    write_characterization_use_eligibility,
)
from .characterization_use_workflow import consume_characterization_bundle_for_use

__all__ = [
    "ELIGIBILITY_FILE_NAME",
    "EVIDENCE_LEVELS",
    "FEATURE_STAGES",
    "MEASUREMENT_TIMINGS",
    "POLICY_SCHEMA_VERSION",
    "REVIEW_STATUSES",
    "USE_LEVELS",
    "CharacterizationUseEligibility",
    "CharacterizationUsePolicyError",
    "consume_characterization_bundle_for_use",
    "evaluate_characterization_use",
    "read_manifest_object",
    "require_characterization_use",
    "write_characterization_use_eligibility",
]
