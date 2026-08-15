from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/input_evidence_origin_pack.py")
TESTS = Path("tests/test_input_evidence_origin_pack.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")
text = replace_once(
    text,
    '                "program_evidence_binding": dict(program_binding),\n',
    '                "program_evidence_binding": {\n'
    '                    "workstream_id": payload.workstream_id,\n'
    '                    "role": payload.role,\n'
    '                    "sha256": payload.evidence_sha256,\n'
    '                },\n',
    "reconstruct-program-binding",
)
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
tests += r'''


def test_reconstructs_manifest_program_binding_from_exact_payload(monkeypatch, tmp_path: Path) -> None:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    evidence = (root / "evidence.bin").read_bytes()
    declaration = (root / "origin-declaration.json").read_bytes()
    verification = (root / "origin-verification.json").read_bytes()
    report_binding = {**bindings[0], "credential_verified": True}
    fake = SimpleNamespace(
        request_bytes=request_bytes,
        report={
            "items": [
                {
                    "program_evidence_binding": report_binding,
                    "origin_class": "empirical_measurement",
                }
            ]
        },
        payloads=(
            InputEvidenceOriginPayload(
                workstream_id="ws-1",
                role="measurement",
                evidence_sha256=hashlib.sha256(evidence).hexdigest(),
                evidence_bytes=evidence,
                origin_declaration_bytes=declaration,
                origin_verification_decision_bytes=verification,
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "authenticate_input_evidence_origin_request",
        lambda **kwargs: fake,
    )
    output = tmp_path / "pack"
    publish_input_evidence_origin_pack(
        request_path=request,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        output_dir=output,
    )
    manifest = json.loads((output / "input_evidence_origin_pack_manifest.json").read_bytes())
    assert manifest["items"][0]["program_evidence_binding"] == bindings[0]
    assert "credential_verified" not in manifest["items"][0]["program_evidence_binding"]
'''
TESTS.write_text(tests, encoding="utf-8")
