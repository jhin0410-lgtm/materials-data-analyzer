"""Installed console entry point for the stable analysis CLI."""

from __future__ import annotations

from process_data import main as _legacy_main


def main() -> None:
    """Run the existing user-facing analyzer without changing its CLI contract."""
    _legacy_main()


if __name__ == "__main__":
    main()
