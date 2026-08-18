from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.ssrm_titanium_zenodo_episode as module
from materials_data_analyzer.research_loop.ssrm_titanium_zenodo_episode import (
    SsrmTitaniumZenodoEpisodeError,
    run_ssrm_titanium_zenodo_episode,
    validate_ssrm_episode_config,
)

ARCHIVE_NAME = "SSRM of Ti, Ti6Al4V, Ti5553.zip"


def _archive() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("README.txt", "instrument and process notes\n")
        handle.writestr("pressure/trace.csv", "time_s,pressure_bar\n0,50\n")
        handle.writestr("SEM/image.tif", b"not-a-real-image")
    return out.getvalue()


def _config(md5: str) -> dict:
    return {
        "schema_version": "1.0",
        "episode_id": "zenodo-ssrm-titanium-nitriding-generalization",
        "research_question": "What can be supported?",
        "zenodo": {
            "record_id": 18504064,
            "version_doi": "10.5281/zenodo.18504064",
            "selected_archive": ARCHIVE_NAME,
            "expected_source_checksum_algorithm": "md5",
            "expected_source_checksum_digest": md5,
            "required_license": "cc0-1.0",
        },
        "source_scope": {
            "materials": ["Ti", "Ti6Al4V", "Ti5553"],
            "process_family": "self-shearing reactive milling under nitrogen",
            "declared_nitrogen_pressure_bar": 50,
            "declared_max_process_time_hours": 10,
            "modalities_to_audit": [
                "temperature_and_pressure",
                "SEM",
                "EDS",
                "XRD",
                "Raman",
                "elemental_nitrogen_analysis",
            ],
        },
        "scientific_boundaries": {
            "filename_is_sample_identity": False,
            "cross_technique_identical_aliquot_assumed": False,
            "replicate_independence_assumed": False,
            "automatic_scientific_promotion": False,
            "model_training_authorized_on_acquisition": False,
        },
    }


def _metadata(archive: bytes) -> bytes:
    payload = {
        "id": 18504064,
        "doi": "10.5281/zenodo.18504064",
        "metadata": {
            "title": "Dataset for mechanical nitriding",
            "access_right": "open",
            "license": {"id": "cc-zero"},
        },
        "files": [
            {
                "key": ARCHIVE_NAME,
                "size": len(archive),
                "checksum": "md5:"
                + hashlib.md5(archive, usedforsecurity=False).hexdigest(),
                "links": {
                    "self": (
                        "https://zenodo.org/api/records/18504064/files/archive/content"
                    )
                },
            }
        ],
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def test_config_refuses_semantic_shortcuts() -> None:
    cfg = _config("a" * 32)
    cfg["scientific_boundaries"]["filename_is_sample_identity"] = True
    with pytest.raises(SsrmTitaniumZenodoEpisodeError, match="must remain false"):
        validate_ssrm_episode_config(cfg)


def test_episode_acquires_and_inventories_without_scientific_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive()
    md5 = hashlib.md5(archive, usedforsecurity=False).hexdigest()
    metadata = _metadata(archive)

    monkeypatch.setattr(
        module,
        "fetch_zenodo_record_metadata",
        lambda record_id: (metadata, f"https://zenodo.org/api/records/{record_id}"),
    )

    def fake_acquire(**kwargs):
        output = Path(kwargs["output_dir"])
        (output / "files").mkdir(parents=True)
        (output / "files" / ARCHIVE_NAME).write_bytes(archive)
        return {
            "files": [
                {
                    "key": ARCHIVE_NAME,
                    "size_bytes": len(archive),
                    "source_checksum_algorithm": "md5",
                    "source_checksum_digest": md5,
                    "local_sha256": hashlib.sha256(archive).hexdigest(),
                    "download_url": (
                        "https://zenodo.org/api/records/18504064/files/archive/content"
                    ),
                    "final_url": (
                        "https://zenodo.org/api/records/18504064/files/archive/content"
                    ),
                }
            ]
        }

    monkeypatch.setattr(module, "acquire_zenodo_files", fake_acquire)
    result = run_ssrm_titanium_zenodo_episode(
        config=_config(md5), output_dir=tmp_path / "episode"
    )

    assert result["record_id"] == "18504064"
    assert result["doi"] == "10.5281/zenodo.18504064"
    assert result["source_license_ids"] == ["cc-zero"]
    assert result["license_ids"] == ["cc0-1.0"]
    assert result["source_checksum_algorithm"] == "md5"
    assert result["source_checksum_digest"] == md5
    assert result["archive_sha256"] == hashlib.sha256(archive).hexdigest()
    assert result["archive_member_count"] == 3
    assert result["archive_text_candidate_count"] == 2
    assert result["archive_text_hashed_count"] == 2
    assert result["bulk_extraction_performed"] is False
    assert result["semantic_lineage_audited"] is False
    assert result["replicate_independence_established"] is False
    assert result["scientific_support_established"] is False
    assert result["scientific_status_changed"] is False
