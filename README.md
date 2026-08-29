# LLM Output Arbitration

Fan out a prompt to multiple LLMs, then synthesize one merged answer with conflict notes and attributions.

Providers: OpenAI-compatible and Anthropic APIs via `httpx` (keys from `.env`).

Surfaces (same core engine):

- **Library** — `from llm_arbitration import arbitrate`
- **CLI** — `arbitrate "prompt" --models a,b --arbiter c`
- **API** — FastAPI at `/v1/arbitrate`
- **Web UI** — React app (dev via Vite, or served by the API after build)

**Full walkthrough:** [docs/TECHNICAL_TUTORIAL.md](docs/TECHNICAL_TUTORIAL.md)

## Setup

```bash
# Python (from repo root)
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -e .

cp .env.example .env
# Edit .env and set OPENAI_API_KEY and/or ANTHROPIC_API_KEY

cd apps/web
npm install
npm run build
```

## Run (UI + API together)

After `npm run build`, the API serves the UI from `apps/web/dist`:

```bash
# from repo root, venv active
uvicorn apps.api.main:app --host 127.0.0.1 --port 18080
```

Open **http://127.0.0.1:18080/** — use the form to run arbitrations and browse history.

API docs: http://127.0.0.1:18080/docs

If a port is blocked on Windows, pick another free port.

## Dev mode (hot reload UI)

```bash
# terminal 1
uvicorn apps.api.main:app --host 127.0.0.1 --port 18080

# terminal 2
cd apps/web
npm run dev
```

Optional: set `VITE_API_PROXY=http://127.0.0.1:18080` if you change the API port.

## CLI

```bash
arbitrate "Compare asyncio and threading in Python" \
  --models gpt-4o-mini,claude-3-5-haiku-latest \
  --arbiter gpt-4o \
  --persist

arbitrate "Explain CRDTs briefly" -m gpt-4o-mini -a gpt-4o -f json
```

## Library

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
```

## API

`POST /v1/arbitrate`

```json
{
  "prompt": "Why is the sky blue?",
  "generator_models": ["gpt-4o-mini", "claude-3-5-haiku-latest"],
  "arbiter_model": "gpt-4o",
  "persist": true
}
```

- `GET /v1/runs` — run history summaries
- `GET /v1/runs/{run_id}` — full result
- `GET /v1/config` — default models
- `GET /health` — liveness

No auth in v1. Put a reverse proxy (or API gateway) in front for production.

## Model ids

- OpenAI-compatible: `gpt-4o`, `gpt-4o-mini`, or any model on `OPENAI_BASE_URL`
- Anthropic: `claude-3-5-haiku-latest`, `claude-sonnet-4-5`, or `anthropic/...`

Keys are read from the server/CLI environment — the browser never sees them.
