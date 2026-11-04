"""A containment-first agent: plan, execute in a sandbox, observe, repeat.

The agent never runs code itself. Every step that touches user data or a shell
goes through sandbox.run_python, which owns the container lifecycle.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import llm, sandbox

SYSTEM = """You are a data analyst that works only inside a disposable sandbox.

Rules:
- You have no shell on the host. Anything you want to run goes in `code`,
  which runs as a fresh Python 3.12 process in a container with no network,
  512 MB of memory, 1 CPU and a 15 second wall clock.
- Do not assume files persist between steps beyond /work, and never put
  credentials in code.
- Prefer small, verifiable steps. Print the evidence you will rely on.
- When you have the answer, set "done": true and leave "code" empty.

Reply with JSON only, shaped like:
{"thought": "...", "code": "python source or empty", "done": false}
"""


@dataclass
class Step:
    index: int
    thought: str
    code: str
    ok: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class TaskRun:
    task: str
    steps: list[Step] = field(default_factory=list)
    answer: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "steps": [s.as_dict() for s in self.steps],
            "answer": self.answer,
            "error": self.error,
        }


def run_task(task: str, *, max_steps: int = 4) -> TaskRun:
    out = TaskRun(task=task)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]

    for i in range(max_steps):
        try:
            plan = llm.complete_json(messages)
        except Exception as exc:  # network, bad key, malformed JSON
            out.error = f"planner failed: {exc}"
            break

        thought = str(plan.get("thought", "")).strip()
        code = str(plan.get("code") or "").strip()
        done = bool(plan.get("done"))

        if done or not code:
            out.answer = thought
            break

        result = sandbox.run_python(code)
        out.steps.append(Step(
            index=i, thought=thought, code=code, ok=result.ok,
            stdout=result.stdout, stderr=result.stderr,
            duration_ms=result.duration_ms, timed_out=result.timed_out,
        ))

        messages.append({"role": "assistant", "content": json.dumps(plan)})
        messages.append({
            "role": "user",
            "content": json.dumps({
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
            }),
        })

    if not out.answer and out.error is None:
        out.answer = "Stopped after the step budget without a final answer."
    return out
