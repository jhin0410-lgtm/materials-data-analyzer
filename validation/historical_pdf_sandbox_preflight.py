"""Fail closed unless the historical parser's sandbox is actually in effect.

This stdlib-only probe runs before the vulnerable parser is installed or loaded.
It neither changes host security settings nor permits an unsandboxed fallback.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import resource
import socket
from pathlib import Path


def verify_sandbox(host_netns: int) -> dict:
    isolated_netns = os.stat("/proc/self/ns/net").st_ino
    if isolated_netns == host_netns:
        raise RuntimeError("historical sandbox did not isolate the network namespace")

    limits = {}
    for name, kind, maximum in (
        ("address_space", resource.RLIMIT_AS, 1610612736),
        ("cpu", resource.RLIMIT_CPU, 90),
        ("open_files", resource.RLIMIT_NOFILE, 256),
    ):
        soft, hard = resource.getrlimit(kind)
        if not (0 < soft <= maximum and 0 < hard <= maximum):
            raise RuntimeError(f"historical sandbox {name} limit is missing or too large")
        limits[name] = [soft, hard]

    source = Path(__file__).resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise RuntimeError("historical sandbox source filesystem is not read-only")
    try:
        descriptor = os.open(source, os.O_WRONLY)
    except OSError as exc:
        # A read-only mount is already independently confirmed by statvfs.
        # Docker can return EACCES/EPERM rather than EROFS on a denied write,
        # especially when capabilities are dropped.  Never accept a write.
        if exc.errno not in {errno.EROFS, errno.EACCES, errno.EPERM}:
            raise RuntimeError("source write was denied for an unexpected reason") from exc
    else:
        os.close(descriptor)  # No write or truncate is performed, even on failure.
        raise RuntimeError("historical sandbox allowed source write access")

    # UDP connect checks routing without sending payload or using DNS.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        try:
            connection.connect(("192.0.2.1", 9))
        except OSError as exc:
            if exc.errno != errno.ENETUNREACH:
                raise RuntimeError("network probe did not establish a missing external route") from exc
        else:
            raise RuntimeError("historical sandbox has an external route")
    return {"isolated_netns": isolated_netns, "source_read_only": True, "limits": limits}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-netns", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_sandbox(args.host_netns), sort_keys=True))
