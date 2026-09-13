from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/materials_data_analyzer/research_loop/public_data_acquisition.py"
TEST = ROOT / "tests/test_public_data_acquisition_transport_errors.py"

source = SOURCE.read_text(encoding="utf-8")
old = '''            content_length = response.headers.get("Content-Length")\n            if content_length is not None:\n                try:\n                    declared_length = int(content_length)\n'''
new = '''            content_length = response.headers.get("Content-Length")\n            declared_length: int | None = None\n            if content_length is not None:\n                try:\n                    declared_length = int(content_length)\n'''
if old not in source:
    raise RuntimeError("Content-Length parser anchor not found")
source = source.replace(old, new, 1)

old = '''                chunks.append(chunk)\n            body = b"".join(chunks)\n            content_type = response.headers.get("Content-Type")\n'''
new = '''                chunks.append(chunk)\n            if declared_length is not None and observed < declared_length:\n                raise PublicAcquisitionTransportError(\n                    "HTTP response ended before declared Content-Length "\n                    f"({observed} < {declared_length})"\n                )\n            body = b"".join(chunks)\n            content_type = response.headers.get("Content-Type")\n'''
if old not in source:
    raise RuntimeError("read-loop completion anchor not found")
source = source.replace(old, new, 1)
SOURCE.write_text(source, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
anchor = '''\ndef test_incomplete_chunk_read_is_transport_failure(\n'''
regression = '''\ndef test_premature_eof_before_declared_content_length_is_transport_failure(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    monkeypatch.setattr(\n        acquisition,\n        "build_opener",\n        lambda *_: _StaticOpener(\n            _Response(\n                status=200,\n                headers={"Content-Length": "12"},\n                body=b"short",\n            )\n        ),\n    )\n\n    with pytest.raises(\n        PublicAcquisitionTransportError,\n        match=r"ended before declared Content-Length \\(5 < 12\\)",\n    ):\n        fetch_https_bytes(\n            "https://data.example.org/example.bin",\n            allowed_hosts=["data.example.org"],\n            max_bytes=1024,\n        )\n\n\ndef test_exact_declared_content_length_still_succeeds(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    body = b"exact-length"\n    monkeypatch.setattr(\n        acquisition,\n        "build_opener",\n        lambda *_: _StaticOpener(\n            _Response(\n                status=200,\n                headers={"Content-Length": str(len(body))},\n                body=body,\n            )\n        ),\n    )\n\n    result = fetch_https_bytes(\n        "https://data.example.org/example.bin",\n        allowed_hosts=["data.example.org"],\n        max_bytes=1024,\n    )\n\n    assert result.body == body\n\n'''
if "test_premature_eof_before_declared_content_length_is_transport_failure" not in test:
    if anchor not in test:
        raise RuntimeError("transport regression insertion anchor not found")
    test = test.replace(anchor, regression + anchor, 1)
TEST.write_text(test, encoding="utf-8")
