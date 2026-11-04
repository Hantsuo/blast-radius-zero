"""Collect real sandbox traces into a dataset file.

Each row is one execution: the code we sent, what the sandbox returned, and
whether the host stayed intact. Nothing here is synthetic — the stdout/stderr,
exit codes and durations are exactly what the container produced.

    python tools/collect_traces.py            # writes data/traces.jsonl
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import sandbox  # noqa: E402

CASES = [
    # (id, label, category, code, expected_behaviour)
    ("benign_sum", "Sum a CSV column", "benign", """
import csv, io
raw = "a,b\\n1,2\\n3,4\\n"
rows = list(csv.DictReader(io.StringIO(raw)))
print("sum_b", sum(int(r["b"]) for r in rows))
"""),
    ("benign_json", "Parse and reshape JSON", "benign", """
import json
data = {"items": [{"n": 1}, {"n": 2}]}
print(json.dumps({"total": sum(i["n"] for i in data["items"])}))
"""),
    ("benign_math", "Numeric sanity check", "benign", """
import statistics
print(round(statistics.mean([1, 2, 3, 4, 5]), 3))
"""),
    ("attack_rm_rf_root", "Delete the root filesystem", "destructive", """
import os, shutil
for target in ("/etc/passwd", "/usr", "/"):
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        print("DELETED", target)
    except Exception as exc:
        print("BLOCKED", target, type(exc).__name__, str(exc)[:60])
print("still alive")
"""),
    ("attack_write_root", "Write outside the workdir", "destructive", """
try:
    open("/etc/pwned", "w").write("x")
    print("WROTE /etc/pwned")
except Exception as exc:
    print("BLOCKED", type(exc).__name__, str(exc)[:60])
"""),
    ("attack_fork_bomb", "Fork bomb", "resource", """
import os
while True:
    try:
        os.fork()
    except Exception as exc:
        print("BLOCKED fork", type(exc).__name__)
        break
"""),
    ("attack_infinite_loop", "Busy loop until the wall clock", "resource", """
while True:
    pass
"""),
    ("attack_memory_bomb", "Allocate past the memory cap", "resource", """
chunks = []
try:
    for _ in range(400):
        chunks.append(bytearray(8 * 1024 * 1024))
    print("ALLOCATED", len(chunks) * 8, "MB")
except MemoryError:
    print("BLOCKED MemoryError")
"""),
    ("attack_network_probe", "Open an outbound connection", "network", """
import socket
try:
    socket.create_connection(("1.1.1.1", 53), timeout=3)
    print("NETWORK OPEN")
except Exception as exc:
    print("BLOCKED", type(exc).__name__, str(exc)[:60])
"""),
    ("attack_http_exfil", "Try to exfiltrate over HTTP", "network", """
import urllib.request
try:
    urllib.request.urlopen("http://example.com", timeout=3)
    print("EXFIL OK")
except Exception as exc:
    print("BLOCKED", type(exc).__name__, str(exc)[:60])
"""),
    ("attack_env_leak", "Read the host environment", "secrets", """
import os
print("LEAK" if any(k in os.environ for k in ("VULTR_INFERENCE_API_KEY", "AWS_SECRET_ACCESS_KEY")) else "CLEAN")
print(sorted(os.environ)[:6])
"""),
    ("attack_proc_scan", "Look for host processes", "informational", """
import os
pids = [p for p in os.listdir("/proc") if p.isdigit()]
print("VISIBLE_PIDS", len(pids))
"""),
]


def is_contained(category: str, exit_code, timed_out: bool, stdout: str) -> bool | None:
    """Whether the sandbox absorbed the case without touching the host."""
    if category == "informational":
        return None
    if timed_out:
        return True                      # wall clock fired, container killed
    if exit_code in (137, 139):
        return True                      # SIGKILL / SIGSEGV inside the box only
    if "BLOCKED" in stdout or "CLEAN" in stdout:
        return True
    if category == "benign":
        return exit_code == 0
    return False


def main() -> None:
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    rows = []
    for case_id, label, category, code, *_ in CASES:
        started = time.perf_counter()
        timeout = 6 if category == "resource" else sandbox.WALL_TIMEOUT
        result = sandbox.run_python(code, timeout=timeout)
        wall_ms = int((time.perf_counter() - started) * 1000)
        rows.append(
            {
                "id": case_id,
                "label": label,
                "category": category,
                "code": code.strip(),
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()[:800],
                "duration_ms": result.duration_ms,
                "wall_ms": wall_ms,
                "contained": is_contained(category, result.exit_code, result.timed_out, result.stdout),
                "isolation": {
                    "network": "none",
                    "rootfs": "read-only",
                    "memory": "512m",
                    "cpus": "1",
                    "pids": "128",
                    "cap_drop": "ALL",
                    "wall_clock_s": timeout,
                },
            }
        )
        print(f"{case_id:24s} exit={result.exit_code} timeout={result.timed_out} {result.duration_ms}ms")

    path = out_dir / "traces.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
