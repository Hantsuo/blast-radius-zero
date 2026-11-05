"""Build the Geek Room pitch deck (PPTX) from code, so it can be regenerated.

    python tools/make_deck.py            # -> docs/geekroom-deck.pptx
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "geekroom-deck.pptx"

INK = RGBColor(0x11, 0x14, 0x1A)
MUTED = RGBColor(0x5B, 0x64, 0x72)
ACCENT = RGBColor(0xFF, 0x4D, 0x00)
GREEN = RGBColor(0x1B, 0x7F, 0x4B)
RED = RGBColor(0xB3, 0x1D, 0x1D)


def text_box(slide, left, top, width, height, text, size=18, bold=False, color=INK):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    para = frame.paragraphs[0]
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Segoe UI"
    return box


def bullets(slide, left, top, width, height, items, size=16, color=INK):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    for i, item in enumerate(items):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        run = para.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.name = "Segoe UI"
        para.space_after = Pt(8)
    return box


def slide_title(prs, title, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    text_box(slide, 0.7, 0.55, 11.5, 0.9, title, size=30, bold=True)
    if subtitle:
        text_box(slide, 0.7, 1.35, 11.5, 0.6, subtitle, size=14, color=MUTED)
    return slide


def build() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 1 - cover
    s = prs.slides.add_slide(prs.slide_layouts[6])
    band = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(3.2))
    band.fill.solid()
    band.fill.fore_color.rgb = INK
    band.line.fill.background()
    text_box(s, 0.8, 1.0, 11.5, 1.0, "Blast Radius Zero", size=44, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    text_box(s, 0.8, 2.0, 11.5, 0.8, "Stale-Answer Detector", size=28, color=ACCENT)
    text_box(s, 0.8, 3.7, 11.5, 0.6, "Geek Room Global AI Hackathon · AI Agents & Intelligent Systems", size=16, color=MUTED)
    text_box(s, 0.8, 4.3, 11.5, 1.2,
             "Every answer ages. This one checks before you trust it: pull the claims that can rot, "
             "re-verify each against live sources with Tavily, and return a freshness score with receipts.",
             size=16)
    text_box(s, 0.8, 6.2, 11.5, 0.5, "github.com/Hantsuo/blast-radius-zero", size=13, color=MUTED)

    # 2 - problem
    s = slide_title(prs, "The problem: answers rot silently", "LLMs state prices, versions and deadlines with the same confidence at any age")
    bullets(s, 0.9, 2.1, 11.6, 4.4, [
        "A model trained last year will happily quote last year's price, API version or filing deadline.",
        "Users cannot tell a fact that is current from a fact that was current in 2023.",
        "Generic \"is this true?\" checks miss the real failure: the fact was true, and stopped being true.",
        "Support, sales and compliance teams need a number they can act on, plus the source behind it.",
    ], size=18)

    # 3 - how it works
    s = slide_title(prs, "How it works", "Four steps, all visible in the output")
    steps = [
        ("1  Extract", "Sentences that can rot: prices, versions, model names,\nregulations, deadlines, support claims."),
        ("2  Re-check", "Each claim becomes a Tavily search, scoped to a recency window\n(days=45 by default)."),
        ("3  Score", "Recency of sources · do the numbers still match ·\ndistinct domains · does the claim date itself."),
        ("4  Verdict", "fresh / doubtful / stale per claim, with the sources\nthat produced the number."),
    ]
    top = 2.0
    for label, detail in steps:
        box = s.shapes.add_shape(1, Inches(0.9), Inches(top), Inches(2.6), Inches(0.95))
        box.fill.solid()
        box.fill.fore_color.rgb = INK
        box.line.fill.background()
        text_box(s, 1.0, top + 0.25, 2.4, 0.5, label, size=17, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        text_box(s, 3.75, top + 0.12, 8.8, 0.9, detail, size=13)
        top += 1.15

    # 4 - architecture
    s = slide_title(prs, "Architecture", "Same containment layer as the agent: nothing runs on the host")
    boxes = [
        (0.9, 2.3, "Answer text", RGBColor(0xEE, 0xF1, 0xF5)),
        (3.6, 2.3, "Claim extractor", RGBColor(0xEE, 0xF1, 0xF5)),
        (6.3, 2.3, "Tavily search\n(days window)", RGBColor(0xFF, 0xE9, 0xE0)),
        (9.0, 2.3, "Scorer\n4 signals", RGBColor(0xEE, 0xF1, 0xF5)),
        (9.0, 4.4, "Verdict +\ncitations", RGBColor(0xE6, 0xF4, 0xEC)),
        (6.3, 4.4, "Sandbox\n(Docker, no net)", RGBColor(0xEE, 0xF1, 0xF5)),
        (3.6, 4.4, "FastAPI\n/api/verify", RGBColor(0xEE, 0xF1, 0xF5)),
    ]
    for left, top_, label, fill in boxes:
        shape = s.shapes.add_shape(1, Inches(left), Inches(top_), Inches(2.3), Inches(1.1))
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        shape.line.color.rgb = RGBColor(0xD5, 0xDA, 0xE1)
        tf = shape.text_frame
        tf.text = label
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(14)
                r.font.color.rgb = INK
                r.font.name = "Segoe UI"
    text_box(s, 0.9, 5.9, 11.6, 0.9,
             "The sandbox matters for the next step: once a claim needs arithmetic (unit prices, version diffs, "
             "table math), the verification code runs in the same throwaway container as the agent — no host access, "
             "no network, 15 s wall clock.", size=13, color=MUTED)

    # 5 - evidence
    s = slide_title(prs, "Measured, not claimed", "Two live runs against the real Tavily API (2026-11-05)")
    rows = [
        ("GPT-4 Turbo was released in November 2023, 128k context", "0.35", "stale", RED),
        ("Vultr's smallest instance costs about $2.50/month", "0.685", "doubtful", MUTED),
        ("Agent Rush deadline is November 9, 2026", "0.996", "fresh", GREEN),
    ]
    top = 2.3
    for claim, score, verdict, colour in rows:
        text_box(s, 0.9, top, 8.2, 0.6, claim, size=15)
        text_box(s, 9.3, top, 1.3, 0.6, score, size=15, bold=True, color=colour)
        text_box(s, 10.7, top, 1.9, 0.6, verdict, size=15, bold=True, color=colour)
        top += 0.85
    text_box(s, 0.9, 5.2, 11.6, 1.4,
             "Why the third one scores 0.996: three independent domains, all published within the last week, "
             "and the claim's own year is current. The first is capped at 0.35 because it dates itself — "
             "old pages repeating it must not make it look fresh.", size=13, color=MUTED)

    # 6 - value
    s = slide_title(prs, "Who pays for this", "Freshness is a support cost and a compliance risk, not a curiosity")
    bullets(s, 0.9, 2.1, 5.6, 4.4, [
        "Support bots: stop quoting discontinued pricing.",
        "Sales enablement: never send last quarter's numbers.",
        "Compliance: prove a claim was re-checked, with the source.",
    ], size=16)
    bullets(s, 6.9, 2.1, 5.6, 4.4, [
        "Runs as one endpoint (/api/verify) next to the agent.",
        "Every score decomposes into four named signals.",
        "8,000 Tavily credits in hand; 1,000/month plan as a floor.",
        "Next: fine-tune the extractor, add numeric diffing in the sandbox.",
    ], size=16)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT}")
    return OUT


if __name__ == "__main__":
    build()
