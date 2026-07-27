from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "PUBLIC_RELEASE_VERSION"
CITATION_FILE = PROJECT_ROOT / "CITATION.cff"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
STATUS_FILE = PROJECT_ROOT / "docs" / "PUBLIC_RELEASE_STATUS.md"


def _public_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    return version


def _unreleased_section(changelog: str, version: str) -> str:
    return changelog.split("## Unreleased", maxsplit=1)[1].split(
        f"## v{version}", maxsplit=1
    )[0]


def test_public_release_metadata_is_complete_and_consistent() -> None:
    version = _public_version()
    citation = CITATION_FILE.read_text(encoding="utf-8")
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / f"V{version.replace('.', '_')}.md"
    )

    assert version == "2.7.0"
    assert release_notes.is_file()
    assert "cff-version: 1.2.0" in citation
    assert 'title: "Materials Data Analyzer"' in citation
    assert f"version: {version}" in citation
    assert "date-released: 2026-07-28" in citation
    assert (
        'repository-code: "https://github.com/jhin0410-lgtm/materials-data-analyzer"'
        in citation
    )
    assert "license: MIT" in citation

    assert f"## v{version}" in changelog
    assert changelog.index("## Unreleased") < changelog.index(f"## v{version}")
    assert f"stable public release is **v{version}**" in status
    assert "exact Git commit SHA" in status
    assert f"# v{version} -" in release_notes.read_text(encoding="utf-8")


def test_v2_7_promotion_moves_complete_stage_history_out_of_unreleased() -> None:
    version = _public_version()
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")

    assert not _unreleased_section(changelog, version).strip()
    for stage in ("2.5.1", "2.5.2", *[f"2.6.{i}" for i in range(1, 15)]):
        assert stage in release_notes

    release_section = changelog.split("## v2.7.0", maxsplit=1)[1].split(
        "## v2.4.0", maxsplit=1
    )[0]
    assert "v2.5.1-v2.5.2" in release_section
    assert "v2.6.1-v2.6.14" in release_section
    assert "38 audited post-v2.6" in release_section


def test_v2_7_release_preserves_negative_and_restricted_results() -> None:
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")

    required_results = (
        "performance_degraded",
        "structure_predictive_value_limited",
        "insufficient_evidence",
        "Ridge pooled MAE: `4.1537`",
        "persistence pooled MAE: `3.4256`",
        "13 of 33",
        "not_ready_for_predictive_or_causal_modeling",
        "final evidence-line scientific status: **Inconclusive**",
        "DWCNT, RWGS, four-carbon-material, and NIST cases: **Diagnostic**",
    )
    for expected in required_results:
        assert expected in release_notes


def test_historical_v2_6_artifacts_are_separate_from_current_v2_7_runtime() -> None:
    runtime_test_paths = (
        "tests/test_battery_comparability_evidence.py",
        "tests/test_battery_external_cohort_admission.py",
        "tests/test_battery_forecast_failure_diagnostics.py",
    )
    for relative in runtime_test_paths:
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert 'assert PLATFORM_VERSION == "2.7.0"' in text
        assert 'assert PLATFORM_VERSION == "2.4.0"' not in text

    closeout = json.loads(
        (
            PROJECT_ROOT
            / "data"
            / "processed"
            / "battery_v2_6_14_external_evidence_line_closeout_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert closeout["software_validation"]["public_version_preserved"] == "2.4.0"
    assert closeout["decision"]["ridge_generalization"] == "unsupported"
    assert closeout["decision"]["predictive_validation_readiness"] == "not_ready"
    assert closeout["scientific_closeout"]["status"] == "inconclusive"


def test_citation_preserves_scientific_and_source_boundaries() -> None:
    citation = CITATION_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")

    assert "exact repository commit used" in citation
    assert "source-data citations" in citation
    assert "does not automatically" in citation
    assert "does not relicense third-party datasets" in status
    assert "does not prove that samples are comparable" in status
