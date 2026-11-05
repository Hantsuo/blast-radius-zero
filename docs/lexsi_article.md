# Blast Radius Zero: making an executing agent's containment measurable

*Lexsi AI Safety & Alignment Hackathon submission — Safety & Alignment track.*

## The problem

Agents that "do real work" all end up in the same place: they run code nobody
wrote. A CSV question becomes `pandas.read_csv`, a code review becomes
`python -c`, a scraping task becomes a shell call. The moment that happens, the
agent's blast radius stops being a metaphor — one bad import and it deletes a
production disk, exfiltrates a key, or forks until the host stops answering.

Most agent demos answer this with a sentence in the system prompt ("be careful
with destructive commands"). A prompt is not a boundary.

## The approach

Blast Radius Zero is built around one rule: **user code never enters the app
process.** The application plans in JSON, writes Python, and hands it to a
supervisor that starts a throwaway container:

```
--network none                     no egress, no SSRF, no exfiltration
--read-only  + tmpfs /tmp (64 MB)   the root filesystem cannot be written
--memory 512m --cpus 1 --pids-limit 128
--cap-drop ALL --security-opt no-new-privileges
15 s wall clock                    the supervisor kills the container by name
--rm                               nothing survives the task
```

The planner calls Vultr Serverless Inference (OpenAI-compatible). No API key is
ever mounted into the sandbox; the container sees no host environment at all.

## The evidence

The interesting part is not the flags — it is that we measured them. The
repository ships a containment suite that attacks its own sandbox, and it runs
in CI:

| Attack | Observed result |
|---|---|
| `shutil.rmtree('/')` + `os.remove('/etc/passwd')` | `OSError [Errno 30] Read-only file system`; container still alive; host sentinel intact (840 ms) |
| `while True: pass` | killed at the wall clock, `timed_out: true` (3.2 s) |
| `socket.create_connection(('1.1.1.1', 53))` | `NETWORK BLOCKED OSError` (392 ms) |
| host environment probe | `CLEAN` — no host variables reach the container |
| fork bomb | `BlockingIOError` at the PID limit |
| 8 MB × 400 allocation | OOM-killed inside the box (exit 137) |

`docker ps` afterwards is empty. The same checks pass on the deployed Vultr
instance, not just on a laptop.

## Published artifacts

- **Traces** — [personaio/blast-radius-zero-traces](https://huggingface.co/datasets/personaio/blast-radius-zero-traces):
  twelve real executions (benign CSV/JSON work, `rm -rf`, fork bomb, OOM,
  egress, environment probe), with the exact stdout, exit codes and durations.
  Regenerated from scratch by `tools/collect_traces.py`.
- **Classifier** — [personaio/blast-radius-classifier](https://huggingface.co/personaio/blast-radius-classifier):
  SmolLM2-135M fine-tuned to answer `RISKY` or `SAFE` for a snippet before it
  runs. 22/22 on a hand-written holdout set the generator never produced. It is
  deliberately *not* the safety mechanism; it only decides what deserves human
  review, which is the part a container cannot give you.
- **Code** — [github.com/Hantsuo/blast-radius-zero](https://github.com/Hantsuo/blast-radius-zero):
  FastAPI app, sandbox supervisor, containment suite, cloud-init bootstrap.
- **Demo** — `http://167.179.96.32:8000/healthz` on a Vultr Cloud Compute
  instance (Ubuntu 24.04, 2 vCPU / 4 GB, Tokyo).

## What we would attack next

- Move from runc to gVisor or Firecracker: the kernel surface is still shared.
- A corpus of prompt-injection payloads that try to smuggle code past the tool
  boundary, each one turned into a regression test.
- Per-task Vultr instances via their API instead of sibling containers, so the
  isolation boundary is a VM, not a namespace.

## Honest limitations

The traces come from one host, the sample is twelve runs, and a
template-trained classifier recognises shapes of risk rather than novel attacks.
Both artifacts are seeds for a larger red-team corpus, not a benchmark. We state
this in the model card because an overclaimed safety number is worse than no
number.

---

*Blast Radius Zero — Lexsi AI Safety & Alignment Hackathon, November 2026.*
