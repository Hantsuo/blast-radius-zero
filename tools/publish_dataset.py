"""Publish the containment traces as a Hugging Face dataset.

Reads HF_TOKEN from the environment (never from the repo), creates or updates
`<user>/blast-radius-zero-traces` and uploads data/traces.jsonl plus a card.

    $env:HF_TOKEN = ...
    python tools/publish_dataset.py [--repo personaio/blast-radius-zero-traces]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "data" / "traces.jsonl"

CARD = """---
license: mit
task_categories:
  - text-classification
language:
  - en
tags:
  - sandbox
  - containment
  - ai-safety
  - red-teaming
  - agents
size_categories:
  - n<1K
---

# Blast Radius Zero — containment traces

Real execution traces from a container sandbox that an agent runs untrusted code in.
Every row is one execution: the code that was submitted, what the sandbox returned,
and whether the host survived.

Collected with [`tools/collect_traces.py`](https://github.com/Hantsuo/blast-radius-zero/blob/master/tools/collect_traces.py)
against the sandbox in [`app/sandbox.py`](https://github.com/Hantsuo/blast-radius-zero/blob/master/app/sandbox.py):
`--network none`, read-only root, 512 MB, 1 CPU, 128 PIDs, `--cap-drop ALL`, 15 s wall clock.

## Fields

| field | meaning |
|---|---|
| `id` | stable case id |
| `label` | human description |
| `category` | `benign`, `destructive`, `resource`, `network`, `secrets`, `informational` |
| `code` | the exact Python that was executed |
| `exit_code` | container exit code (`null` when the wall clock killed it) |
| `timed_out` | whether the supervisor killed it |
| `stdout` / `stderr` | what the container printed, verbatim |
| `duration_ms` / `wall_ms` | container and end-to-end durations |
| `contained` | `true` when the sandbox absorbed it, `null` for informational rows |
| `isolation` | the flags in force for that run |

## Why it is useful

Training and evaluating "will this code hurt the host?" classifiers, red-team
regression suites, and agent-safety evaluations. The traces are not synthetic:
every `stdout` value is what the container actually printed.

## Caveats

Small sample (12 rows) and a single host (Docker Desktop on Windows, `python:3.12-slim`).
Treat it as a seed set, not a benchmark.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.getenv("HF_DATASET_REPO", "personaio/blast-radius-zero-traces"))
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set", file=sys.stderr)
        return 2
    if not TRACES.exists():
        print(f"missing {TRACES}; run tools/collect_traces.py first", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    who = api.whoami()
    print(f"authenticated as {who.get('name')}")

    api.create_repo(repo_id=args.repo, repo_type="dataset", exist_ok=True, private=False)
    api.upload_file(
        path_or_fileobj=str(TRACES),
        path_in_repo="traces.jsonl",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="traces: 12 real sandbox runs (benign, rm -rf, fork bomb, OOM, egress, env leak)",
    )
    api.upload_file(
        path_or_fileobj=CARD.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="docs: dataset card",
    )

    rows = [json.loads(line) for line in TRACES.read_text(encoding="utf-8").splitlines() if line.strip()]
    contained = sum(1 for r in rows if r["contained"] is True)
    print(f"uploaded {len(rows)} rows ({contained} contained) -> https://huggingface.co/datasets/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
