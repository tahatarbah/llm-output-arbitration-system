"""Arbiter synthesis: merge candidates into one structured answer."""

from __future__ import annotations

import json
import re
from typing import Any

from llm_arbitration.models import (
    Attribution,
    CandidateResult,
    SynthesisPayload,
    TokenUsage,
)
from llm_arbitration.providers import complete

SYNTHESIS_SYSTEM = """You are an expert arbiter. Multiple language models answered the same user prompt.
Your job is to SYNTHESIZE a single best answer by merging the strongest parts of their responses.

Rules:
- Prefer accurate, specific, well-supported content over verbosity.
- Merge complementary points into one coherent answer.
- When candidates conflict, pick the better-supported claim and record the conflict.
- Do not invent facts that are absent from all candidates.
- Return ONLY valid JSON matching this schema (no markdown fences):
{
  "final_answer": "<merged answer as a string>",
  "conflicts": ["<description of disagreement>", ...],
  "attributions": [{"model": "<model id>", "contribution": "<what was taken from this candidate>"}, ...]
}
Include an attribution entry for each successful candidate that contributed something useful.
If there were no meaningful conflicts, return an empty conflicts array."""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        return json.loads(fence.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Could not parse JSON from arbiter response")


def _build_user_message(
    prompt: str,
    candidates: list[CandidateResult],
    failures: list[CandidateResult],
) -> str:
    parts = [f"## Original user prompt\n{prompt}\n"]
    parts.append("## Candidate answers\n")
    for i, c in enumerate(candidates, start=1):
        parts.append(f"### Candidate {i} — model: `{c.model}`\n{c.content or ''}\n")
    if failures:
        names = ", ".join(f"`{f.model}` ({f.error})" for f in failures)
        parts.append(f"## Failed generators\nThe following models failed and must be ignored: {names}\n")
    parts.append(
        "Synthesize the best merged answer. Respond with JSON only "
        '(keys: final_answer, conflicts, attributions).'
    )
    return "\n".join(parts)


def _to_payload(data: dict[str, Any]) -> SynthesisPayload:
    attributions_raw = data.get("attributions") or []
    attributions: list[Attribution] = []
    for item in attributions_raw:
        if isinstance(item, dict):
            attributions.append(
                Attribution(
                    model=str(item.get("model", "")),
                    contribution=str(item.get("contribution", "")),
                )
            )
    conflicts = data.get("conflicts") or []
    if not isinstance(conflicts, list):
        conflicts = [str(conflicts)]
    return SynthesisPayload(
        final_answer=str(data.get("final_answer", "")),
        conflicts=[str(c) for c in conflicts],
        attributions=attributions,
    )


def synthesize(
    *,
    prompt: str,
    candidates: list[CandidateResult],
    arbiter_model: str,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    timeout_s: float = 120.0,
) -> tuple[SynthesisPayload, TokenUsage, float, str | None]:
    """
    Run the arbiter model over successful candidates.

    Returns (payload, usage, latency_ms, error).
    On total failure, returns a fallback payload built from the first success.
    """
    successes = [c for c in candidates if c.content and not c.error]
    failures = [c for c in candidates if c.error or not c.content]

    if not successes:
        return (
            SynthesisPayload(
                final_answer="",
                conflicts=["All generator models failed; nothing to synthesize."],
                attributions=[],
            ),
            TokenUsage(),
            0.0,
            "No successful candidates to synthesize",
        )

    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {
            "role": "user",
            "content": _build_user_message(prompt, successes, failures),
        },
    ]

    result = complete(
        model=arbiter_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )

    if result.error or not result.content:
        fallback = SynthesisPayload(
            final_answer=successes[0].content or "",
            conflicts=["Arbiter failed; returned first successful candidate as fallback."],
            attributions=[
                Attribution(model=successes[0].model, contribution="Used as fallback answer")
            ],
        )
        return fallback, result.usage, result.latency_ms, result.error or "Empty arbiter response"

    try:
        payload = _to_payload(_extract_json(result.content))
        return payload, result.usage, result.latency_ms, None
    except (json.JSONDecodeError, ValueError, TypeError):
        # One repair retry
        repair_messages = messages + [
            {"role": "assistant", "content": result.content},
            {
                "role": "user",
                "content": (
                    "Your previous reply was not valid JSON. "
                    "Reply again with ONLY valid JSON matching the schema."
                ),
            },
        ]
        retry = complete(
            model=arbiter_model,
            messages=repair_messages,
            temperature=0.0,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        combined_usage = result.usage.add(retry.usage)
        combined_latency = result.latency_ms + retry.latency_ms
        if retry.error or not retry.content:
            fallback = SynthesisPayload(
                final_answer=successes[0].content or "",
                conflicts=["Arbiter JSON parse failed; returned first successful candidate."],
                attributions=[
                    Attribution(
                        model=successes[0].model,
                        contribution="Used as fallback after parse failure",
                    )
                ],
            )
            return fallback, combined_usage, combined_latency, retry.error or "Parse repair failed"
        try:
            payload = _to_payload(_extract_json(retry.content))
            return payload, combined_usage, combined_latency, None
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            fallback = SynthesisPayload(
                final_answer=successes[0].content or "",
                conflicts=["Arbiter JSON parse failed; returned first successful candidate."],
                attributions=[
                    Attribution(
                        model=successes[0].model,
                        contribution="Used as fallback after parse failure",
                    )
                ],
            )
            return fallback, combined_usage, combined_latency, str(exc)
