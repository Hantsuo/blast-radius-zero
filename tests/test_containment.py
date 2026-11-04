"""Containment proof: the sandbox absorbs the blast, the host does not.

Run directly:  python tests/test_containment.py
Or with pytest: pytest -q tests/test_containment.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sandbox  # noqa: E402

SENTINEL = "sentinel-do-not-delete.txt"


def _sentinel() -> Path:
    path = Path(tempfile.gettempdir()) / SENTINEL
    path.write_text("host file, must survive", encoding="utf-8")
    return path


def test_host_survives_rm_rf() -> None:
    host_file = _sentinel()
    code = """
import os, shutil, pathlib
shutil.rmtree('/work', ignore_errors=True)
for target in ('/etc/passwd', '/'):
    try:
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        else:
            os.remove(target)
        print('DELETED', target)
    except Exception as exc:
        print('BLOCKED', target, type(exc).__name__)
print('still alive')
"""
    result = sandbox.run_python(code)
    assert host_file.exists(), "host sentinel was deleted by the sandbox"
    assert "still alive" in result.stdout
    assert "DELETED /etc/passwd" not in result.stdout, "read-only root filesystem was writable"
    print("PASS host_survives_rm_rf", result.duration_ms, "ms")


def test_timeout_kills_infinite_loop() -> None:
    started = time.perf_counter()
    result = sandbox.run_python("while True:\n    pass\n", timeout=3)
    elapsed = time.perf_counter() - started
    assert result.timed_out, "infinite loop was not stopped"
    assert result.killed, "container was not killed"
    assert elapsed < 20, f"took {elapsed:.1f}s, wall clock is not enforced"
    print("PASS timeout_kills_infinite_loop", f"{elapsed:.1f}s")


def test_network_is_blocked() -> None:
    code = """
import socket
try:
    socket.create_connection(('1.1.1.1', 53), timeout=3)
    print('NETWORK OPEN')
except Exception as exc:
    print('NETWORK BLOCKED', type(exc).__name__)
"""
    result = sandbox.run_python(code)
    assert "NETWORK BLOCKED" in result.stdout, result.stdout + result.stderr
    print("PASS network_is_blocked")


def test_secrets_do_not_leak_in() -> None:
    os.environ["SANDBOX_SENTINEL_SECRET"] = "must-not-appear"
    try:
        code = "import os; print('LEAK' if 'SANDBOX_SENTINEL_SECRET' in os.environ else 'CLEAN')"
        result = sandbox.run_python(code)
        assert "CLEAN" in result.stdout, "host environment leaked into the sandbox"
        print("PASS secrets_do_not_leak_in")
    finally:
        os.environ.pop("SANDBOX_SENTINEL_SECRET", None)


if __name__ == "__main__":
    test_host_survives_rm_rf()
    test_timeout_kills_infinite_loop()
    test_network_is_blocked()
    test_secrets_do_not_leak_in()
    print("\nall containment checks passed")
