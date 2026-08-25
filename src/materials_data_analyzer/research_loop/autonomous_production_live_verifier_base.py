"""Non-executable loader for the preserved reviewed live-verifier base implementation.

The reviewed source is stored as package data rather than as an independently executable Python
module. Importers receive that implementation module transparently; direct ``python -m`` use of
this compatibility loader fails closed so it cannot bypass the public semantic-hardening entrypoint.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

if __name__ == "__main__":
    print(
        "autonomous_production_live_verifier_base is not an executable verifier; "
        "use materials_data_analyzer.research_loop.autonomous_production_live_verifier",
        file=sys.stderr,
    )
    raise SystemExit(2)

_STORAGE_PATH = Path(__file__).with_name("autonomous_production_live_verifier_base.inc")
_STORAGE_NAME = f"{__package__}._autonomous_production_live_verifier_base_storage"
_LOADER = importlib.machinery.SourceFileLoader(_STORAGE_NAME, str(_STORAGE_PATH))
_SPEC = importlib.util.spec_from_loader(_STORAGE_NAME, _LOADER)
if _SPEC is None:
    raise ImportError("cannot construct preserved live-verifier base implementation spec")
_STORAGE = importlib.util.module_from_spec(_SPEC)
sys.modules[_STORAGE_NAME] = _STORAGE
_LOADER.exec_module(_STORAGE)
sys.modules[__name__] = _STORAGE
