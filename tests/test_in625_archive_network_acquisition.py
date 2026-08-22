from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_archive_network_acquisition import (
    In625ArchiveNetworkAcquisitionError,
    NetworkFetchResult,
    build_in625_archive_network_authorization,
    execute_authorized_in625_archive_download,
    validate_in625_archive_network_authorization,
)


def _config(readme: bytes, archive: bytes) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "source_id": "zenodo-20503603-in625-lpbf-publication-supplement",
        "source_family": "zenodo_publication_supplement",
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
                    "provider_checksum_digest": hashlib.md5(
                        readme, usedforsecurity=False
                    ).hexdigest(),
                    "verified_sha256": hashlib.sha256(readme).hexdigest(),
                },
                "Dataset.zip": {
                    "size_bytes": len(archive),
                    "provider_checksum_algorithm": "md5",
                    "provider_checksum_digest": hashlib.md5(
                        archive, usedforsecurity=False
                    ).hexdigest(),
                    "verified_sha256": hashlib.sha256(archive).hexdigest(),
                },
            },
            "archive_policy": {
                "max_members": 100,
                "max_total_uncompressed_bytes": 10_000_000,
                "max_member_uncompressed_bytes": 5_000_000,
                "max_selected_tabular_bytes": 5_000_000,
                "selected_extensions": [".csv", ".txt", ".dat", ".xlsx", ".xls"],
                "reject_symlinks": True,
                "reject_path_traversal": True,
            },
        },
        "scientific_boundaries": {
            "authority_class": "source_artifact_only",
            "issue_76_eligible": False,
            "automatic_scientific_promotion": False,
            "source_acquisition_establishes_direct_nist_comparability": False,
            "source_acquisition_establishes_hypothesis_truth": False,
            "source_acquisition_establishes_positive_scientific_closeout": False,
        },
    }


def _config_bytes(config: dict[str, object]) -> bytes:
    return (json.dumps(config, sort_keys=True) + "\n").encode("utf-8")


def _metadata(readme: bytes, archive: bytes, *, archive_url: str | None = None) -> bytes:
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
                "checksum": "md5:"
                + hashlib.md5(archive, usedforsecurity=False).hexdigest(),
                "links": {
                    "self": archive_url
                    or "https://zenodo.org/api/records/20503603/files/Dataset.zip/content"
                },
            },
            {
                "key": "README - Dataset description.txt",
                "size": len(readme),
                "checksum": "md5:"
                + hashlib.md5(readme, usedforsecurity=False).hexdigest(),
                "links": {
                    "self": "https://zenodo.org/api/records/20503603/files/README%20-%20Dataset%20description.txt/content"
                },
            },
        ],
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _authorization_fixture(archive: bytes = b"real binary archive bytes") -> tuple[
    dict[str, object], bytes, bytes, bytes, dict[str, object]
]:
    readme = b"verified publication dataset description\n"
    config = _config(readme, archive)
    config_bytes = _config_bytes(config)
    metadata = _metadata(readme, archive)
    authorization = build_in625_archive_network_authorization(
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata,
        readme_bytes=readme,
    )
    return config, config_bytes, metadata, readme, authorization


def test_exact_readme_and_source_identity_authorize_only_future_network_execution() -> None:
    config, config_bytes, metadata, readme, authorization = _authorization_fixture()
    assert authorization["authorization_status"] == "authorized_exact_archive_download"
    assert authorization["network_execution_authorized"] is True
    assert authorization["network_access_performed"] is False
    assert authorization["archive_bytes_observed"] is False
    assert authorization["archive"]["allowed_hosts"] == ["zenodo.org"]
    assert authorization["preconditions_verified"] == {
        "exact_repository_source_config": True,
        "exact_live_zenodo_record": True,
        "exact_readme_bytes": True,
        "open_license_identity": True,
        "archive_provider_identity": True,
        "project_archive_sha256_pre_pinned": True,
        "https_exact_host_restriction": True,
    }
    assert validate_in625_archive_network_authorization(
        authorization,
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata,
        readme_bytes=readme,
    ) == authorization


def test_authorization_rejects_wrong_archive_host_before_network_access() -> None:
    archive = b"archive"
    readme = b"verified publication dataset description\n"
    config = _config(readme, archive)
    with pytest.raises(In625ArchiveNetworkAcquisitionError, match="exact Zenodo host"):
        build_in625_archive_network_authorization(
            config=config,
            config_bytes=_config_bytes(config),
            metadata_bytes=_metadata(
                readme,
                archive,
                archive_url="https://example.org/Dataset.zip",
            ),
            readme_bytes=readme,
        )


def test_resigned_authorization_substitution_is_rejected_by_reconstruction() -> None:
    config, config_bytes, metadata, readme, authorization = _authorization_fixture()
    tampered = json.loads(json.dumps(authorization))
    tampered["archive"]["download_url"] = (
        "https://zenodo.org/api/records/20503603/files/other.zip/content"
    )
    unsigned = dict(tampered)
    unsigned.pop("authorization_sha256")
    tampered["authorization_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(
        In625ArchiveNetworkAcquisitionError,
        match="deterministic exact-source reconstruction",
    ):
        validate_in625_archive_network_authorization(
            tampered,
            config=config,
            config_bytes=config_bytes,
            metadata_bytes=metadata,
            readme_bytes=readme,
        )


def test_authorized_download_verifies_exact_size_md5_sha_and_writes_atomically(
    tmp_path: Path,
) -> None:
    archive = b"PK\x03\x04real pinned archive bytes"
    config, config_bytes, metadata, readme, authorization = _authorization_fixture(archive)
    calls: list[tuple[str, int]] = []

    def fetcher(
        url: str,
        *,
        max_bytes: int,
        timeout_seconds: float,
    ) -> NetworkFetchResult:
        calls.append((url, max_bytes))
        assert timeout_seconds > 0
        return NetworkFetchResult(
            body=archive,
            status_code=200,
            final_url=url,
            content_type="application/zip",
        )

    output = tmp_path / "Dataset.zip"
    receipt = execute_authorized_in625_archive_download(
        authorization=authorization,
        config=config,
        config_bytes=config_bytes,
        metadata_bytes=metadata,
        readme_bytes=readme,
        output_path=output,
        fetcher=fetcher,
    )
    assert calls == [(authorization["archive"]["download_url"], len(archive) + 1)]
    assert output.read_bytes() == archive
    assert receipt["network_execution_authorized"] is True
    assert receipt["network_access_performed"] is True
    assert receipt["exact_host_restriction_enforced"] is True
    assert receipt["byte_count_verified"] is True
    assert receipt["provider_checksum_verified"] is True
    assert receipt["project_sha256_verified"] is True
    assert receipt["archive"]["sha256"] == hashlib.sha256(archive).hexdigest()
    assert receipt["scientific_boundary"]["direct_nist_condition_comparability_established"] is False
    assert receipt["scientific_boundary"]["hypothesis_truth_established"] is False


@pytest.mark.parametrize("failure", ["wrong_size", "wrong_bytes", "wrong_host", "html"])
def test_authorized_download_fails_closed_on_transport_or_payload_drift(
    tmp_path: Path,
    failure: str,
) -> None:
    archive = b"PK\x03\x04real pinned archive bytes"
    config, config_bytes, metadata, readme, authorization = _authorization_fixture(archive)

    def fetcher(
        url: str,
        *,
        max_bytes: int,
        timeout_seconds: float,
    ) -> NetworkFetchResult:
        del max_bytes, timeout_seconds
        if failure == "wrong_size":
            body = archive + b"x"
        elif failure == "wrong_bytes":
            body = b"X" * len(archive)
        elif failure == "html":
            body = b"<html>" + b"x" * (len(archive) - len(b"<html>"))
        else:
            body = archive
        final_url = "https://example.org/redirect" if failure == "wrong_host" else url
        return NetworkFetchResult(
            body=body,
            status_code=200,
            final_url=final_url,
            content_type="application/octet-stream",
        )

    with pytest.raises(In625ArchiveNetworkAcquisitionError):
        execute_authorized_in625_archive_download(
            authorization=authorization,
            config=config,
            config_bytes=config_bytes,
            metadata_bytes=metadata,
            readme_bytes=readme,
            output_path=tmp_path / f"{failure}.zip",
            fetcher=fetcher,
        )
    assert not (tmp_path / f"{failure}.zip").exists()
