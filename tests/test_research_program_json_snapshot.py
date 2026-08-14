from __future__ import annotations

import hashlib
from pathlib import Path

from materials_data_analyzer.research_program_cli import _load_json_object


def test_research_program_graph_loader_hashes_the_same_single_byte_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "graph.json"
    raw = b'{"schema_version":"1.0"}\n'
    path.write_bytes(raw)
    real_read_bytes = Path.read_bytes
    reads = 0

    def counted_read_bytes(candidate: Path) -> bytes:
        nonlocal reads
        if candidate.resolve() == path.resolve():
            reads += 1
        return real_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    value, resolved, digest = _load_json_object(path)

    assert value == {"schema_version": "1.0"}
    assert resolved == path.resolve()
    assert digest == hashlib.sha256(raw).hexdigest()
    assert reads == 1
