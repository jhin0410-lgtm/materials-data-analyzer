from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/acquisition_record_binding.py")
TESTS = Path("tests/test_acquisition_record_binding.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")
old = '''    missing = sorted(_REQUIRED_CLAIMS - names)
    if missing:
        raise AcquisitionRecordBindingError(
            "manifest_claim_bindings are missing required recorded-provenance claims: "
            + ", ".join(missing)
        )
    return result
'''
new = '''    missing = sorted(_REQUIRED_CLAIMS - names)
    if missing:
        raise AcquisitionRecordBindingError(
            "manifest_claim_bindings are missing required recorded-provenance claims: "
            + ", ".join(missing)
        )
    by_name = {item["claim"]: item for item in result}
    for claim_name in (
        "source_system",
        "source_version",
        "retrieval_endpoint",
        "retrieval_status",
    ):
        if not isinstance(by_name[claim_name]["expected_value"], str):
            raise AcquisitionRecordBindingError(
                f"required manifest claim {claim_name!r} must declare a text value"
            )
    if not isinstance(by_name["network_performed"]["expected_value"], bool):
        raise AcquisitionRecordBindingError(
            "required manifest claim 'network_performed' must declare a boolean value"
        )
    return result
'''
text = replace_once(text, old, new, "semantic-required-claim-types")
old = '''    limitations = _string_list(
        declaration["limitations"], "acquisition declaration limitations"
    )
'''
new = '''    limitations = _string_list(
        declaration["limitations"], "acquisition declaration limitations"
    )
    if not limitations:
        raise AcquisitionRecordBindingError(
            "acquisition declaration limitations must be non-empty"
        )
'''
text = replace_once(text, old, new, "required-limitations")
old = '''        "recorded_acquisition_provenance_authenticated": True,
        "source_identity_or_credential_authenticated": False,
'''
new = '''        "recorded_acquisition_provenance_authenticated": True,
        "historical_acquisition_event_authenticated": False,
        "acquisition_manifest_authorship_authenticated": False,
        "source_identity_or_credential_authenticated": False,
'''
text = replace_once(text, old, new, "historical-event-boundary")
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_rejects_non_text_required_source_claims" not in tests:
    tests += r'''


@pytest.mark.parametrize(
    "claim_name,bad_value",
    [
        ("source_system", 1),
        ("source_version", True),
        ("retrieval_endpoint", None),
        ("retrieval_status", 1),
    ],
)
def test_rejects_non_text_required_source_claims(
    claim_name: str,
    bad_value: object,
) -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    declaration = json.loads(declaration_bytes)
    target = next(
        item
        for item in declaration["manifest_claim_bindings"]
        if item["claim"] == claim_name
    )
    target["expected_value"] = bad_value
    manifest_pointer_key = target["json_pointer"].removeprefix("/")
    manifest[manifest_pointer_key] = bad_value
    rewritten_manifest = _json_bytes(manifest)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="must declare a text value"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_non_boolean_required_network_claim() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    declaration = json.loads(declaration_bytes)
    target = next(
        item
        for item in declaration["manifest_claim_bindings"]
        if item["claim"] == "network_performed"
    )
    target["expected_value"] = 1
    manifest["network_called"] = 1
    rewritten_manifest = _json_bytes(manifest)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="must declare a boolean value"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_requires_explicit_nonempty_limitations() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["limitations"] = []
    with pytest.raises(AcquisitionRecordBindingError, match="limitations must be non-empty"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_reports_historical_and_authorship_boundaries() -> None:
    evidence, manifest, declaration = _fixture()
    report = authenticate_acquisition_record_binding(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
    )
    assert report["historical_acquisition_event_authenticated"] is False
    assert report["acquisition_manifest_authorship_authenticated"] is False
'''
TESTS.write_text(tests, encoding="utf-8")
