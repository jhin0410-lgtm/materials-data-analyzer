from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_cycle1_transport_stop_verifier as verifier,
)
from materials_data_analyzer.research_loop.autonomous_production_cycle1_transport_stop import (
    Cycle1TransportStopError,
    authenticate_cycle1_transport_stop,
    build_cycle1_transport_stop,
)


def _stop() -> dict[str, object]:
    return build_cycle1_transport_stop(
        mission_sha256="a" * 64,
        network_policy_sha256="b" * 64,
        source_config_sha256="c" * 64,
        maximum_network_requests_per_cycle=3,
        stage="zenodo_record_metadata",
        requested_url="https://zenodo.org/api/records/20503603",
        transport_error_class="PublicAcquisitionTransportError",
        transport_error_detail="HTTP acquisition failed: 504 Gateway Time-out",
    )


def _rehash(value: dict[str, object]) -> dict[str, object]:
    forged = copy.deepcopy(value)
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


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("cycle_index", 1.0),
        ("scientific_status_changed", 0),
    ],
)
def test_rehashed_type_confused_bounded_copy_fails_intrinsic_authentication(
    field: str,
    replacement: object,
) -> None:
    bounded = _stop()
    bounded[field] = replacement
    bounded = _rehash(bounded)

    with pytest.raises(Cycle1TransportStopError):
        authenticate_cycle1_transport_stop(bounded)


def test_canonical_copy_comparison_preserves_json_type_identity() -> None:
    assert verifier._canonical_json_bytes(
        {"cycle_index": 1}, field="integer fixture"
    ) != verifier._canonical_json_bytes(
        {"cycle_index": 1.0}, field="float fixture"
    )
    assert verifier._canonical_json_bytes(
        {"scientific_status_changed": False}, field="boolean fixture"
    ) != verifier._canonical_json_bytes(
        {"scientific_status_changed": 0}, field="integer fixture"
    )
