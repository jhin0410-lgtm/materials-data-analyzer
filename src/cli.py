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
from .platform_core.artifacts import build_default_artifact_registry
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
from .platform_core.manifests import (
    build_run_manifest,
    default_manifest_output,
    load_run_manifest,
    write_run_manifest,
)
from .platform_core.onboarding import load_and_validate_onboarding_config
from .platform_core.planner import build_dry_run_plan
from .platform_core.registry import build_default_plugin_registry
from .platform_core.trust_registry import build_default_trust_policy_registry
from .platform_core.validation_registry import build_default_validation_policy_registry
from .platform_core.version import PLATFORM_VERSION


EXIT_INVALID_CONFIG = 2
EXIT_ADAPTER_NOT_FOUND = 3
EXIT_EXECUTION_DISABLED = 4
EXIT_MISSING_ARTIFACT = 5
EXIT_SIDE_EFFECT = 6
EXIT_VERIFICATION_MISMATCH = 7
EXIT_RUNTIME_FAILURE = 8
EXIT_PATH_POLICY = 9


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


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _emit_lines(lines: list[str]) -> None:
    print("\n".join(lines))


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
    payload = {
        "config_validation": validation.to_dict(),
        "dry_run_plan": plan.to_dict(),
        "manifest_path": manifest_path,
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
    payload = {"status": manifest["status"], "manifest": manifest, "result": result.to_dict() if result else None}
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
    dry_run_parser.set_defaults(func=_cmd_dry_run)

    execute_parser = subparsers.add_parser("execute", help="execute an approved adapter in controlled mode")
    execute_parser.add_argument("config_path")
    execute_parser.add_argument("--mode", choices=["verify", "isolated_run"], default=None)
    execute_parser.add_argument("--write-manifest", action="store_true", help="accepted for compatibility; execute always writes a terminal manifest")
    execute_parser.add_argument("--run-id")
    execute_parser.add_argument("--output-dir")
    execute_parser.add_argument("--overwrite", action="store_true")
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

    subparsers.add_parser("show-version", help="show platform scaffold version").set_defaults(func=_cmd_show_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
