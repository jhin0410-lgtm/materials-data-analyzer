"""Generic dataset/domain onboarding validation for platform v2."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ALLOWED_TRACKED_POLICIES, validate_relative_path
from .case_study_registry import CaseStudyRegistry
from .case_studies import CASE_STUDY_LIFECYCLE_STAGES
from .trust_registry import TrustPolicyRegistry
from .validation_registry import ValidationPolicyRegistry


SUPPORTED_ONBOARDING_SCHEMA_VERSION = "2.0"

REQUIRED_ONBOARDING_FIELDS = (
    "schema_version",
    "case_study_id",
    "display_name",
    "domain",
    "description",
    "primary_unit",
    "input_data_type",
    "target_or_event",
    "target_type",
    "supported_stages",
    "data_contract",
    "leakage_policy",
    "validation_policy",
    "trust_policy",
    "artifact_definitions",
    "local_only_patterns",
    "credential_policy",
    "resource_budget",
    "allowed_claims",
    "prohibited_claims",
    "stop_conditions",
    "documentation",
    "tests",
)

OPTIONAL_ONBOARDING_FIELDS = (
    "plugin_id",
    "adapter_id",
    "time_key",
    "time_key_unavailable_reason",
    "group_keys",
    "group_key_unavailable_reason",
    "execution_candidate",
)

SAFE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class OnboardingValidationResult:
    valid: bool
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    readiness_matrix: dict[str, bool]
    next_steps: tuple[str, ...]
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "readiness_matrix": self.readiness_matrix,
            "next_steps": list(self.next_steps),
            "config": self.config,
        }


def load_onboarding_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("onboarding config must be a JSON object")
    return payload


def _is_safe_id(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID_PATTERN.match(value) is not None


def _as_list(config: dict[str, Any], field: str, errors: list[str]) -> list[Any]:
    value = config.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    return value


def _validate_artifacts(config: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    artifact_ids: set[str] = set()
    for index, artifact in enumerate(_as_list(config, "artifact_definitions", errors)):
        prefix = f"artifact_definitions[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{prefix} must be an object")
            continue
        required = (
            "artifact_id",
            "stage",
            "path",
            "format",
            "tracked_policy",
            "producer",
            "consumers",
            "provenance_required",
            "checksum_required",
            "required_for_dry_run",
            "required_for_execution",
        )
        for field in required:
            if field not in artifact:
                errors.append(f"{prefix} missing required field: {field}")
        artifact_id = artifact.get("artifact_id")
        if not _is_safe_id(artifact_id):
            errors.append(f"{prefix}.artifact_id must be a safe snake_case ID")
        elif artifact_id in artifact_ids:
            errors.append(f"duplicate artifact_id: {artifact_id}")
        else:
            artifact_ids.add(str(artifact_id))
        stage = artifact.get("stage")
        if stage not in CASE_STUDY_LIFECYCLE_STAGES:
            errors.append(f"{prefix}.stage is unsupported: {stage}")
        path = artifact.get("path")
        if isinstance(path, str):
            try:
                validate_relative_path(path)
            except ValueError as exc:
                errors.append(f"{prefix}.path invalid: {exc}")
        elif path is not None:
            errors.append(f"{prefix}.path must be a string")
        tracked_policy = artifact.get("tracked_policy")
        if tracked_policy not in ALLOWED_TRACKED_POLICIES:
            errors.append(f"{prefix}.tracked_policy is unsupported: {tracked_policy}")
        path_string = path.replace("\\", "/") if isinstance(path, str) else ""
        if path_string.startswith("data/raw/") and tracked_policy in {"tracked", "generated_compact"}:
            errors.append(f"{prefix} raw artifacts cannot be tracked")
        if bool(artifact.get("local_only", False)) and tracked_policy in {"tracked", "generated_compact"}:
            errors.append(f"{prefix} has local_only/tracked conflict")
        consumers = artifact.get("consumers")
        if consumers is not None and not isinstance(consumers, list):
            errors.append(f"{prefix}.consumers must be a list")
        if not artifact.get("producer"):
            warnings.append(f"{prefix} has no producer")


def _validate_policy_compatibility(
    config: dict[str, Any],
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    errors: list[str],
    warnings: list[str],
) -> None:
    validation_policy_id = config.get("validation_policy")
    validation_policy = None
    if validation_policy_id:
        try:
            validation_policy = validation_registry.get(str(validation_policy_id))
        except KeyError:
            errors.append(f"unknown validation_policy: {validation_policy_id}")
    else:
        errors.append("validation_policy is required")

    trust_policy_id = config.get("trust_policy")
    if trust_policy_id:
        try:
            trust_policy = trust_registry.get(str(trust_policy_id))
        except KeyError:
            errors.append(f"unknown trust_policy: {trust_policy_id}")
        else:
            if "production_ready" in trust_policy.allowed_statuses:
                errors.append("trust_policy must not allow production_ready")
            if trust_policy.production_claim_allowed:
                errors.append("trust_policy must not allow production claims")
    else:
        errors.append("trust_policy is required")

    time_key = config.get("time_key")
    group_keys = config.get("group_keys", [])
    if group_keys is None:
        group_keys = []
    if not isinstance(group_keys, list):
        errors.append("group_keys must be a list")
        group_keys = []

    if validation_policy is None:
        return
    if validation_policy.time_key is not None and not time_key:
        errors.append("time-aware validation policy requires time_key")
        if not config.get("time_key_unavailable_reason"):
            errors.append("time_key_unavailable_reason is required when time_key is unavailable")
    if validation_policy.group_key is not None and not group_keys:
        errors.append("group-aware validation policy requires group_keys")
        if not config.get("group_key_unavailable_reason"):
            errors.append("group_key_unavailable_reason is required when group_keys are unavailable")
    if validation_policy.policy_id == "random_reference_only":
        warnings.append("random_reference_only is not primary evidence")
    if validation_policy.validation_type in {"asset_disjoint_time_aware_classification"} and (
        not time_key or not group_keys
    ):
        errors.append("combined asset/time validation requires both time_key and group_keys")


def _readiness_matrix(config: dict[str, Any]) -> dict[str, bool]:
    group_keys = config.get("group_keys") or []
    return {
        "identity_defined": bool(config.get("case_study_id") and config.get("display_name")),
        "time_structure_defined": bool(config.get("time_key") or config.get("time_key_unavailable_reason")),
        "group_structure_defined": bool(group_keys or config.get("group_key_unavailable_reason")),
        "target_defined": bool(config.get("target_or_event") and config.get("target_type")),
        "leakage_policy_defined": bool(config.get("leakage_policy")),
        "validation_policy_defined": bool(config.get("validation_policy")),
        "trust_policy_defined": bool(config.get("trust_policy")),
        "artifacts_defined": bool(config.get("artifact_definitions")),
        "local_only_policy_defined": bool(config.get("local_only_patterns")),
        "provenance_defined": bool(config.get("data_contract", {}).get("provenance_requirements"))
        if isinstance(config.get("data_contract"), dict)
        else False,
        "tests_defined": bool(config.get("tests")),
        "docs_defined": bool(config.get("documentation")),
        "adapter_mapped": bool(config.get("adapter_id")),
        "executable_allowed": False,
    }


def _status_for(config: dict[str, Any], errors: list[str], warnings: list[str]) -> str:
    if errors:
        if any("policy" in error for error in errors):
            return "blocked_policy_mismatch"
        return "invalid"
    if config.get("execution_candidate") is True:
        warnings.append("execution_candidate does not enable execution; allowlist approval is separate")
        return "valid_execution_candidate"
    if config.get("adapter_id"):
        return "valid_dry_run_ready"
    return "valid_metadata_only"


def _next_steps(readiness: dict[str, bool], status: str) -> tuple[str, ...]:
    steps: list[str] = []
    if not readiness["adapter_mapped"]:
        steps.append("map a dry-run adapter only after artifact and policy contracts are stable")
    if not readiness["executable_allowed"]:
        steps.append("request a separate execution-policy review before enabling any runtime execution")
    if status == "valid_metadata_only":
        steps.append("add compact artifact examples and synthetic tests before dry-run mapping")
    elif status == "valid_dry_run_ready":
        steps.append("validate manifest-only dry-runs before considering controlled execution")
    elif status == "valid_execution_candidate":
        steps.append("keep execution disabled until an explicit allowlist grants a narrow mode")
    return tuple(steps)


def validate_onboarding_config(
    config: dict[str, Any],
    *,
    case_study_registry: CaseStudyRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
) -> OnboardingValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    unknown = sorted(set(config) - set(REQUIRED_ONBOARDING_FIELDS) - set(OPTIONAL_ONBOARDING_FIELDS))
    if unknown:
        errors.append(f"unknown fields: {', '.join(unknown)}")
    for field in REQUIRED_ONBOARDING_FIELDS:
        if field not in config:
            errors.append(f"missing required field: {field}")
    if config.get("schema_version") != SUPPORTED_ONBOARDING_SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {config.get('schema_version')!r}; expected {SUPPORTED_ONBOARDING_SCHEMA_VERSION}"
        )
    case_study_id = config.get("case_study_id")
    if not _is_safe_id(case_study_id):
        errors.append("case_study_id must be a safe snake_case ID")
    elif case_study_id in {case.case_study_id for case in case_study_registry.list_case_studies()}:
        errors.append(f"case_study_id already registered: {case_study_id}")
    plugin_id = config.get("plugin_id")
    if plugin_id is not None and not _is_safe_id(plugin_id):
        errors.append("plugin_id must be a safe snake_case ID when provided")
    for field in ("supported_stages", "local_only_patterns", "allowed_claims", "prohibited_claims", "stop_conditions", "tests"):
        for value in _as_list(config, field, errors):
            if not isinstance(value, str):
                errors.append(f"{field} entries must be strings")
    for stage in _as_list(config, "supported_stages", errors):
        if stage not in CASE_STUDY_LIFECYCLE_STAGES:
            errors.append(f"unsupported supported_stages entry: {stage}")
    if not config.get("allowed_claims"):
        errors.append("allowed_claims must not be empty")
    if not config.get("prohibited_claims"):
        errors.append("prohibited_claims must not be empty")
    if not config.get("stop_conditions"):
        errors.append("stop_conditions must not be empty")
    credential_policy = config.get("credential_policy")
    if isinstance(credential_policy, dict):
        if credential_policy.get("store_credentials") is True:
            errors.append("credential_policy.store_credentials must not be true")
    elif credential_policy is not None:
        errors.append("credential_policy must be an object")
    resource_budget = config.get("resource_budget")
    if resource_budget is not None and not isinstance(resource_budget, dict):
        errors.append("resource_budget must be an object")
    _validate_artifacts(config, errors, warnings)
    _validate_policy_compatibility(config, validation_registry, trust_registry, errors, warnings)
    readiness = _readiness_matrix(config)
    status = _status_for(config, errors, warnings)
    return OnboardingValidationResult(
        valid=not errors,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        readiness_matrix=readiness,
        next_steps=_next_steps(readiness, status),
        config=config,
    )


def load_and_validate_onboarding_config(
    config_path: str | Path,
    *,
    case_study_registry: CaseStudyRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
) -> OnboardingValidationResult:
    return validate_onboarding_config(
        load_onboarding_config(config_path),
        case_study_registry=case_study_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
    )
