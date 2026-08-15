from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    old = '''    result: dict[str, Any] = {"sha256": _lineage_sha256(value, "sha256")}
    if "role" in value:
        result["role"] = _lineage_identity(value, "role")
    authoritative = value.get("source_path_authoritative")
    if authoritative is not None:
        if authoritative is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.source_path_authoritative must remain false"
            )
        result["source_path_authoritative"] = False
    size_bytes = value.get("size_bytes")
    if size_bytes is not None:
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.size_bytes must be a non-negative integer"
            )
        result["size_bytes"] = size_bytes
    return result
'''
    new = '''    result: dict[str, Any] = {"sha256": _lineage_sha256(value, "sha256")}
    if "role" in value:
        result["role"] = _lineage_identity(value, "role")
    # Paths, source-path annotations, and size are rebundling metadata rather than
    # graph-hop identity. Validate them when present, but compare authority identity
    # only by exact checksum and role so a portable re-snapshot remains equivalent.
    authoritative = value.get("source_path_authoritative")
    if authoritative is not None and authoritative is not False:
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.source_path_authoritative must remain false"
        )
    size_bytes = value.get("size_bytes")
    if size_bytes is not None and (
        not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.size_bytes must be a non-negative integer"
        )
    return result
'''
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"metadata identity fix anchor count={count}")
    SOURCE.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
