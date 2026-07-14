from pathlib import Path


def test_stdlib_platform_import_unaffected():
    import platform

    assert platform.python_implementation() in {"CPython", "PyPy"}
    assert not Path("src/platform").exists()


def test_pandas_import_still_succeeds():
    import pandas as pd

    assert hasattr(pd, "DataFrame")
