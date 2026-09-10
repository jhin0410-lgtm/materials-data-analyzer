from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop import evidence_expectation_trust as trust
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256


def _expected() -> dict[str, object]:
    return {
        "provider_id": "trusted-provider",
        "subject_identities": [
            {"namespace": "material", "value": "IN625", "role": "material"}
        ],
        "source_bindings": [
            {
                "binding_id": "source-1",
                "role": "measurement_source",
                "artifact_id": "artifact-1",
                "locator": "artifacts/source.csv",
                "sha256": "1" * 64,
                "byte_size": 12,
                "media_type": "text/csv",
            }
        ],
        "result_units": {"result-uts": "MPa"},
        "calibration_status": "unknown",
        "uncertainty_status_by_id": {"uncertainty-uts": "unknown"},
        "existing_source_family_ids": [],
        "packet_sha256": "2" * 64,
    }


def test_expectation_object_is_authenticated_only_against_external_digest() -> None:
    expected = _expected()
    trusted_digest = canonical_sha256(expected)

    authenticated = trust.authenticate_validation_expectations(
        expected,
        trusted_expectation_sha256=trusted_digest,
    )

    assert authenticated == expected
    assert authenticated is not expected
    authenticated["provider_id"] = "mutated-after-authentication"
    assert expected["provider_id"] == "trusted-provider"


def test_missing_or_malformed_external_trust_root_fails_closed() -> None:
    expected = _expected()

    for value in ("", "0" * 63, "G" * 64):
        with pytest.raises(
            trust.EvidenceExpectationTrustError,
            match="external lowercase SHA-256 digest",
        ):
            trust.authenticate_validation_expectations(
                expected,
                trusted_expectation_sha256=value,
            )


def test_jointly_rehashed_packet_expectation_pair_cannot_replace_original_trust_root() -> None:
    original_expected = _expected()
    original_trust_root = canonical_sha256(original_expected)

    # Model the important attack: a result value is changed in the packet, the packet is
    # re-hashed, and the attacker also updates expected.packet_sha256 so the low-level packet
    # validator would see a self-consistent packet/expectation pair.  The original external
    # expectation root must still reject the rewritten expectation object.
    forged_expected = copy.deepcopy(original_expected)
    forged_expected["packet_sha256"] = "3" * 64
    assert canonical_sha256(forged_expected) != original_trust_root

    with pytest.raises(
        trust.EvidenceExpectationTrustError,
        match="external trust-root digest",
    ):
        trust.authenticate_validation_expectations(
            forged_expected,
            trusted_expectation_sha256=original_trust_root,
        )


def test_attacker_cannot_replace_provider_and_packet_hash_under_original_trust_root() -> None:
    original_expected = _expected()
    original_trust_root = canonical_sha256(original_expected)
    forged_expected = copy.deepcopy(original_expected)
    forged_expected["provider_id"] = "attacker-provider"
    forged_expected["packet_sha256"] = "4" * 64

    with pytest.raises(trust.EvidenceExpectationTrustError):
        trust.authenticate_validation_expectations(
            forged_expected,
            trusted_expectation_sha256=original_trust_root,
        )


def test_authenticated_validation_checks_trust_root_before_packet_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _expected()
    trusted_digest = canonical_sha256(expected)
    called: list[dict[str, object]] = []

    def fake_validate(
        value: object,
        *,
        artifacts: dict[str, bytes],
        expected: dict[str, object],
    ) -> dict[str, object]:
        called.append(expected)
        return {"validated": True}

    monkeypatch.setattr(trust._packet, "validate_evidence_packet", fake_validate)

    result = trust.validate_authenticated_evidence_packet(
        {"packet": "opaque-to-this-boundary"},
        artifacts={"source-1": b"exact-source"},
        expected=expected,
        trusted_expectation_sha256=trusted_digest,
    )
    assert result == {"validated": True}
    assert called == [expected]
    assert called[0] is not expected

    forged = copy.deepcopy(expected)
    forged["packet_sha256"] = "5" * 64
    called.clear()
    with pytest.raises(trust.EvidenceExpectationTrustError):
        trust.validate_authenticated_evidence_packet(
            {"packet": "forged"},
            artifacts={"source-1": b"exact-source"},
            expected=forged,
            trusted_expectation_sha256=trusted_digest,
        )
    assert called == []


def test_authenticated_normalization_uses_same_trust_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _expected()
    trusted_digest = canonical_sha256(expected)
    called: list[dict[str, object]] = []

    def fake_normalize(
        value: object,
        *,
        artifacts: dict[str, bytes],
        expected: dict[str, object],
    ) -> dict[str, object]:
        called.append(expected)
        return {"normalized": True}

    monkeypatch.setattr(trust._packet, "normalize_evidence_packet", fake_normalize)
    assert trust.normalize_authenticated_evidence_packet(
        {"packet": "opaque-to-this-boundary"},
        artifacts={"source-1": b"exact-source"},
        expected=expected,
        trusted_expectation_sha256=trusted_digest,
    ) == {"normalized": True}
    assert called == [expected]
