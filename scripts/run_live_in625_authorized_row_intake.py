#!/usr/bin/env python3
"""Run the exact live IN625 authorization -> acquisition -> row-intake chain.

This acceptance runner performs network access only after deterministic source authorization.
The full external archive is verified ephemerally and removed before completion.  The durable
outputs are provenance manifests, reviewed row-level evidence, typed registration evidence,
and a conservative post-acquisition re-diagnosis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from materials_data_analyzer.research_loop.action_authorization import (
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import execute_authorized_action
from materials_data_analyzer.research_loop.in625_archive_network_acquisition import (
    build_in625_archive_network_authorization,
    execute_authorized_in625_archive_download,
)
from materials_data_analyzer.research_loop.in625_execution_verifier import (
    verify_in625_execution_handoff,
)
from materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis import (
    build_in625_post_acquisition_rediagnosis,
)
from materials_data_analyzer.research_loop.in625_tensile_reviewed_intake_v2 import (
    build_reviewed_in625_tensile_intake_v2,
)
from materials_data_analyzer.research_loop.in625_zenodo_live_evidence import (
    build_verified_in625_zenodo_readme_manifest,
    inspect_verified_in625_dataset_archive,
)
from materials_data_analyzer.research_loop.kernel import (
    initialize_research_loop,
    load_research_state,
)
from materials_data_analyzer.research_loop.planning_adapter import plan_research_next_action


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _exact_zenodo_get(url: str, *, timeout: int = 60) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "zenodo.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise RuntimeError(
            f"pre-authorization metadata URL left exact Zenodo HTTPS host: {url}"
        )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "materials-data-analyzer/in625-preauthorization-metadata"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if (
            final.scheme.lower() != "https"
            or (final.hostname or "").lower() != "zenodo.org"
            or final.username is not None
            or final.password is not None
            or final.port not in (None, 443)
            or final.fragment
        ):
            raise RuntimeError(
                f"metadata redirect left exact Zenodo HTTPS host: {final_url}"
            )
        return response.read()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_live_chain(*, repository_root: Path, output_root: Path) -> dict[str, Any]:
    repository_root = repository_root.expanduser().resolve(strict=True)
    output_root = output_root.expanduser().resolve(strict=False)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("live IN625 output directory must be absent or empty")
    output_root.mkdir(parents=True, exist_ok=True)

    source_config_path = (
        repository_root
        / "configs/research/in625_zenodo_20503603_verified_source.v1.json"
    ).resolve(strict=True)
    tensile_policy_path = (
        repository_root / "configs/research/in625_tensile_reviewed_intake.v1.json"
    ).resolve(strict=True)
    registry_path = (
        repository_root / "configs/research/in625_external_evidence_action_registry.v1.json"
    ).resolve(strict=True)

    config_bytes = source_config_path.read_bytes()
    config = json.loads(config_bytes.decode("utf-8"))
    record_id = str(config["zenodo"]["record_id"])
    metadata_url = f"https://zenodo.org/api/records/{record_id}"
    metadata_bytes = _exact_zenodo_get(metadata_url)
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    files = {item["key"]: item for item in metadata.get("files", [])}
    readme_name = config["zenodo"]["readme_file"]
    readme_url = files[readme_name]["links"]["self"]
    readme_bytes = _exact_zenodo_get(readme_url)

    pre_manifest = build_verified_in625_zenodo_readme_manifest(
        config=config,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    _write_json(output_root / "source-readme-manifest.json", pre_manifest)
    (output_root / "record.json").write_bytes(metadata_bytes)
    (output_root / readme_name).write_bytes(readme_bytes)

    authorization = build_in625_archive_network_authorization(
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    _require(
        authorization["network_access_performed"] is False,
        "pre-download authorization may not claim archive network access already occurred",
    )
    _write_json(output_root / "network-authorization.json", authorization)

    archive_name = config["zenodo"]["archive_file"]
    archive_path = output_root / archive_name
    receipt = execute_authorized_in625_archive_download(
        authorization=authorization,
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
        output_path=archive_path,
    )
    _require(
        Path(receipt["archive"]["path"]).resolve() == archive_path.resolve(),
        "network receipt archive path differs from authorized output path",
    )
    _require(
        receipt["archive"]["sha256"]
        == config["zenodo"]["files"][archive_name]["verified_sha256"],
        "network receipt lost repository-pinned archive SHA-256",
    )
    _write_json(output_root / "network-acquisition-receipt.json", receipt)

    selected_root = output_root / "selected-source-files"
    archive_manifest = inspect_verified_in625_dataset_archive(
        config=config,
        archive_path=archive_path,
        selected_output_dir=selected_root,
    )
    _require(
        archive_manifest["archive"]["sha256_previously_pinned"] is True,
        "archive inspection did not preserve pre-pinned SHA-256",
    )
    _write_json(output_root / "archive-manifest.json", archive_manifest)

    tensile_policy = json.loads(tensile_policy_path.read_text(encoding="utf-8"))
    workbook_member = PurePosixPath(
        tensile_policy["workbook"]["archive_member_path"]
    )
    tensile_readme_member = PurePosixPath(
        tensile_policy["documentation"]["archive_member_path"]
    )
    workbook_path = selected_root.joinpath(*workbook_member.parts)
    tensile_readme_path = selected_root.joinpath(*tensile_readme_member.parts)
    _require(workbook_path.is_file(), "verified archive intake did not expose tensile workbook")
    _require(
        tensile_readme_path.is_file(),
        "verified archive intake did not expose tensile README",
    )
    _require(
        _sha256_file(workbook_path) == tensile_policy["workbook"]["sha256"],
        "extracted tensile workbook differs from reviewed policy",
    )
    _require(
        _sha256_file(tensile_readme_path)
        == tensile_policy["documentation"]["sha256"],
        "extracted tensile README differs from reviewed policy",
    )

    tensile_output = output_root / "reviewed-tensile"
    tensile_manifest = build_reviewed_in625_tensile_intake_v2(
        workbook_path=workbook_path,
        readme_path=tensile_readme_path,
        policy_path=tensile_policy_path,
        output_dir=tensile_output,
    )
    _require(
        tensile_manifest["measurement_row_count"] == 200289,
        "live reviewed tensile intake did not reproduce exactly 200,289 time-indexed rows",
    )
    _require(
        tensile_manifest["parallel_test_block_count"] == 19,
        "live reviewed tensile intake did not reproduce exactly 19 parallel-test blocks",
    )
    _require(
        tensile_manifest["reviewed_semantics"]["missing_values_imputed"] is False,
        "row-preserving tensile intake may not impute source missingness",
    )
    _require(
        tensile_manifest["scientific_boundaries"][
            "direct_nist_condition_comparability_established"
        ]
        is False,
        "reviewed tensile intake improperly promoted direct NIST comparability",
    )

    objective_path = output_root / "typed-research-objective.json"
    _write_json(
        objective_path,
        {
            "schema_version": "1.0",
            "research_id": "authorized-live-in625-external-evidence-20503603",
            "question": (
                "Can the exact authorized Zenodo 20503603 IN625 archive be registered "
                "and moved into reviewed row-preserving tensile intake?"
            ),
            "metrics": {
                "primary": "external_source_provenance",
                "secondary": [
                    "archive_byte_integrity",
                    "reviewed_row_level_measurement_availability",
                    "reviewed_numeric_completeness",
                ],
            },
            "constraints": [
                "Archive network access requires deterministic pre-download authorization",
                "Source missingness is preserved without imputation or coercion",
                "No direct NIST condition-comparability claim",
                "No empirical model-validation or hypothesis-truth promotion",
            ],
            "budget": {"maximum_actions": 2, "maximum_cost_units": 4},
            "stop_rules": [
                "Stop acquisition after one exact source registration or fail-closed verifier rejection"
            ],
        },
    )
    research_run = output_root / "typed-research-run"
    initialize_research_loop(objective_path, research_run)
    registry = load_action_registry(registry_path, repository_root=repository_root)
    request_path = output_root / "typed-execution-request.json"
    _write_json(
        request_path,
        {
            "schema_version": "1.0",
            "action_id": "register-authorized-zenodo-20503603-in625",
            "action_type": "external_evidence_search",
            "action_version": "1.0",
            "research_run": str(research_run),
            "source_config": str(source_config_path),
            "expected_source_config_sha256": _sha256_file(source_config_path),
            "archive_path": str(archive_path),
            "expected_archive_sha256": receipt["archive"]["sha256"],
            "registry": str(registry_path),
            "repository_root": str(repository_root),
            "expected_registry_sha256": registry["registry_sha256"],
        },
    )
    planning = plan_research_next_action(
        "in625-external-evidence",
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=registry_path,
    )
    _require(
        planning["selection_status"] == "ready_to_execute",
        "IN625 typed planner did not expose exact acquired source",
    )
    typed_authorization = assess_current_action_authorization(
        "in625-external-evidence",
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=registry_path,
    )
    _require(
        typed_authorization["authorization_status"]
        == "ready_for_explicit_execution_request",
        "IN625 typed registration did not pass authorization boundary",
    )
    handoff = verify_in625_execution_handoff(
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=registry_path,
        request_path=request_path,
    )
    _require(
        handoff["archive_sha256"] == receipt["archive"]["sha256"],
        "typed execution handoff archive differs from network receipt archive",
    )
    execution = execute_authorized_action(
        "in625-external-evidence",
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=registry_path,
        request_path=request_path,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )
    final_state = load_research_state(research_run)
    execution_with_request = dict(execution)
    execution_with_request["request_sha256"] = handoff["request_sha256"]

    rediagnosis = build_in625_post_acquisition_rediagnosis(
        network_authorization=authorization,
        network_receipt=receipt,
        typed_execution_result=execution_with_request,
        reviewed_tensile_manifest=tensile_manifest,
    )
    _require(
        rediagnosis["current_blocker"]["code"]
        == "cross_source_physical_comparability_not_established",
        "post-acquisition diagnosis did not move to physical-comparability blocker",
    )
    _require(
        rediagnosis["stop_state"]["positive_scientific_closeout"] is False,
        "post-acquisition diagnosis improperly closed scientific validation",
    )

    _write_json(output_root / "typed-planning.json", planning)
    _write_json(
        output_root / "typed-registration-authorization.json",
        typed_authorization,
    )
    _write_json(output_root / "typed-execution-handoff.json", handoff)
    _write_json(
        output_root / "typed-execution-result.json",
        execution_with_request,
    )
    _write_json(output_root / "typed-research-state.json", final_state)
    _write_json(output_root / "post-acquisition-rediagnosis.json", rediagnosis)

    chain: dict[str, Any] = {
        "schema_version": "2.0",
        "source_id": authorization["source_id"],
        "archive_sha256": receipt["archive"]["sha256"],
        "network_authorization_sha256": authorization["authorization_sha256"],
        "network_receipt_sha256": receipt["receipt_sha256"],
        "typed_request_sha256": handoff["request_sha256"],
        "typed_pre_execution_ledger_sha256": handoff["research_ledger_sha256"],
        "typed_final_ledger_sha256": final_state["ledger_sha256"],
        "reviewed_tensile_manifest_sha256": tensile_manifest["manifest_sha256"],
        "reviewed_tensile_row_artifact_sha256": tensile_manifest["row_artifact"][
            "sha256"
        ],
        "reviewed_tensile_measurement_row_count": tensile_manifest[
            "measurement_row_count"
        ],
        "reviewed_tensile_complete_numeric_row_count": tensile_manifest[
            "complete_numeric_measurement_row_count"
        ],
        "reviewed_tensile_incomplete_numeric_row_count": tensile_manifest[
            "incomplete_numeric_measurement_row_count"
        ],
        "reviewed_tensile_parallel_test_block_count": tensile_manifest[
            "parallel_test_block_count"
        ],
        "post_acquisition_rediagnosis_sha256": rediagnosis["rediagnosis_sha256"],
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
    }
    chain["chain_sha256"] = _canonical_sha(chain)
    _write_json(output_root / "authorized-provenance-chain.json", chain)

    archive_path.unlink()
    _require(
        not archive_path.exists(),
        "full external archive was not removed before completion",
    )

    summary = {
        "record_id": record_id,
        "authorization_sha256": authorization["authorization_sha256"],
        "network_receipt_sha256": receipt["receipt_sha256"],
        "archive_sha256": chain["archive_sha256"],
        "measurement_row_count": tensile_manifest["measurement_row_count"],
        "complete_numeric_measurement_row_count": tensile_manifest[
            "complete_numeric_measurement_row_count"
        ],
        "incomplete_numeric_measurement_row_count": tensile_manifest[
            "incomplete_numeric_measurement_row_count"
        ],
        "numeric_completeness_fraction_structural_only": tensile_manifest[
            "numeric_completeness_fraction_structural_only"
        ],
        "parallel_test_block_count": tensile_manifest["parallel_test_block_count"],
        "row_artifact_sha256": tensile_manifest["row_artifact"]["sha256"],
        "typed_registered_outcome": execution_with_request["verified_report"][
            "registered_outcome"
        ],
        "post_acquisition_blocker": rediagnosis["current_blocker"]["code"],
        "next_action_class": rediagnosis["next_action"]["action_class"],
        "positive_scientific_closeout": rediagnosis["stop_state"][
            "positive_scientific_closeout"
        ],
        "chain_sha256": chain["chain_sha256"],
    }
    _write_json(output_root / "live-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", default=".")
    parser.add_argument(
        "--output",
        default="outputs/in625-authorized-network-row-intake",
    )
    args = parser.parse_args()
    repository_root = Path(args.repository_root)
    output = Path(args.output)
    if not output.is_absolute():
        output = repository_root / output
    summary = run_live_chain(
        repository_root=repository_root,
        output_root=output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
