"""Fine-tune a tiny model to label code as RISKY or SAFE before it runs.

Why a generative classifier instead of a sequence-classification head: the same
model then doubles as a guard prompt inside the agent, and it needs no custom
architecture to be loadable from the Hub.

    python tools/train_classifier.py --epochs 4 --out models/blast-radius-classifier
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "classifier"

PROMPT = (
    "You are a pre-flight check for an agent that runs untrusted Python.\n"
    "Decide whether this code could damage the host it runs on: deleting files "
    "outside its working directory, writing outside it, talking to the network, "
    "spawning unbounded processes, exhausting memory, reading secrets, or "
    "modifying the system.\n"
    "Answer with exactly one word: RISKY or SAFE.\n\n"
    "CODE:\n```python\n{code}\n```\nANSWER:"
)


class CodeRiskDataset(Dataset):
    def __init__(self, path: Path, tokenizer, max_len: int = 256):
        self.rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        row = self.rows[i]
        prompt = PROMPT.format(code=row["code"])
        answer = row["label"]
        p_ids = self.tok(prompt, add_special_tokens=False)["input_ids"]
        a_ids = self.tok(" " + answer, add_special_tokens=False)["input_ids"] + [self.tok.eos_token_id]
        ids = (p_ids + a_ids)[: self.max_len]
        labels = ([-100] * len(p_ids) + a_ids)[: self.max_len]
        return {"input_ids": ids, "labels": labels, "attention_mask": [1] * len(ids)}


def evaluate(model, tok, rows: list[dict]) -> tuple[float, list[dict]]:
    model.eval()
    correct = 0
    details = []
    for row in rows:
        prompt = PROMPT.format(code=row["code"])
        ids = tok(prompt, return_tensors="pt").input_ids
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=6, do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(out[0][ids.shape[-1]:], skip_special_tokens=True).strip().upper()
        pred = "RISKY" if text.startswith("RISK") else "SAFE"
        ok = pred == row["label"]
        correct += ok
        details.append({"label": row["label"], "pred": pred, "ok": ok, "raw": text[:16]})
    return correct / max(1, len(rows)), details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M-Instruct")
    ap.add_argument("--epochs", type=float, default=4.0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--out", default=str(ROOT / "models" / "blast-radius-classifier"))
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32)
    model.config.use_cache = False

    train_ds = CodeRiskDataset(DATA / "train.jsonl", tok)
    val_rows = [json.loads(l) for l in (DATA / "val.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    collator = DataCollatorForSeq2Seq(tok, model=model, padding=True, label_pad_token_id=-100)

    targs = TrainingArguments(
        output_dir=str(ROOT / "models" / "_runs"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        logging_steps=20,
        save_strategy="no",
        report_to=[],
        use_cpu=True,
        dataloader_num_workers=0,
        seed=7,
    )

    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, data_collator=collator)
    trainer.train()

    acc, details = evaluate(model, tok, val_rows)
    print(f"\nvalidation accuracy: {acc:.3f} ({sum(d['ok'] for d in details)}/{len(details)})")
    wrong = [d for d in details if not d["ok"]]
    for d in wrong[:6]:
        print("  miss:", d)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    (out / "training_summary.json").write_text(
        json.dumps(
            {
                "base_model": args.model,
                "epochs": args.epochs,
                "batch": args.batch,
                "lr": args.lr,
                "train_rows": len(train_ds),
                "val_rows": len(val_rows),
                "val_accuracy": round(acc, 4),
                "misses": wrong[:12],
                "prompt_template": PROMPT,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"saved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
