"""FastAPI surface: health, raw sandbox run, agent task, and the demo UI."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import agent, sandbox

app = FastAPI(title="Blast Radius Zero", version="0.1.0")
WEB = Path(__file__).resolve().parent.parent / "web"


class RunIn(BaseModel):
    code: str = Field(..., max_length=200_000)
    timeout: int = Field(default=15, ge=1, le=60)


class TaskIn(BaseModel):
    task: str = Field(..., max_length=8_000)
    max_steps: int = Field(default=4, ge=1, le=8)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "image": sandbox.IMAGE, "model": os.getenv("VULTR_INFERENCE_MODEL", "")}


@app.post("/api/run")
def run(payload: RunIn) -> JSONResponse:
    return JSONResponse(sandbox.run_python(payload.code, timeout=payload.timeout).as_dict())


@app.post("/api/agent")
def run_agent(payload: TaskIn) -> JSONResponse:
    try:
        return JSONResponse(agent.run_task(payload.task, max_steps=payload.max_steps).as_dict())
    except RuntimeError as exc:  # missing API key
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    index_file = WEB / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(index_file)
