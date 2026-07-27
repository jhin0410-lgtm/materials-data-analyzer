"""Check a public checkout for likely committed secrets and forbidden files."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_BASENAMES = {
    ".env",
    "kaggle.json",
    "secrets.toml",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".pfx"}
BINARY_SUFFIXES = {
    ".7z",
    ".db",
    ".dll",
    ".exe",
    ".feather",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mat",
    ".npy",
    ".npz",
    ".parquet",
    ".pdf",
    ".pickle",
    ".pkl",
    ".png",
    ".so",
    ".sqlite",
    ".tar",
    ".tif",
    ".tiff",
    ".xls",
    ".xlsx",
    ".zip",
}
SECRET_PATTERNS = (
    (
        "private_key_header",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "openai_style_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    (
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ),
)


def tracked_files(project_root: Path = PROJECT_ROOT) -> list[Path]:
    """Return tracked repository files from git without scanning local outputs."""
    completed = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {message}")
    return [
        project_root / item.decode(errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def scan_repository(project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return sanitized findings without printing any matched secret value."""
    findings: list[str] = []
    for path in tracked_files(project_root):
        relative = path.relative_to(project_root)
        if path.name in FORBIDDEN_BASENAMES:
            findings.append(f"forbidden tracked file: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"forbidden sensitive suffix: {relative}")
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue

        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        for pattern_name, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            findings.append(
                f"likely {pattern_name}: {relative}:{line_number}"
            )
    return sorted(set(findings))


def main() -> int:
    findings = scan_repository()
    if findings:
        print("Public repository hygiene check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Public repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
