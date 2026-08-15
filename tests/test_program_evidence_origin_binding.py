from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.program_evidence_origin_binding import (
    ProgramEvidenceOriginBindingError,
    authenticate_program_evidence_origin_binding,
)


def _bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture() -> tuple[dict[str, object], dict[str, str], bytes, bytes, bytes]:
    evidence = b"instrument-output\x00\x01"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    binding = {
        "workstream_id": "ws-characterization",
        "role": "primary_measurement",
        "sha256": evidence_sha,
    }
    program_state: dict[str, object] = {
        "schema_version": "1.0",
        "workstreams": [
            {
                "workstream_id": "ws-characterization",
                "planning_state": {
                    "evidence_bindings": [
                        dict(binding),
                        {
                            "role": "protocol_record",
                            "sha256": "1" * 64,
                        },
                    ]
                },
            },
            {
                "workstream_id": "ws-model",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "model_output",
                            "sha256": "2" * 64,
                        }
                    ]
                },
            },
        ],
    }
    declaration_obj: dict[str, object] = {
        "schema_version": "1.0",
        "evidence_id": "evidence-001",
        "evidence_artifact_sha256": evidence_sha,
        "origin_class": "empirical_measurement",
        "origin_statement": "Recorded measurement bytes are classified as empirical measurement output.",
        "limitations": ["Classification does not prove instrument calibration or physical truth."],
    }
    declaration = _bytes(declaration_obj)
    verification_obj: dict[str, object] = {
        "schema_version": "1.0",
        "decision_id": "origin-decision-001",
        "evidence_id": "evidence-001",
        "evidence_artifact_sha256": evidence_sha,
        "origin_declaration_sha256": hashlib.sha256(declaration).hexdigest(),
        "origin_class": "empirical_measurement",
        "verification_scope": "origin_classification_only",
        "verifier_id": "domain-origin-reviewer",
        "rationale": "The exact evidence/declaration pair is classified for provenance only.",
        "limitations": ["Verifier credentials are outside this contract."],
        "domain_verified_origin": True,
    }
    verification = _bytes(verification_obj)
    return program_state, binding, evidence, declaration, verification


def _authenticate() -> dict[str, object]:
    program_state, binding, evidence, declaration, verification = _fixture()
    return authenticate_program_evidence_origin_binding(
        program_state=program_state,
        program_evidence_binding=binding,
        evidence_bytes=evidence,
        origin_declaration_bytes=declaration,
        origin_verification_decision_bytes=verification,
    )


def test_authenticates_exact_program_membership_and_origin_identity() -> None:
    result = _authenticate()
    assert result["schema_version"] == "1.0"
    assert result["origin_class"] == "empirical_measurement"
    assert result["verified_program_state_membership_established"] is True
    assert result["exact_evidence_identity_joined"] is True
    assert result["origin_classification_record_authenticated"] is True
    origin = result["evidence_origin_binding"]
    assert isinstance(origin, dict)
    assert origin["origin_classification_domain_verified"] is True


@pytest.mark.parametrize(
    "field",
    [
        "program_state_provenance_reauthenticated",
        "physical_origin_truth_authenticated",
        "verifier_identity_or_credential_authenticated",
        "scientific_result_validity_authenticated",
        "support_independence_established",
        "empirical_authority_granted",
        "scientific_status_changed",
        "execution_authorized",
        "positive_closeout_granted",
    ],
)
def test_bridge_never_overclaims_authority(field: str) -> None:
    result = _authenticate()
    assert result[field] is False


def test_rejects_evidence_bytes_not_matching_program_binding() -> None:
    program_state, binding, _evidence, declaration, verification = _fixture()
    with pytest.raises(ProgramEvidenceOriginBindingError, match="exact evidence bytes"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=binding,
            evidence_bytes=b"different-bytes",
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_rejects_program_binding_absent_from_verified_state() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    missing = dict(binding)
    missing["role"] = "not-present"
    with pytest.raises(ProgramEvidenceOriginBindingError, match="not present"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=missing,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_rejects_unknown_authority_field_on_program_binding() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    poisoned: dict[str, object] = dict(binding)
    poisoned["empirical_authority_granted"] = True
    with pytest.raises(ProgramEvidenceOriginBindingError, match="unknown keys"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=poisoned,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_rejects_duplicate_program_workstream_identity() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    workstreams = program_state["workstreams"]
    assert isinstance(workstreams, list)
    workstreams.append(copy.deepcopy(workstreams[0]))
    with pytest.raises(ProgramEvidenceOriginBindingError, match="duplicate normalized workstream_id"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=binding,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_rejects_duplicate_program_evidence_role_sha_identity() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    workstreams = program_state["workstreams"]
    assert isinstance(workstreams, list)
    first = workstreams[0]
    assert isinstance(first, dict)
    planning = first["planning_state"]
    assert isinstance(planning, dict)
    evidence_bindings = planning["evidence_bindings"]
    assert isinstance(evidence_bindings, list)
    evidence_bindings.append(dict(binding))
    with pytest.raises(ProgramEvidenceOriginBindingError, match="duplicate evidence role/SHA"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=binding,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_rejects_origin_verification_substitution() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    value = json.loads(verification)
    value["origin_class"] = "analysis_output"
    tampered = _bytes(value)
    with pytest.raises(
        ProgramEvidenceOriginBindingError,
        match="evidence-origin classification could not be authenticated",
    ):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=binding,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=tampered,
        )


def test_program_binding_digest_must_be_canonical_sha256() -> None:
    program_state, binding, evidence, declaration, verification = _fixture()
    binding["sha256"] = binding["sha256"].upper()
    with pytest.raises(ProgramEvidenceOriginBindingError, match="lowercase SHA-256"):
        authenticate_program_evidence_origin_binding(
            program_state=program_state,
            program_evidence_binding=binding,
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )
