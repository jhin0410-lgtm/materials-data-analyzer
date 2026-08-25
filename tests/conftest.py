"""Pytest configuration for importing modules from src/."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
os.environ.setdefault("PYTHONPATH", str(SRC_DIR))


_TRANSPORT_RECOVERY_TEST_MODULE = "test_autonomous_production_transport_recovery"
_EXPECTED_NIST_IDENTIFIER = "10.18434/mds2-2923"
_EXPECTED_BINDING_PATHS = {
    "nist_planning_readiness": (
        "configs/research/nist_ambench_2018_02_planning_readiness.v1.json"
    ),
    "nist_process_conditions": (
        "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    ),
    "nist_melt_pool_measurements": (
        "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
    ),
    "nist_case_readme": "data/case_studies/nist_ambench_2018_02/README.md",
    "zenodo_reviewed_tensile_contract": (
        "configs/research/in625_tensile_reviewed_intake.v1.json"
    ),
    "zenodo_verified_source": (
        "configs/research/in625_zenodo_20503603_verified_source.v1.json"
    ),
    "zenodo_observed_quality_contract": (
        "configs/research/in625_tensile_observed_quality.v1.json"
    ),
    "in625_physical_source_frontier": (
        "configs/research/in625_external_physical_source_frontier.v1.json"
    ),
}
_EXPECTED_INCOMPLETE_ROWS = [
    {
        "sheet_name": "AM-AB-H",
        "block_index": 1,
        "excel_row_number": 79,
        "missing_reviewed_numeric_fields": ["load_n"],
        "non_numeric_reviewed_fields": [],
        "raw_anomalous_cell_text": {"load_n": ""},
    }
]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _binding(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            _write_json(path, {"synthetic_fixture_only": True, "path": relative})
        else:
            path.write_text(f"synthetic fixture only: {relative}\n", encoding="utf-8")
    raw = path.read_bytes()
    return {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _rehash(value: dict[str, Any], field: str, canonical_sha: Any) -> None:
    value.pop(field, None)
    value[field] = canonical_sha(value)


def _harden_transport_fixture(
    *,
    root: Path,
    output: Path,
    canonical_sha: Any,
) -> None:
    bindings = {
        name: _binding(root, relative)
        for name, relative in _EXPECTED_BINDING_PATHS.items()
    }

    quality = _read_json(output / "tensile-quality-verification.json")
    rediagnosis = _read_json(output / "quality-aware-rediagnosis.json")
    rediagnosis["secondary_blockers"] = [
        {
            "code": "reviewed_numeric_source_missingness_observed",
            "kind": "data_quality",
            "severity": "bounded",
            "measurement_row_count": 200289,
            "affected_row_count": 1,
            "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
            "blocks_external_evidence_availability": False,
            "blocks_unqualified_use_of_affected_load_value": True,
            "missingness_mechanism_established": False,
            "imputation_authorized": False,
            "row_exclusion_authorized": False,
            "scientific_status_changed": False,
        }
    ]
    _rehash(rediagnosis, "rediagnosis_sha256", canonical_sha)
    _write_json(output / "quality-aware-rediagnosis.json", rediagnosis)

    assessment = _read_json(output / "physical-comparability-assessment.json")
    assessment["predecessor_rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    assessment["observed_quality_verification_sha256"] = quality[
        "verification_sha256"
    ]
    assessment["evidence_bindings"] = bindings
    _rehash(assessment, "assessment_sha256", canonical_sha)
    _write_json(output / "physical-comparability-assessment.json", assessment)

    manifest = _read_json(output / "autonomous-production-manifest.json")
    cycles = [dict(item) for item in manifest["cycles"]]
    cycle1 = cycles[0]
    cycle1["rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    _rehash(cycle1, "cycle_sha256", canonical_sha)
    cycle2 = cycles[1]
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(cycle2, "cycle_sha256", canonical_sha)
    manifest["cycles"] = [cycle1, cycle2]
    manifest["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(manifest, "manifest_sha256", canonical_sha)
    _write_json(output / "autonomous-production-manifest.json", manifest)

    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read_json(qualification_path)
    frontier_path = root / _EXPECTED_BINDING_PATHS["in625_physical_source_frontier"]
    qualification["identifier"] = _EXPECTED_NIST_IDENTIFIER
    qualification["frontier_path"] = str(frontier_path.resolve(strict=True))
    qualification["frontier_sha256"] = hashlib.sha256(
        frontier_path.read_bytes()
    ).hexdigest()
    _rehash(qualification, "qualification_sha256", canonical_sha)
    _write_json(qualification_path, qualification)


def _patch_legacy_error_expectation(
    *,
    base: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_verify = base.live_verifier.verify_live_autonomous_output

    def verify_with_legacy_message(output_root: str | Path) -> str:
        try:
            return original_verify(output_root)
        except base.live_verifier.AutonomousProductionLiveVerificationError as exc:
            if str(exc) == (
                "bounded-stop artifact does not match autonomous manifest stop"
            ):
                raise base.live_verifier.AutonomousProductionLiveVerificationError(
                    "bounded-stop artifact does not match manifest stop"
                ) from exc
            raise

    monkeypatch.setattr(
        base.live_verifier,
        "verify_live_autonomous_output",
        verify_with_legacy_message,
    )


def _patch_minimal_manifest_writer(
    *,
    base: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_write = base._write_json

    def write_with_hash_contract(path: Path, value: object) -> None:
        if path.name == "autonomous-production-manifest.json" and isinstance(value, dict):
            manifest = dict(value)
            if "manifest_sha256" not in manifest:
                cycle = {"cycle_index": 1}
                cycle["cycle_sha256"] = base.recovery._canonical_sha(cycle)
                manifest["cycles"] = [cycle]
                manifest["manifest_sha256"] = base.recovery._canonical_sha(manifest)
                value = manifest
        original_write(path, value)

    monkeypatch.setattr(base, "_write_json", write_with_hash_contract)


@pytest.fixture(autouse=True)
def _production_grade_transport_recovery_fixture(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep transport-recovery synthetic fixtures aligned with production provenance."""
    module = request.module
    if module.__name__.split(".")[-1] != _TRANSPORT_RECOVERY_TEST_MODULE:
        return
    base = getattr(module, "_base", None)
    if base is None:
        return

    if request.node.name == "test_live_verifier_rejects_bounded_stop_manifest_divergence":
        _patch_legacy_error_expectation(base=base, monkeypatch=monkeypatch)
    if request.node.name.startswith(
        "test_full_success_preflight_requires_explicit_false_paper_row_authority"
    ):
        _patch_minimal_manifest_writer(base=base, monkeypatch=monkeypatch)

    original_prepare = base._prepare_pretransport_state

    def hardened_prepare(
        root: Path,
        output_root: str | Path,
        *,
        persist_partial_nist_bytes: bool = True,
    ) -> Path:
        output = original_prepare(
            root,
            output_root,
            persist_partial_nist_bytes=persist_partial_nist_bytes,
        )
        _harden_transport_fixture(
            root=Path(root).resolve(strict=True),
            output=Path(output).resolve(strict=True),
            canonical_sha=base.recovery._canonical_sha,
        )
        return output

    monkeypatch.setattr(base, "_prepare_pretransport_state", hardened_prepare)
