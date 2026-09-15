from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_cycle1_transport_stop as stop_contract,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop import (
    Cycle1TransportStopError,
    authenticate_cycle1_transport_stop,
    build_cycle1_transport_stop,
)


def _stop(stage: str) -> dict[str, object]:
    prior: dict[str, str]
    if stage == "zenodo_record_metadata":
        prior = {}
    elif stage == "zenodo_readme":
        prior = {"metadata_sha256": "d" * 64}
    else:
        prior = {
            "metadata_sha256": "d" * 64,
            "readme_sha256": "e" * 64,
            "network_authorization_sha256": "f" * 64,
        }
    return build_cycle1_transport_stop(
        mission_sha256="a" * 64,
        network_policy_sha256="b" * 64,
        source_config_sha256="c" * 64,
        maximum_network_requests_per_cycle=3,
        stage=stage,
        requested_url=(
            "https://zenodo.org/api/records/20503603"
            if stage == "zenodo_record_metadata"
            else "https://zenodo.org/api/files/example"
        ),
        transport_error_class=(
            "In625ArchiveNetworkTransportError"
            if stage == "zenodo_archive"
            else "PublicAcquisitionTransportError"
        ),
        transport_error_detail="HTTP acquisition failed: 504 Gateway Time-out",
        observed_prior_evidence=prior,
    )


@pytest.mark.parametrize(
    ("stage", "ordinal"),
    [
        ("zenodo_record_metadata", 1),
        ("zenodo_readme", 2),
        ("zenodo_archive", 3),
    ],
)
def test_transport_stop_authenticates_exact_stage_and_request_ordinal(
    stage: str,
    ordinal: int,
) -> None:
    stop = _stop(stage)
    authenticated = authenticate_cycle1_transport_stop(stop)

    assert authenticated == stop
    assert authenticated["request_ordinal"] == ordinal
    assert authenticated["transient_transport_classification"] is True
    assert authenticated["provider_event_externally_attested"] is False
    assert authenticated["scientific_status_changed"] is False


def test_transport_stop_rejects_request_ordinal_tampering_even_if_not_rehashed() -> None:
    stop = _stop("zenodo_readme")
    forged = copy.deepcopy(stop)
    forged["request_ordinal"] = 3

    with pytest.raises(Cycle1TransportStopError, match="self-hash is invalid"):
        authenticate_cycle1_transport_stop(forged)


def test_transport_stop_rejects_widened_host_at_build_time() -> None:
    with pytest.raises(Cycle1TransportStopError, match="exact authorized Zenodo"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=3,
            stage="zenodo_record_metadata",
            requested_url="https://example.com/api/records/20503603",
            transport_error_class="PublicAcquisitionTransportError",
            transport_error_detail="HTTP acquisition failed: 504",
        )


def test_transport_stop_requires_prior_metadata_binding_for_readme_failure() -> None:
    with pytest.raises(Cycle1TransportStopError, match="prior_evidence field set"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=3,
            stage="zenodo_readme",
            requested_url="https://zenodo.org/api/files/example",
            transport_error_class="PublicAcquisitionTransportError",
            transport_error_detail="HTTP acquisition failed: 504",
            observed_prior_evidence={},
        )


def test_transport_stop_requires_archive_authorization_binding() -> None:
    with pytest.raises(Cycle1TransportStopError, match="prior_evidence field set"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=3,
            stage="zenodo_archive",
            requested_url="https://zenodo.org/api/files/example",
            transport_error_class="In625ArchiveNetworkTransportError",
            transport_error_detail="authorized archive acquisition failed: 504",
            observed_prior_evidence={
                "metadata_sha256": "d" * 64,
                "readme_sha256": "e" * 64,
            },
        )


def test_transport_stop_does_not_allow_scientific_promotion() -> None:
    stop = _stop("zenodo_record_metadata")
    forged = copy.deepcopy(stop)
    forged["scientific_status_changed"] = True

    with pytest.raises(Cycle1TransportStopError, match="self-hash is invalid"):
        authenticate_cycle1_transport_stop(forged)


def test_transport_stop_rejects_request_budget_widening() -> None:
    with pytest.raises(Cycle1TransportStopError, match="exact three-request"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=4,
            stage="zenodo_record_metadata",
            requested_url="https://zenodo.org/api/records/20503603",
            transport_error_class="PublicAcquisitionTransportError",
            transport_error_detail="HTTP acquisition failed: 504",
        )


def test_builder_rejects_hard_failure_class_as_transport_stop() -> None:
    with pytest.raises(Cycle1TransportStopError, match="trusted transient type"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=3,
            stage="zenodo_record_metadata",
            requested_url="https://zenodo.org/api/records/20503603",
            transport_error_class="PublicAcquisitionError",
            transport_error_detail="HTTP acquisition failed: 404 Not Found",
        )


def test_authenticator_rejects_rehashed_forged_transport_class() -> None:
    forged = copy.deepcopy(_stop("zenodo_record_metadata"))
    forged["transport_error_class"] = "PublicAcquisitionError"
    unsigned = dict(forged)
    unsigned.pop("stop_sha256_without_self_field")
    forged["stop_sha256_without_self_field"] = stop_contract._canonical_sha(unsigned)

    with pytest.raises(Cycle1TransportStopError, match="trusted transient type"):
        authenticate_cycle1_transport_stop(forged)

@pytest.mark.parametrize(
    ("container", "field", "value"),
    [
        ("root", "cycle_index", True),
        ("root", "cycle_index", 1.0),
        ("root", "request_ordinal", True),
        ("root", "request_ordinal", 1.0),
        ("authority", "record_id", True),
        ("authority", "record_id", 20503603.0),
        ("authority", "maximum_network_requests_per_cycle", True),
        ("authority", "maximum_network_requests_per_cycle", 3.0),
    ],
)
def test_authenticator_rejects_non_integer_identity_even_when_rehashed(
    container: str,
    field: str,
    value: object,
) -> None:
    forged = copy.deepcopy(_stop("zenodo_record_metadata"))
    target = forged if container == "root" else forged["authority"]
    assert isinstance(target, dict)
    target[field] = value
    unsigned = dict(forged)
    unsigned.pop("stop_sha256_without_self_field")
    forged["stop_sha256_without_self_field"] = stop_contract._canonical_sha(unsigned)

    with pytest.raises(Cycle1TransportStopError, match="must be exact integer"):
        authenticate_cycle1_transport_stop(forged)


def test_builder_rejects_float_request_budget() -> None:
    with pytest.raises(Cycle1TransportStopError, match="exact three-request"):
        build_cycle1_transport_stop(
            mission_sha256="a" * 64,
            network_policy_sha256="b" * 64,
            source_config_sha256="c" * 64,
            maximum_network_requests_per_cycle=3.0,  # type: ignore[arg-type]
            stage="zenodo_record_metadata",
            requested_url="https://zenodo.org/api/records/20503603",
            transport_error_class="PublicAcquisitionTransportError",
            transport_error_detail="HTTP acquisition failed: 504",
        )
