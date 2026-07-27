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


def test_public_release_metadata_is_complete_and_consistent() -> None:
    version = _public_version()
    citation = CITATION_FILE.read_text(encoding="utf-8")
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / f"V{version.replace('.', '_')}.md"
    )

    assert release_notes.is_file()
    assert "cff-version: 1.2.0" in citation
    assert 'title: "Materials Data Analyzer"' in citation
    assert f"version: {version}" in citation
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


def test_unreleased_feature_stages_are_not_mislabeled_as_public_release() -> None:
    version = _public_version()
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")

    unreleased = changelog.split("## Unreleased", maxsplit=1)[1].split(
        f"## v{version}", maxsplit=1
    )[0]
    assert "v2.6.2" in unreleased
    assert "development-stage identifiers" in status
    assert "They are not automatically promoted" in status


def test_citation_preserves_scientific_and_source_boundaries() -> None:
    citation = CITATION_FILE.read_text(encoding="utf-8")
    status = STATUS_FILE.read_text(encoding="utf-8")

    assert "exact repository commit used" in citation
    assert "source-data citations" in citation
    assert "does not automatically" in citation
    assert "does not relicense third-party datasets" in status
    assert "does not prove that samples are comparable" in status
