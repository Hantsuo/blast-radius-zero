# Lexsi submission abstract (< 500 words)

**Blast Radius Zero: making an executing agent's containment measurable**

Agents that "do real work" all end up in the same place: they run code they did
not write. A CSV question becomes `pandas.read_csv`, a code review becomes
`python -c`, a scraping task becomes a shell call. The moment that happens, the
agent's blast radius stops being a metaphor — one bad import and it deletes a
production disk, exfiltrates a key, or forks until the host stops answering.

We built Blast Radius Zero around one rule: **user code never enters the app
process.** The application plans in JSON, writes Python, and hands it to a
supervisor that starts a throwaway container with `--network none`, a read-only
root filesystem, a 64 MB tmpfs `/tmp`, 512 MB RAM, one CPU, 128 PIDs,
`--cap-drop ALL`, `no-new-privileges`, and a 15 second wall clock enforced by
killing the container by name. `--rm` means nothing survives the task. The LLM
calls go to Vultr Serverless Inference; no key is ever mounted into the box.

The interesting part is not the flags — it is that we measured them. The
repository ships a containment suite that attacks its own sandbox:

| Attack | Observed result |
|---|---|
| `shutil.rmtree('/')` + `os.remove('/etc/passwd')` | `OSError [Errno 30] Read-only file system`, container still alive, host sentinel intact (840 ms) |
| `while True: pass` | killed at the wall clock, `timed_out: true` (3.2 s) |
| `socket.create_connection(('1.1.1.1', 53))` | `NETWORK BLOCKED OSError` (392 ms) |
| host environment probe | `CLEAN` — no host variables reach the container |
| fork bomb | `BlockingIOError` at the PID limit |
| 8 MB × 400 allocation | OOM-killed inside the box (exit 137) |

We also published twelve real execution traces — the exact stdout, exit codes
and durations above, plus three benign CSV/JSON tasks — as a public Hugging Face
dataset (`personaio/blast-radius-zero-traces`). Red-team work needs evidence, and
evidence needs to be reproducible: `tools/collect_traces.py` regenerates the
whole file from scratch.

On top of that we trained a small pre-flight classifier: SmolLM2-135M fine-tuned
to answer RISKY or SAFE for a snippet before it runs (`personaio/blast-radius-classifier`).
It scores 22/22 on a hand-written holdout set that the generator never produced.
It is deliberately *not* the safety mechanism — the container is. The classifier
only decides what deserves human review, which is the part a container cannot
give you.

Limitations we state rather than hide: the traces come from one host (Docker
Desktop on Windows), the sample is twelve runs, and a template-trained classifier
recognises shapes of risk, not novel attacks. Both artifacts are seeds for a
larger red-team corpus, not a benchmark.

What we would do with more time: gVisor or Firecracker instead of runc, a
per-task Vultr instance via their API, and a corpus of prompt-injection payloads
that try to smuggle code past the tool boundary.

Repository: https://github.com/Hantsuo/blast-radius-zero
