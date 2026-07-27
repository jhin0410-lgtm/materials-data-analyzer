"""Tests for NIST AM-Bench manifest-to-feature integrity verification."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_nist_ambench_2018_02_case_study.py"
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_nist_ambench_2018_02_case_study.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_case(output_dir: Path):
    builder = _load_module(BUILD_SCRIPT, "ambench_case_builder_for_verification")
    builder.run_case_study(output_dir)
    return builder


def test_integrity_verifier_accepts_fresh_case_and_cli(tmp_path: Path) -> None:
    output_dir = tmp_path / "ambench"
    _build_case(output_dir)
    verifier = _load_module(VERIFY_SCRIPT, "ambench_integrity_verifier")

    result = verifier.verify_case_study(output_dir)

    assert result == {
        "status": "verified",
        "case_study_id": "nist_ambench_2018_02_process_characterization",
        "checksummed_artifact_count": 11,
        "feature_record_count": 40,
        "sample_count": 10,
        "measurement_count": 10,
        "matched_sample_count": 10,
        "scientific_status": "diagnostic",
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--output",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "integrity verification passed" in completed.stdout.lower()


def test_integrity_verifier_rejects_checksummed_artifact_tampering(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "ambench"
    _build_case(output_dir)
    verifier = _load_module(VERIFY_SCRIPT, "ambench_integrity_checksum_verifier")

    summary_path = output_dir / "ambench_case_summary.csv"
    summary_path.write_text(
        summary_path.read_text(encoding="utf-8") + "\n# tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case output case_summary checksum mismatch"):
        verifier.verify_case_study(output_dir)


def test_integrity_verifier_rejects_feature_source_hash_rebinding(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "ambench"
    _build_case(output_dir)
    verifier = _load_module(VERIFY_SCRIPT, "ambench_integrity_source_verifier")

    long_path = output_dir / "ambench_characterization_features_long.csv"
    table = pd.read_csv(long_path)
    table.loc[0, "source_sha256"] = "0" * 64
    table.to_csv(long_path, index=False)

    manifest_path = output_dir / "ambench_case_study_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_checksums"]["characterization_long"] = verifier.sha256_file(
        long_path
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_sha256 values do not bind"):
        verifier.verify_case_study(output_dir)


def test_integrity_verifier_rejects_handoff_input_rebinding(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "ambench"
    _build_case(output_dir)
    verifier = _load_module(VERIFY_SCRIPT, "ambench_integrity_handoff_verifier")

    handoff_path = output_dir / "characterization_handoff_manifest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["process_source"]["sha256"] = "0" * 64
    handoff_path.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Handoff process source sha256"):
        verifier.verify_case_study(output_dir)
