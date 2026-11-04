# lablab submission copy (Vultr: Agent Rush)

Paste these into the lablab "Submit Project" form. Keep the numbers identical to
what the repo proves; do not inflate them.

## Title

Blast Radius Zero — an agent that cannot hurt the host

## Short description (≤ 200 chars)

An agent that plans a task, runs every step in a throwaway Docker sandbox on a
Vultr VM, and proves the host survives `rm -rf /`, fork bombs and egress attempts.

## Long description

Blast Radius Zero is a web agent whose every action is executed inside a
disposable container instead of the app process.

Ask it to analyse a CSV, fix a file or check a URL. It plans in JSON, writes
Python, runs it in a fresh container, and returns the real stdout — not a
description of what it would do.

The container is the product. Each run is created with:

- `--network none` — no egress, no SSRF, no exfiltration
- `--read-only` root plus a 64 MB tmpfs `/tmp`
- 512 MB RAM, 1 CPU, 128 PIDs
- `--cap-drop ALL` and `no-new-privileges`
- a 15 s wall clock enforced by the supervisor, which kills the container by name
- `--rm`, so nothing survives a task; `docker ps` is empty afterwards

The planner calls Vultr Serverless Inference (OpenAI-compatible at
`https://api.vultrinference.com/v1`); execution never leaves the sandbox, and no
API key is ever mounted into it.

## What is proven, not asserted

`python tests/test_containment.py` runs four attacks against the sandbox and the
host:

| Test | Result on this machine |
|---|---|
| `shutil.rmtree('/')` + `os.remove('/etc/passwd')` inside the box | `BLOCKED ... [Errno 30] Read-only file system`, container still alive, host sentinel intact (840 ms) |
| `while True: pass` | killed at the wall clock, `timed_out: true` (3.2 s) |
| `socket.create_connection(('1.1.1.1', 53))` | `NETWORK BLOCKED OSError` (392 ms) |
| host env var leak check | `CLEAN` — no host environment reaches the container |

`docker ps` afterwards: empty.

## Architecture

Browser → FastAPI on the Vultr VM → planner (Vultr Serverless Inference) → code →
sandbox supervisor → `docker run` with the flags above → stdout back to the UI.

## Business value

Every team shipping an "agent that executes code" is one bad import away from
deleting a production disk. Blast Radius Zero is the containment layer: a task
runner you can point at untrusted input — user CSVs, LLM-written scripts,
scraped code — and still sleep. The red-team suite doubles as a CI gate for the
same reason.

## Tags

`vultr`, `serverless-inference`, `docker`, `sandbox`, `agent`, `containment`,
`code-execution`, `ai-safety`

## Demo video storyboard (90 s)

1. **0:00–0:15** — ask the agent a CSV question; show the step trace with code + real stdout.
2. **0:15–0:40** — containment moment: submit `shutil.rmtree('/')`. Trace shows `Read-only file system`, the app keeps serving, host file still there.
3. **0:40–0:55** — submit `while True: pass`; killed at 15 s; `docker ps` empty.
4. **0:55–1:15** — architecture slide: Vultr VM, Serverless Inference, container flags.
5. **1:15–1:30** — what it is worth: untrusted code execution for teams.

## Repo

https://github.com/Hantsuo/blast-radius-zero
