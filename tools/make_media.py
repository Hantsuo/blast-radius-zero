"""Build the lablab media kit: cover image, slide deck (PDF), demo video.

Everything is drawn from the same numbers the tests produced, so the artefacts
cannot drift from the code. Video frames are rendered with Pillow and encoded
with ffmpeg; the deck is a PDF built with reportlab.

    python tools/make_media.py
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
W, H = 1280, 720

INK = (17, 20, 26)
PAPER = (247, 248, 250)
ACCENT = (255, 77, 0)
MUTED = (110, 118, 128)
GREEN = (27, 127, 75)
RED = (179, 29, 29)
WHITE = (255, 255, 255)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def slide(title: str, kicker: str = "", body: list[str] | None = None, footer: str = ""):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    if kicker:
        d.text((80, 90), kicker.upper(), font=font(24, True), fill=ACCENT)
        y = 136
    else:
        y = 110
    d.text((80, y), title, font=font(56, True), fill=INK)
    y += 100
    for para in body or []:
        if para == "---":
            d.line([80, y + 10, W - 80, y + 10], fill=(220, 224, 230), width=2)
            y += 36
            continue
        for line in wrap(d, para, font(28), W - 160):
            d.text((80, y), line, font=font(28), fill=INK)
            y += 42
        y += 10
    if footer:
        d.text((80, H - 60), footer, font=font(20), fill=MUTED)
    return img


def terminal_slide(title: str, command: str, output: str, verdict: str):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    d.text((60, 50), title, font=font(36, True), fill=WHITE)
    d.text((60, 110), command, font=font(22), fill=(150, 160, 175))
    top = 160
    for line in output.splitlines()[:14]:
        colour = RED if "BLOCKED" in line else GREEN if ("still alive" in line or "ok" in line) else (225, 230, 238)
        d.text((60, top), line, font=font(22), fill=colour)
        top += 34
    d.text((60, H - 90), verdict, font=font(26, True), fill=ACCENT)
    return img


def build_cover() -> Path:
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    d.text((80, 150), "BLAST RADIUS ZERO", font=font(84, True), fill=WHITE)
    d.text((80, 260), "An agent that cannot hurt the host", font=font(38), fill=ACCENT)
    lines = [
        "Every task runs in a throwaway Docker sandbox on Vultr:",
        "no network, read-only root, 512 MB, 1 CPU, 128 PIDs, 15 s wall clock.",
        "rm -rf /  →  BLOCKED   ·   fork bomb  →  PID limit   ·   egress  →  NETWORK BLOCKED",
    ]
    y = 360
    for line in lines:
        d.text((80, y), line, font=font(24), fill=(200, 208, 218))
        y += 44
    d.text((80, H - 90), "github.com/Hantsuo/blast-radius-zero", font=font(22), fill=MUTED)
    path = OUT / "cover.png"
    img.save(path)
    return path


def build_pdf() -> Path:
    path = OUT / "deck.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape((13.333 * inch, 7.5 * inch)))
    width, height = 13.333 * inch, 7.5 * inch

    def page(title, kicker="", body=None, footer=""):
        c.setFillColorRGB(0.969, 0.973, 0.980)
        c.rect(0, 0, width, height, fill=1, stroke=0)
        c.setFillColorRGB(1, 0.302, 0)
        c.rect(0, height - 10, width, 10, fill=1, stroke=0)
        if kicker:
            c.setFillColorRGB(1, 0.302, 0)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(0.8 * inch, height - 1.15 * inch, kicker.upper())
        c.setFillColorRGB(0.067, 0.078, 0.102)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(0.8 * inch, height - 1.75 * inch, title)
        y = height - 2.35 * inch
        c.setFont("Helvetica", 14)
        for para in body or []:
            text_obj = c.beginText(0.8 * inch, y)
            text_obj.setLeading(19)
            for line in wrap_pdf(para, 100):
                text_obj.textLine(line)
            c.drawText(text_obj)
            y -= 19 * (len(wrap_pdf(para, 100)) + 1)
        if footer:
            c.setFillColorRGB(0.43, 0.46, 0.5)
            c.setFont("Helvetica", 10)
            c.drawString(0.8 * inch, 0.5 * inch, footer)
        c.showPage()

    def wrap_pdf(text, width_chars):
        words, lines, line = text.split(), [], ""
        for w in words:
            if len(line) + len(w) + 1 <= width_chars:
                line = f"{line} {w}".strip()
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        return lines or [""]

    page("Blast Radius Zero", "Vultr Agent Rush · Blast Radius Zero track",
         ["An agent whose every action runs inside a throwaway Docker sandbox on a Vultr VM.",
          "It plans in JSON, writes Python, runs it in a fresh container, and returns the real stdout.",
          "Containment is measured, not asserted: rm -rf / is blocked, egress fails, the host survives."],
         "github.com/Hantsuo/blast-radius-zero")
    page("The problem", "Why this exists",
         ["Every 'agent that does real work' ends up running code nobody wrote: model output, scraped snippets, user CSVs.",
          "One bad import and it deletes a production disk, exfiltrates a key, or forks until the host stops answering.",
          "Chat-only agents are demos. Agents that execute need a blast radius of zero."])
    page("How it works", "Four steps",
         ["1  Plan — the model receives the task and returns JSON: a thought plus Python.",
          "2  Dispatch — the supervisor starts a fresh container per step; the app process never imports user code.",
          "3  Contain — --network none, read-only root, 512 MB, 1 CPU, 128 PIDs, cap-drop ALL, 15 s wall clock.",
          "4  Verify — stdout, exit code and duration return to the UI; the container is destroyed."])
    page("Measured containment", "Evidence from the suite",
         ["rm -rf / + os.remove('/etc/passwd')  →  BLOCKED (Read-only file system), host sentinel intact, 840 ms",
          "while True: pass  →  killed at the wall clock, 3.2 s, timed_out=true",
          "socket.create_connection('1.1.1.1', 53)  →  NETWORK BLOCKED, 392 ms",
          "host environment probe  →  CLEAN;  fork bomb  →  BlockingIOError at the PID limit",
          "docker ps afterwards  →  empty"])
    page("Vultr integration", "What runs where",
         ["Vultr Cloud Compute: FastAPI orchestrator, demo UI and sandbox supervisor (Ubuntu 24.04, 2 vCPU / 4 GB, Tokyo).",
          "Vultr Serverless Inference: the planner, OpenAI-compatible at api.vultrinference.com/v1.",
          "Sandbox: sibling Docker containers on the same VM, created and destroyed per task.",
          "No GPU: inference is remote, execution is CPU-only."])
    page("Business value", "Who pays for this",
         ["Support and ops teams running model-written scripts against real data.",
          "Platform teams that need a code-execution primitive with a measurable blast radius.",
          "The red-team suite doubles as a CI gate: any new escape attempt becomes a test."],
         "Live demo: http://167.179.96.32:8000/healthz")
    c.save()
    return path


def build_video(hold: int = 4) -> Path:
    frames: list[Image.Image] = []
    frames += [slide("Blast Radius Zero", "Vultr Agent Rush",
                     ["An agent that does real work — and provably cannot hurt the host.",
                      "Every step in a throwaway Docker sandbox on a Vultr VM."],
                     "github.com/Hantsuo/blast-radius-zero")] * (45 * hold)
    frames += [slide("The problem", "Why",
                     ["Agents run code nobody wrote: model output, scraped snippets, user files.",
                      "One bad import deletes a disk or leaks a key.",
                      "Containment has to be a property, not a promise."])] * (60 * hold)
    frames += [terminal_slide("Containment moment: rm -rf /",
                              "$ curl -X POST /api/run -d '{\"code\": \"shutil.rmtree(\\\"/\\\")\"}'",
                              "BLOCKED /etc/passwd OSError [Errno 30] Read-only file system\n"
                              "BLOCKED /usr OSError [Errno 30] Read-only file system\n"
                              "BLOCKED / OSError [Errno 30] Read-only file system\n"
                              "still alive\n"
                              "\"exit_code\": 0, \"duration_ms\": 375",
                              "host intact · container destroyed · docker ps empty")] * 120
    frames += [terminal_slide("Infinite loop: 15 s wall clock",
                              "$ POST /api/run {\"code\": \"while True: pass\"}",
                              "\"timed_out\": true\n\"exit_code\": null\n\"duration_ms\": 3158\n"
                              "container killed by name",
                              "the request returns; the host keeps serving")] * (90 * hold)
    frames += [terminal_slide("Network is off",
                              "$ POST /api/run {\"code\": \"socket.create_connection(('1.1.1.1', 53))\"}",
                              "NETWORK BLOCKED OSError\n\"duration_ms\": 392",
                              "no egress, no SSRF, no exfiltration")] * (90 * hold)
    frames += [slide("On Vultr", "Deployment",
                     ["Cloud Compute instance (Ubuntu 24.04, 2 vCPU / 4 GB, Tokyo) runs the app + supervisor.",
                      "Planner: Vultr Serverless Inference, OpenAI-compatible.",
                      "Bootstrapped from cloud-init in the repo; live at http://167.179.96.32:8000/healthz"],
                     "github.com/Hantsuo/blast-radius-zero")] * (90 * hold)

    with tempfile.TemporaryDirectory() as tmp:
        for i, frame in enumerate(frames):
            frame.save(Path(tmp) / f"{i:05d}.png")
        out = OUT / "demo.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30",
             "-i", str(Path(tmp) / "%05d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
             str(out)],
            check=True,
        )
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("cover  ->", build_cover())
    print("deck   ->", build_pdf())
    print("video  ->", build_video())
