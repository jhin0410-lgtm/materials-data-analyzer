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
from .platform_core.config import load_and_validate_pipeline_config, load_json_config
from .platform_core.manifests import (
    build_run_manifest,
    default_manifest_output,
    load_run_manifest,
    write_run_manifest,
)
from .platform_core.planner import build_dry_run_plan
from .platform_core.registry import build_default_plugin_registry
from .platform_core.trust_registry import build_default_trust_policy_registry
from .platform_core.validation_registry import build_default_validation_policy_registry
from .platform_core.version import PLATFORM_VERSION


def _registries() -> tuple[Any, Any, Any, Any, Any]:
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    return (
        plugin_registry,
        artifact_registry,
        build_default_validation_policy_registry(),
        build_default_trust_policy_registry(),
        adapter_registry,
    )


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _emit_lines(lines: list[str]) -> None:
    print("\n".join(lines))


def _cmd_list_plugins(args: argparse.Namespace) -> int:
    plugin_registry, _, _, _, _ = _registries()
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
    plugin_registry, _, _, _, _ = _registries()
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
    plugin_registry, artifact_registry, _, _, _ = _registries()
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
    _, _, _, _, adapter_registry = _registries()
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
    _, _, _, _, adapter_registry = _registries()
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


def _cmd_validate_config(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry = _registries()
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
        return 2
    if args.json:
        _emit_json(result.to_dict())
    else:
        if result.valid:
            _emit_lines(["valid: true", *[f"warning: {warning}" for warning in result.warnings]])
        else:
            _emit_lines(["valid: false", *[f"error: {error}" for error in result.errors]])
    return 0 if result.valid else 2


def _cmd_dry_run(args: argparse.Namespace) -> int:
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry = _registries()
    try:
        config = load_json_config(args.config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {"execution_status": "blocked_invalid_config", "errors": [str(exc)]}
        if args.json:
            _emit_json(payload)
        else:
            print(f"blocked_invalid_config: {exc}", file=sys.stderr)
        return 2
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
            return 2
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
    return 0 if validation.valid else 2


def _cmd_show_policy(args: argparse.Namespace) -> int:
    _, _, validation_registry, trust_registry, _ = _registries()
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


def _cmd_show_manifest(args: argparse.Namespace) -> int:
    try:
        manifest = load_run_manifest(args.manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return 2
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
        return 2
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

    validate_parser = subparsers.add_parser("validate-config", help="validate a pipeline config")
    validate_parser.add_argument("config_path")
    validate_parser.set_defaults(func=_cmd_validate_config)

    dry_run_parser = subparsers.add_parser("dry-run", help="build a dry-run execution plan")
    dry_run_parser.add_argument("config_path")
    dry_run_parser.add_argument("--write-manifest", action="store_true", help="write a local dry-run manifest")
    dry_run_parser.add_argument("--manifest-out", help="relative output path for the run manifest")
    dry_run_parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing manifest")
    dry_run_parser.set_defaults(func=_cmd_dry_run)

    policy_parser = subparsers.add_parser("show-policy", help="show validation or trust policy metadata")
    policy_parser.add_argument("policy_id")
    policy_parser.set_defaults(func=_cmd_show_policy)

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
