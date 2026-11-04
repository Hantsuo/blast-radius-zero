"""LLM client for Vultr Serverless Inference (OpenAI-compatible)."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

BASE_URL = os.getenv("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1")
MODEL = os.getenv("VULTR_INFERENCE_MODEL", "llama-3.3-70b-instruct-fp8")


def client() -> OpenAI:
    key = os.getenv("VULTR_INFERENCE_API_KEY")
    if not key:
        raise RuntimeError(
            "VULTR_INFERENCE_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return OpenAI(base_url=BASE_URL, api_key=key)


def complete(messages: list[dict[str, Any]], *, temperature: float = 0.2) -> str:
    resp = client().chat.completions.create(
        model=MODEL, messages=messages, temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def complete_json(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask for JSON and tolerate the usual fenced-block noise."""
    raw = complete(messages + [{"role": "user", "content": "Reply with JSON only."}])
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
