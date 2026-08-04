from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
CATALOG_PATH = PROCESSED_ROOT / "artifact_catalog.csv"
CATALOG_EXCLUSIONS = {
    "README.md",
    "ARTIFACT_INDEX.md",
    "artifact_catalog.csv",
}


def _catalog_rows() -> list[dict[str, str]]:
    with CATALOG_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def test_every_tracked_processed_file_matches_one_family_prefix() -> None:
    rows = _catalog_rows()
    assert rows
    assert all(row["family"].strip() for row in rows)
    assert all(row["path_prefix"].strip() for row in rows)
    assert all(
        row["deletion_policy"] == "retain_pending_reference_audit"
        for row in rows
    )

    processed_files = sorted(
        path.name
        for path in PROCESSED_ROOT.iterdir()
        if path.is_file() and path.name not in CATALOG_EXCLUSIONS
    )
    assert processed_files
    unmatched: list[str] = []
    ambiguous: dict[str, list[str]] = {}
    for filename in processed_files:
        matches = [
            row["family"]
            for row in rows
            if filename.startswith(row["path_prefix"])
        ]
        if not matches:
            unmatched.append(filename)
        elif len(matches) != 1:
            ambiguous[filename] = matches

    assert unmatched == []
    assert ambiguous == {}


def test_navigation_documents_separate_current_and_historical_surfaces() -> None:
    navigation = (PROJECT_ROOT / "docs" / "REPOSITORY_NAVIGATION.md").read_text(
        encoding="utf-8"
    )
    script_index = (PROJECT_ROOT / "scripts" / "README.md").read_text(
        encoding="utf-8"
    )
    artifact_index = (PROCESSED_ROOT / "ARTIFACT_INDEX.md").read_text(
        encoding="utf-8"
    )
    normalized_navigation = _normalized_text(navigation)
    normalized_script_index = _normalized_text(script_index)
    normalized_artifact_index = _normalized_text(artifact_index)

    assert "mda-battery-intelligence" in normalized_navigation
    assert "python -m src.cli" in normalized_navigation
    assert "compatibility-sensitive" in normalized_navigation
    assert (
        "Historical plans are not current implementation specifications"
        in normalized_navigation
    )

    assert "close_nasa_pcoe_audit.ps1" in normalized_script_index
    assert "Release and Historical Workflows" in normalized_script_index
    assert (
        "Do not run broad groups of scripts automatically"
        in normalized_script_index
    )

    assert "Negative results are durable evidence" in normalized_artifact_index
    assert "retain_pending_reference_audit" in normalized_artifact_index
    assert (
        "data/processed/nasa_pcoe_battery_import/"
        in normalized_artifact_index
    )
