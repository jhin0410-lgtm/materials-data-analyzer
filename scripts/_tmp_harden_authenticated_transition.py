from __future__ import annotations

from pathlib import Path

TARGET = Path(
    "src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py"
)


def replace_function_block(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[:start_index] + replacement.rstrip() + "\n\n\n" + text[end_index:]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = text.replace(
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.2"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.3"',
    )

    lineage = '''def _remap_authenticated_lineage_artifacts(
    metadata: dict[str, Any],
    *,
    artifact_root: Path,
    payloads: dict[str, bytes],
) -> None:
    raw_lineage = metadata.get("authenticated_transition_lineage", [])
    if not isinstance(raw_lineage, list):
        raise AuthenticatedEpistemicTransitionError(
            "base graph metadata.authenticated_transition_lineage must be a list"
        )
    remapped: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_lineage):
        if not isinstance(raw_record, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] must be an object"
            )
        record = copy.deepcopy(dict(raw_record))
        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].schema_version must be "
                f"{AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION}"
            )
        binding = record.get("authenticated_inference_binding")
        if not isinstance(binding, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].authenticated_inference_binding "
                "must be an object"
            )
        record_transition_id = _lineage_identity(record, "transition_id")
        if str(binding.get("transition_id", "")).strip() != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] transition identity is inconsistent"
            )
        if record.get("scientific_authority_applied") is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].scientific_authority_applied "
                "must be false for producer lineage"
            )
        for name in (
            "base_graph_artifact",
            "proposal_artifact",
            "verification_decision_artifact",
        ):
            raw_binding = record.get(name)
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    f"authenticated_transition_lineage[{index}].{name} must be an object"
                )
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"authenticated_transition_lineage[{index}].{name}.path",
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                f"{name}{_safe_suffix(suffix_source)}",
            )
            record[name] = _snapshot_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"authenticated_transition_lineage[{index}].{name}",
                payloads=payloads,
            )
        raw_results = record.get("result_artifact_snapshots")
        if not isinstance(raw_results, list):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].result_artifact_snapshots must be a list"
            )
        result_records: list[dict[str, Any]] = []
        for result_index, raw_binding in enumerate(raw_results):
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    "authenticated lineage result artifact snapshot must be an object"
                )
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=(
                    f"authenticated_transition_lineage[{index}]"
                    f".result_artifact_snapshots[{result_index}].path"
                ),
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                "result_artifacts",
                f"result-{result_index:03d}{_safe_suffix(suffix_source)}",
            )
            result_records.append(
                _snapshot_lineage_binding(
                    raw_binding,
                    artifact_root=artifact_root,
                    bundle_path=relative,
                    field=(
                        f"authenticated_transition_lineage[{index}]"
                        f".result_artifact_snapshots[{result_index}]"
                    ),
                    payloads=payloads,
                )
            )
        record["result_artifact_snapshots"] = result_records
        remapped.append(record)
    metadata["authenticated_transition_lineage"] = remapped
'''
    text = replace_function_block(
        text,
        "def _remap_authenticated_lineage_artifacts(",
        "def _remap_base_graph_artifacts(",
        lineage,
    )

    staged = '''def _is_reparse_point(info: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(marker and (getattr(info, "st_file_attributes", 0) & marker))


def _read_fd_bytes(fd: int, *, field: str) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must be a regular staged file"
        )
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _read_staged_regular_file_posix(
    root: Path, relative: Path, *, field: str
) -> bytes:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    current_fd = root_fd
    try:
        for component in relative.parts[:-1]:
            try:
                next_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=current_fd,
                )
            except OSError as exc:
                raise AuthenticatedEpistemicTransitionError(
                    f"{field} contains an unsafe staged parent component"
                ) from exc
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        try:
            fd = os.open(relative.name, file_flags, dir_fd=current_fd)
        except OSError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} could not be opened as a no-follow staged file"
            ) from exc
        try:
            return _read_fd_bytes(fd, field=field)
        finally:
            os.close(fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _read_staged_regular_file_portable(
    root: Path, relative: Path, *, field: str
) -> bytes:
    current = root
    try:
        root_info = os.lstat(root)
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root could not be inspected"
        ) from exc
    if stat.S_ISLNK(root_info.st_mode) or _is_reparse_point(root_info):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root must not be a link or reparse point"
        )
    if not stat.S_ISDIR(root_info.st_mode):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root must be a directory"
        )
    for index, component in enumerate(relative.parts):
        current = current / component
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged path could not be inspected"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged path must not contain links or reparse points"
            )
        is_last = index == len(relative.parts) - 1
        if not is_last and not stat.S_ISDIR(info.st_mode):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged parent must be a directory"
            )
        if is_last and not stat.S_ISREG(info.st_mode):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} must be a regular staged file"
            )
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(current, flags)
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staged file could not be opened"
        ) from exc
    try:
        return _read_fd_bytes(fd, field=field)
    finally:
        os.close(fd)


def _read_staged_regular_file(root: Path, relative: str, *, field: str) -> bytes:
    """Read one staged file without accepting linked path components."""
    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must use a normalized bundle-relative staged path"
        )
    if (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
    ):
        return _read_staged_regular_file_posix(root, relative_path, field=field)
    return _read_staged_regular_file_portable(root, relative_path, field=field)
'''
    text = replace_function_block(
        text,
        "def _read_staged_regular_file(",
        "def _validate_written_payloads(",
        staged,
    )
    TARGET.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
