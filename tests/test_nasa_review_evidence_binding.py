from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from platform_core.battery_intelligence.common import canonical_json, file_sha256
from platform_core.battery_intelligence.nasa_review_evidence import (
    audit_nasa_review_evidence,
)
from nasa_review_evidence_run_fixture import _write_run
from nasa_review_evidence_source_fixtures import _excluded


def test_review_evidence_rejects_stale_queue_after_protocol_audit_refresh(
    tmp_path: Path,
) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)
    profile_path = analysis_output / "tables" / "nasa_protocol_battery_profile.csv"
    profile = pd.read_csv(profile_path)
    profile.loc[profile["battery_id"] == "A", "cycle_gap_count"] = 1
    profile.to_csv(profile_path, index=False)
    manifest_path = analysis_output / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_checksums"][
        "tables/nasa_protocol_battery_profile.csv"
    ] = file_sha256(profile_path)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="stale relative"):
        audit_nasa_review_evidence(
            import_output=import_output,
            analysis_output=analysis_output,
        )


def test_review_evidence_rejects_different_valid_import_run(tmp_path: Path) -> None:
    first_import = tmp_path / "import_a"
    second_import = tmp_path / "import_b"
    analysis_output = tmp_path / "analysis"
    _write_run(first_import, analysis_output)
    changed = _excluded().copy()
    changed.loc[0, "cycle_index"] = 4
    changed.loc[0, "source_location"] = "other.zip!A.mat"
    _write_run(
        second_import,
        tmp_path / "throwaway_analysis",
        excluded=changed,
        import_input={"sha256": "different-valid-import"},
    )

    with pytest.raises(ValueError, match="binding mismatch"):
        audit_nasa_review_evidence(
            import_output=second_import,
            analysis_output=analysis_output,
        )


def test_review_evidence_rejects_tampered_import_artifact(tmp_path: Path) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)
    protocol_path = import_output / "nasa_pcoe_protocol_summary.csv"
    protocol_path.write_text(
        protocol_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        audit_nasa_review_evidence(
            import_output=import_output,
            analysis_output=analysis_output,
        )
