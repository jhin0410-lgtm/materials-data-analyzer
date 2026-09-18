from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop_verifier import (
    Cycle1TransportStopVerificationError,
    verify_cycle1_transport_stop,
)

_FIXTURE_NAMESPACE = runpy.run_path(
    str(Path(__file__).with_name("test_autonomous_production_cycle1_transport_stop_verifier.py"))
)
REPOSITORY_ROOT = _FIXTURE_NAMESPACE["REPOSITORY_ROOT"]
ARCHIVE_URL = _FIXTURE_NAMESPACE["ARCHIVE_URL"]
_write_stop = _FIXTURE_NAMESPACE["_write_stop"]
_patch_archive_manifest_builder = _FIXTURE_NAMESPACE["_patch_archive_manifest_builder"]
stop_verifier = _FIXTURE_NAMESPACE["stop_verifier"]


def test_retained_qualification_rejects_equal_valued_json_type_substitution(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(path.read_text(encoding="utf-8"))
    qualification["maximum_network_requests_per_cycle"] = 3.0
    qualification["unrestricted_search_authorized"] = 0
    path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="qualification differs from reconstructed authority",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_retained_source_manifest_rejects_equal_valued_json_type_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    reconstructed = {
        "source_provenance_established": True,
        "size_bytes": 3,
    }
    monkeypatch.setattr(
        stop_verifier,
        "build_verified_in625_zenodo_readme_manifest",
        lambda **_kwargs: reconstructed,
    )
    persisted = {
        "source_provenance_established": 1,
        "size_bytes": 3.0,
    }
    (output / "source-readme-manifest.json").write_text(
        json.dumps(persisted) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="source README manifest differs from authoritative reconstruction",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_retained_authorization_rejects_equal_valued_json_type_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)

    authorization_path = output / "network-authorization.json"
    retained = json.loads(authorization_path.read_text(encoding="utf-8"))
    retained["network_execution_authorized"] = 1
    authorization_path.write_text(json.dumps(retained) + "\n", encoding="utf-8")

    reconstructed = {
        "authorization_sha256": "f" * 64,
        "archive": {"download_url": ARCHIVE_URL},
        "network_execution_authorized": True,
    }
    monkeypatch.setattr(
        stop_verifier,
        "validate_in625_archive_network_authorization",
        lambda _authorization, **_kwargs: reconstructed,
    )

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="retained authorization differs from authoritative reconstruction",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
