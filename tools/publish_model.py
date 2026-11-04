"""Publish the classifier to the Hugging Face Hub and wire both collections.

    $env:HF_TOKEN = ...
    python tools/publish_model.py --repo personaio/blast-radius-classifier
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "blast-radius-classifier"

CARD = """---
license: mit
base_model: {base_model}
library_name: transformers
pipeline_tag: text-generation
language:
  - en
tags:
  - code
  - safety
  - sandbox
  - agents
  - red-teaming
datasets:
  - {dataset_repo}
---

# Blast Radius Zero — code risk classifier

A {params} parameter model fine-tuned to answer one question before an agent runs
untrusted code: **will this hurt the host?**

It replies `RISKY` when the snippet deletes or writes outside its working
directory, talks to the network, spawns unbounded processes, exhausts memory,
reads secrets or mutates the system — and `SAFE` otherwise.

Part of [Blast Radius Zero](https://github.com/Hantsuo/blast-radius-zero), an agent
that executes every step inside a throwaway container. The classifier is the cheap
pre-flight gate; the container is the guarantee.

## Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_id = "{repo}"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32)

PROMPT = (
    "You are a pre-flight check for an agent that runs untrusted Python.\\n"
    "Decide whether this code could damage the host it runs on: deleting files "
    "outside its working directory, writing outside it, talking to the network, "
    "spawning unbounded processes, exhausting memory, reading secrets, or "
    "modifying the system.\\n"
    "Answer with exactly one word: RISKY or SAFE.\\n\\n"
    "CODE:\\n```python\\n{{code}}\\n```\\nANSWER:"
)

code = "import shutil; shutil.rmtree('/')"
ids = tok(PROMPT.format(code=code), return_tensors="pt").input_ids
out = model.generate(ids, max_new_tokens=6, do_sample=False, pad_token_id=tok.eos_token_id)
print(tok.decode(out[0][ids.shape[-1]:], skip_special_tokens=True).strip())  # RISKY
```

## Training

- Base: `{base_model}`
- Data: {train_rows} generated snippets ({half}/{half} RISKY/SAFE) from
  [`tools/make_classifier_data.py`](https://github.com/Hantsuo/blast-radius-zero/blob/master/tools/make_classifier_data.py),
  plus the real sandbox traces in [{dataset_repo}](https://huggingface.co/datasets/{dataset_repo}).
- {epochs} epochs, batch {batch}, lr {lr}, cosine schedule, CPU only.
- Validation accuracy **{acc} ({correct}/{val_rows})** on the held-out split of the same generator.
- Holdout accuracy **{holdout} ({holdout_correct}/{holdout_rows})** on 22 hand-written snippets the generator never produced — this is the number to trust.

## Limits — read this before trusting it

- Trained on generated snippets, so it recognises *shapes* of risk, not novel
  attacks. It is a triage signal, not a sandbox.
- Python only.
- The sandbox in the repo still runs every snippet regardless of this verdict;
  the classifier decides what gets a human review, not what gets executed.

## Licence

MIT, same as the parent project.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="personaio/blast-radius-classifier")
    ap.add_argument("--dataset-repo", default="personaio/blast-radius-zero-traces")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set", file=sys.stderr)
        return 2
    if not (MODEL_DIR / "training_summary.json").exists():
        print(f"missing {MODEL_DIR}/training_summary.json; train first", file=sys.stderr)
        return 2

    summary = json.loads((MODEL_DIR / "training_summary.json").read_text(encoding="utf-8"))
    acc = summary["val_accuracy"]
    holdout = summary.get("holdout_accuracy")
    correct = round(acc * summary["val_rows"])
    card = CARD.format(
        base_model=summary["base_model"],
        dataset_repo=args.dataset_repo,
        params="135M",
        repo=args.repo,
        train_rows=summary["train_rows"],
        half=summary["train_rows"] // 2,
        epochs=summary["epochs"],
        batch=summary["batch"],
        lr=summary["lr"],
        acc=f"{acc:.1%}",
        correct=correct,
        val_rows=summary["val_rows"],
        holdout=f"{holdout:.0%}" if holdout is not None else "n/a",
        holdout_correct=round((holdout or 0) * summary.get("holdout_rows", 0)),
        holdout_rows=summary.get("holdout_rows", 0),
    )
    (MODEL_DIR / "README.md").write_text(card, encoding="utf-8")

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    print("authenticated as", api.whoami().get("name"))

    api.create_repo(repo_id=args.repo, repo_type="model", exist_ok=True, private=False)
    api.upload_folder(
        folder_path=str(MODEL_DIR),
        repo_id=args.repo,
        repo_type="model",
        commit_message=f"classifier: SmolLM2-135M fine-tune, val accuracy {acc:.1%}",
        ignore_patterns=["*.log", "training_summary.json"],
    )

    # collections: one for the model, one for the data
    model_col = api.create_collection(
        title="Blast Radius Zero — model",
        description="Pre-flight code risk classifier used by the Blast Radius Zero agent.",
        exists_ok=True,
    )
    api.add_collection_item(collection_slug=model_col.slug, item_id=args.repo, item_type="model", exists_ok=True)

    data_col = api.create_collection(
        title="Blast Radius Zero — traces",
        description="Real container-sandbox execution traces: benign work, rm -rf, fork bombs, OOM, egress.",
        exists_ok=True,
    )
    api.add_collection_item(collection_slug=data_col.slug, item_id=args.dataset_repo, item_type="dataset", exists_ok=True)

    print(f"model  -> https://huggingface.co/{args.repo}")
    print(f"collection -> https://huggingface.co/collections/{model_col.slug}")
    print(f"collection -> https://huggingface.co/collections/{data_col.slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
