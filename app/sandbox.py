"""Container-isolated code execution.

Every task runs in a throwaway Docker container with no network, capped CPU,
memory and PID count, a read-only root filesystem and a tmpfs /tmp. The host
process never imports or evals user code; it only talks to the Docker CLI.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field

IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.12-slim")
WALL_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT_S", "15"))
MAX_OUTPUT = int(os.getenv("SANDBOX_MAX_OUTPUT", "20000"))

# Hard containment flags. No host env is passed in, no secrets reach the container.
_CONTAINMENT = [
    "--network", "none",
    "--memory", "512m", "--memory-swap", "512m",
    "--cpus", "1",
    "--pids-limit", "128",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--read-only",
    "--tmpfs", "/tmp:rw,size=64m",
    "-e", "PYTHONDONTWRITEBYTECODE=1",
    "-e", "HOME=/tmp",
]


@dataclass
class RunResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    run_id: str
    killed: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "run_id": self.run_id,
        }


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n... [truncated {len(text) - MAX_OUTPUT} chars]"


def run_python(code: str, *, timeout: int | None = None) -> RunResult:
    """Execute `code` in a fresh container and return what happened.

    The code goes in over stdin (`python -u -`), not through a bind mount. The
    app may itself run in a container, where a host temp path is not visible to
    its sibling — stdin keeps the two independent and exposes no host path.
    """
    timeout = timeout or WALL_TIMEOUT
    run_id = uuid.uuid4().hex[:12]
    name = f"crush-{run_id}"
    started = time.perf_counter()
    try:
        cmd = [
            "docker", "run", "--rm", "-i", "--name", name, *_CONTAINMENT,
            "-w", "/tmp",
            IMAGE, "python", "-u", "-",
        ]
        try:
            proc = subprocess.run(
                cmd, input=code, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            return RunResult(
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=_truncate(proc.stdout),
                stderr=_truncate(proc.stderr),
                duration_ms=elapsed,
                timed_out=False,
                run_id=run_id,
            )
        except subprocess.TimeoutExpired as exc:
            # The container keeps running after the CLI is killed: destroy it.
            subprocess.run(["docker", "kill", name], capture_output=True)
            elapsed = int((time.perf_counter() - started) * 1000)
            out = (exc.stdout or b"")
            err = (exc.stderr or b"")
            if isinstance(out, bytes):
                out = out.decode("utf-8", "replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", "replace")
            return RunResult(
                ok=False, exit_code=None,
                stdout=_truncate(out), stderr=_truncate(err),
                duration_ms=elapsed, timed_out=True,
                run_id=run_id, killed=True,
                notes=[f"wall clock exceeded {timeout}s, container killed"],
            )
    finally:
        # `--rm` handles the container; nothing else is left on the host.
        pass

