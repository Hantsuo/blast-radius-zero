"""Tests for the stale-answer detector: deterministic, no network.

The live path is exercised by `app/api/verify`; here we pin the scoring rules so
a refactor cannot quietly change what "stale" means.

    python tests/test_stale.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import stale  # noqa: E402


def _src(url: str, snippet: str, published: str | None = None, score: float = 0.9) -> stale.Source:
    return stale.Source(title=url, url=url, published=published, snippet=snippet, score=score)


def test_extracts_only_rotting_claims() -> None:
    answer = (
        "Bananas are yellow. "
        "Vultr's smallest instance costs $2.50 per month. "
        "The sky is blue. "
        "The GDPR came into force in 2018."
    )
    claims = stale.extract_claims(answer)
    assert len(claims) == 2, claims
    assert any("2.50" in c for c in claims)
    assert any("GDPR" in c for c in claims)
    print("PASS extracts_only_rotting_claims", len(claims))


def test_fresh_claim_with_recent_sources() -> None:
    today = date(2026, 11, 5)
    claim = "The Agent Rush submission deadline is November 9, 2026."
    sources = [
        _src("https://a.example/x", "Submissions close November 9, 2026.", "2026-11-01"),
        _src("https://b.example/y", "Deadline: November 9, 2026.", "2026-10-28"),
        _src("https://c.example/z", "The event ends on November 9, 2026.", "2026-11-03"),
    ]
    result = stale.score_claim(claim, sources, today=today)
    assert result.freshness > 0.7, result.freshness
    assert result.verdict == "fresh", result.verdict
    print("PASS fresh_claim_with_recent_sources", round(result.freshness, 3))


def test_claim_pinned_to_an_old_year_is_capped() -> None:
    today = date(2026, 11, 5)
    claim = "GPT-4 Turbo was released in November 2023 and supports a 128k context window."
    sources = [
        _src("https://a.example/x", "GPT-4 Turbo launched in November 2023 with a 128k window.", "2026-10-30"),
        _src("https://b.example/y", "GPT-4 Turbo: 128k context window, released 2023.", "2026-09-12"),
        _src("https://c.example/z", "GPT-4 Turbo was announced November 2023.", "2026-08-01"),
    ]
    result = stale.score_claim(claim, sources, today=today)
    assert result.freshness <= 0.35, result.freshness
    assert result.verdict == "stale", result.verdict
    print("PASS claim_pinned_to_an_old_year_is_capped", round(result.freshness, 3))


def test_no_sources_is_unverifiable() -> None:
    result = stale.score_claim("Vultr costs $2.50 per month.", [])
    assert result.verdict == "unverifiable"
    assert result.freshness < 0.1
    print("PASS no_sources_is_unverifiable")


def test_contradicting_numbers_lower_confidence() -> None:
    today = date(2026, 11, 5)
    claim = "Vultr's smallest instance costs $2.50 per month."
    agree = [
        _src("https://a.example/x", "Plans start at $2.50 per month.", "2026-10-20"),
        _src("https://b.example/y", "The cheapest plan is $2.50/month.", "2026-10-22"),
    ]
    disagree = [
        _src("https://a.example/x", "Plans start at $5.00 per month.", "2026-10-20"),
        _src("https://b.example/y", "The cheapest plan is $6.00/month.", "2026-10-22"),
    ]
    fresh = stale.score_claim(claim, agree, today=today)
    stale_result = stale.score_claim(claim, disagree, today=today)
    assert fresh.freshness > stale_result.freshness, (fresh.freshness, stale_result.freshness)
    print("PASS contradicting_numbers_lower_confidence", round(fresh.freshness, 3), ">", round(stale_result.freshness, 3))


if __name__ == "__main__":
    test_extracts_only_rotting_claims()
    test_fresh_claim_with_recent_sources()
    test_claim_pinned_to_an_old_year_is_capped()
    test_no_sources_is_unverifiable()
    test_contradicting_numbers_lower_confidence()
    print("\nall stale-answer checks passed")
