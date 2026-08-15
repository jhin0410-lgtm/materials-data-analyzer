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
if "from .evidence_origin_binding import" not in text:
    text = replace_once(
        text,
        '''from typing import Any

from .input_evidence_origin_request import (
''',
        '''from typing import Any

from .evidence_origin_binding import (
    EvidenceOriginBindingError,
    authenticate_evidence_origin_binding,
)
from .input_evidence_origin_request import (
''',
        "origin-binding-import",
    )
if "authenticated request changed the exact request bytes" not in text:
    text = replace_once(
        text,
        '''    report_items = authenticated.report.get("items")
''',
        '''    if authenticated.request_bytes != request_bytes:
        raise InputEvidenceOriginPackError(
            "authenticated request changed the exact request bytes"
        )

    report_items = authenticated.report.get("items")
''',
        "request-byte-crosscheck",
    )
if "authenticated request origin_class diverged from exact origin bytes" not in text:
    old = '''        origin_class = report_item.get("origin_class")
        if origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackError(
                "authenticated request returned unsupported origin_class"
            )
        manifest_items.append(
'''
    new = '''        origin_class = report_item.get("origin_class")
        if origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackError(
                "authenticated request returned unsupported origin_class"
            )
        try:
            recomputed_origin = authenticate_evidence_origin_binding(
                evidence_bytes=payload.evidence_bytes,
                origin_declaration_bytes=payload.origin_declaration_bytes,
                origin_verification_decision_bytes=(
                    payload.origin_verification_decision_bytes
                ),
            )
        except EvidenceOriginBindingError as exc:
            raise InputEvidenceOriginPackError(
                "authenticated request payload origin bytes failed independent cross-check"
            ) from exc
        if recomputed_origin["origin_class"] != origin_class:
            raise InputEvidenceOriginPackError(
                "authenticated request origin_class diverged from exact origin bytes"
            )
        if recomputed_origin["evidence_artifact_sha256"] != payload.evidence_sha256:
            raise InputEvidenceOriginPackError(
                "authenticated request origin binding evidence SHA diverged from payload"
            )
        manifest_items.append(
'''
    text = replace_once(text, old, new, "origin-byte-crosscheck")
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_rejects_authenticator_request_byte_substitution" not in tests:
    tests += r'''


def test_rejects_authenticator_request_byte_substitution(monkeypatch, tmp_path: Path) -> None:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    evidence = (root / "evidence.bin").read_bytes()
    declaration = (root / "origin-declaration.json").read_bytes()
    verification = (root / "origin-verification.json").read_bytes()
    fake = SimpleNamespace(
        request_bytes=request_bytes + b" ",
        report={
            "items": [
                {
                    "program_evidence_binding": dict(bindings[0]),
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
    with pytest.raises(InputEvidenceOriginPackError, match="changed the exact request bytes"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )


def test_rejects_authenticator_origin_class_report_payload_mismatch(monkeypatch, tmp_path: Path) -> None:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    evidence = (root / "evidence.bin").read_bytes()
    declaration = (root / "origin-declaration.json").read_bytes()
    verification = (root / "origin-verification.json").read_bytes()
    fake = SimpleNamespace(
        request_bytes=request_bytes,
        report={
            "items": [
                {
                    "program_evidence_binding": dict(bindings[0]),
                    "origin_class": "analysis_output",
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
    with pytest.raises(InputEvidenceOriginPackError, match="origin_class diverged"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )
'''
TESTS.write_text(tests, encoding="utf-8")
