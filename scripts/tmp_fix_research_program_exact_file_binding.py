from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/research_program.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")

old = '''def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ResearchProgramError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchProgramError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
'''
new = '''def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Read, parse, and hash one immutable byte snapshot of a bound JSON file."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ResearchProgramError(f"could not read exact JSON snapshot: {path}") from exc
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchProgramError(f"{path} must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ResearchProgramError(f"JSON root must be an object: {path}")
    return value, hashlib.sha256(raw).hexdigest()
'''
text = replace_once(text, old, new, "snapshot-loader")

old = '''    resolved = path.expanduser().resolve(strict=True)
    raw = _load_json(resolved)
    context = _require_exact_keys(
'''
new = '''    resolved = path.expanduser().resolve(strict=True)
    raw, snapshot_sha256 = _load_json_snapshot(resolved)
    context = _require_exact_keys(
'''
text = replace_once(text, old, new, "runtime-context-read")

old = '''    return {"schema_version": "1.0", "workstreams": normalized}, {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
    }
'''
new = '''    return {"schema_version": "1.0", "workstreams": normalized}, {
        "path": str(resolved),
        "sha256": snapshot_sha256,
    }
'''
text = replace_once(text, old, new, "runtime-context-binding")

old = '''    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    mission = validate_research_mission(_load_json(mission_file))
    context_file = (
'''
new = '''    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    mission_raw, mission_sha256 = _load_json_snapshot(mission_file)
    mission = validate_research_mission(mission_raw)
    context_file = (
'''
text = replace_once(text, old, new, "mission-read")

old = '''        "mission_binding": {
            "path": str(mission_file),
            "sha256": _sha256_file(mission_file),
        },
'''
new = '''        "mission_binding": {
            "path": str(mission_file),
            "sha256": mission_sha256,
        },
'''
text = replace_once(text, old, new, "mission-binding")

old = '''    path = Path(proposal_path).expanduser().resolve(strict=True)
    result = validate_reasoning_proposal(_load_json(path), program_state)
    return {
        **result,
        "proposal_binding": {"path": str(path), "sha256": _sha256_file(path)},
    }
'''
new = '''    path = Path(proposal_path).expanduser().resolve(strict=True)
    proposal_raw, proposal_sha256 = _load_json_snapshot(path)
    result = validate_reasoning_proposal(proposal_raw, program_state)
    return {
        **result,
        "proposal_binding": {"path": str(path), "sha256": proposal_sha256},
    }
'''
text = replace_once(text, old, new, "proposal-binding")

if "_load_json(" in text or "_sha256_file(" in text:
    raise SystemExit("legacy separate-read helpers remain")

SOURCE.write_text(text, encoding="utf-8")
