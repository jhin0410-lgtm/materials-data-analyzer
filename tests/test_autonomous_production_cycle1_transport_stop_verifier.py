from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_cycle1_transport_stop_verifier as stop_verifier,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop import (
    Cycle1TransportStopError,
    build_cycle1_transport_stop,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop_verifier import (
    EXPECTED_MISSION_SHA256,
    Cycle1TransportStopVerificationError,
    verify_cycle1_transport_stop,
)
from materials_data_analyzer.research_loop.in625_archive_network_acquisition import (
    In625ArchiveNetworkAcquisitionError,
)
from materials_data_analyzer.research_loop.in625_network_policy import (
    authenticate_in625_network_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPOSITORY_ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
POLICY = REPOSITORY_ROOT / "configs/research/in625_zenodo_network_acquisition_policy.v1.json"
SOURCE = REPOSITORY_ROOT / "configs/research/in625_zenodo_20503603_verified_source.v1.json"
METADATA_URL = "https://zenodo.org/api/records/20503603"
README_NAME = "README - Dataset description.txt"
README_URL = (
    "https://zenodo.org/api/records/20503603/files/"
    "README%20-%20Dataset%20description.txt/content"
)
README_URL_EXPLICIT_443 = (
    "https://zenodo.org:443/api/records/20503603/files/"
    "README%20-%20Dataset%20description.txt/content"
)
ARCHIVE_URL = "https://zenodo.org/api/records/20503603/files/Dataset.zip/content"


def _qualification() -> dict[str, object]:
    return authenticate_in625_network_policy(
        repository_root=REPOSITORY_ROOT,
        mission_path=MISSION,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=POLICY,
        source_config_path=SOURCE,
    )


def _metadata_bytes(
    *,
    readme_url: str = README_URL,
    record_id: int = 20503603,
    duplicate_readme: bool = False,
    title: str | None = None,
) -> bytes:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    zenodo = source["zenodo"]
    configured_files = zenodo["files"]
    files: list[dict[str, object]] = [
        {
            "key": README_NAME,
            "size": configured_files[README_NAME]["size_bytes"],
            "checksum": (
                f"{configured_files[README_NAME]['provider_checksum_algorithm']}:"
                f"{configured_files[README_NAME]['provider_checksum_digest']}"
            ),
            "links": {"self": readme_url},
        },
        {
            "key": "Dataset.zip",
            "size": configured_files["Dataset.zip"]["size_bytes"],
            "checksum": (
                f"{configured_files['Dataset.zip']['provider_checksum_algorithm']}:"
                f"{configured_files['Dataset.zip']['provider_checksum_digest']}"
            ),
            "links": {"self": ARCHIVE_URL},
        },
    ]
    if duplicate_readme:
        files.append(dict(files[0]))
    return json.dumps(
        {
            "id": record_id,
            "doi": zenodo["version_doi"],
            "metadata": {
                "title": title or zenodo["expected_title"],
                "publication_date": zenodo["publication_date"],
                "access_right": "open",
                "license": {"id": zenodo["license_id"]},
                "related_identifiers": [
                    {
                        "identifier": zenodo["related_article_doi"],
                        "relation": zenodo["related_article_relation"],
                        "scheme": "doi",
                    }
                ],
            },
            "files": files,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _persist_stop(output: Path, stop: dict[str, object]) -> None:
    for name in ("cycle-1-transport-stop.json", "bounded-stop.json"):
        (output / name).write_text(json.dumps(stop) + "\n", encoding="utf-8")


def _rehash(stop: dict[str, object]) -> dict[str, object]:
    forged = copy.deepcopy(stop)
    unsigned = dict(forged)
    unsigned.pop("stop_sha256_without_self_field", None)
    raw = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    forged["stop_sha256_without_self_field"] = hashlib.sha256(raw).hexdigest()
    return forged


def _write_stop(output: Path, *, stage: str = "zenodo_record_metadata") -> dict[str, object]:
    output.mkdir(parents=True)
    qualification = _qualification()
    (output / "standing-network-policy-qualification.json").write_text(
        json.dumps(qualification, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prior: dict[str, str] = {}
    error_class = "PublicAcquisitionTransportError"
    requested_url = METADATA_URL
    if stage == "zenodo_readme":
        metadata = _metadata_bytes()
        (output / "record.json").write_bytes(metadata)
        prior = {"metadata_sha256": hashlib.sha256(metadata).hexdigest()}
        requested_url = README_URL
    elif stage == "zenodo_archive":
        metadata = _metadata_bytes()
        source_config = json.loads(SOURCE.read_text(encoding="utf-8"))
        readme_name = source_config["zenodo"]["readme_file"]
        readme = b"completed readme bytes"
        authorization: dict[str, object] = {
            "authorization_sha256": "f" * 64,
            "archive": {"download_url": ARCHIVE_URL},
        }
        (output / "record.json").write_bytes(metadata)
        (output / readme_name).write_bytes(readme)
        (output / "source-readme-manifest.json").write_text(
            json.dumps({"fixture": "trusted-source-manifest"}) + "\n",
            encoding="utf-8",
        )
        (output / "network-authorization.json").write_text(
            json.dumps(authorization) + "\n", encoding="utf-8"
        )
        prior = {
            "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            "readme_sha256": hashlib.sha256(readme).hexdigest(),
            "network_authorization_sha256": "f" * 64,
        }
        error_class = "In625ArchiveNetworkTransportError"
        requested_url = ARCHIVE_URL
    stop = build_cycle1_transport_stop(
        mission_sha256=EXPECTED_MISSION_SHA256,
        network_policy_sha256=str(qualification["policy_sha256"]),
        source_config_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        maximum_network_requests_per_cycle=3,
        stage=stage,
        requested_url=requested_url,
        transport_error_class=error_class,
        transport_error_detail="HTTP acquisition failed: 504 Gateway Time-out",
        observed_prior_evidence=prior,
    )
    _persist_stop(output, stop)
    return stop


def _patch_archive_manifest_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stop_verifier,
        "build_verified_in625_zenodo_readme_manifest",
        lambda **_kwargs: {"fixture": "trusted-source-manifest"},
    )


def test_verifier_reconstructs_current_authority_for_metadata_stop(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output)

    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )

    assert result["verification_status"] == "cycle_1_transport_stop_authenticated"
    assert result["stage"] == "zenodo_record_metadata"
    assert result["requested_url_authenticated"] is True
    assert result["requested_route_basis"] == "standing_network_policy_record_api"
    assert result["completed_metadata_control_plane_witness_replayed"] is False
    assert result["stop_sha256_without_self_field"] == stop["stop_sha256_without_self_field"]
    assert result["provider_event_externally_attested"] is False
    assert result["full_autonomous_live_gate_satisfied"] is False
    assert result["scientific_status_changed"] is False


def test_verifier_authenticates_pinned_readme_content_route(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")

    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )

    assert result["stage"] == "zenodo_readme"
    assert result["requested_url_authenticated"] is True
    assert result["requested_route_basis"] == (
        "retained_metadata_and_pinned_readme_content_route"
    )
    assert result["completed_metadata_control_plane_witness_replayed"] is True
    assert result["provider_event_externally_attested"] is False


def test_verifier_rejects_bounded_stop_copy_drift(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    bounded = json.loads((output / "bounded-stop.json").read_text(encoding="utf-8"))
    bounded["transport_error_detail"] = "different observation"
    (output / "bounded-stop.json").write_text(json.dumps(bounded), encoding="utf-8")

    with pytest.raises(Cycle1TransportStopVerificationError, match="differs"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_verifier_rejects_success_manifest_on_transport_stop_path(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    (output / "autonomous-production-manifest.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(Cycle1TransportStopVerificationError, match="successful autonomous"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_verifier_rejects_rehashed_policy_binding_forgery(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output)
    forged = copy.deepcopy(stop)
    authority = forged["authority"]
    assert isinstance(authority, dict)
    authority["network_policy_sha256"] = "0" * 64
    forged = _rehash(forged)
    _persist_stop(output, forged)

    with pytest.raises(Cycle1TransportStopVerificationError, match="network-policy binding"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_verifier_rejects_rehashed_same_host_metadata_url_forgery(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output)
    stop["requested_url"] = "https://zenodo.org/api/records/20503604"
    _persist_stop(output, _rehash(stop))

    with pytest.raises(Cycle1TransportStopVerificationError, match="standing-policy record API"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_verifier_rejects_rehashed_same_host_readme_route_forgery(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output, stage="zenodo_readme")
    stop["requested_url"] = ARCHIVE_URL
    _persist_stop(output, _rehash(stop))

    with pytest.raises(Cycle1TransportStopVerificationError, match="pinned published-record"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_intrinsic_stop_rejects_query_bearing_zenodo_url() -> None:
    qualification = _qualification()
    with pytest.raises(Cycle1TransportStopError, match="params/query/fragment"):
        build_cycle1_transport_stop(
            mission_sha256=EXPECTED_MISSION_SHA256,
            network_policy_sha256=str(qualification["policy_sha256"]),
            source_config_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            maximum_network_requests_per_cycle=3,
            stage="zenodo_record_metadata",
            requested_url=f"{METADATA_URL}?download=1",
            transport_error_class="PublicAcquisitionTransportError",
            transport_error_detail="HTTP acquisition failed: 504 Gateway Time-out",
        )


def test_metadata_stop_rejects_retained_completed_record_witness(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    (output / "record.json").write_bytes(_metadata_bytes())

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="nonexistent completed metadata",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_readme_stop_requires_retained_completed_metadata_witness(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    (output / "record.json").unlink()

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="requires retained completed record metadata",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_readme_stop_rejects_metadata_byte_drift(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    metadata = json.loads((output / "record.json").read_text(encoding="utf-8"))
    metadata["runtime_noise"] = "changed-after-stop"
    (output / "record.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="prior metadata hash",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_readme_stop_rejects_self_consistent_metadata_url_forgery(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output, stage="zenodo_readme")
    forged_metadata = _metadata_bytes(readme_url=README_URL_EXPLICIT_443)
    (output / "record.json").write_bytes(forged_metadata)
    prior = stop["observed_prior_evidence"]
    assert isinstance(prior, dict)
    prior["metadata_sha256"] = hashlib.sha256(forged_metadata).hexdigest()
    _persist_stop(output, _rehash(stop))

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="differs from retained completed metadata",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_readme_stop_rejects_self_consistent_source_identity_forgery(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output, stage="zenodo_readme")
    forged_metadata = _metadata_bytes(title="forged source title")
    (output / "record.json").write_bytes(forged_metadata)
    prior = stop["observed_prior_evidence"]
    assert isinstance(prior, dict)
    prior["metadata_sha256"] = hashlib.sha256(forged_metadata).hexdigest()
    _persist_stop(output, _rehash(stop))

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="authoritative source-identity replay",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT, output_root=output
        )


def test_readme_stop_rejects_duplicate_metadata_readme_identity(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output, stage="zenodo_readme")
    forged_metadata = _metadata_bytes(duplicate_readme=True)
    (output / "record.json").write_bytes(forged_metadata)
    prior = stop["observed_prior_evidence"]
    assert isinstance(prior, dict)
    prior["metadata_sha256"] = hashlib.sha256(forged_metadata).hexdigest()
    _persist_stop(output, _rehash(stop))

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="authoritative source-identity replay",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_readme_stop_rejects_failed_readme_bytes_as_completed_evidence(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    (output / README_NAME).write_bytes(b"partial failed response")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="failed README bytes",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_archive_stop_verifier_replays_prior_completed_byte_bindings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)

    monkeypatch.setattr(
        stop_verifier,
        "validate_in625_archive_network_authorization",
        lambda authorization, **_kwargs: authorization,
    )
    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )
    assert result["stage"] == "zenodo_archive"
    assert result["requested_url_authenticated"] is True
    assert result["requested_route_basis"] == "reconstructed_archive_authorization"
    assert result["completed_metadata_control_plane_witness_replayed"] is True

    record = output / "record.json"
    metadata = json.loads(record.read_text(encoding="utf-8"))
    metadata["runtime_noise"] = "tamper"
    record.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(Cycle1TransportStopVerificationError, match="prior metadata hash"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_archive_stop_verifier_rejects_rehashed_requested_url_forgery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)
    stop["requested_url"] = README_URL
    _persist_stop(output, _rehash(stop))
    monkeypatch.setattr(
        stop_verifier,
        "validate_in625_archive_network_authorization",
        lambda authorization, **_kwargs: authorization,
    )

    with pytest.raises(Cycle1TransportStopVerificationError, match="reconstructed authorization"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_archive_stop_verifier_rejects_authorization_reconstruction_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)

    def reject(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise In625ArchiveNetworkAcquisitionError("forged authorization")

    monkeypatch.setattr(
        stop_verifier,
        "validate_in625_archive_network_authorization",
        reject,
    )
    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="authoritative reconstruction",
    ):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)

def test_verifier_rejects_duplicate_keys_in_persisted_stop_json(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output)
    raw = json.dumps(stop, separators=(",", ":"))
    raw = raw.replace("{", '{"scientific_status_changed":true,', 1)
    (output / "cycle-1-transport-stop.json").write_text(raw, encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="duplicate JSON key",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_archive_stop_rejects_forged_retained_source_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)
    (output / "source-readme-manifest.json").write_text(
        json.dumps({"fixture": "forged-source-manifest"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="source README manifest differs",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


@pytest.mark.parametrize(
    ("artifact_name", "error_match"),
    [
        ("Dataset.zip", "completed archive bytes"),
        ("network-acquisition-receipt.json", "completed network acquisition receipt"),
    ],
)
def test_archive_stop_rejects_impossible_completed_archive_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    artifact_name: str,
    error_match: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)
    (output / artifact_name).write_bytes(b"impossible completed artifact")

    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )

@pytest.mark.parametrize(
    ("artifact_name", "error_match"),
    [
        (README_NAME, "downstream README bytes"),
        ("Dataset.zip", "completed archive bytes"),
        (
            "network-acquisition-receipt.json",
            "completed network acquisition receipt",
        ),
    ],
)
def test_metadata_stop_rejects_impossible_downstream_artifacts(
    tmp_path: Path,
    artifact_name: str,
    error_match: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    (output / artifact_name).write_bytes(b"impossible downstream artifact")

    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


@pytest.mark.parametrize(
    ("artifact_name", "error_match"),
    [
        ("Dataset.zip", "completed archive bytes"),
        (
            "network-acquisition-receipt.json",
            "completed network acquisition receipt",
        ),
    ],
)
def test_readme_stop_rejects_impossible_archive_success_artifacts(
    tmp_path: Path,
    artifact_name: str,
    error_match: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    (output / artifact_name).write_bytes(b"impossible downstream artifact")

    with pytest.raises(Cycle1TransportStopVerificationError, match=error_match):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )

@pytest.mark.parametrize(
    "artifact_name",
    [
        "selected-source-files",
        "archive-manifest.json",
        "reviewed-tensile",
        "tensile-quality-verification.json",
        "typed-research-objective.json",
        "typed-research-run",
        "cycle-1-planning.json",
        "machine-authored-request",
        "machine-request-compilation.json",
        "typed-execution-handoff.json",
        "typed-execution-result.json",
        "typed-research-state.json",
        "quality-aware-rediagnosis.json",
        "physical-comparability-assessment.json",
    ],
)
def test_transport_stop_rejects_known_post_archive_production_outputs(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    artifact = output / artifact_name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("forged downstream production artifact", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="post-archive production artifact",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_verifier_rejects_forged_retained_policy_qualification(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["unrestricted_search_authorized"] = True
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="qualification differs from reconstructed authority",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_readme_stop_rejects_oversized_retained_metadata_before_parse(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_readme")
    with (output / "record.json").open("wb") as handle:
        handle.truncate(stop_verifier._ZENODO_CONTROL_PLANE_MAX_BYTES + 1)

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="record metadata exceeds .* verification bound",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_archive_stop_rejects_oversized_retained_readme_before_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")
    _patch_archive_manifest_builder(monkeypatch)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    maximum = source["zenodo"]["files"][README_NAME]["size_bytes"]
    assert isinstance(maximum, int) and not isinstance(maximum, bool)
    with (output / README_NAME).open("wb") as handle:
        handle.truncate(maximum + 1)

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="completed README exceeds .* verification bound",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )


def test_verifier_accepts_exported_qualification_from_different_checkout_root(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["source_config_path"] = (
        "/different/checkout/materials-data-analyzer/"
        "configs/research/in625_zenodo_20503603_verified_source.v1.json"
    )
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )
    assert result["verification_status"] == "cycle_1_transport_stop_authenticated"


def test_verifier_rejects_exported_qualification_with_wrong_source_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output)
    qualification_path = output / "standing-network-policy-qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["source_config_path"] = "/different/checkout/configs/research/other.json"
    qualification_path.write_text(json.dumps(qualification) + "\n", encoding="utf-8")

    with pytest.raises(
        Cycle1TransportStopVerificationError,
        match="source config path differs from repository-pinned identity",
    ):
        verify_cycle1_transport_stop(
            repository_root=REPOSITORY_ROOT,
            output_root=output,
        )
