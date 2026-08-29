"""FastAPI service wrapping the arbitration pipeline (+ optional static UI)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm_arbitration.models import ArbitrateRequest, ArbitrateResult, RunSummary
from llm_arbitration.pipeline import arbitrate
from llm_arbitration.store import RunStore

load_dotenv()

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


class ArbitrateBody(BaseModel):
    prompt: str
    generator_models: list[str] | None = None
    arbiter_model: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_s: float = 180.0
    persist: bool = True


class ConfigResponse(BaseModel):
    default_generator_models: list[str]
    default_arbiter_model: str
    suggested_models: list[str] = Field(
        default_factory=lambda: [
            "gpt-4o-mini",
            "gpt-4o",
            "claude-3-5-haiku-latest",
            "claude-sonnet-4-5",
        ]
    )


def _default_models() -> list[str]:
    raw = os.getenv("DEFAULT_GENERATOR_MODELS", "gpt-4o-mini")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _default_arbiter() -> str:
    return os.getenv("DEFAULT_ARBITER_MODEL", "gpt-4o")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = RunStore(os.getenv("DATABASE_URL"))
    yield


app = FastAPI(
    title="LLM Output Arbitration",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(
        default_generator_models=_default_models(),
        default_arbiter_model=_default_arbiter(),
    )


@app.post("/v1/arbitrate", response_model=ArbitrateResult)
def post_arbitrate(body: ArbitrateBody) -> ArbitrateResult:
    generators = body.generator_models or _default_models()
    arbiter = body.arbiter_model or _default_arbiter()
    if not generators:
        raise HTTPException(status_code=400, detail="generator_models must not be empty")

    request = ArbitrateRequest(
        prompt=body.prompt,
        generator_models=generators,
        arbiter_model=arbiter,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout_s=body.timeout_s,
    )

    try:
        result = arbitrate(
            request,
            persist=body.persist,
            database_url=os.getenv("DATABASE_URL"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


@app.get("/v1/runs", response_model=list[RunSummary])
def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RunSummary]:
    store: RunStore = app.state.store
    return store.list_runs(limit=limit, offset=offset)


@app.get("/v1/runs/{run_id}", response_model=ArbitrateResult)
def get_run(run_id: str) -> ArbitrateResult:
    store: RunStore = app.state.store
    result = store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


# Serve the built Vite app when apps/web/dist exists (single-process mode).
if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
