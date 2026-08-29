# Technical Tutorial: LLM Output Arbitration System

This tutorial explains how the system works end-to-end: architecture, data flow, each layer of code, how to run every surface (UI, API, CLI, library), and how to extend it.

---

## 1. What problem it solves

A single LLM can be wrong, incomplete, or biased. **Arbitration** here means:

1. Send the **same prompt** to several generator models **in parallel**.
2. Pass all successful answers to an **arbiter** model.
3. The arbiter **synthesizes** one merged answer (keeps the best parts, resolves disagreements, notes residual conflicts, and attributes contributions).

You get a final answer plus an audit trail: raw candidates, conflicts, attributions, latency, and token usage.

---

## 2. Architecture overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐
│  Web UI     │────▶│  FastAPI     │────▶│  llm_arbitration    │
│  (React)    │     │  /v1/*       │     │  pipeline.arbitrate │
└─────────────┘     └──────────────┘     └──────────┬──────────┘
┌─────────────┐              ▲                      │
│  CLI        │──────────────┘                      ▼
│  arbitrate  │                          ┌─────────────────────┐
└─────────────┘                          │ generate (parallel) │
┌─────────────┐                          │ synthesize (arbiter)│
│  Python lib │─────────────────────────▶│ store (SQLite)      │
└─────────────┘                          └──────────┬──────────┘
                                                    ▼
                                         OpenAI / Anthropic APIs
```

| Layer | Path | Role |
|-------|------|------|
| Core library | `src/llm_arbitration/` | Schemas, providers, fan-out, synthesis, store, CLI |
| API | `apps/api/main.py` | HTTP wrappers + optional static UI hosting |
| Web UI | `apps/web/` | Compose runs, inspect results, browse history |
| Config | `.env` | API keys and defaults (never sent to the browser) |

All surfaces call the same function: `pipeline.arbitrate(...)`.

---

## 3. Repository map

```
llm-output-arbitration/
├── pyproject.toml              # Package + CLI entrypoint
├── .env.example                # Keys and defaults
├── README.md                   # Quick start
├── docs/TECHNICAL_TUTORIAL.md  # This file
├── src/llm_arbitration/
│   ├── models.py               # Pydantic request/result types
│   ├── providers.py            # httpx → OpenAI / Anthropic
│   ├── generate.py             # Parallel fan-out
│   ├── synthesize.py           # Arbiter prompt + JSON parse
│   ├── pipeline.py             # Orchestration + optional persist
│   ├── store.py                # SQLite run history
│   └── cli.py                  # `arbitrate` command
├── apps/api/main.py            # FastAPI
└── apps/web/                   # Vite + React + TypeScript UI
```

---

## 4. Data contracts

### Request (`ArbitrateRequest`)

| Field | Meaning |
|-------|---------|
| `prompt` | User question |
| `generator_models` | List of model ids to call in parallel |
| `arbiter_model` | Model that synthesizes the final answer |
| `system_prompt` | Optional shared system message for generators |
| `temperature` | Sampling temperature for generators (arbiter is capped ≤ 0.3) |
| `max_tokens` / `timeout_s` | Optional limits |

### Result (`ArbitrateResult`)

| Field | Meaning |
|-------|---------|
| `run_id` | UUID for this run |
| `final_answer` | Synthesized text |
| `conflicts` | Disagreements the arbiter recorded |
| `attributions` | `{model, contribution}` entries |
| `candidates` | Per-model content / error / latency / usage |
| `usage` | Aggregated token counts |
| `meta` | Arbiter latency / error notes |

---

## 5. Pipeline walkthrough (core)

### Step A — Generate (`generate.py`)

1. Build chat messages (`system` optional + `user` prompt).
2. Submit one completion per model on a thread pool (`ThreadPoolExecutor`).
3. Preserve input order in the returned `candidates` list.
4. Failures become `CandidateResult(error=...)`; they do **not** abort the whole run.

### Step B — Provider (`providers.py`)

Routing is by model id string:

- Names starting with `claude` or `anthropic/` → Anthropic Messages API.
- Everything else → OpenAI-compatible Chat Completions (`OPENAI_BASE_URL` optional).

Keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

### Step C — Synthesize (`synthesize.py`)

1. Keep only successful candidates; list failures for the arbiter.
2. Send a fixed system prompt that demands **JSON only**:
   - `final_answer`, `conflicts`, `attributions`
3. Parse JSON (raw, fenced, or first `{...}` slice).
4. On parse failure: **one repair retry** at temperature 0.
5. If the arbiter still fails: fall back to the first successful candidate and note that in `conflicts`.

### Step D — Persist (`store.py`)

When `persist=True`, the full `ArbitrateResult` is written to SQLite (`DATABASE_URL`, default `./data/arbitration.db`). The API history endpoints read from this table.

---

## 6. Setup (once)

```bash
# Repo root
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -e .
cp .env.example .env
# Edit .env — set at least one provider key

cd apps/web
npm install
npm run build    # produces apps/web/dist for single-server mode
```

Example `.env`:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_GENERATOR_MODELS=gpt-4o-mini,claude-3-5-haiku-latest
DEFAULT_ARBITER_MODEL=gpt-4o
DATABASE_URL=sqlite:///./data/arbitration.db
```

---

## 7. Using the Web UI

### Option A — Single process (API serves the UI)

After `npm run build` in `apps/web`:

```bash
# From repo root, venv active
uvicorn apps.api.main:app --host 127.0.0.1 --port 18080
```

Open **http://127.0.0.1:18080/** — the built SPA and `/v1` API share one origin.

> On some Windows setups ports like `8000`/`8001` are blocked. Prefer a free high port (e.g. `18080`).

### Option B — Dev mode (hot reload)

Terminal 1 — API:

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 18080
```

Terminal 2 — Vite (proxies `/v1` and `/health` to the API):

```bash
cd apps/web
npm run dev
```

Open the URL Vite prints (often `http://127.0.0.1:5173`). If the proxy port in `apps/web/vite.config.ts` does not match your API port, update it.

### UI workflow

1. Confirm **API online** in the header pill.
2. Enter a prompt (or click a **Try** example).
3. Select one or more **generators**; pick an **arbiter**.
4. Optionally open **System prompt & temperature**.
5. Click **Run arbitration**.
6. Inspect tabs: **Synthesized**, **Candidates**, **Conflicts & usage**.
7. Use **History** to reload past runs; **Copy answer** / **Download JSON** to export.

The browser never sees API keys — only the server does.

---

## 8. Using the API directly

Base URL example: `http://127.0.0.1:18080`

### Health

```bash
curl http://127.0.0.1:18080/health
```

### Arbitrate

```bash
curl -X POST http://127.0.0.1:18080/v1/arbitrate \
  -H "Content-Type: application/json" \
  -d "{
    \"prompt\": \"Why is the sky blue?\",
    \"generator_models\": [\"gpt-4o-mini\", \"claude-3-5-haiku-latest\"],
    \"arbiter_model\": \"gpt-4o\",
    \"persist\": true
  }"
```

### History

```bash
curl http://127.0.0.1:18080/v1/runs
curl http://127.0.0.1:18080/v1/runs/<run_id>
curl http://127.0.0.1:18080/v1/config
```

Interactive docs: **http://127.0.0.1:18080/docs**

---

## 9. Using the CLI

```bash
arbitrate "Compare asyncio and threading in Python" \
  --models gpt-4o-mini,claude-3-5-haiku-latest \
  --arbiter gpt-4o \
  --persist

arbitrate "Explain CRDTs briefly" -m gpt-4o-mini -a gpt-4o -f json
```

| Flag | Purpose |
|------|---------|
| `-m / --models` | Comma-separated generators |
| `-a / --arbiter` | Arbiter model |
| `-s / --system` | System prompt |
| `-f json\|markdown` | Output format |
| `--persist` | Save to SQLite |

---

## 10. Using the Python library

```python
from llm_arbitration import arbitrate, ArbitrateRequest

result = arbitrate(
    ArbitrateRequest(
        prompt="What causes aurora borealis?",
        generator_models=["gpt-4o-mini", "claude-3-5-haiku-latest"],
        arbiter_model="gpt-4o",
    ),
    persist=True,
)

print(result.final_answer)
print(result.conflicts)
for c in result.candidates:
    print(c.model, c.error or f"{c.latency_ms:.0f}ms")
```

Keyword form also works: `arbitrate(prompt=..., generator_models=..., arbiter_model=...)`.

---

## 11. Synthesis policy (what the arbiter is told)

The arbiter system prompt encodes product rules:

- Prefer accurate, specific, well-supported content over verbosity.
- Merge complementary points into one coherent answer.
- On conflict: pick the better-supported claim and record the conflict.
- Do **not** invent facts absent from all candidates.
- Reply with **JSON only** matching the schema.

Changing behavior for your domain usually means editing `SYNTHESIS_SYSTEM` in `synthesize.py` (and optionally tightening JSON schema validation).

---

## 12. Failure modes & behavior

| Situation | Behavior |
|-----------|----------|
| Missing API key for a generator | That candidate has `error`; others continue |
| All generators fail | Empty `final_answer`; conflict explains why |
| Arbiter HTTP / parse failure | Fallback to first success + conflict note |
| API offline in UI | Pill shows offline; Run stays disabled |

---

## 13. Extending the system

**Add a provider** — extend `providers.py` with another HTTP branch (e.g. Gemini) and document the model-id convention.

**Stream progress** — today the API returns one JSON blob. For live per-model status, add SSE/WebSocket events from `generate.py`.

**Auth** — v1 has none. Put a reverse proxy / API gateway in front, or add FastAPI dependencies.

**Evals** — log `ArbitrateResult` rows and score `final_answer` against golden labels offline.

**Debate rounds** — out of scope for v1; would wrap synthesize in a critique → revise loop before the final merge.

---

## 14. Smoke checklist

1. `pip install -e .` and `npm install` / `npm run build` succeed.
2. `/health` returns `{"status":"ok"}`.
3. UI shows **API online**.
4. A two-model run returns `final_answer`, at least one candidate, and a row in History.
5. CLI `arbitrate "ping" -m gpt-4o-mini -a gpt-4o-mini -f json` prints JSON.
6. `scripts/smoke_test.py` passes (store + JSON parse, no network).

---

## 15. Design choices (why this shape)

- **One core, many surfaces** — avoids drift between UI and scripts.
- **httpx providers** — small dependency footprint vs a full multi-provider SDK.
- **Synthesize (not vote-only)** — produces a usable merged answer, not just a winner id.
- **SQLite** — zero-ops history for local/dev; swap the store later if you need multi-tenant scale.

You now have the mental model and the exact paths to change when customizing arbitration for your product.
