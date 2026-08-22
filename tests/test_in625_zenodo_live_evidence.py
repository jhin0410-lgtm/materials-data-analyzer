from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_zenodo_live_evidence import (
    In625ZenodoLiveEvidenceError,
    build_verified_in625_zenodo_readme_manifest,
    inspect_verified_in625_dataset_archive,
)


def _zip_bytes(*, unsafe: bool = False) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../escape.csv" if unsafe else "Mechanical/tensile_results.csv", "x,y\n1,2\n")
        archive.writestr("Metallography/image.tif", b"image")
        archive.writestr("Corrosion/raw_curve.txt", "potential,current\n0.1,1e-6\n")
    return stream.getvalue()


def _config(readme: bytes, archive: bytes, *, archive_sha: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "zenodo": {
            "record_id": 20503603,
            "version_doi": "10.5281/zenodo.20503603",
            "expected_title": "Pinned LPBF IN625 dataset",
            "publication_date": "2026-06-02",
            "license_id": "cc-by-4.0",
            "related_article_doi": "10.1016/j.jmrt.2026.05.163",
            "related_article_relation": "isSupplementTo",
            "selected_files": ["README - Dataset description.txt", "Dataset.zip"],
            "readme_file": "README - Dataset description.txt",
            "archive_file": "Dataset.zip",
            "files": {
                "README - Dataset description.txt": {
                    "size_bytes": len(readme),
                    "provider_checksum_algorithm": "md5",
                    "provider_checksum_digest": hashlib.md5(readme, usedforsecurity=False).hexdigest(),
                    "verified_sha256": hashlib.sha256(readme).hexdigest(),
                },
                "Dataset.zip": {
                    "size_bytes": len(archive),
                    "provider_checksum_algorithm": "md5",
                    "provider_checksum_digest": hashlib.md5(archive, usedforsecurity=False).hexdigest(),
                    "verified_sha256": archive_sha,
                },
            },
            "archive_policy": {
                "max_members": 100,
                "max_total_uncompressed_bytes": 10_000_000,
                "max_member_uncompressed_bytes": 5_000_000,
                "max_selected_tabular_bytes": 5_000_000,
                "selected_extensions": [".csv", ".txt"],
                "reject_symlinks": True,
                "reject_path_traversal": True,
            },
        },
        "scientific_boundaries": {
            "source_acquisition_establishes_direct_nist_comparability": False,
            "source_acquisition_establishes_hypothesis_truth": False,
            "source_acquisition_establishes_positive_scientific_closeout": False,
        },
    }


def _metadata(readme: bytes, archive: bytes) -> bytes:
    payload = {
        "id": 20503603,
        "doi": "10.5281/zenodo.20503603",
        "metadata": {
            "title": "Pinned LPBF IN625 dataset",
            "publication_date": "2026-06-02",
            "access_right": "open",
            "license": {"id": "cc-by-4.0"},
            "related_identifiers": [
                {
                    "identifier": "10.1016/j.jmrt.2026.05.163",
                    "relation": "isSupplementTo",
                    "scheme": "doi",
                }
            ],
        },
        "files": [
            {
                "key": "Dataset.zip",
                "size": len(archive),
                "checksum": "md5:" + hashlib.md5(archive, usedforsecurity=False).hexdigest(),
                "links": {"self": "https://zenodo.org/api/records/20503603/files/Dataset.zip/content"},
            },
            {
                "key": "README - Dataset description.txt",
                "size": len(readme),
                "checksum": "md5:" + hashlib.md5(readme, usedforsecurity=False).hexdigest(),
                "links": {
                    "self": "https://zenodo.org/api/records/20503603/files/README%20-%20Dataset%20description.txt/content"
                },
            },
        ],
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def test_exact_record_and_readme_bind_without_scientific_promotion() -> None:
    readme = b"verified publication dataset description\n"
    archive = _zip_bytes()
    manifest = build_verified_in625_zenodo_readme_manifest(
        config=_config(readme, archive),
        metadata_bytes=_metadata(readme, archive),
        readme_bytes=readme,
    )
    assert manifest["record_id"] == "20503603"
    assert manifest["readme"]["sha256"] == hashlib.sha256(readme).hexdigest()
    assert manifest["scientific_boundary"]["source_provenance_established"] is True
    assert manifest["scientific_boundary"]["direct_nist_condition_comparability_established"] is False
    assert manifest["scientific_boundary"]["hypothesis_truth_established"] is False
    assert manifest["scientific_boundary"]["positive_scientific_closeout_established"] is False


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("title", "title drifted"),
        ("date", "publication date drifted"),
        ("doi", "DOI/relation"),
        ("license", "license identity drifted"),
        ("size", "file size drifted"),
        ("checksum", "provider checksum drifted"),
    ],
)
def test_record_identity_drift_fails_closed(mutation: str, match: str) -> None:
    readme = b"verified publication dataset description\n"
    archive = _zip_bytes()
    metadata = json.loads(_metadata(readme, archive))
    if mutation == "title":
        metadata["metadata"]["title"] = "Different dataset"
    elif mutation == "date":
        metadata["metadata"]["publication_date"] = "2026-06-03"
    elif mutation == "doi":
        metadata["metadata"]["related_identifiers"][0]["identifier"] = "10.0000/wrong"
    elif mutation == "license":
        metadata["metadata"]["license"]["id"] = "cc0-1.0"
    elif mutation == "size":
        metadata["files"][0]["size"] += 1
    elif mutation == "checksum":
        metadata["files"][0]["checksum"] = "md5:" + "0" * 32
    with pytest.raises(In625ZenodoLiveEvidenceError, match=match):
        build_verified_in625_zenodo_readme_manifest(
            config=_config(readme, archive),
            metadata_bytes=json.dumps(metadata, sort_keys=True).encode("utf-8"),
            readme_bytes=readme,
        )


def test_mutated_or_html_readme_fails_closed() -> None:
    readme = b"verified publication dataset description\n"
    archive = _zip_bytes()
    config = _config(readme, archive)
    metadata = _metadata(readme, archive)
    with pytest.raises(In625ZenodoLiveEvidenceError, match="byte size|MD5|SHA-256"):
        build_verified_in625_zenodo_readme_manifest(
            config=config,
            metadata_bytes=metadata,
            readme_bytes=readme + b"x",
        )
    html = b"<html>error</html>" + b" " * (len(readme) - len(b"<html>error</html>"))
    with pytest.raises(In625ZenodoLiveEvidenceError, match="looks like HTML"):
        build_verified_in625_zenodo_readme_manifest(
            config=config,
            metadata_bytes=metadata,
            readme_bytes=html,
        )


def test_archive_inventory_extracts_only_bounded_tabular_files(tmp_path: Path) -> None:
    readme = b"verified publication dataset description\n"
    archive = _zip_bytes()
    archive_path = tmp_path / "Dataset.zip"
    archive_path.write_bytes(archive)
    selected = tmp_path / "selected"
    manifest = inspect_verified_in625_dataset_archive(
        config=_config(readme, archive),
        archive_path=archive_path,
        selected_output_dir=selected,
    )
    assert manifest["archive"]["sha256"] == hashlib.sha256(archive).hexdigest()
    assert manifest["archive"]["sha256_previously_pinned"] is False
    assert manifest["inventory_summary"]["selected_tabular_count"] == 2
    assert {item["path"] for item in manifest["selected_tabular_files"]} == {
        "Mechanical/tensile_results.csv",
        "Corrosion/raw_curve.txt",
    }
    assert (selected / "Mechanical" / "tensile_results.csv").is_file()
    assert not (selected / "Metallography" / "image.tif").exists()
    assert manifest["scientific_boundary"]["empirical_model_validation_established"] is False


def test_archive_sha_pin_and_path_traversal_fail_closed(tmp_path: Path) -> None:
    readme = b"verified publication dataset description\n"
    good = _zip_bytes()
    path = tmp_path / "Dataset.zip"
    path.write_bytes(good)
    with pytest.raises(In625ZenodoLiveEvidenceError, match="SHA-256"):
        inspect_verified_in625_dataset_archive(
            config=_config(readme, good, archive_sha="0" * 64),
            archive_path=path,
        )

    unsafe = _zip_bytes(unsafe=True)
    unsafe_path = tmp_path / "unsafe.zip"
    unsafe_path.write_bytes(unsafe)
    with pytest.raises(In625ZenodoLiveEvidenceError, match="unsafe ZIP member path"):
        inspect_verified_in625_dataset_archive(
            config=_config(readme, unsafe),
            archive_path=unsafe_path,
        )
