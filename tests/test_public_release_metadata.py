from __future__ import annotations

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


def test_v2_7_closeout_moves_development_stages_out_of_unreleased() -> None:
    version = _public_version()
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")

    unreleased = _unreleased_section(changelog, version)
    assert not unreleased.strip()
    assert "v2.5.1" not in unreleased
    assert "v2.6.2" not in unreleased

    release_section = changelog.split("## v2.7.0", maxsplit=1)[1].split(
        "## v2.4.0", maxsplit=1
    )[0]
    for stage in ("v2.5.1", "v2.5.2", "v2.6.1", "v2.6.2"):
        assert stage in release_notes
    assert "Consolidated the internal v2.5.1" in release_section
    assert "internal feature-stage labels" in status


def test_v2_7_release_preserves_negative_and_restricted_results() -> None:
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")

    required_results = (
        "performance_degraded",
        "structure_predictive_value_limited",
        "insufficient_evidence",
        "Ridge pooled MAE: `4.1537`",
        "persistence pooled MAE: `3.4256`",
        "13 of 33",
        "not_ready_for_predictive_or_causal_modeling",
        "No response model is trained",
    )
    for expected in required_results:
        assert expected in release_notes

    assert "Battery forecast `unsupported`" in changelog
    assert "process-characterization `Diagnostic`" in changelog


def test_citation_preserves_scientific_and_source_boundaries() -> None:
    citation = CITATION_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")

    assert "exact repository commit used" in citation
    assert "source-data citations" in citation
    assert "does not automatically" in citation
    assert "does not relicense third-party datasets" in status
    assert "does not prove that samples are comparable" in status
