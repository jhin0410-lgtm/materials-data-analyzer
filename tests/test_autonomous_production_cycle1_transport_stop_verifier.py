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
    build_cycle1_transport_stop,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop_verifier import (
    Cycle1TransportStopVerificationError,
    EXPECTED_MISSION_SHA256,
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


def _qualification() -> dict[str, object]:
    return authenticate_in625_network_policy(
        repository_root=REPOSITORY_ROOT,
        mission_path=MISSION,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=POLICY,
        source_config_path=SOURCE,
    )


def _write_stop(output: Path, *, stage: str = "zenodo_record_metadata") -> dict[str, object]:
    output.mkdir(parents=True)
    qualification = _qualification()
    prior: dict[str, str] = {}
    error_class = "PublicAcquisitionTransportError"
    requested_url = "https://zenodo.org/api/records/20503603"
    if stage == "zenodo_archive":
        metadata = b'{"id":20503603}'
        source_config = json.loads(SOURCE.read_text(encoding="utf-8"))
        readme_name = source_config["zenodo"]["readme_file"]
        readme = b"completed readme bytes"
        authorization = {"authorization_sha256": "f" * 64}
        (output / "record.json").write_bytes(metadata)
        (output / readme_name).write_bytes(readme)
        (output / "source-readme-manifest.json").write_text("{}\n", encoding="utf-8")
        (output / "network-authorization.json").write_text(
            json.dumps(authorization) + "\n", encoding="utf-8"
        )
        prior = {
            "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            "readme_sha256": hashlib.sha256(readme).hexdigest(),
            "network_authorization_sha256": "f" * 64,
        }
        error_class = "In625ArchiveNetworkTransportError"
        requested_url = "https://zenodo.org/api/records/20503603/files/Dataset.zip/content"
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
    for name in ("cycle-1-transport-stop.json", "bounded-stop.json"):
        (output / name).write_text(json.dumps(stop) + "\n", encoding="utf-8")
    return stop


def test_verifier_reconstructs_current_authority_for_metadata_stop(tmp_path: Path) -> None:
    output = tmp_path / "stop"
    stop = _write_stop(output)

    result = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )

    assert result["verification_status"] == "cycle_1_transport_stop_authenticated"
    assert result["stage"] == "zenodo_record_metadata"
    assert result["stop_sha256_without_self_field"] == stop["stop_sha256_without_self_field"]
    assert result["provider_event_externally_attested"] is False
    assert result["full_autonomous_live_gate_satisfied"] is False
    assert result["scientific_status_changed"] is False


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
    forged["authority"]["network_policy_sha256"] = "0" * 64  # type: ignore[index]
    unsigned = dict(forged)
    unsigned.pop("stop_sha256_without_self_field")
    raw = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    forged["stop_sha256_without_self_field"] = hashlib.sha256(raw).hexdigest()
    for name in ("cycle-1-transport-stop.json", "bounded-stop.json"):
        (output / name).write_text(json.dumps(forged), encoding="utf-8")

    with pytest.raises(Cycle1TransportStopVerificationError, match="network-policy binding"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_archive_stop_verifier_replays_prior_completed_byte_bindings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")

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

    record = output / "record.json"
    record.write_bytes(record.read_bytes() + b"tamper")
    with pytest.raises(Cycle1TransportStopVerificationError, match="prior metadata hash"):
        verify_cycle1_transport_stop(repository_root=REPOSITORY_ROOT, output_root=output)


def test_archive_stop_verifier_rejects_authorization_reconstruction_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "stop"
    _write_stop(output, stage="zenodo_archive")

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
