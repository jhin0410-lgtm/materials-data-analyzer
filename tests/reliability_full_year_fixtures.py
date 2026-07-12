"""Synthetic fixtures for Reliability v1.5.3 full-year audit tests."""

from __future__ import annotations

import zipfile
from pathlib import Path


HEADER = "date,serial_number,model,capacity_bytes,failure,smart_5_raw,smart_5_normalized\n"


def write_synthetic_backblaze_zip(path: Path) -> Path:
    """Create a tiny Backblaze-like ZIP with metadata artifacts."""
    rows = {
        "2013/2020-01-01.csv": [
            "2020-01-01,A,M1,100,0,1,100",
            "2020-01-01,B,M1,100,0,0,100",
            "2020-01-01,C,M1,100,0,0,100",
            "2020-01-01,E,M1,100,0,0,100",
            "2020-01-01,F,M1,100,0,0,100",
            "2020-01-01,F,M1,100,0,0,100",
        ],
        "2013/2020-01-02.csv": [
            "2020-01-02,A,M1,100,1,9,90",
            "2020-01-02,B,M1,100,0,0,100",
            "2020-01-02,E,M2,100,0,0,100",
        ],
        "2013/2020-01-03.csv": [
            "2020-01-03,A,M1,100,0,10,80",
            "2020-01-03,B,M1,100,0,0,100",
            "2020-01-03,D,M1,100,0,0,100",
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        for member, member_rows in rows.items():
            archive.writestr(member, HEADER + "\n".join(member_rows) + "\n")
        archive.writestr("__MACOSX/2013/._2020-01-01.csv", "metadata")
        archive.writestr("2013/.DS_Store", "metadata")
        archive.writestr("2013/not_daily.csv", HEADER)
    return path
