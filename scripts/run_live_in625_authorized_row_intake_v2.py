#!/usr/bin/env python3
"""Run the quality-bound final IN625 live acceptance chain.

The base runner establishes authorized acquisition, exact archive registration, reviewed v2
row intake, and conservative re-diagnosis.  This wrapper then binds the observed source
missingness contract, emits a quality-aware recursive diagnosis, and publishes one final
provenance chain without reacquiring or modifying the source bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis_v2 import (
    build_in625_post_acquisition_rediagnosis_v2,
)
from materials_data_analyzer.research_loop.in625_tensile_quality_contract import (
    verify_in625_tensile_observed_quality,
)
from run_live_in625_authorized_row_intake import run_live_chain


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


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


def run_quality_bound_live_chain(
    *,
    repository_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    repository_root = repository_root.expanduser().resolve(strict=True)
    output_root = output_root.expanduser().resolve(strict=False)
    base_summary = run_live_chain(
        repository_root=repository_root,
        output_root=output_root,
    )

    quality_contract_path = (
        repository_root / "configs/research/in625_tensile_observed_quality.v1.json"
    ).resolve(strict=True)
    tensile_manifest = _read_json(
        output_root / "reviewed-tensile/reviewed_tensile_manifest.v2.json"
    )
    quality = verify_in625_tensile_observed_quality(
        reviewed_tensile_manifest=tensile_manifest,
        quality_contract_path=quality_contract_path,
    )
    _write_json(output_root / "tensile-quality-verification.json", quality)

    authorization = _read_json(output_root / "network-authorization.json")
    receipt = _read_json(output_root / "network-acquisition-receipt.json")
    execution = _read_json(output_root / "typed-execution-result.json")
    rediagnosis_v2 = build_in625_post_acquisition_rediagnosis_v2(
        network_authorization=authorization,
        network_receipt=receipt,
        typed_execution_result=execution,
        reviewed_tensile_manifest=tensile_manifest,
        quality_contract_path=quality_contract_path,
    )
    _write_json(
        output_root / "post-acquisition-rediagnosis.v2.json",
        rediagnosis_v2,
    )

    base_chain = _read_json(output_root / "authorized-provenance-chain.json")
    base_chain_sha = base_chain.get("chain_sha256")
    if not isinstance(base_chain_sha, str) or len(base_chain_sha) != 64:
        raise RuntimeError("base authorized provenance chain lacks canonical SHA-256")

    final_chain: dict[str, Any] = {
        "schema_version": "2.0",
        "source_id": base_chain["source_id"],
        "archive_sha256": base_chain["archive_sha256"],
        "predecessor_chain_sha256": base_chain_sha,
        "network_authorization_sha256": base_chain[
            "network_authorization_sha256"
        ],
        "network_receipt_sha256": base_chain["network_receipt_sha256"],
        "typed_request_sha256": base_chain["typed_request_sha256"],
        "typed_pre_execution_ledger_sha256": base_chain[
            "typed_pre_execution_ledger_sha256"
        ],
        "typed_final_ledger_sha256": base_chain[
            "typed_final_ledger_sha256"
        ],
        "reviewed_tensile_manifest_sha256": tensile_manifest["manifest_sha256"],
        "reviewed_tensile_row_artifact_sha256": tensile_manifest["row_artifact"][
            "sha256"
        ],
        "quality_contract_sha256": quality["quality_contract"]["sha256"],
        "quality_verification_sha256": quality["verification_sha256"],
        "quality_aware_rediagnosis_sha256": rediagnosis_v2[
            "rediagnosis_sha256"
        ],
        "measurement_row_count": quality["measurement_row_count"],
        "complete_numeric_measurement_row_count": quality[
            "complete_numeric_measurement_row_count"
        ],
        "incomplete_numeric_measurement_row_count": quality[
            "incomplete_numeric_measurement_row_count"
        ],
        "known_incomplete_rows": quality["known_incomplete_rows"],
        "primary_blocker": rediagnosis_v2["current_blocker"]["code"],
        "secondary_blockers": [
            item["code"] for item in rediagnosis_v2["secondary_blockers"]
        ],
        "missing_value_imputation_authorized": False,
        "row_exclusion_authorized": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
        "scientific_status_changed": False,
    }
    final_chain["chain_sha256"] = _canonical_sha(final_chain)
    _write_json(
        output_root / "authorized-provenance-chain.v2.json",
        final_chain,
    )

    summary: dict[str, Any] = {
        **base_summary,
        "quality_status": quality["quality_status"],
        "quality_contract_sha256": quality["quality_contract"]["sha256"],
        "quality_verification_sha256": quality["verification_sha256"],
        "known_incomplete_rows": quality["known_incomplete_rows"],
        "primary_blocker": rediagnosis_v2["current_blocker"]["code"],
        "secondary_blockers": [
            item["code"] for item in rediagnosis_v2["secondary_blockers"]
        ],
        "quality_aware_rediagnosis_sha256": rediagnosis_v2[
            "rediagnosis_sha256"
        ],
        "final_chain_sha256": final_chain["chain_sha256"],
        "missing_value_imputation_authorized": False,
        "row_exclusion_authorized": False,
        "positive_scientific_closeout": False,
    }
    _write_json(output_root / "live-summary.v2.json", summary)
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
    summary = run_quality_bound_live_chain(
        repository_root=repository_root,
        output_root=output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
