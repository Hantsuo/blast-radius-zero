"""Stale-answer detection: score how likely a claim is out of date.

Geek Room Global AI Hackathon, problem statement: "Build a Stale-Answer Detector
for AI Applications".

Given an answer produced by another model, find the claims that can rot —
prices, API versions, regulations, company facts — re-check each against live
web sources through Tavily, and return a freshness score with citations.

Deliberately explainable: every point of the score comes from something we can
point at (how recent the source is, how many independent sources agree, whether
a number or version in the claim still appears). No hidden model in the loop.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

import httpx

TAVILY_URL = "https://api.tavily.com/search"

# Claims that rot: prices, versions, model names, legal facts, headcounts, dates.
ROTTING = re.compile(
    r"(\$\s?\d|\b\d+(?:\.\d+)?\s?(?:usd|eur|gbp|rmb|cny)\b"
    r"|\bv?\d+\.\d+(?:\.\d+)?\b"
    r"|\b(?:as of|updated|released|launched|announced|deprecated|acquired|effective|deadline)\b"
    r"|\b(?:GDPR|CCPA|SOC ?2|HIPAA|ISO ?27001)\b"
    r"|\b(?:price|pricing|costs?|fees?|per month|per year|/mo|/yr)\b"
    r"|\b(?:supports?|compatible with|requires?)\b"
    r"|\b(?:GPT-?\d|Claude|Gemini|Llama|DeepSeek|Qwen)[\w.\- ]{0,20}\b)",
    re.IGNORECASE,
)

SENTENCE = re.compile(r"(?<=[.!?])\s+")

MAX_CLAIMS = 8


@dataclass
class Source:
    title: str
    url: str
    published: str | None
    snippet: str
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "published": self.published,
            "snippet": self.snippet[:400],
            "relevance": round(self.score, 3),
        }


@dataclass
class ClaimResult:
    claim: str
    freshness: float
    verdict: str
    reasons: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "freshness": round(self.freshness, 3),
            "verdict": self.verdict,
            "reasons": self.reasons,
            "sources": [s.as_dict() for s in self.sources],
        }


def _tavily_key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    return key


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(value[: len(fmt) + 2].strip(), fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def extract_claims(answer: str) -> list[str]:
    """Sentences that contain something that can go stale, longest first."""
    sentences = [s.strip() for s in SENTENCE.split(answer) if s.strip()]
    picks = [s for s in sentences if ROTTING.search(s)]
    picks.sort(key=len, reverse=True)
    return picks[:MAX_CLAIMS]


def search(claim: str, *, days: int = 45, max_results: int = 5, timeout: float = 20.0) -> list[Source]:
    payload = {
        "query": claim[:380],
        "max_results": max_results,
        "search_depth": "basic",
        "topic": "general",
        "days": days,
        "include_raw_content": False,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            TAVILY_URL,
            json=payload,
            headers={"Authorization": f"Bearer {_tavily_key()}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    out: list[Source] = []
    for hit in data.get("results", []):
        out.append(
            Source(
                title=(hit.get("title") or "").strip(),
                url=hit.get("url") or "",
                published=hit.get("published_date"),
                snippet=(hit.get("content") or "").strip(),
                score=float(hit.get("score") or 0.0),
            )
        )
    return out


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", text)}


def score_claim(claim: str, sources: Iterable[Source], *, today: date | None = None) -> ClaimResult:
    """Four transparent signals, averaged. No model, no vibes."""
    today = today or datetime.now(timezone.utc).date()
    sources = list(sources)
    if not sources:
        return ClaimResult(claim, 0.05, "unverifiable", ["no live source matched this claim"])

    reasons: list[str] = []

    dated = [(s, _parse_date(s.published)) for s in sources]
    ages = [(today - d).days for _, d in dated if d]
    if ages:
        median_age = sorted(ages)[len(ages) // 2]
        recency = max(0.0, 1.0 - median_age / 365.0)
        reasons.append(f"median source age {median_age} days")
    else:
        recency = 0.4
        reasons.append("no publish dates on the sources")

    claim_nums = _numbers(claim)
    support = 0
    if claim_nums:
        for s, _ in dated:
            if claim_nums & _numbers(s.snippet + " " + s.title):
                support += 1
        overlap = support / max(1, len(dated))
        reasons.append(f"{support}/{len(dated)} sources repeat the claim's numbers")
    else:
        overlap = 0.5
        reasons.append("no numbers to cross-check; neutral")

    distinct = len({re.sub(r"https?://(www\.)?", "", s.url).split("/")[0] for s in sources})
    breadth = min(1.0, distinct / 3.0)
    reasons.append(f"{distinct} distinct domains")

    # A claim that pins itself to an old year is stale by construction, even if
    # the web still repeats it: "released in November 2023" ages every month.
    claim_years = {int(y) for y in re.findall(r"\b(20\d{2})\b", claim)}
    if claim_years:
        newest = max(claim_years)
        if newest >= today.year - 1:
            year_fit = 1.0
            reasons.append(f"claim's own year {newest} is current")
        else:
            year_fit = 0.15
            reasons.append(f"claim is pinned to {newest}, {today.year - newest} years old")
    else:
        year_fit = 0.5

    freshness = 0.40 * recency + 0.30 * overlap + 0.15 * breadth + 0.15 * year_fit
    if claim_years and max(claim_years) < today.year - 1:
        # A claim that dates itself is capped: repetition by old pages must not
        # make it look fresh.
        freshness = min(freshness, 0.35)
        reasons.append("capped at 0.35 because the claim dates itself")
    if freshness >= 0.7:
        verdict = "fresh"
    elif freshness >= 0.4:
        verdict = "doubtful"
    else:
        verdict = "stale"
    return ClaimResult(claim, freshness, verdict, reasons, sources[:3])


def verify_answer(answer: str, *, days: int = 45, max_claims: int = MAX_CLAIMS) -> dict[str, Any]:
    claims = extract_claims(answer)[:max_claims]
    results = [score_claim(c, search(c, days=days)) for c in claims]
    overall = sum(r.freshness for r in results) / len(results) if results else 1.0
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "claims_checked": len(results),
        "overall_freshness": round(overall, 3),
        "verdict": (
            "fresh" if overall >= 0.7 else "doubtful" if overall >= 0.4 else "stale"
        ) if results else "nothing-to-check",
        "results": [r.as_dict() for r in results],
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(verify_answer(sys.stdin.read()), indent=2))
