"""CLI entrypoint: arbitrate \"prompt\" --models a,b --arbiter c."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from llm_arbitration.models import ArbitrateRequest
from llm_arbitration.pipeline import arbitrate


def _default_models() -> list[str]:
    raw = os.getenv("DEFAULT_GENERATOR_MODELS", "gpt-4o-mini")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _default_arbiter() -> str:
    return os.getenv("DEFAULT_ARBITER_MODEL", "gpt-4o")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arbitrate",
        description="Fan out a prompt to multiple LLMs and synthesize one answer.",
    )
    parser.add_argument("prompt", help="User prompt to arbitrate")
    parser.add_argument(
        "--models",
        "-m",
        default=None,
        help="Comma-separated generator model ids (default: DEFAULT_GENERATOR_MODELS)",
    )
    parser.add_argument(
        "--arbiter",
        "-a",
        default=None,
        help="Arbiter model id (default: DEFAULT_ARBITER_MODEL)",
    )
    parser.add_argument("--system", "-s", default=None, help="Optional system prompt")
    parser.add_argument("--temperature", "-t", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--format",
        "-f",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Save the run to the SQLite store",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLite URL when --persist is set",
    )
    return parser


def format_markdown(result) -> str:
    lines = [
        f"# Arbitration `{result.run_id}`",
        "",
        f"**Arbiter:** `{result.arbiter_model}`  ",
        f"**Generators:** {', '.join(f'`{m}`' for m in result.generator_models)}",
        "",
        "## Final answer",
        "",
        result.final_answer or "_(empty)_",
        "",
    ]
    if result.conflicts:
        lines.extend(["## Conflicts", ""])
        for c in result.conflicts:
            lines.append(f"- {c}")
        lines.append("")
    if result.attributions:
        lines.extend(["## Attributions", ""])
        for a in result.attributions:
            lines.append(f"- **{a.model}:** {a.contribution}")
        lines.append("")
    lines.extend(["## Candidates", ""])
    for cand in result.candidates:
        status = "error" if cand.error else f"{cand.latency_ms:.0f} ms"
        lines.append(f"### `{cand.model}` ({status})")
        lines.append("")
        if cand.error:
            lines.append(f"Error: {cand.error}")
        else:
            lines.append(cand.content or "_(empty)_")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    models_raw = args.models
    models = (
        [m.strip() for m in models_raw.split(",") if m.strip()]
        if models_raw
        else _default_models()
    )
    arbiter = args.arbiter or _default_arbiter()

    request = ArbitrateRequest(
        prompt=args.prompt,
        generator_models=models,
        arbiter_model=arbiter,
        system_prompt=args.system,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout,
    )

    try:
        result = arbitrate(
            request,
            persist=args.persist,
            database_url=args.database_url,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print(format_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
