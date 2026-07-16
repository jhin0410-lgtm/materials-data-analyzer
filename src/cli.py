"""Unified v2 platform CLI scaffold.

This command is additive. It does not replace `src/process_data.py` or existing
case-study scripts, and it does not execute acquisition, modeling, or network
operations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .platform_core.adapter_registry import build_default_adapter_registry
from .platform_core.artifacts import build_default_artifact_registry, validate_relative_path
from .platform_core.case_study_adapter import build_case_study_stage_plan
from .platform_core.case_study_registry import build_default_case_study_registry
from .platform_core.config import load_and_validate_pipeline_config, load_json_config
from .platform_core.executable_adapters import build_approved_adapter_callables
from .platform_core.execution_policy import build_default_execution_policy_registry
from .platform_core.execution_runtime import (
    AdapterExecutionDisabled,
    MissingArtifactError,
    PathPolicyError,
    PlatformExecutionError,
    SideEffectViolationError,
    VerificationMismatchError,
    execute_adapter_runtime,
)
from .platform_core.diagnostic_service import (
    DiagnosticSchemaError,
    UnsupportedRuleSet,
    compare_diagnostic_evaluations,
    diagnose_run,
    diagnostic_summary_exit_status,
    diagnostics_validate,
    evaluate_claim,
    export_diagnostics,
    list_diagnostic_findings,
    list_evidence_gaps,
    show_diagnostics,
)
from .platform_core.manifests import (
    build_run_manifest,
    default_manifest_output,
    load_run_manifest,
    write_run_manifest,
)
from .platform_core.onboarding import load_and_validate_onboarding_config
from .platform_core.planner import build_dry_run_plan
from .platform_core.registry import build_default_plugin_registry
from .platform_core.report_generator import (
    generate_report,
    load_report_config,
    load_report_json,
    load_report_manifest,
)
from .platform_core.registry_service import RegistryService
from .platform_core.run_registry import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_REGISTRY_PATH,
    assert_no_sensitive_strings,
    get_scientific_trust_evaluation,
    list_scientific_feature_eligibility,
    list_scientific_trust_evaluations,
    RegistryConflictError,
    RegistryPathError,
    RegistryValidationError,
    RunRegistryError,
    store_scientific_trust_evaluation,
    UnsupportedRegistryVersion,
)
from .platform_core.domain_knowledge import build_default_domain_knowledge_registry
from .platform_core.scientific_applicability import (
    check_scientific_applicability,
    load_scientific_config,
    validate_scientific_input,
)
from .platform_core.scientific_constraint_registry import build_default_scientific_constraint_registry
from .platform_core.scientific_evaluators import build_default_evaluator_registry
from .platform_core.entity_serialization import deserialize_entity_record, serialize_entity, validate_record
from .platform_core.quantities import quantity_from_payload, validate_quantity_payload
from .platform_core.schema_evolution import build_default_migration_registry
from .platform_core.scientific_entities import (
    SUPPORTED_ENTITY_TYPES,
    ScientificEntity,
    entity_type_schemas,
    validate_entity_payload,
)
from .platform_core.scientific_execution import (
    execute_scientific_config,
    export_scientific_findings,
    get_scientific_claim_evaluation,
    get_scientific_execution,
    list_scientific_findings,
    load_execution_config,
    validate_scientific_registry,
    validate_scientific_result_payload,
    write_scientific_outputs,
)
from .platform_core.scientific_relations import default_scientific_relations
from .platform_core.scientific_feature_registry import build_default_scientific_feature_registry
from .platform_core.scientific_trust import (
    CLAIM_BOUNDARY_IDS,
    closeout_conclusion,
    constraint_role_snapshot,
    evaluate_feature_candidate_against_execution,
    evaluate_scientific_trust,
)
from .platform_core.units import build_default_unit_registry
from .platform_core.unit_backend import BuiltinUnitBackend, unit_backend_decision
from .platform_core.uncertainty_propagation import propagate_bragg_uncertainty, scherrer_uncertainty_eligibility
from .platform_core.trust_registry import build_default_trust_policy_registry
from .platform_core.validation_registry import build_default_validation_policy_registry
from .platform_core.version import PLATFORM_VERSION
from .analyzers.materials_physics_features import (
    build_request_from_config as build_materials_feature_request_from_config,
    comparison_request_from_config as build_materials_comparison_request_from_config,
    feature_definitions as materials_feature_definitions,
    get_feature_definition as get_materials_feature_definition,
    load_json as load_materials_json,
    render_predictive_value_report,
    run_feature_build,
    run_predictive_comparison,
    validate_feature_artifact,
)


EXIT_INVALID_CONFIG = 2
EXIT_ADAPTER_NOT_FOUND = 3
EXIT_EXECUTION_DISABLED = 4
EXIT_MISSING_ARTIFACT = 5
EXIT_SIDE_EFFECT = 6
EXIT_VERIFICATION_MISMATCH = 7
EXIT_RUNTIME_FAILURE = 8
EXIT_PATH_POLICY = 9
EXIT_REGISTRY = 10
EXIT_DIAGNOSTIC_WARNING = 10
EXIT_DIAGNOSTIC_BLOCKER = 11
EXIT_DIAGNOSTIC_RUN_NOT_FOUND = 12
EXIT_DIAGNOSTIC_POLICY_MISSING = 13
EXIT_DIAGNOSTIC_SCHEMA = 14
EXIT_DIAGNOSTIC_RULESET = 15


def _registries() -> tuple[Any, Any, Any, Any, Any, Any]:
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    return (
        plugin_registry,
        artifact_registry,
        build_default_validation_policy_registry(),
        build_default_trust_policy_registry(),
        adapter_registry,
        build_default_execution_policy_registry(),
    )


def _case_study_registries() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, execution_policy_registry = _registries()
    case_study_registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    return (
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
        execution_policy_registry,
        case_study_registry,
    )


def _scientific_registries() -> tuple[Any, Any, Any, Any]:
    unit_registry = build_default_unit_registry()
    evaluator_registry = build_default_evaluator_registry()
    constraint_registry = build_default_scientific_constraint_registry(evaluator_registry, unit_registry)
    knowledge_registry = build_default_domain_knowledge_registry()
    return unit_registry, evaluator_registry, constraint_registry, knowledge_registry


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _emit_lines(lines: list[str]) -> None:
    print("\n".join(lines))


def _registry_service(args: argparse.Namespace) -> RegistryService:
    return RegistryService(Path.cwd(), getattr(args, "registry_path", None) or DEFAULT_REGISTRY_PATH)


def _registry_error_code(exc: Exception) -> int:
    if isinstance(exc, (RegistryPathError, FileExistsError)):
        return EXIT_PATH_POLICY
    if isinstance(exc, (RegistryConflictError, RegistryValidationError, UnsupportedRegistryVersion)):
        return EXIT_REGISTRY
    if isinstance(exc, RunRegistryError):
        return EXIT_REGISTRY
    return EXIT_RUNTIME_FAILURE


def _emit_registry_error(args: argparse.Namespace, status: str, exc: Exception) -> int:
    code = _registry_error_code(exc)
    payload = {"status": status, "exit_code": code, "error": str(exc)}
    if args.json:
        _emit_json(payload)
    else:
        print(f"{status}: {exc}", file=sys.stderr)
    return code


def _diagnostic_error_code(exc: Exception) -> int:
    if isinstance(exc, UnsupportedRuleSet):
        return EXIT_DIAGNOSTIC_RULESET
    if isinstance(exc, DiagnosticSchemaError):
        return EXIT_DIAGNOSTIC_SCHEMA
    if isinstance(exc, KeyError):
        message = str(exc)
        if "run_id" in message or "no diagnostics" in message:
            return EXIT_DIAGNOSTIC_RUN_NOT_FOUND
        return EXIT_DIAGNOSTIC_POLICY_MISSING
    if isinstance(exc, RunRegistryError):
        return EXIT_DIAGNOSTIC_SCHEMA
    return EXIT_RUNTIME_FAILURE


def _emit_diagnostic_error(args: argparse.Namespace, status: str, exc: Exception) -> int:
    code = _diagnostic_error_code(exc)
    payload = {"status": status, "exit_code": code, "error": str(exc)}
    if args.json:
        _emit_json(payload)
    else:
        print(f"{status}: {exc}", file=sys.stderr)
    return code


def _cmd_list_plugins(args: argparse.Namespace) -> int:
    plugin_registry, _, _, _, _, _ = _registries()
    plugins = plugin_registry.snapshot()
    if args.json:
        _emit_json(plugins)
    else:
        _emit_lines(
            [
                f"{plugin['plugin_id']}\t{plugin['status']}\t{','.join(plugin['supported_stages'])}"
                for plugin in plugins
            ]
        )
    return 0


def _cmd_inspect_plugin(args: argparse.Namespace) -> int:
    plugin_registry, _, _, _, _, _ = _registries()
    try:
        plugin = plugin_registry.get(args.plugin_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit_json(plugin.to_dict())
    else:
        data = plugin.to_dict()
        _emit_lines(
            [
                f"plugin_id: {data['plugin_id']}",
                f"case_study_id: {data['case_study_id']}",
                f"status: {data['status']}",
                f"supported_stages: {', '.join(data['supported_stages'])}",
                f"validation_policy_id: {data['validation_policy_id']}",
                f"trust_policy_id: {data['trust_policy_id']}",
                f"description: {data['description']}",
            ]
        )
    return 0


def _cmd_list_artifacts(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, _, _, _, _ = _registries()
    case_study_id = None
    if args.plugin:
        try:
            case_study_id = plugin_registry.get(args.plugin).case_study_id
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    artifacts = artifact_registry.snapshot(case_study_id)
    if args.json:
        _emit_json(artifacts)
    else:
        _emit_lines(
            [
                f"{artifact['artifact_id']}\t{artifact['tracked_policy']}\t{artifact['relative_path']}"
                for artifact in artifacts
            ]
        )
    return 0


def _cmd_list_adapters(args: argparse.Namespace) -> int:
    _, _, _, _, adapter_registry, _ = _registries()
    adapters = adapter_registry.snapshot(args.plugin)
    if args.json:
        _emit_json(adapters)
    else:
        _emit_lines(
            [
                f"{adapter['adapter_id']}\t{adapter['plugin_id']}\t{adapter['stage']}\t{adapter['executable_status']}"
                for adapter in adapters
            ]
        )
    return 0


def _cmd_inspect_adapter(args: argparse.Namespace) -> int:
    _, _, _, _, adapter_registry, _ = _registries()
    try:
        adapter = adapter_registry.get(args.adapter_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit_json(adapter.to_dict())
    else:
        data = adapter.to_dict()
        _emit_lines(
            [
                f"adapter_id: {data['adapter_id']}",
                f"plugin_id: {data['plugin_id']}",
                f"stage: {data['stage']}",
                f"executable_status: {data['executable_status']}",
                f"execution_allowed: {data['execution_allowed']}",
                f"required_artifacts: {', '.join(data['required_artifacts'])}",
                f"produced_artifacts: {', '.join(data['produced_artifacts'])}",
            ]
        )
    return 0


def _cmd_list_case_studies(args: argparse.Namespace) -> int:
    *_, case_study_registry = _case_study_registries()
    payload = case_study_registry.completeness_snapshot()
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                (
                    f"{item['case_study_id']}\t{item['status']}\t"
                    f"{item['onboarding_status']}\t{','.join(item['supported_stages'])}"
                )
                for item in payload
            ]
        )
    return 0


def _cmd_inspect_case_study(args: argparse.Namespace) -> int:
    *_, case_study_registry = _case_study_registries()
    try:
        case_study = case_study_registry.get(args.case_study_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ADAPTER_NOT_FOUND
    payload = case_study.to_dict()
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"case_study_id: {payload['case_study_id']}",
                f"display_name: {payload['display_name']}",
                f"domain: {payload['domain']}",
                f"status: {payload['status']}",
                f"onboarding_status: {payload['onboarding_status']}",
                f"plugin_id: {payload['plugin_id']}",
                f"validation_policy_id: {payload['validation_policy_id']}",
                f"trust_policy_id: {payload['trust_policy_id']}",
                f"executable_stages: {', '.join(payload['executable_stages']) if payload['executable_stages'] else 'none'}",
                f"documentation_path: {payload['documentation_path']}",
            ]
        )
    return 0


def _cmd_list_case_study_stages(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, _, case_study_registry = _case_study_registries()
    del plugin_registry, validation_registry, trust_registry
    try:
        case_study = case_study_registry.get(args.case_study_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ADAPTER_NOT_FOUND
    plans = [
        build_case_study_stage_plan(
            case_study_id=case_study.case_study_id,
            stage=stage,
            case_study_registry=case_study_registry,
            artifact_registry=artifact_registry,
            adapter_registry=adapter_registry,
        ).to_dict()
        for stage in case_study.supported_stages
    ]
    if args.json:
        _emit_json(plans)
    else:
        _emit_lines(
            [
                (
                    f"{plan['stage']}\t{plan['execution_status']}\t"
                    f"{plan['adapter_id'] or 'no_adapter'}\t{plan['execution_boundary']}"
                )
                for plan in plans
            ]
        )
    return 0


def _load_onboarding_result(config_path: str):
    _, _, validation_registry, trust_registry, _, _, case_study_registry = _case_study_registries()
    return load_and_validate_onboarding_config(
        config_path,
        case_study_registry=case_study_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
    )


def _cmd_validate_onboarding(args: argparse.Namespace) -> int:
    try:
        result = _load_onboarding_result(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"valid": False, "status": "invalid", "errors": [str(exc)], "warnings": []}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(result.to_dict())
    else:
        lines = [f"valid: {str(result.valid).lower()}", f"status: {result.status}"]
        lines.extend(f"error: {error}" for error in result.errors)
        lines.extend(f"warning: {warning}" for warning in result.warnings)
        _emit_lines(lines)
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_inspect_onboarding(args: argparse.Namespace) -> int:
    try:
        result = _load_onboarding_result(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if args.json:
            _emit_json({"valid": False, "status": "invalid", "errors": [str(exc)]})
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {
        "status": result.status,
        "readiness_matrix": result.readiness_matrix,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "config": result.config,
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {result.status}",
                *[
                    f"{key}: {str(value).lower()}"
                    for key, value in sorted(result.readiness_matrix.items())
                ],
            ]
        )
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_onboarding_plan(args: argparse.Namespace) -> int:
    try:
        result = _load_onboarding_result(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if args.json:
            _emit_json({"valid": False, "status": "invalid", "errors": [str(exc)]})
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    config = result.config or {}
    artifacts = config.get("artifact_definitions", []) if isinstance(config.get("artifact_definitions", []), list) else []
    payload = {
        "case_study_id": config.get("case_study_id"),
        "status": result.status,
        "plugin": config.get("plugin_id") or "not_registered",
        "validation_policy": config.get("validation_policy"),
        "trust_policy": config.get("trust_policy"),
        "artifact_count": len(artifacts),
        "missing_fields": [key for key, value in result.readiness_matrix.items() if not value],
        "stage_readiness": {
            stage: {
                "declared": stage in (config.get("supported_stages") or []),
                "adapter_mapped": bool(config.get("adapter_id") and stage == "trust"),
                "execution_allowed": False,
            }
            for stage in sorted(set(config.get("supported_stages") or []))
            if isinstance(stage, str)
        },
        "next_steps": list(result.next_steps),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"case_study_id: {payload['case_study_id']}",
                f"status: {payload['status']}",
                f"plugin: {payload['plugin']}",
                f"validation_policy: {payload['validation_policy']}",
                f"trust_policy: {payload['trust_policy']}",
                f"artifact_count: {payload['artifact_count']}",
                f"missing_fields: {', '.join(payload['missing_fields']) if payload['missing_fields'] else 'none'}",
                f"next_steps: {'; '.join(payload['next_steps']) if payload['next_steps'] else 'none'}",
            ]
        )
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_validate_config(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, _ = _registries()
    try:
        result = load_and_validate_pipeline_config(
            args.config_path,
            plugin_registry,
            artifact_registry,
            validation_registry,
            trust_registry,
            adapter_registry,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result_payload = {"valid": False, "errors": [str(exc)], "warnings": []}
        if args.json:
            _emit_json(result_payload)
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(result.to_dict())
    else:
        if result.valid:
            _emit_lines(["valid: true", *[f"warning: {warning}" for warning in result.warnings]])
        else:
            _emit_lines(["valid: false", *[f"error: {error}" for error in result.errors]])
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_dry_run(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, _ = _registries()
    try:
        config = load_json_config(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"execution_status": "blocked_invalid_config", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"blocked_invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    validation, plan = build_dry_run_plan(
        config,
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
        repo_root=Path.cwd(),
    )
    manifest_path = config.get("manifest_output") if isinstance(config.get("manifest_output"), str) else None
    manifest = None
    written_manifest_path: Path | None = None
    registry_result = None
    if args.write_manifest:
        try:
            manifest = build_run_manifest(
                config,
                validation,
                plan,
                artifact_registry,
                trust_registry,
                repo_root=Path.cwd(),
            )
            manifest_path = manifest_path or args.manifest_out or default_manifest_output(str(manifest["run_id"]))
            written_path = write_run_manifest(
                manifest,
                repo_root=Path.cwd(),
                manifest_output=manifest_path,
                overwrite=bool(args.overwrite or config.get("overwrite_manifest") is True),
            )
            written_manifest_path = written_path
            manifest_path = str(written_path.relative_to(Path.cwd()))
        except (OSError, ValueError) as exc:
            payload = {
                "config_validation": validation.to_dict(),
                "dry_run_plan": plan.to_dict(),
                "manifest_error": str(exc),
            }
            if args.json:
                _emit_json(payload)
            else:
                print(f"manifest_error: {exc}", file=sys.stderr)
            return EXIT_PATH_POLICY
    if args.register_run:
        if written_manifest_path is None:
            payload = {"status": "registry_failed", "error": "--register-run requires --write-manifest"}
            if args.json:
                _emit_json(payload)
            else:
                print("registry_failed: --register-run requires --write-manifest", file=sys.stderr)
            return EXIT_REGISTRY
        try:
            registry_result = _registry_service(args).ingest(written_manifest_path)
        except Exception as exc:
            return _emit_registry_error(args, "registry_failed", exc)
    payload = {
        "config_validation": validation.to_dict(),
        "dry_run_plan": plan.to_dict(),
        "manifest_path": manifest_path,
        "registry_result": registry_result,
    }
    if manifest is not None:
        payload["run_manifest"] = manifest
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"selected_plugin: {plan.selected_plugin}",
                f"selected_stage: {plan.selected_stage}",
                f"execution_status: {plan.execution_status}",
                f"blocked_reasons: {', '.join(plan.blocked_reasons) if plan.blocked_reasons else 'none'}",
                f"required_inputs: {', '.join(plan.required_inputs) if plan.required_inputs else 'none'}",
                f"missing_inputs: {', '.join(plan.missing_inputs) if plan.missing_inputs else 'none'}",
                f"expected_tracked_outputs: {', '.join(plan.expected_tracked_outputs) if plan.expected_tracked_outputs else 'none'}",
                f"expected_local_only_outputs: {', '.join(plan.expected_local_only_outputs) if plan.expected_local_only_outputs else 'none'}",
                f"adapter_id: {plan.adapter_id}",
                f"execution_allowed: {plan.execution_allowed}",
                f"manifest_path: {manifest_path or 'none'}",
                f"registry_status: {registry_result['status'] if registry_result else 'not_requested'}",
            ]
        )
    return 0 if validation.valid else EXIT_INVALID_CONFIG


def _cmd_show_policy(args: argparse.Namespace) -> int:
    _, _, validation_registry, trust_registry, _, _ = _registries()
    policy = None
    policy_type = None
    try:
        policy = validation_registry.get(args.policy_id)
        policy_type = "validation"
    except KeyError:
        try:
            policy = trust_registry.get(args.policy_id)
            policy_type = "trust"
        except KeyError:
            print(f"unknown policy_id: {args.policy_id}", file=sys.stderr)
            return 2
    payload = {"policy_type": policy_type, "policy": policy.to_dict()}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"policy_type: {policy_type}", f"policy_id: {args.policy_id}"])
    return 0


def _cmd_list_executable_adapters(args: argparse.Namespace) -> int:
    _, _, _, _, _, execution_policy_registry = _registries()
    permissions = execution_policy_registry.snapshot()
    if args.json:
        _emit_json(permissions)
    else:
        _emit_lines(
            [
                f"{permission['adapter_id']}\t{permission['execution_allowed']}\t{','.join(permission['allowed_modes']) or 'none'}"
                for permission in permissions
            ]
        )
    return 0


def _cmd_show_execution_policy(args: argparse.Namespace) -> int:
    _, _, _, _, _, execution_policy_registry = _registries()
    try:
        permission = execution_policy_registry.get(args.adapter_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ADAPTER_NOT_FOUND
    if args.json:
        _emit_json(permission.to_dict())
    else:
        data = permission.to_dict()
        _emit_lines(
            [
                f"adapter_id: {data['adapter_id']}",
                f"execution_allowed: {data['execution_allowed']}",
                f"allowed_modes: {', '.join(data['allowed_modes']) if data['allowed_modes'] else 'none'}",
                f"network_allowed: {data['network_allowed']}",
                f"raw_data_allowed: {data['raw_data_allowed']}",
                f"model_training_allowed: {data['model_training_allowed']}",
                f"canonical_overwrite_allowed: {data['canonical_overwrite_allowed']}",
                f"reason: {data['reason']}",
            ]
        )
    return 0


def _execute_error_code(exc: Exception) -> int:
    if isinstance(exc, AdapterExecutionDisabled):
        return EXIT_EXECUTION_DISABLED
    if isinstance(exc, MissingArtifactError) or isinstance(exc, FileNotFoundError):
        return EXIT_MISSING_ARTIFACT
    if isinstance(exc, SideEffectViolationError):
        return EXIT_SIDE_EFFECT
    if isinstance(exc, VerificationMismatchError):
        return EXIT_VERIFICATION_MISMATCH
    if isinstance(exc, PathPolicyError) or isinstance(exc, FileExistsError):
        return EXIT_PATH_POLICY
    if isinstance(exc, PlatformExecutionError):
        return exc.exit_code
    return EXIT_RUNTIME_FAILURE


def _cmd_execute(args: argparse.Namespace) -> int:
    (
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
        execution_policy_registry,
    ) = _registries()
    try:
        config = load_json_config(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if args.json:
            _emit_json({"status": "invalid_config", "errors": [str(exc)]})
        else:
            print(f"invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.mode:
        config["execution_mode"] = args.mode
    if args.run_id:
        config["run_id"] = args.run_id
    if args.output_dir:
        config["output_directory"] = args.output_dir
    validation, plan = build_dry_run_plan(
        config,
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
        repo_root=Path.cwd(),
    )
    if not validation.valid:
        payload = {"status": "invalid_config", "errors": list(validation.errors), "warnings": list(validation.warnings)}
        if args.json:
            _emit_json(payload)
        else:
            _emit_lines(["valid: false", *[f"error: {error}" for error in validation.errors]])
        return EXIT_INVALID_CONFIG
    try:
        manifest, result = execute_adapter_runtime(
            config=config,
            validation=validation,
            plan=plan,
            plugin_registry=plugin_registry,
            adapter_registry=adapter_registry,
            artifact_registry=artifact_registry,
            trust_registry=trust_registry,
            execution_policy_registry=execution_policy_registry,
            callables=build_approved_adapter_callables(),
            repository_root=Path.cwd(),
            execution_mode=str(config.get("execution_mode") or "verify"),
            output_directory=config.get("output_directory"),
            run_id_override=config.get("run_id"),
            overwrite_manifest=bool(args.overwrite or config.get("overwrite_manifest") is True),
        )
    except Exception as exc:
        code = _execute_error_code(exc)
        payload = {"status": "failed", "exit_code": code, "error": str(exc), "adapter_id": plan.adapter_id}
        if args.json:
            _emit_json(payload)
        else:
            print(f"execution_failed: {exc}", file=sys.stderr)
        return code
    registry_result = None
    if args.register_run:
        try:
            registry_result = _registry_service(args).ingest(Path(str(manifest["output_directory"])) / "run_manifest.json")
        except Exception as exc:
            return _emit_registry_error(args, "registry_failed", exc)
    payload = {
        "status": manifest["status"],
        "manifest": manifest,
        "result": result.to_dict() if result else None,
        "registry_result": registry_result,
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {manifest['status']}",
                f"run_id: {manifest['run_id']}",
                f"adapter_id: {manifest['adapter_id']}",
                f"execution_mode: {manifest['execution_mode']}",
                f"side_effect_status: {manifest['side_effect_status']}",
                f"produced_artifacts: {', '.join(manifest['produced_artifacts']) if manifest['produced_artifacts'] else 'none'}",
                f"registry_status: {registry_result['status'] if registry_result else 'not_requested'}",
            ]
        )
    return 0


def _cmd_verify_run(args: argparse.Namespace) -> int:
    try:
        manifest = load_run_manifest(args.manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if args.json:
            _emit_json({"valid": False, "errors": [str(exc)]})
        else:
            print(f"invalid manifest: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    valid_statuses = {"verification_completed", "dry_run_completed"}
    is_valid = manifest["status"] in valid_statuses
    payload = {"valid": is_valid, "run_id": manifest["run_id"], "status": manifest["status"]}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"valid: {str(is_valid).lower()}", f"run_id: {manifest['run_id']}", f"status: {manifest['status']}"])
    return 0 if is_valid else EXIT_VERIFICATION_MISMATCH


def _cmd_show_manifest(args: argparse.Namespace) -> int:
    try:
        manifest = load_run_manifest(args.manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(manifest)
    else:
        _emit_lines(
            [
                f"run_id: {manifest['run_id']}",
                f"plugin_id: {manifest['plugin_id']}",
                f"adapter_id: {manifest['adapter_id']}",
                f"stage: {manifest['stage']}",
                f"status: {manifest['status']}",
            ]
        )
    return 0


def _cmd_validate_manifest(args: argparse.Namespace) -> int:
    try:
        manifest = load_run_manifest(args.manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"valid": False, "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"valid: false\nerror: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {"valid": True, "run_id": manifest["run_id"], "status": manifest["status"]}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(["valid: true", f"run_id: {manifest['run_id']}", f"status: {manifest['status']}"])
    return 0


def _report_formats(args: argparse.Namespace) -> tuple[str, ...] | None:
    if not getattr(args, "format", None):
        return None
    if args.format == "all":
        return ("json", "markdown")
    return (args.format,)


def _load_report_config_for_cli(args: argparse.Namespace) -> dict[str, Any]:
    config = load_report_config(args.config_path)
    if getattr(args, "case_study", None):
        config["selected_case_studies"] = list(args.case_study)
    if getattr(args, "report_id", None):
        config["report_id"] = args.report_id
    if getattr(args, "output_dir", None):
        config["output_dir"] = args.output_dir
    if getattr(args, "format", None):
        config["formats"] = list(_report_formats(args) or [])
    if getattr(args, "overwrite", False):
        config["overwrite"] = True
    return config


def _cmd_preview_report(args: argparse.Namespace) -> int:
    try:
        config = _load_report_config_for_cli(args)
        result = generate_report(
            config,
            repo_root=Path.cwd(),
            write=False,
            formats_override=_report_formats(args),
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        payload = {"status": "invalid_report_config", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid_report_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = result.summary()
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"report_id: {payload['report_id']}",
                f"generation_status: {payload['generation_status']}",
                f"case_study_ids: {', '.join(payload['case_study_ids'])}",
                f"generated_formats: {', '.join(payload['generated_formats'])}",
                f"scientific_recomputation_performed: {payload['scientific_recomputation_performed']}",
                "output_dir: none",
            ]
        )
    return 0


def _cmd_generate_report(args: argparse.Namespace) -> int:
    try:
        config = _load_report_config_for_cli(args)
        result = generate_report(
            config,
            repo_root=Path.cwd(),
            write=True,
            output_dir_override=args.output_dir,
            report_id_override=args.report_id,
            formats_override=_report_formats(args),
            overwrite=args.overwrite or None,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError, FileExistsError) as exc:
        payload = {"status": "report_generation_failed", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"report_generation_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY if isinstance(exc, (ValueError, FileExistsError)) else EXIT_INVALID_CONFIG
    payload = result.summary()
    registry_result = None
    if args.register_run:
        try:
            registry_result = _registry_service(args).ingest(Path(str(result.output_dir)) / "report_manifest.json")
        except Exception as exc:
            return _emit_registry_error(args, "registry_failed", exc)
        payload["registry_result"] = registry_result
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"report_id: {payload['report_id']}",
                f"generation_status: {payload['generation_status']}",
                f"output_dir: {payload['output_dir']}",
                f"written_files: {', '.join(payload['written_files'])}",
                f"scientific_recomputation_performed: {payload['scientific_recomputation_performed']}",
                f"registry_status: {registry_result['status'] if registry_result else 'not_requested'}",
            ]
        )
    return 0


def _cmd_validate_report(args: argparse.Namespace) -> int:
    try:
        manifest = load_report_manifest(args.report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"valid": False, "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"valid: false\nerror: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {
        "valid": True,
        "report_id": manifest["report_id"],
        "generation_status": manifest["generation_status"],
        "case_study_ids": manifest["case_study_ids"],
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                "valid: true",
                f"report_id: {payload['report_id']}",
                f"generation_status: {payload['generation_status']}",
                f"case_study_ids: {', '.join(payload['case_study_ids'])}",
            ]
        )
    return 0


def _cmd_inspect_report(args: argparse.Namespace) -> int:
    try:
        report = load_report_json(args.report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"valid": False, "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid report: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {
        "report_schema_version": report.get("report_schema_version"),
        "platform_version": report.get("platform_version"),
        "platform_status": report.get("platform_status"),
        "case_study_ids": [case["case_study_id"] for case in report.get("case_studies", [])],
        "scientific_recomputation_performed": report.get("scientific_recomputation_performed"),
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"platform_version: {payload['platform_version']}",
                f"platform_status: {payload['platform_status']}",
                f"case_study_ids: {', '.join(payload['case_study_ids'])}",
                f"scientific_recomputation_performed: {payload['scientific_recomputation_performed']}",
            ]
        )
    return 0


def _cmd_list_report_sources(args: argparse.Namespace) -> int:
    config = {
        "schema_version": "2.0",
        "report_id": "report_sources_preview",
        "formats": ["json", "markdown"],
        "output_dir": "outputs/platform_reports/report_sources_preview",
    }
    try:
        result = generate_report(config, repo_root=Path.cwd(), write=False)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        payload = {"status": "failed", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"failed: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    sources = [
        {
            "case_study_id": case.case_study_id,
            "source_artifacts": [artifact.artifact_id for artifact in case.artifacts],
            "warning_count": len(case.warnings),
        }
        for case in result.report.case_studies
    ]
    if args.json:
        _emit_json(sources)
    else:
        _emit_lines(
            [
                f"{source['case_study_id']}\t{','.join(source['source_artifacts']) or 'none'}\twarnings={source['warning_count']}"
                for source in sources
            ]
        )
    return 0


def _cmd_registry_init(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).initialize()
    except Exception as exc:
        return _emit_registry_error(args, "registry_init_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload['status']}",
                f"registry_path: {payload['registry_path']}",
                f"schema_version: {payload['schema_version']}",
            ]
        )
    return 0


def _cmd_registry_ingest(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).ingest(args.manifest_path)
    except Exception as exc:
        return _emit_registry_error(args, "registry_ingest_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload['status']}",
                f"run_id: {payload['run_id']}",
                f"manifest_kind: {payload['manifest_kind']}",
                f"artifact_records: {payload['artifact_records']}",
                f"lineage_records: {payload['lineage_records']}",
            ]
        )
    return 0


def _cmd_registry_list_runs(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).list_runs()
    except Exception as exc:
        return _emit_registry_error(args, "registry_list_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"{run['run_id']}\t{run['plugin_id']}\t{run['stage']}\t{run['status']}\t{run['manifest_kind']}"
                for run in payload
            ]
        )
    return 0


def _cmd_registry_show_run(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).get_run(args.run_id)
    except Exception as exc:
        return _emit_registry_error(args, "registry_show_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        run = payload["run"]
        _emit_lines(
            [
                f"run_id: {run['run_id']}",
                f"plugin_id: {run['plugin_id']}",
                f"adapter_id: {run['adapter_id']}",
                f"stage: {run['stage']}",
                f"status: {run['status']}",
                f"artifact_records: {len(payload['artifacts'])}",
                f"warnings: {len(payload['warnings'])}",
            ]
        )
    return 0


def _cmd_registry_list_artifacts(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).list_artifacts(args.run_id)
    except Exception as exc:
        return _emit_registry_error(args, "registry_artifacts_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                (
                    f"{artifact['artifact_record_id']}\t{artifact['run_id']}\t{artifact['role']}\t"
                    f"{artifact['artifact_id']}\t{artifact['relative_path']}"
                )
                for artifact in payload
            ]
        )
    return 0


def _cmd_registry_lineage(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).lineage(args.artifact_record_id)
    except Exception as exc:
        return _emit_registry_error(args, "registry_lineage_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        artifact = payload["artifact"]
        _emit_lines(
            [
                f"artifact_record_id: {artifact['artifact_record_id']}",
                f"artifact_id: {artifact['artifact_id']}",
                f"parents: {len(payload['parents'])}",
                f"children: {len(payload['children'])}",
            ]
        )
    return 0


def _cmd_registry_reproducibility(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).reproducibility(args.run_id)
    except Exception as exc:
        return _emit_registry_error(args, "registry_reproducibility_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"run_id: {payload['run_id']}",
                f"status: {payload['status']}",
                f"reasons: {', '.join(payload['reasons']) if payload['reasons'] else 'none'}",
            ]
        )
    return 0


def _cmd_registry_compare_runs(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).compare(args.run_a, args.run_b)
    except Exception as exc:
        return _emit_registry_error(args, "registry_compare_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"run_a: {payload['run_a']}",
                f"run_b: {payload['run_b']}",
                f"status: {payload['status']}",
                f"reasons: {', '.join(payload['reasons']) if payload['reasons'] else 'none'}",
            ]
        )
    return 0


def _cmd_registry_validate(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).validate()
    except Exception as exc:
        return _emit_registry_error(args, "registry_validate_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"schema_version: {payload['schema_version']}",
                *[f"error: {error}" for error in payload["errors"]],
            ]
        )
    return 0 if payload["valid"] else EXIT_REGISTRY


def _cmd_registry_export(args: argparse.Namespace) -> int:
    try:
        payload = _registry_service(args).export(args.export_dir, overwrite=args.overwrite)
    except Exception as exc:
        return _emit_registry_error(args, "registry_export_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload['status']}",
                f"json_path: {payload['json_path']}",
                f"csv_path: {payload['csv_path']}",
                f"run_count: {payload['run_count']}",
                f"artifact_count: {payload['artifact_count']}",
            ]
        )
    return 0


def _cmd_diagnose_run(args: argparse.Namespace) -> int:
    try:
        report = diagnose_run(
            args.run_id,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            rule_set=args.rule_set,
            persist=not args.no_persist,
            check_files=bool(args.check_files),
        )
    except Exception as exc:
        return _emit_diagnostic_error(args, "diagnose_run_failed", exc)
    payload = report.to_dict()
    if args.json:
        _emit_json(payload)
    else:
        evaluation = payload["evaluation"]
        _emit_lines(
            [
                f"run_id: {evaluation['run_id']}",
                f"evaluation_id: {evaluation['evaluation_id']}",
                f"overall_status: {evaluation['overall_status']}",
                f"promotion_status: {evaluation['promotion_status']}",
                f"findings: {evaluation['finding_count']}",
                f"blockers: {evaluation['blocker_count']}",
                f"evidence_gaps: {len(payload['evidence_gaps'])}",
            ]
        )
    return diagnostic_summary_exit_status(report)


def _cmd_show_diagnostics(args: argparse.Namespace) -> int:
    try:
        payload = show_diagnostics(args.run_id, repo_root=Path.cwd(), registry_path=args.registry_path)
    except Exception as exc:
        return _emit_diagnostic_error(args, "show_diagnostics_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        evaluation = payload["evaluation"]
        _emit_lines(
            [
                f"run_id: {evaluation['run_id']}",
                f"evaluation_id: {evaluation['evaluation_id']}",
                f"overall_status: {evaluation['overall_status']}",
                f"promotion_status: {evaluation['promotion_status']}",
                f"findings: {len(payload['findings'])}",
                f"evidence_gaps: {len(payload['evidence_gaps'])}",
            ]
        )
    return 0


def _cmd_list_findings(args: argparse.Namespace) -> int:
    try:
        payload = list_diagnostic_findings(
            run_id=args.run_id,
            severity=args.severity,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except Exception as exc:
        return _emit_diagnostic_error(args, "list_findings_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"{item['run_id']}\t{item['rule_id']}\t{item['severity']}\t{item['status']}\t{item['claim_impact']}"
                for item in payload
            ]
        )
    return 0


def _cmd_list_evidence_gaps(args: argparse.Namespace) -> int:
    try:
        payload = list_evidence_gaps(args.run_id, repo_root=Path.cwd(), registry_path=args.registry_path)
    except Exception as exc:
        return _emit_diagnostic_error(args, "list_evidence_gaps_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"{item['gap_code']}\t{item['priority']}\t{item['current_status']}\t{item['impact']}"
                for item in payload
            ]
        )
    return 0


def _cmd_evaluate_claim(args: argparse.Namespace) -> int:
    try:
        payload = evaluate_claim(
            args.run_id,
            args.claim_id,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            rule_set=args.rule_set,
            persist=not args.no_persist,
        )
    except Exception as exc:
        return _emit_diagnostic_error(args, "evaluate_claim_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"claim_id: {payload['claim_id']}",
                f"status: {payload['status']}",
                f"reason_code: {payload['reason_code']}",
            ]
        )
    return 0 if payload["status"] == "supported" else EXIT_DIAGNOSTIC_WARNING


def _cmd_compare_diagnostics(args: argparse.Namespace) -> int:
    try:
        payload = compare_diagnostic_evaluations(
            args.run_a,
            args.run_b,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except Exception as exc:
        return _emit_diagnostic_error(args, "compare_diagnostics_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"run_a: {payload['run_a']}",
                f"run_b: {payload['run_b']}",
                f"promotion_status_change: {payload['promotion_status_change'][0]} -> {payload['promotion_status_change'][1]}",
                f"newly_violated_rules: {', '.join(payload['newly_violated_rules']) if payload['newly_violated_rules'] else 'none'}",
                f"new_gaps: {', '.join(payload['new_gaps']) if payload['new_gaps'] else 'none'}",
            ]
        )
    return 0


def _cmd_diagnostics_validate(args: argparse.Namespace) -> int:
    try:
        payload = diagnostics_validate(repo_root=Path.cwd(), registry_path=args.registry_path)
    except Exception as exc:
        return _emit_diagnostic_error(args, "diagnostics_validate_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"registry_path: {payload['registry_path']}",
                *[f"error: {error}" for error in payload["errors"]],
            ]
        )
    return 0 if payload["valid"] else EXIT_DIAGNOSTIC_SCHEMA


def _cmd_diagnostics_export(args: argparse.Namespace) -> int:
    try:
        payload = export_diagnostics(
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            export_dir=args.export_dir,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        return _emit_diagnostic_error(args, "diagnostics_export_failed", exc)
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload['status']}",
                f"json_path: {payload['json_path']}",
                f"csv_path: {payload['csv_path']}",
                f"evaluation_count: {payload['evaluation_count']}",
                f"finding_count: {payload['finding_count']}",
            ]
        )
    return 0


def _cmd_list_scientific_constraints(args: argparse.Namespace) -> int:
    _, _, constraint_registry, _ = _scientific_registries()
    constraints = constraint_registry.snapshot(args.domain, args.category)
    if args.json:
        _emit_json(constraints)
    else:
        _emit_lines(
            [
                f"{constraint['constraint_id']}\t{constraint['domain']}\t{constraint['category']}\t{constraint['status']}"
                for constraint in constraints
            ]
        )
    return 0


def _cmd_inspect_scientific_constraint(args: argparse.Namespace) -> int:
    _, _, constraint_registry, _ = _scientific_registries()
    try:
        constraint = constraint_registry.get(args.constraint_id).to_dict()
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(constraint)
    else:
        _emit_lines(
            [
                f"constraint_id: {constraint['constraint_id']}",
                f"domain: {constraint['domain']}",
                f"category: {constraint['category']}",
                f"evaluator_id: {constraint['evaluator_id']}",
                f"evaluation_role: {constraint['evaluation_role']}",
                f"status: {constraint['status']}",
                f"description: {constraint['description']}",
            ]
        )
    return 0


def _cmd_list_knowledge_packs(args: argparse.Namespace) -> int:
    _, _, _, knowledge_registry = _scientific_registries()
    packs = knowledge_registry.snapshot(args.domain)
    if args.json:
        _emit_json(packs)
    else:
        _emit_lines([f"{pack['pack_id']}\t{pack['domain']}\t{pack['status']}" for pack in packs])
    return 0


def _cmd_inspect_knowledge_pack(args: argparse.Namespace) -> int:
    _, _, _, knowledge_registry = _scientific_registries()
    try:
        pack = knowledge_registry.get(args.pack_id).to_dict()
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(pack)
    else:
        _emit_lines(
            [
                f"pack_id: {pack['pack_id']}",
                f"domain: {pack['domain']}",
                f"status: {pack['status']}",
                f"constraints: {', '.join(pack['constraint_ids'])}",
                f"description: {pack['description']}",
            ]
        )
    return 0


def _cmd_check_scientific_applicability(args: argparse.Namespace) -> int:
    _, evaluator_registry, constraint_registry, _ = _scientific_registries()
    try:
        config = load_scientific_config(args.config_path)
        result = check_scientific_applicability(
            config,
            constraint_registry=constraint_registry,
            evaluator_registry=evaluator_registry,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        payload = {"valid": False, "status": "invalid_config", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = result.to_dict()
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"status: {payload['status']}",
                *[f"{item['constraint_id']}: {item['status']}" for item in payload["applicability"]],
            ]
        )
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_validate_scientific_input(args: argparse.Namespace) -> int:
    unit_registry, evaluator_registry, constraint_registry, _ = _scientific_registries()
    try:
        config = load_scientific_config(args.config_path)
        result = validate_scientific_input(
            config,
            constraint_registry=constraint_registry,
            evaluator_registry=evaluator_registry,
            unit_registry=unit_registry,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        payload = {"valid": False, "status": "invalid_config", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = result.to_dict()
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"status: {payload['status']}",
                f"findings: {len(payload['findings'])}",
                *[f"{finding['constraint_id']}: {finding['status']}" for finding in payload["findings"]],
            ]
        )
    return 0 if result.valid else EXIT_INVALID_CONFIG


def _cmd_list_unit_definitions(args: argparse.Namespace) -> int:
    unit_registry, _, _, _ = _scientific_registries()
    units = unit_registry.snapshot(args.dimension)
    if args.json:
        _emit_json(units)
    else:
        _emit_lines([f"{unit['unit_id']}\t{unit['dimension']}\tbase={unit['base_unit']}" for unit in units])
    return 0


def _cmd_convert_unit(args: argparse.Namespace) -> int:
    unit_registry, _, _, _ = _scientific_registries()
    try:
        converted = unit_registry.convert_value(args.value, args.from_unit, args.to_unit)
    except (KeyError, ValueError) as exc:
        payload = {"status": "conversion_failed", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"conversion_failed: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {"status": "converted", "value": args.value, "from_unit": args.from_unit, "to_unit": args.to_unit, "converted_value": converted}
    if args.json:
        _emit_json(payload)
    else:
        print(converted)
    return 0


def _cmd_list_scientific_entity_types(args: argparse.Namespace) -> int:
    schemas = entity_type_schemas()
    payload = [
        {"entity_type": entity_type, **schemas[entity_type]}
        for entity_type in sorted(SUPPORTED_ENTITY_TYPES)
    ]
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"{item['entity_type']}\t{item['purpose']}" for item in payload])
    return 0


def _cmd_inspect_scientific_entity_schema(args: argparse.Namespace) -> int:
    schemas = entity_type_schemas()
    if args.entity_type not in schemas:
        payload = {"status": "not_found", "entity_type": args.entity_type}
        if args.json:
            _emit_json(payload)
        else:
            print(f"not_found: {args.entity_type}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    payload = {"schema_version": "2.2.2", "entity_type": args.entity_type, **schemas[args.entity_type]}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"entity_type: {args.entity_type}",
                f"purpose: {payload['purpose']}",
                f"required_attributes: {', '.join(payload['required_attributes'])}",
            ]
        )
    return 0


def _load_small_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    assert_no_sensitive_strings(payload)
    return payload


def _cmd_validate_scientific_entity(args: argparse.Namespace) -> int:
    try:
        payload = _load_small_json(args.path)
        if "record" in payload and "checksum_sha256" in payload:
            result = validate_record(payload)
        else:
            result = validate_entity_payload(payload).to_dict()
    except (OSError, json.JSONDecodeError, ValueError, RegistryValidationError) as exc:
        result = {"valid": False, "errors": [str(exc)], "validation_status": "invalid"}
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"valid: {str(result.get('valid')).lower()}", *[f"error: {error}" for error in result.get("errors", [])]])
    return 0 if result.get("valid") else EXIT_INVALID_CONFIG


def _cmd_convert_entity_record(args: argparse.Namespace) -> int:
    try:
        payload = _load_small_json(args.path)
        if "record" in payload:
            entity = deserialize_entity_record(payload)
        else:
            entity = ScientificEntity(
                entity_id=str(payload["entity_id"]),
                entity_type=str(payload["entity_type"]),
                schema_id=str(payload["schema_id"]),
                schema_version=str(payload["schema_version"]),
                domain=str(payload["domain"]),
                attributes=payload.get("attributes", {}),
                quantity_fields=payload.get("quantity_fields", {}),
                provenance_refs=tuple(str(item) for item in payload.get("provenance_refs", ())),
                artifact_refs=tuple(str(item) for item in payload.get("artifact_refs", ())),
                created_by=str(payload.get("created_by", "cli")),
                validation_status=str(payload.get("validation_status", "valid")),
            )
        if args.to_version != entity.schema_version:
            registry = build_default_migration_registry()
            migration = registry.migrate(entity.to_dict(), schema_id=entity.entity_type, from_version=entity.schema_version, to_version=args.to_version)
            if migration.status not in {"migrated", "already_current"}:
                raise ValueError("; ".join(migration.errors) or migration.status)
            converted = migration.payload
        else:
            converted = serialize_entity(entity)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, RegistryValidationError) as exc:
        payload = {"status": "conversion_failed", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"conversion_failed: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(converted)
    else:
        _emit_lines([f"entity_id: {converted.get('entity_id')}", f"schema_version: {converted.get('schema_version')}"])
    return 0


def _cmd_list_scientific_relations(args: argparse.Namespace) -> int:
    relations = [relation.to_dict() for relation in default_scientific_relations()]
    if args.json:
        _emit_json(relations)
    else:
        _emit_lines([f"{item['relation_id']}\t{item['category']}\t{item['execution_status']}" for item in relations])
    return 0


def _cmd_inspect_scientific_relation(args: argparse.Namespace) -> int:
    for relation in default_scientific_relations():
        if relation.relation_id == args.relation_id:
            payload = relation.to_dict()
            if args.json:
                _emit_json(payload)
            else:
                _emit_lines(
                    [
                        f"relation_id: {payload['relation_id']}",
                        f"category: {payload['category']}",
                        f"operator_id: {payload['operator_id']}",
                        f"execution_status: {payload['execution_status']}",
                    ]
                )
            return 0
    payload = {"status": "not_found", "relation_id": args.relation_id}
    if args.json:
        _emit_json(payload)
    else:
        print(f"not_found: {args.relation_id}", file=sys.stderr)
    return EXIT_INVALID_CONFIG


def _cmd_validate_scientific_quantity(args: argparse.Namespace) -> int:
    try:
        payload = _load_small_json(args.path)
        result = validate_quantity_payload(payload)
        if result["valid"]:
            quantity = quantity_from_payload(payload)
            result = {**result, "quantity": quantity.to_dict()}
    except (OSError, json.JSONDecodeError, ValueError, KeyError, RegistryValidationError) as exc:
        result = {"valid": False, "errors": [str(exc)]}
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"valid: {str(result.get('valid')).lower()}", *[f"error: {error}" for error in result.get("errors", [])]])
    return 0 if result.get("valid") else EXIT_INVALID_CONFIG


def _cmd_propagate_scientific_uncertainty(args: argparse.Namespace) -> int:
    try:
        config = _load_small_json(args.config)
        operator_id = str(config.get("operator_id", ""))
        if operator_id == "xrd_bragg_uncertainty_v2_2":
            payload = propagate_bragg_uncertainty(config)
        elif operator_id == "xrd_scherrer_uncertainty_v2_2":
            payload = scherrer_uncertainty_eligibility(config)
        else:
            raise ValueError(f"unsupported uncertainty operator_id: {operator_id}")
    except (OSError, json.JSONDecodeError, ValueError, KeyError, RegistryValidationError) as exc:
        payload = {"status": "invalid_config", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"operator_id: {payload.get('operator_id')}", f"status: {payload.get('status')}"])
    return 0 if payload.get("status") not in {"invalid_config", "invalid_input"} else EXIT_INVALID_CONFIG


def _cmd_inspect_unit_backend(args: argparse.Namespace) -> int:
    payload = unit_backend_decision()
    backend = BuiltinUnitBackend()
    payload["builtin_unit_count"] = len(backend.registry.snapshot())
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"decision: {payload['decision']}",
                f"default_backend: {payload['default_backend']}",
                f"pint_available: {str(payload['pint_available']).lower()}",
            ]
        )
    return 0


def _cmd_validate_schema_migrations(args: argparse.Namespace) -> int:
    registry = build_default_migration_registry()
    sample = {
        "entity_id": "composition_demo",
        "entity_type": "MaterialCompositionEntity",
        "schema_id": "scientific_entity_schema_v2",
        "schema_version": "1",
        "domain": "materials",
        "attributes": {"formula": "FeSi", "elements": ["Fe", "Si"], "amounts": {"Fe": 1, "Si": 1}, "atomic_fractions": {"Fe": 0.5, "Si": 0.5}},
    }
    result = registry.migrate(sample, schema_id="MaterialCompositionEntity", from_version="1", to_version="2")
    payload = {"valid": result.status == "migrated", "migration": result.to_dict(), "registered_migrations": registry.snapshot()}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"valid: {str(payload['valid']).lower()}", f"status: {result.status}"])
    return 0 if payload["valid"] else EXIT_INVALID_CONFIG


def _resolve_scientific_export_output(repo_root: Path, output: str) -> Path:
    validate_relative_path(output)
    normalized = output.replace("\\", "/")
    if not normalized.startswith("outputs/"):
        raise ValueError("scientific registry export must be under outputs/")
    root = repo_root.resolve()
    target = (root / output).resolve()
    if root != target and root not in target.parents:
        raise ValueError("scientific registry export must stay inside repository root")
    return target


def _cmd_export_scientific_registry(args: argparse.Namespace) -> int:
    unit_registry, evaluator_registry, constraint_registry, knowledge_registry = _scientific_registries()
    payload = {
        "schema_version": "2.1",
        "platform_version": PLATFORM_VERSION,
        "status": "scaffold_stage",
        "units": unit_registry.snapshot(),
        "evaluators": evaluator_registry.snapshot(),
        "constraints": constraint_registry.snapshot(args.domain),
        "knowledge_packs": knowledge_registry.snapshot(args.domain),
    }
    try:
        target = _resolve_scientific_export_output(Path.cwd(), args.output)
        if target.exists() and not args.overwrite:
            raise FileExistsError(f"output already exists: {args.output}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(target)
    except (OSError, ValueError, FileExistsError) as exc:
        result = {"status": "export_failed", "error": str(exc)}
        if args.json:
            _emit_json(result)
        else:
            print(f"export_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY
    result = {
        "status": "exported",
        "output": target.relative_to(Path.cwd()).as_posix(),
        "constraint_count": len(payload["constraints"]),
        "knowledge_pack_count": len(payload["knowledge_packs"]),
    }
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"status: {result['status']}", f"output: {result['output']}", f"constraint_count: {result['constraint_count']}"])
    return 0


def _science_persist_override(args: argparse.Namespace) -> bool | None:
    if getattr(args, "persist", False) and getattr(args, "no_persist", False):
        raise ValueError("--persist and --no-persist are mutually exclusive")
    if getattr(args, "persist", False):
        return True
    if getattr(args, "no_persist", False):
        return False
    return None


def _scientific_result_summary(result: Any, output_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = result.to_dict()
    summary = {
        "execution_id": payload["execution_id"],
        "knowledge_pack_id": payload["knowledge_pack_id"],
        "overall_status": payload["overall_status"],
        "applicability_status": payload["applicability_status"],
        "finding_count": payload["finding_count"],
        "blocker_count": payload["blocker_count"],
        "scientific_recomputation_performed": payload["scientific_recomputation_performed"],
        "raw_data_read": payload["raw_data_read"],
        "model_training_performed": payload["model_training_performed"],
        "derived_outputs": payload["derived_outputs"],
        "claim_evaluations": payload["claim_evaluations"],
    }
    if output_payload:
        summary["output"] = output_payload
    return summary


def _emit_scientific_summary(args: argparse.Namespace, summary: dict[str, Any]) -> None:
    if args.json:
        _emit_json(summary)
    else:
        _emit_lines(
            [
                f"execution_id: {summary['execution_id']}",
                f"overall_status: {summary['overall_status']}",
                f"applicability_status: {summary['applicability_status']}",
                f"finding_count: {summary['finding_count']}",
                f"blocker_count: {summary['blocker_count']}",
                f"scientific_recomputation_performed: {str(summary['scientific_recomputation_performed']).lower()}",
            ]
        )


def _cmd_preview_scientific_check(args: argparse.Namespace) -> int:
    try:
        config = load_execution_config(args.config_path)
        result = execute_scientific_config(
            config,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            persist=False,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError, RegistryConflictError) as exc:
        payload = {"status": "invalid_config", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"invalid_config: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    _emit_scientific_summary(args, _scientific_result_summary(result))
    return 0 if result.overall_status not in {"invalid_input", "failed"} else EXIT_INVALID_CONFIG


def _cmd_execute_scientific_check(args: argparse.Namespace) -> int:
    try:
        config = load_execution_config(args.config_path)
        result = execute_scientific_config(
            config,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            persist=_science_persist_override(args),
        )
        output_payload = None
        output_policy = config.get("output_policy", {}) if isinstance(config.get("output_policy", {}), dict) else {}
        if args.output_dir or output_policy.get("write_outputs") is True:
            output_payload = write_scientific_outputs(
                result,
                repo_root=Path.cwd(),
                output_dir=args.output_dir or output_policy.get("output_dir"),
                overwrite=bool(output_policy.get("overwrite", False) or getattr(args, "overwrite", False)),
            )
    except (OSError, json.JSONDecodeError, ValueError, KeyError, RegistryConflictError) as exc:
        payload = {"status": "execution_failed", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"execution_failed: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    except (RegistryPathError, FileExistsError) as exc:
        payload = {"status": "output_failed", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"output_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY
    _emit_scientific_summary(args, _scientific_result_summary(result, output_payload))
    return 0 if result.overall_status not in {"invalid_input", "failed"} else EXIT_INVALID_CONFIG


def _cmd_show_scientific_execution(args: argparse.Namespace) -> int:
    try:
        payload = get_scientific_execution(args.execution_id, repo_root=Path.cwd(), registry_path=args.registry_path)
    except (KeyError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        row = payload["execution"]
        _emit_lines(
            [
                f"execution_id: {row['execution_id']}",
                f"knowledge_pack_id: {row['knowledge_pack_id']}",
                f"status: {row['status']}",
                f"finding_count: {row['finding_count']}",
                f"blocker_count: {row['blocker_count']}",
            ]
        )
    return 0


def _cmd_list_scientific_findings(args: argparse.Namespace) -> int:
    try:
        payload = list_scientific_findings(
            execution_id=args.execution_id,
            severity=args.severity,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except (RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "list_failed", "error": str(exc)})
        else:
            print(f"list_failed: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"{row['execution_id']}\t{row['constraint_id']}\t{row['severity']}\t{row['status']}" for row in payload])
    return 0


def _cmd_evaluate_scientific_claim(args: argparse.Namespace) -> int:
    try:
        payload = get_scientific_claim_evaluation(
            args.execution_id,
            args.claim_id,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except (KeyError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "claim_failed", "error": str(exc)})
        else:
            print(f"claim_failed: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"execution_id: {payload.get('execution_id', args.execution_id)}",
                f"claim_id: {payload['claim_id']}",
                f"status: {payload['status']}",
                f"reason_code: {payload['reason_code']}",
            ]
        )
    return 0


def _cmd_validate_scientific_result(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
        result = validate_scientific_result_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"valid": False, "errors": [str(exc)]}
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"valid: {str(result['valid']).lower()}", *[f"error: {error}" for error in result["errors"]]])
    return 0 if result["valid"] else EXIT_INVALID_CONFIG


def _cmd_export_scientific_findings(args: argparse.Namespace) -> int:
    try:
        payload = export_scientific_findings(
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
            output=args.output,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, FileExistsError, RegistryPathError) as exc:
        payload = {"status": "export_failed", "error": str(exc)}
        if args.json:
            _emit_json(payload)
        else:
            print(f"export_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"status: {payload['status']}", f"output: {payload['output']}", f"finding_count: {payload['finding_count']}"])
    return 0


def _cmd_scientific_registry_validate(args: argparse.Namespace) -> int:
    try:
        payload = validate_scientific_registry(repo_root=Path.cwd(), registry_path=args.registry_path)
    except (RunRegistryError, RegistryPathError) as exc:
        payload = {"valid": False, "errors": [str(exc)]}
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"valid: {str(payload['valid']).lower()}", *[f"error: {error}" for error in payload["errors"]]])
    return 0 if payload["valid"] else EXIT_REGISTRY


def _cmd_list_scientific_feature_candidates(args: argparse.Namespace) -> int:
    registry = build_default_scientific_feature_registry()
    payload = registry.snapshot(
        domain=args.domain,
        eligibility_status=args.eligibility_status,
        validation_status=args.validation_status,
    )
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"{row['feature_id']}\t{row['domain']}\t{row['eligibility_status']}\t{row['validation_status']}"
                for row in payload
            ]
        )
    return 0


def _cmd_inspect_scientific_feature_candidate(args: argparse.Namespace) -> int:
    try:
        payload = build_default_scientific_feature_registry().get(args.feature_id).to_dict()
    except KeyError as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"feature_id: {payload['feature_id']}",
                f"domain: {payload['domain']}",
                f"eligibility_status: {payload['eligibility_status']}",
                f"validation_status: {payload['validation_status']}",
                f"expected_claim: {payload['expected_claim']}",
            ]
        )
    return 0


def _cmd_evaluate_scientific_feature(args: argparse.Namespace) -> int:
    try:
        execution = get_scientific_execution(args.execution_id, repo_root=Path.cwd(), registry_path=args.registry_path)
        feature = build_default_scientific_feature_registry().get(args.feature_id)
        payload = evaluate_feature_candidate_against_execution(feature, execution).to_dict()
    except (KeyError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "feature_evaluation_failed", "error": str(exc)})
        else:
            print(f"feature_evaluation_failed: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"feature_id: {payload['feature_id']}",
                f"eligibility_status: {payload['eligibility_status']}",
                f"leakage_status: {payload['leakage_status']}",
                f"assumption_status: {payload['assumption_status']}",
            ]
        )
    return 0


def _cmd_evaluate_scientific_trust(args: argparse.Namespace) -> int:
    try:
        execution = get_scientific_execution(args.execution_id, repo_root=Path.cwd(), registry_path=args.registry_path)
        evaluation = evaluate_scientific_trust(execution)
        payload = evaluation.to_dict()
        storage = None
        if not args.no_persist:
            storage = store_scientific_trust_evaluation(payload, repo_root=Path.cwd(), registry_path=args.registry_path)
            payload["persistence"] = storage
    except (KeyError, RunRegistryError, RegistryPathError, RegistryConflictError, ValueError) as exc:
        if args.json:
            _emit_json({"status": "trust_evaluation_failed", "error": str(exc)})
        else:
            print(f"trust_evaluation_failed: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        eligible_count = sum(
            row["eligibility_status"] in {"eligible_bounded", "eligible_with_metadata_requirement"}
            for row in payload["feature_eligibility"]
        )
        _emit_lines(
            [
                f"trust_evaluation_id: {payload['evaluation_id']}",
                f"execution_id: {payload['execution_id']}",
                f"evidence_level: {payload['evidence_level']}",
                f"feature_eligible_count: {eligible_count}",
                f"prohibited_claim_count: {len(payload['prohibited_claims'])}",
                f"persisted: {str(not args.no_persist).lower()}",
            ]
        )
    return 0


def _cmd_show_scientific_trust(args: argparse.Namespace) -> int:
    try:
        payload = get_scientific_trust_evaluation(
            args.trust_evaluation_id,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except (KeyError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        row = payload["evaluation"]
        _emit_lines(
            [
                f"trust_evaluation_id: {row['trust_evaluation_id']}",
                f"execution_id: {row['execution_id']}",
                f"evidence_level: {row['evidence_level']}",
                f"feature_eligible_count: {row['feature_eligible_count']}",
                f"blocker_count: {row['blocker_count']}",
            ]
        )
    return 0


def _cmd_list_feature_eligibility(args: argparse.Namespace) -> int:
    try:
        payload = list_scientific_feature_eligibility(
            args.trust_evaluation_id,
            repo_root=Path.cwd(),
            registry_path=args.registry_path,
        )
    except (KeyError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_REGISTRY
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"{row['feature_id']}\t{row['eligibility_status']}\t{row['leakage_status']}" for row in payload])
    return 0


def _cmd_list_scientific_claim_boundaries(args: argparse.Namespace) -> int:
    if args.trust_evaluation_id:
        try:
            payload = get_scientific_trust_evaluation(
                args.trust_evaluation_id,
                repo_root=Path.cwd(),
                registry_path=args.registry_path,
            )["claim_boundaries"]
        except (KeyError, RunRegistryError, RegistryPathError) as exc:
            if args.json:
                _emit_json({"status": "not_found", "error": str(exc)})
            else:
                print(f"not_found: {exc}", file=sys.stderr)
            return EXIT_REGISTRY
    else:
        payload = [
            {
                "claim_id": claim_id,
                "default_status": "registered_boundary",
                "execution_evidence_required": claim_id
                not in {"physics_informed_feature_available", "bounded_quantity_estimated"},
            }
            for claim_id in CLAIM_BOUNDARY_IDS
        ]
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"{row.get('claim_id')}\t{row.get('status', row.get('default_status'))}" for row in payload])
    return 0


def _cmd_scientific_trust_validate(args: argparse.Namespace) -> int:
    registry = build_default_scientific_feature_registry()
    feature_validation = registry.validate()
    constraint_registry = build_default_scientific_constraint_registry()
    constraint_roles = constraint_role_snapshot(constraint_registry)
    registry_validation = validate_scientific_registry(repo_root=Path.cwd(), registry_path=args.registry_path)
    payload = {
        "valid": bool(feature_validation["valid"] and registry_validation["valid"]),
        "feature_registry": feature_validation,
        "constraint_role_count": len(constraint_roles),
        "registry_validation": registry_validation,
    }
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"feature_count: {feature_validation['feature_count']}",
                f"constraint_role_count: {len(constraint_roles)}",
            ]
        )
    return 0 if payload["valid"] else EXIT_REGISTRY


def _cmd_export_scientific_trust(args: argparse.Namespace) -> int:
    try:
        validate_relative_path(args.output)
        normalized = args.output.replace("\\", "/")
        if not normalized.startswith("outputs/platform_science/"):
            raise RegistryPathError("scientific trust export must be under outputs/platform_science/")
        root = Path.cwd().resolve()
        target = (root / args.output).resolve()
        if root != target and root not in target.parents:
            raise RegistryPathError("scientific trust export must stay inside repository root")
        if target.exists() and not args.overwrite:
            raise FileExistsError(f"export already exists: {target.relative_to(root).as_posix()}")
        trust_rows = list_scientific_trust_evaluations(repo_root=root, registry_path=args.registry_path)
        payload = {
            "schema_version": "2.1.5",
            "trust_evaluations": [
                get_scientific_trust_evaluation(
                    row["trust_evaluation_id"],
                    repo_root=root,
                    registry_path=args.registry_path,
                )
                for row in trust_rows
            ],
            "closeout": closeout_conclusion().to_dict(),
        }
        assert_no_sensitive_strings(payload)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.tmp")
        try:
            temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp.replace(target)
        finally:
            if temp.exists():
                temp.unlink()
    except (OSError, ValueError, FileExistsError, RunRegistryError, RegistryPathError) as exc:
        if args.json:
            _emit_json({"status": "export_failed", "error": str(exc)})
        else:
            print(f"export_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY
    result = {
        "status": "exported",
        "output": target.relative_to(root).as_posix(),
        "trust_evaluation_count": len(payload["trust_evaluations"]),
    }
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"status: {result['status']}", f"output: {result['output']}", f"trust_evaluation_count: {result['trust_evaluation_count']}"])
    return 0


def _cmd_list_materials_feature_builders(args: argparse.Namespace) -> int:
    payload = materials_feature_definitions().to_dict(orient="records")
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines([f"{row['feature_id']}\t{row['role']}\t{row['unit']}" for row in payload])
    return 0


def _cmd_inspect_materials_feature_builder(args: argparse.Namespace) -> int:
    try:
        payload = get_materials_feature_definition(args.feature_id)
    except KeyError as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"feature_id: {payload['feature_id']}",
                f"column_name: {payload['column_name']}",
                f"role: {payload['role']}",
                f"unit: {payload['unit']}",
                f"formula: {payload['formula']}",
            ]
        )
    return 0


def _cmd_build_materials_physics_features(args: argparse.Namespace) -> int:
    try:
        config = load_materials_json(args.config_path)
        request = build_materials_feature_request_from_config(config)
        payload = run_feature_build(request)
    except (OSError, ValueError, RuntimeError, FileExistsError) as exc:
        if args.json:
            _emit_json({"status": "materials_feature_build_failed", "error": str(exc)})
        else:
            print(f"materials_feature_build_failed: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_FAILURE
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload.get('run_stage')}",
                f"feature_rows: {payload.get('feature_rows')}",
                f"generated_rows: {payload.get('generated_rows')}",
                f"feature_matrix: {payload['local_outputs']['feature_matrix']}",
            ]
        )
    return 0


def _cmd_validate_materials_feature_artifact(args: argparse.Namespace) -> int:
    try:
        payload = validate_feature_artifact(args.path)
    except (OSError, ValueError) as exc:
        if args.json:
            _emit_json({"valid": False, "error": str(exc)})
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"valid: {str(payload['valid']).lower()}",
                f"row_count: {payload['row_count']}",
                f"generated_rows: {payload['generated_rows']}",
            ]
        )
    return 0 if payload["valid"] else EXIT_INVALID_CONFIG


def _cmd_run_materials_feature_comparison(args: argparse.Namespace) -> int:
    try:
        config = load_materials_json(args.config_path)
        request = build_materials_comparison_request_from_config(config)
        payload = run_predictive_comparison(request)
    except (OSError, ValueError, RuntimeError, FileExistsError) as exc:
        if args.json:
            _emit_json({"status": "materials_feature_comparison_failed", "error": str(exc)})
        else:
            print(f"materials_feature_comparison_failed: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_FAILURE
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"status: {payload['decision_status']}",
                f"matched_rows: {payload['rows']['matched_rows']}",
                f"local_manifest: {payload['local_outputs']['local_manifest']}",
            ]
        )
    return 0


def _cmd_show_materials_feature_comparison(args: argparse.Namespace) -> int:
    candidate = Path(args.result)
    if not candidate.exists():
        if args.result == "latest":
            candidate = Path("data/processed/materials_physics_v2_2_predictive_value_decision.json")
        else:
            candidate = Path("outputs/materials_physics_v2_2") / args.result / "materials_physics_v2_2_comparison_manifest.json"
    try:
        payload = load_materials_json(candidate)
    except (OSError, ValueError) as exc:
        if args.json:
            _emit_json({"status": "not_found", "error": str(exc)})
        else:
            print(f"not_found: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    if args.json:
        _emit_json(payload)
    else:
        _emit_lines(
            [
                f"schema_version: {payload.get('schema_version')}",
                f"status: {payload.get('predictive_value_status', payload.get('decision_status', 'unavailable'))}",
                f"matched_rows: {payload.get('matched_rows', payload.get('rows', {}).get('matched_rows', 'unavailable'))}",
            ]
        )
    return 0


def _cmd_export_materials_feature_summary(args: argparse.Namespace) -> int:
    try:
        decision = load_materials_json(args.decision)
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8")) if args.summary.endswith(".json") else None
        if summary is None:
            import pandas as pd

            summary_df = pd.read_csv(args.summary)
            report = render_predictive_value_report(decision, summary_df)
            payload: dict[str, Any] = {
                "schema_version": decision.get("schema_version"),
                "decision": decision,
                "summary_row_count": int(len(summary_df)),
            }
        else:
            report = json.dumps(summary, indent=2, sort_keys=True)
            payload = {"schema_version": decision.get("schema_version"), "decision": decision, "summary": summary}
        output = Path(args.output)
        validate_relative_path(output.as_posix())
        if not output.as_posix().startswith("outputs/"):
            raise ValueError("materials feature summary export must be under outputs/")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.markdown_output:
            markdown_output = Path(args.markdown_output)
            validate_relative_path(markdown_output.as_posix())
            if not markdown_output.as_posix().startswith("outputs/"):
                raise ValueError("materials feature markdown export must be under outputs/")
            markdown_output.parent.mkdir(parents=True, exist_ok=True)
            markdown_output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as exc:
        if args.json:
            _emit_json({"status": "export_failed", "error": str(exc)})
        else:
            print(f"export_failed: {exc}", file=sys.stderr)
        return EXIT_PATH_POLICY
    result = {"status": "exported", "output": output.as_posix()}
    if args.json:
        _emit_json(result)
    else:
        _emit_lines([f"status: exported", f"output: {output.as_posix()}"])
    return 0


def _cmd_show_version(args: argparse.Namespace) -> int:
    payload = {"platform_version": PLATFORM_VERSION}
    if args.json:
        _emit_json(payload)
    else:
        print(PLATFORM_VERSION)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="materials_data_analyzer v2 platform scaffold")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_registry_path(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--registry-path",
            default=DEFAULT_REGISTRY_PATH,
            help="repository-relative SQLite registry path under outputs/platform_registry",
        )

    subparsers.add_parser("list-plugins", help="list registered case-study plugins").set_defaults(func=_cmd_list_plugins)

    inspect_parser = subparsers.add_parser("inspect-plugin", help="inspect one plugin")
    inspect_parser.add_argument("plugin_id")
    inspect_parser.set_defaults(func=_cmd_inspect_plugin)

    artifacts_parser = subparsers.add_parser("list-artifacts", help="list registered artifacts")
    artifacts_parser.add_argument("--plugin", help="filter by plugin_id")
    artifacts_parser.set_defaults(func=_cmd_list_artifacts)

    adapters_parser = subparsers.add_parser("list-adapters", help="list registered stage adapters")
    adapters_parser.add_argument("--plugin", help="filter by plugin_id")
    adapters_parser.set_defaults(func=_cmd_list_adapters)

    inspect_adapter_parser = subparsers.add_parser("inspect-adapter", help="inspect one adapter")
    inspect_adapter_parser.add_argument("adapter_id")
    inspect_adapter_parser.set_defaults(func=_cmd_inspect_adapter)

    subparsers.add_parser("list-case-studies", help="list registered case-study interfaces").set_defaults(
        func=_cmd_list_case_studies
    )

    inspect_case_study_parser = subparsers.add_parser("inspect-case-study", help="inspect one case-study interface")
    inspect_case_study_parser.add_argument("case_study_id")
    inspect_case_study_parser.set_defaults(func=_cmd_inspect_case_study)

    case_study_stages_parser = subparsers.add_parser(
        "list-case-study-stages", help="list lifecycle-stage metadata for one case study"
    )
    case_study_stages_parser.add_argument("case_study_id")
    case_study_stages_parser.set_defaults(func=_cmd_list_case_study_stages)

    validate_parser = subparsers.add_parser("validate-config", help="validate a pipeline config")
    validate_parser.add_argument("config_path")
    validate_parser.set_defaults(func=_cmd_validate_config)

    validate_onboarding_parser = subparsers.add_parser(
        "validate-onboarding", help="validate a new-domain onboarding contract"
    )
    validate_onboarding_parser.add_argument("config_path")
    validate_onboarding_parser.set_defaults(func=_cmd_validate_onboarding)

    inspect_onboarding_parser = subparsers.add_parser(
        "inspect-onboarding", help="inspect onboarding readiness without side effects"
    )
    inspect_onboarding_parser.add_argument("config_path")
    inspect_onboarding_parser.set_defaults(func=_cmd_inspect_onboarding)

    onboarding_plan_parser = subparsers.add_parser(
        "onboarding-plan", help="show next steps for a new-domain onboarding contract"
    )
    onboarding_plan_parser.add_argument("config_path")
    onboarding_plan_parser.set_defaults(func=_cmd_onboarding_plan)

    dry_run_parser = subparsers.add_parser("dry-run", help="build a dry-run execution plan")
    dry_run_parser.add_argument("config_path")
    dry_run_parser.add_argument("--write-manifest", action="store_true", help="write a local dry-run manifest")
    dry_run_parser.add_argument("--manifest-out", help="relative output path for the run manifest")
    dry_run_parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing manifest")
    dry_run_parser.add_argument("--register-run", action="store_true", help="ingest the written manifest into the local registry")
    add_registry_path(dry_run_parser)
    dry_run_parser.set_defaults(func=_cmd_dry_run)

    execute_parser = subparsers.add_parser("execute", help="execute an approved adapter in controlled mode")
    execute_parser.add_argument("config_path")
    execute_parser.add_argument("--mode", choices=["verify", "isolated_run"], default=None)
    execute_parser.add_argument("--write-manifest", action="store_true", help="accepted for compatibility; execute always writes a terminal manifest")
    execute_parser.add_argument("--run-id")
    execute_parser.add_argument("--output-dir")
    execute_parser.add_argument("--overwrite", action="store_true")
    execute_parser.add_argument("--register-run", action="store_true", help="ingest the terminal manifest into the local registry")
    add_registry_path(execute_parser)
    execute_parser.set_defaults(func=_cmd_execute)

    verify_run_parser = subparsers.add_parser("verify-run", help="verify a terminal run manifest")
    verify_run_parser.add_argument("manifest_path")
    verify_run_parser.set_defaults(func=_cmd_verify_run)

    policy_parser = subparsers.add_parser("show-policy", help="show validation or trust policy metadata")
    policy_parser.add_argument("policy_id")
    policy_parser.set_defaults(func=_cmd_show_policy)

    subparsers.add_parser("list-executable-adapters", help="list execution allowlist entries").set_defaults(func=_cmd_list_executable_adapters)

    execution_policy_parser = subparsers.add_parser("show-execution-policy", help="show adapter execution policy")
    execution_policy_parser.add_argument("adapter_id")
    execution_policy_parser.set_defaults(func=_cmd_show_execution_policy)

    show_manifest_parser = subparsers.add_parser("show-manifest", help="show a run manifest")
    show_manifest_parser.add_argument("manifest_path")
    show_manifest_parser.set_defaults(func=_cmd_show_manifest)

    validate_manifest_parser = subparsers.add_parser("validate-manifest", help="validate a run manifest")
    validate_manifest_parser.add_argument("manifest_path")
    validate_manifest_parser.set_defaults(func=_cmd_validate_manifest)

    generate_report_parser = subparsers.add_parser("generate-report", help="generate a local-only platform report")
    generate_report_parser.add_argument("--config", dest="config_path", required=True)
    generate_report_parser.add_argument("--format", choices=["json", "markdown", "all"])
    generate_report_parser.add_argument("--case-study", action="append", help="filter to a case_study_id; may be repeated")
    generate_report_parser.add_argument("--output-dir", help="repository-relative outputs/platform_reports directory")
    generate_report_parser.add_argument("--report-id", help="override report_id")
    generate_report_parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing report")
    generate_report_parser.add_argument("--register-run", action="store_true", help="ingest the report manifest into the local registry")
    add_registry_path(generate_report_parser)
    generate_report_parser.set_defaults(func=_cmd_generate_report)

    preview_report_parser = subparsers.add_parser("preview-report", help="preview a platform report without writing files")
    preview_report_parser.add_argument("--config", dest="config_path", required=True)
    preview_report_parser.add_argument("--format", choices=["json", "markdown", "all"])
    preview_report_parser.add_argument("--case-study", action="append", help="filter to a case_study_id; may be repeated")
    preview_report_parser.add_argument("--output-dir", help="accepted for preview compatibility")
    preview_report_parser.add_argument("--report-id", help="override report_id")
    preview_report_parser.set_defaults(func=_cmd_preview_report)

    validate_report_parser = subparsers.add_parser("validate-report", help="validate a generated platform report manifest")
    validate_report_parser.add_argument("report_path")
    validate_report_parser.set_defaults(func=_cmd_validate_report)

    inspect_report_parser = subparsers.add_parser("inspect-report", help="inspect a generated platform report")
    inspect_report_parser.add_argument("report_path")
    inspect_report_parser.set_defaults(func=_cmd_inspect_report)

    subparsers.add_parser("list-report-sources", help="list tracked compact artifacts used by platform reports").set_defaults(
        func=_cmd_list_report_sources
    )

    registry_init_parser = subparsers.add_parser("registry-init", help="initialize the local platform registry")
    add_registry_path(registry_init_parser)
    registry_init_parser.set_defaults(func=_cmd_registry_init)

    registry_ingest_parser = subparsers.add_parser("registry-ingest", help="ingest one run or report manifest")
    registry_ingest_parser.add_argument("manifest_path")
    add_registry_path(registry_ingest_parser)
    registry_ingest_parser.set_defaults(func=_cmd_registry_ingest)

    registry_list_runs_parser = subparsers.add_parser("registry-list-runs", help="list persisted run records")
    add_registry_path(registry_list_runs_parser)
    registry_list_runs_parser.set_defaults(func=_cmd_registry_list_runs)

    registry_show_run_parser = subparsers.add_parser("registry-show-run", help="show one persisted run record")
    registry_show_run_parser.add_argument("run_id")
    add_registry_path(registry_show_run_parser)
    registry_show_run_parser.set_defaults(func=_cmd_registry_show_run)

    registry_list_artifacts_parser = subparsers.add_parser("registry-list-artifacts", help="list persisted artifact records")
    registry_list_artifacts_parser.add_argument("--run-id")
    add_registry_path(registry_list_artifacts_parser)
    registry_list_artifacts_parser.set_defaults(func=_cmd_registry_list_artifacts)

    registry_lineage_parser = subparsers.add_parser("registry-lineage", help="show lineage for one artifact record")
    registry_lineage_parser.add_argument("artifact_record_id")
    add_registry_path(registry_lineage_parser)
    registry_lineage_parser.set_defaults(func=_cmd_registry_lineage)

    registry_repro_parser = subparsers.add_parser("registry-reproducibility", help="assess one run's metadata reproducibility")
    registry_repro_parser.add_argument("run_id")
    add_registry_path(registry_repro_parser)
    registry_repro_parser.set_defaults(func=_cmd_registry_reproducibility)

    registry_compare_parser = subparsers.add_parser("registry-compare-runs", help="compare two persisted run records")
    registry_compare_parser.add_argument("run_a")
    registry_compare_parser.add_argument("run_b")
    add_registry_path(registry_compare_parser)
    registry_compare_parser.set_defaults(func=_cmd_registry_compare_runs)

    registry_validate_parser = subparsers.add_parser("registry-validate", help="validate registry integrity")
    add_registry_path(registry_validate_parser)
    registry_validate_parser.set_defaults(func=_cmd_registry_validate)

    registry_export_parser = subparsers.add_parser("registry-export", help="export a local registry snapshot")
    registry_export_parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR)
    registry_export_parser.add_argument("--overwrite", action="store_true")
    add_registry_path(registry_export_parser)
    registry_export_parser.set_defaults(func=_cmd_registry_export)

    diagnose_run_parser = subparsers.add_parser("diagnose-run", help="evaluate deterministic policy diagnostics for one run")
    diagnose_run_parser.add_argument("run_id")
    diagnose_run_parser.add_argument("--rule-set", default="diagnostic_rules_v1")
    diagnose_run_parser.add_argument("--no-persist", action="store_true", help="do not store the diagnostic evaluation")
    diagnose_run_parser.add_argument("--check-files", action="store_true", help="verify tracked artifact checksums when files exist")
    add_registry_path(diagnose_run_parser)
    diagnose_run_parser.set_defaults(func=_cmd_diagnose_run)

    show_diagnostics_parser = subparsers.add_parser("show-diagnostics", help="show the latest persisted diagnostics for one run")
    show_diagnostics_parser.add_argument("run_id")
    add_registry_path(show_diagnostics_parser)
    show_diagnostics_parser.set_defaults(func=_cmd_show_diagnostics)

    findings_parser = subparsers.add_parser("list-findings", help="list persisted diagnostic findings")
    findings_parser.add_argument("--run-id")
    findings_parser.add_argument("--severity", choices=["info", "warning", "error", "blocker"])
    add_registry_path(findings_parser)
    findings_parser.set_defaults(func=_cmd_list_findings)

    gaps_parser = subparsers.add_parser("list-evidence-gaps", help="list evidence gaps for one diagnosed run")
    gaps_parser.add_argument("run_id")
    add_registry_path(gaps_parser)
    gaps_parser.set_defaults(func=_cmd_list_evidence_gaps)

    claim_parser = subparsers.add_parser("evaluate-claim", help="evaluate one registered claim against persisted run evidence")
    claim_parser.add_argument("run_id")
    claim_parser.add_argument("claim_id")
    claim_parser.add_argument("--rule-set", default="diagnostic_rules_v1")
    claim_parser.add_argument("--no-persist", action="store_true")
    add_registry_path(claim_parser)
    claim_parser.set_defaults(func=_cmd_evaluate_claim)

    compare_diagnostics_parser = subparsers.add_parser("compare-diagnostics", help="compare latest diagnostic evaluations for two runs")
    compare_diagnostics_parser.add_argument("run_a")
    compare_diagnostics_parser.add_argument("run_b")
    add_registry_path(compare_diagnostics_parser)
    compare_diagnostics_parser.set_defaults(func=_cmd_compare_diagnostics)

    diagnostics_validate_parser = subparsers.add_parser("diagnostics-validate", help="validate diagnostic registry tables")
    add_registry_path(diagnostics_validate_parser)
    diagnostics_validate_parser.set_defaults(func=_cmd_diagnostics_validate)

    diagnostics_export_parser = subparsers.add_parser("diagnostics-export", help="export a local diagnostics snapshot")
    diagnostics_export_parser.add_argument("--export-dir", default="outputs/platform_registry/exports/diagnostics")
    diagnostics_export_parser.add_argument("--overwrite", action="store_true")
    add_registry_path(diagnostics_export_parser)
    diagnostics_export_parser.set_defaults(func=_cmd_diagnostics_export)

    scientific_constraints_parser = subparsers.add_parser(
        "list-scientific-constraints", help="list registered scientific constraint metadata"
    )
    scientific_constraints_parser.add_argument("--domain")
    scientific_constraints_parser.add_argument("--category")
    scientific_constraints_parser.set_defaults(func=_cmd_list_scientific_constraints)

    inspect_constraint_parser = subparsers.add_parser(
        "inspect-scientific-constraint", help="inspect one scientific constraint"
    )
    inspect_constraint_parser.add_argument("constraint_id")
    inspect_constraint_parser.set_defaults(func=_cmd_inspect_scientific_constraint)

    knowledge_packs_parser = subparsers.add_parser("list-knowledge-packs", help="list domain-knowledge packs")
    knowledge_packs_parser.add_argument("--domain")
    knowledge_packs_parser.set_defaults(func=_cmd_list_knowledge_packs)

    inspect_pack_parser = subparsers.add_parser("inspect-knowledge-pack", help="inspect one domain-knowledge pack")
    inspect_pack_parser.add_argument("pack_id")
    inspect_pack_parser.set_defaults(func=_cmd_inspect_knowledge_pack)

    applicability_parser = subparsers.add_parser(
        "check-scientific-applicability", help="check scientific constraint applicability for a small JSON config"
    )
    applicability_parser.add_argument("config_path")
    applicability_parser.set_defaults(func=_cmd_check_scientific_applicability)

    validate_scientific_parser = subparsers.add_parser(
        "validate-scientific-input", help="validate small explicit scientific metadata against registered constraints"
    )
    validate_scientific_parser.add_argument("config_path")
    validate_scientific_parser.set_defaults(func=_cmd_validate_scientific_input)

    units_parser = subparsers.add_parser("list-unit-definitions", help="list supported unit metadata")
    units_parser.add_argument("--dimension")
    units_parser.set_defaults(func=_cmd_list_unit_definitions)

    convert_parser = subparsers.add_parser("convert-unit", help="convert a numeric value between supported compatible units")
    convert_parser.add_argument("--value", type=float, required=True)
    convert_parser.add_argument("--from", dest="from_unit", required=True)
    convert_parser.add_argument("--to", dest="to_unit", required=True)
    convert_parser.set_defaults(func=_cmd_convert_unit)

    entity_types_parser = subparsers.add_parser("list-scientific-entity-types", help="list supported scientific entity types")
    entity_types_parser.set_defaults(func=_cmd_list_scientific_entity_types)

    inspect_entity_schema_parser = subparsers.add_parser(
        "inspect-scientific-entity-schema",
        help="inspect a scientific entity schema contract",
    )
    inspect_entity_schema_parser.add_argument("entity_type")
    inspect_entity_schema_parser.set_defaults(func=_cmd_inspect_scientific_entity_schema)

    validate_entity_parser = subparsers.add_parser(
        "validate-scientific-entity",
        help="validate a small scientific entity JSON record",
    )
    validate_entity_parser.add_argument("path")
    validate_entity_parser.set_defaults(func=_cmd_validate_scientific_entity)

    convert_entity_parser = subparsers.add_parser(
        "convert-entity-record",
        help="convert or serialize a scientific entity record to a supported schema version",
    )
    convert_entity_parser.add_argument("path")
    convert_entity_parser.add_argument("--to-version", required=True)
    convert_entity_parser.set_defaults(func=_cmd_convert_entity_record)

    relations_parser = subparsers.add_parser("list-scientific-relations", help="list registered scientific relation metadata")
    relations_parser.set_defaults(func=_cmd_list_scientific_relations)

    inspect_relation_parser = subparsers.add_parser("inspect-scientific-relation", help="inspect one scientific relation")
    inspect_relation_parser.add_argument("relation_id")
    inspect_relation_parser.set_defaults(func=_cmd_inspect_scientific_relation)

    validate_quantity_parser = subparsers.add_parser("validate-scientific-quantity", help="validate a scientific quantity JSON record")
    validate_quantity_parser.add_argument("path")
    validate_quantity_parser.set_defaults(func=_cmd_validate_scientific_quantity)

    propagate_uncertainty_parser = subparsers.add_parser(
        "propagate-scientific-uncertainty",
        help="run a bounded uncertainty propagation or eligibility check from a small JSON config",
    )
    propagate_uncertainty_parser.add_argument("config")
    propagate_uncertainty_parser.set_defaults(func=_cmd_propagate_scientific_uncertainty)

    unit_backend_parser = subparsers.add_parser("inspect-unit-backend", help="inspect the active unit backend decision")
    unit_backend_parser.set_defaults(func=_cmd_inspect_unit_backend)

    schema_migration_parser = subparsers.add_parser("validate-schema-migrations", help="validate registered schema migration fixtures")
    schema_migration_parser.set_defaults(func=_cmd_validate_schema_migrations)

    export_scientific_parser = subparsers.add_parser(
        "export-scientific-registry", help="export scientific registry metadata to an ignored outputs path"
    )
    export_scientific_parser.add_argument("--output", default="outputs/platform_science/scientific_registry.json")
    export_scientific_parser.add_argument("--domain")
    export_scientific_parser.add_argument("--overwrite", action="store_true")
    export_scientific_parser.set_defaults(func=_cmd_export_scientific_registry)

    preview_scientific_parser = subparsers.add_parser(
        "preview-scientific-check", help="preview a bounded scientific check without persistence or file output"
    )
    preview_scientific_parser.add_argument("config_path")
    add_registry_path(preview_scientific_parser)
    preview_scientific_parser.set_defaults(func=_cmd_preview_scientific_check)

    execute_scientific_parser = subparsers.add_parser(
        "execute-scientific-check", help="execute a bounded scientific check with optional persistence"
    )
    execute_scientific_parser.add_argument("config_path")
    add_registry_path(execute_scientific_parser)
    persist_group = execute_scientific_parser.add_mutually_exclusive_group()
    persist_group.add_argument("--persist", action="store_true")
    persist_group.add_argument("--no-persist", action="store_true")
    execute_scientific_parser.add_argument("--output-dir")
    execute_scientific_parser.add_argument("--overwrite", action="store_true")
    execute_scientific_parser.set_defaults(func=_cmd_execute_scientific_check)

    show_scientific_execution_parser = subparsers.add_parser(
        "show-scientific-execution", help="show one persisted scientific execution"
    )
    show_scientific_execution_parser.add_argument("execution_id")
    add_registry_path(show_scientific_execution_parser)
    show_scientific_execution_parser.set_defaults(func=_cmd_show_scientific_execution)

    list_scientific_findings_parser = subparsers.add_parser(
        "list-scientific-findings", help="list persisted scientific findings"
    )
    list_scientific_findings_parser.add_argument("--execution-id")
    list_scientific_findings_parser.add_argument("--severity")
    add_registry_path(list_scientific_findings_parser)
    list_scientific_findings_parser.set_defaults(func=_cmd_list_scientific_findings)

    scientific_claim_parser = subparsers.add_parser(
        "evaluate-scientific-claim", help="show one persisted scientific claim evaluation"
    )
    scientific_claim_parser.add_argument("execution_id")
    scientific_claim_parser.add_argument("claim_id")
    add_registry_path(scientific_claim_parser)
    scientific_claim_parser.set_defaults(func=_cmd_evaluate_scientific_claim)

    validate_scientific_result_parser = subparsers.add_parser(
        "validate-scientific-result", help="validate a scientific execution result JSON file"
    )
    validate_scientific_result_parser.add_argument("path")
    validate_scientific_result_parser.set_defaults(func=_cmd_validate_scientific_result)

    export_scientific_findings_parser = subparsers.add_parser(
        "export-scientific-findings", help="export persisted scientific findings to local-only outputs"
    )
    add_registry_path(export_scientific_findings_parser)
    export_scientific_findings_parser.add_argument("--output", default="outputs/platform_science/scientific_findings_export.json")
    export_scientific_findings_parser.add_argument("--overwrite", action="store_true")
    export_scientific_findings_parser.set_defaults(func=_cmd_export_scientific_findings)

    scientific_registry_validate_parser = subparsers.add_parser(
        "scientific-registry-validate", help="validate scientific execution tables in the local registry"
    )
    add_registry_path(scientific_registry_validate_parser)
    scientific_registry_validate_parser.set_defaults(func=_cmd_scientific_registry_validate)

    feature_candidates_parser = subparsers.add_parser(
        "list-scientific-feature-candidates", help="list scientific feature-candidate metadata"
    )
    feature_candidates_parser.add_argument("--domain")
    feature_candidates_parser.add_argument("--eligibility-status")
    feature_candidates_parser.add_argument("--validation-status")
    feature_candidates_parser.set_defaults(func=_cmd_list_scientific_feature_candidates)

    inspect_feature_parser = subparsers.add_parser(
        "inspect-scientific-feature-candidate", help="inspect one scientific feature candidate"
    )
    inspect_feature_parser.add_argument("feature_id")
    inspect_feature_parser.set_defaults(func=_cmd_inspect_scientific_feature_candidate)

    evaluate_feature_parser = subparsers.add_parser(
        "evaluate-scientific-feature", help="evaluate metadata eligibility for one feature candidate against a persisted execution"
    )
    evaluate_feature_parser.add_argument("execution_id")
    evaluate_feature_parser.add_argument("feature_id")
    add_registry_path(evaluate_feature_parser)
    evaluate_feature_parser.set_defaults(func=_cmd_evaluate_scientific_feature)

    evaluate_trust_parser = subparsers.add_parser(
        "evaluate-scientific-trust", help="evaluate scientific trust boundary for a persisted scientific execution"
    )
    evaluate_trust_parser.add_argument("execution_id")
    evaluate_trust_parser.add_argument("--no-persist", action="store_true", help="preview trust evaluation without writing registry rows")
    add_registry_path(evaluate_trust_parser)
    evaluate_trust_parser.set_defaults(func=_cmd_evaluate_scientific_trust)

    show_trust_parser = subparsers.add_parser("show-scientific-trust", help="show one persisted scientific trust evaluation")
    show_trust_parser.add_argument("trust_evaluation_id")
    add_registry_path(show_trust_parser)
    show_trust_parser.set_defaults(func=_cmd_show_scientific_trust)

    list_feature_eligibility_parser = subparsers.add_parser(
        "list-feature-eligibility", help="list feature eligibility rows for a trust evaluation"
    )
    list_feature_eligibility_parser.add_argument("trust_evaluation_id")
    add_registry_path(list_feature_eligibility_parser)
    list_feature_eligibility_parser.set_defaults(func=_cmd_list_feature_eligibility)

    claim_boundaries_parser = subparsers.add_parser(
        "list-scientific-claim-boundaries", help="list registered or persisted scientific claim boundaries"
    )
    claim_boundaries_parser.add_argument("--trust-evaluation-id")
    add_registry_path(claim_boundaries_parser)
    claim_boundaries_parser.set_defaults(func=_cmd_list_scientific_claim_boundaries)

    trust_validate_parser = subparsers.add_parser(
        "scientific-trust-validate", help="validate scientific trust registry metadata and local tables"
    )
    add_registry_path(trust_validate_parser)
    trust_validate_parser.set_defaults(func=_cmd_scientific_trust_validate)

    export_trust_parser = subparsers.add_parser(
        "export-scientific-trust", help="export persisted scientific trust summaries to local-only outputs"
    )
    add_registry_path(export_trust_parser)
    export_trust_parser.add_argument("--output", default="outputs/platform_science/scientific_trust_export.json")
    export_trust_parser.add_argument("--overwrite", action="store_true")
    export_trust_parser.set_defaults(func=_cmd_export_scientific_trust)

    subparsers.add_parser(
        "list-materials-feature-builders",
        help="list registered Materials v2.2 physics feature builders",
    ).set_defaults(func=_cmd_list_materials_feature_builders)

    inspect_materials_feature_parser = subparsers.add_parser(
        "inspect-materials-feature-builder",
        help="inspect one registered Materials v2.2 feature builder",
    )
    inspect_materials_feature_parser.add_argument("feature_id")
    inspect_materials_feature_parser.set_defaults(func=_cmd_inspect_materials_feature_builder)

    build_materials_features_parser = subparsers.add_parser(
        "build-materials-physics-features",
        help="build local-only Materials v2.2 physics feature matrix from an existing local source CSV",
    )
    build_materials_features_parser.add_argument("config_path")
    build_materials_features_parser.set_defaults(func=_cmd_build_materials_physics_features)

    validate_materials_features_parser = subparsers.add_parser(
        "validate-materials-feature-artifact",
        help="validate a Materials v2.2 feature matrix artifact",
    )
    validate_materials_features_parser.add_argument("path")
    validate_materials_features_parser.set_defaults(func=_cmd_validate_materials_feature_artifact)

    compare_materials_features_parser = subparsers.add_parser(
        "run-materials-feature-comparison",
        help="run matched baseline/physics feature-set comparison for Materials v2.2",
    )
    compare_materials_features_parser.add_argument("config_path")
    compare_materials_features_parser.set_defaults(func=_cmd_run_materials_feature_comparison)

    show_materials_comparison_parser = subparsers.add_parser(
        "show-materials-feature-comparison",
        help="show a Materials v2.2 predictive-value decision or comparison manifest",
    )
    show_materials_comparison_parser.add_argument("result")
    show_materials_comparison_parser.set_defaults(func=_cmd_show_materials_feature_comparison)

    export_materials_summary_parser = subparsers.add_parser(
        "export-materials-feature-summary",
        help="export Materials v2.2 predictive summary to local-only outputs",
    )
    export_materials_summary_parser.add_argument(
        "--decision",
        default="data/processed/materials_physics_v2_2_predictive_value_decision.json",
    )
    export_materials_summary_parser.add_argument(
        "--summary",
        default="data/processed/materials_physics_v2_2_predictive_comparison_summary.csv",
    )
    export_materials_summary_parser.add_argument(
        "--output",
        default="outputs/materials_physics_v2_2/materials_feature_summary_export.json",
    )
    export_materials_summary_parser.add_argument("--markdown-output")
    export_materials_summary_parser.set_defaults(func=_cmd_export_materials_feature_summary)

    subparsers.add_parser("show-version", help="show platform scaffold version").set_defaults(func=_cmd_show_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
