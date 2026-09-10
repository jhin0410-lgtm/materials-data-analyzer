from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import autonomous_production_driver as driver
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop import (
    authenticate_cycle1_transport_stop,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop_verifier import (
    verify_cycle1_transport_stop,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
    PublicAcquisitionTransportError,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPOSITORY_ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
SOURCE = REPOSITORY_ROOT / "configs/research/in625_zenodo_20503603_verified_source.v1.json"
EXPECTED_MISSION_SHA256 = hashlib.sha256(MISSION.read_bytes()).hexdigest()


def _policy() -> dict[str, object]:
    return {
        "policy_sha256": "b" * 64,
        "source_config_sha256": "c" * 64,
        "maximum_network_requests_per_cycle": 3,
    }


def test_exact_zenodo_get_preserves_shared_transport_subtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_transport(*_: object, **__: object) -> FetchResult:
        raise PublicAcquisitionTransportError("HTTP acquisition failed: 504 Gateway Time-out")

    monkeypatch.setattr(driver, "fetch_https_bytes", fail_transport)

    with pytest.raises(PublicAcquisitionTransportError):
        driver._exact_zenodo_get(
            "https://zenodo.org/api/records/20503603",
            expected_path="/api/records/20503603",
        )


def test_exact_zenodo_get_maps_shared_hard_failure_to_driver_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_hard(*_: object, **__: object) -> FetchResult:
        raise PublicAcquisitionError("HTTP acquisition failed: 404 Not Found")

    monkeypatch.setattr(driver, "fetch_https_bytes", fail_hard)

    with pytest.raises(
        driver.AutonomousProductionDriverError,
        match="trust/integrity boundary",
    ) as caught:
        driver._exact_zenodo_get(
            "https://zenodo.org/api/records/20503603",
            expected_path="/api/records/20503603",
        )

    assert not isinstance(caught.value, driver.AutonomousProductionTransportStop)


def test_exact_zenodo_get_rejects_same_host_route_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_called = False

    def must_not_fetch(*_: object, **__: object) -> FetchResult:
        nonlocal network_called
        network_called = True
        return FetchResult(
            body=b"unexpected",
            status_code=200,
            final_url="https://zenodo.org/api/records/20503604",
        )

    monkeypatch.setattr(driver, "fetch_https_bytes", must_not_fetch)

    with pytest.raises(
        driver.AutonomousProductionDriverError,
        match="exact authorized Zenodo production route",
    ):
        driver._exact_zenodo_get(
            "https://zenodo.org/api/records/20503604",
            expected_path="/api/records/20503603",
        )

    assert network_called is False


def test_exact_zenodo_get_rejects_query_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_called = False

    def must_not_fetch(*_: object, **__: object) -> FetchResult:
        nonlocal network_called
        network_called = True
        return FetchResult(
            body=b"unexpected",
            status_code=200,
            final_url="https://zenodo.org/api/records/20503603?download=1",
        )

    monkeypatch.setattr(driver, "fetch_https_bytes", must_not_fetch)

    with pytest.raises(
        driver.AutonomousProductionDriverError,
        match="exact authorized Zenodo production route",
    ):
        driver._exact_zenodo_get(
            "https://zenodo.org/api/records/20503603?download=1",
            expected_path="/api/records/20503603",
        )

    assert network_called is False


def test_record_transport_stop_is_self_authenticated_before_raise(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    transport = PublicAcquisitionTransportError(
        "HTTP acquisition failed: 504 Gateway Time-out"
    )

    with pytest.raises(driver.AutonomousProductionTransportStop) as caught:
        driver._raise_cycle1_transport_stop(
            output=output,
            observed_mission_sha="a" * 64,
            network_policy=_policy(),
            source_config_sha256="c" * 64,
            stage="zenodo_record_metadata",
            requested_url="https://zenodo.org/api/records/20503603",
            transport_error=transport,
        )

    persisted = json.loads(
        (output / "cycle-1-transport-stop.json").read_text(encoding="utf-8")
    )
    assert authenticate_cycle1_transport_stop(persisted) == persisted
    assert caught.value.stop == persisted
    assert json.loads((output / "bounded-stop.json").read_text(encoding="utf-8")) == persisted
    assert persisted["transport_error_class"] == "PublicAcquisitionTransportError"
    assert persisted["provider_event_externally_attested"] is False
    assert persisted["network_failure_interpreted_as_negative_scientific_evidence"] is False


def test_live_driver_metadata_transport_failure_persists_exact_authority_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "production-output"

    def use_test_output(_: Path, __: Path) -> Path:
        output.mkdir(parents=True, exist_ok=True)
        return output

    monkeypatch.setattr(driver, "_repo_output", use_test_output)
    monkeypatch.setattr(
        driver,
        "_exact_zenodo_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PublicAcquisitionTransportError(
                "HTTP acquisition failed: 504 Gateway Time-out"
            )
        ),
    )

    with pytest.raises(driver.AutonomousProductionTransportStop) as caught:
        driver.run_autonomous_production(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA256,
            output_root=Path("ignored-by-test"),
            max_cycles=3,
        )

    stop = authenticate_cycle1_transport_stop(caught.value.stop)
    qualified = json.loads(
        (output / "standing-network-policy-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert stop["stage"] == "zenodo_record_metadata"
    assert stop["request_ordinal"] == 1
    assert stop["authority"]["mission_sha256"] == EXPECTED_MISSION_SHA256
    assert stop["authority"]["network_policy_sha256"] == qualified["policy_sha256"]
    assert stop["authority"]["source_config_sha256"] == hashlib.sha256(
        SOURCE.read_bytes()
    ).hexdigest()
    assert stop["observed_prior_evidence"] == {}
    assert not (output / "record.json").exists()
    assert not (output / "autonomous-production-manifest.json").exists()


def test_live_driver_readme_transport_failure_retains_replayable_metadata_witness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "production-output"
    source_config = json.loads(SOURCE.read_text(encoding="utf-8"))
    readme_name = source_config["zenodo"]["readme_file"]
    readme_url = (
        "https://zenodo.org/api/records/20503603/files/"
        "README%20-%20Dataset%20description.txt/content"
    )
    metadata_bytes = json.dumps(
        {
            "id": 20503603,
            "files": [
                {"key": readme_name, "links": {"self": readme_url}},
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    requested_urls: list[str] = []

    def use_test_output(_: Path, __: Path) -> Path:
        output.mkdir(parents=True, exist_ok=True)
        return output

    def metadata_then_readme_timeout(url: str, **_kwargs: object) -> bytes:
        requested_urls.append(url)
        if len(requested_urls) == 1:
            return metadata_bytes
        raise PublicAcquisitionTransportError(
            "HTTP acquisition failed: 504 Gateway Time-out"
        )

    monkeypatch.setattr(driver, "_repo_output", use_test_output)
    monkeypatch.setattr(driver, "_exact_zenodo_get", metadata_then_readme_timeout)

    with pytest.raises(driver.AutonomousProductionTransportStop) as caught:
        driver.run_autonomous_production(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA256,
            output_root=Path("ignored-by-test"),
            max_cycles=3,
        )

    stop = authenticate_cycle1_transport_stop(caught.value.stop)
    assert stop["stage"] == "zenodo_readme"
    assert stop["request_ordinal"] == 2
    assert requested_urls == [
        "https://zenodo.org/api/records/20503603",
        readme_url,
    ]
    assert (output / "record.json").read_bytes() == metadata_bytes
    assert stop["observed_prior_evidence"]["metadata_sha256"] == hashlib.sha256(
        metadata_bytes
    ).hexdigest()
    assert not (output / readme_name).exists()
    assert not (output / "source-readme-manifest.json").exists()
    assert not (output / "network-authorization.json").exists()
    assert not (output / "autonomous-production-manifest.json").exists()

    verification = verify_cycle1_transport_stop(
        repository_root=REPOSITORY_ROOT,
        output_root=output,
    )
    assert verification["stage"] == "zenodo_readme"
    assert verification["completed_metadata_control_plane_witness_replayed"] is True
    assert verification["provider_event_externally_attested"] is False
    assert verification["scientific_status_changed"] is False


def test_readme_transport_stop_requires_and_preserves_metadata_binding(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    metadata = b'{"id":20503603}'

    with pytest.raises(driver.AutonomousProductionTransportStop) as caught:
        driver._raise_cycle1_transport_stop(
            output=output,
            observed_mission_sha="a" * 64,
            network_policy=_policy(),
            source_config_sha256="c" * 64,
            stage="zenodo_readme",
            requested_url="https://zenodo.org/api/records/20503603/files/readme/content",
            transport_error=PublicAcquisitionTransportError("temporary timeout"),
            observed_prior_evidence={
                "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            },
        )

    stop = authenticate_cycle1_transport_stop(caught.value.stop)
    assert stop["request_ordinal"] == 2
    assert stop["observed_prior_evidence"]["metadata_sha256"] == hashlib.sha256(
        metadata
    ).hexdigest()
