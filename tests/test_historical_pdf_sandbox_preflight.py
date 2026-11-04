from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "posix" or not Path("/proc/self/ns/net").exists(),
                    reason="Linux network namespace preflight")
def test_preflight_rejects_host_network_namespace() -> None:
    path = Path(__file__).resolve().parents[1] / "validation/historical_pdf_sandbox_preflight.py"
    spec = importlib.util.spec_from_file_location("pdf_sandbox_preflight", path)
    assert spec is not None and spec.loader is not None
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)
    with pytest.raises(RuntimeError, match="did not isolate the network namespace"):
        preflight.verify_sandbox(os.stat("/proc/self/ns/net").st_ino)
