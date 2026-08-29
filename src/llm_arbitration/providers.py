"""Multi-provider chat completions via httpx (OpenAI + Anthropic)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm_arbitration.models import CandidateResult, TokenUsage


def _usage_from_openai(data: dict[str, Any]) -> TokenUsage:
    usage = data.get("usage") or {}
    return TokenUsage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
    )


def _usage_from_anthropic(data: dict[str, Any]) -> TokenUsage:
    usage = data.get("usage") or {}
    prompt = int(usage.get("input_tokens") or 0)
    completion = int(usage.get("output_tokens") or 0)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def _is_anthropic(model: str) -> bool:
    m = model.lower()
    return m.startswith("claude") or m.startswith("anthropic/")


def _normalize_anthropic_model(model: str) -> str:
    if model.startswith("anthropic/"):
        return model.split("/", 1)[1]
    return model


def _normalize_openai_model(model: str) -> str:
    if model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _split_system(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
    system: str | None = None
    rest: list[dict[str, str]] = []
    for msg in messages:
        if msg.get("role") == "system" and system is None:
            system = msg.get("content")
        else:
            rest.append(msg)
    return system, rest


def _openai_complete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
    timeout_s: float,
) -> CandidateResult:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return CandidateResult(
            model=model,
            error="OPENAI_API_KEY is not set",
        )
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload: dict[str, Any] = {
        "model": _normalize_openai_model(model),
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            res = client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        if res.status_code >= 400:
            return CandidateResult(
                model=model,
                latency_ms=latency_ms,
                error=f"OpenAI HTTP {res.status_code}: {res.text[:500]}",
            )
        data = res.json()
        content = ""
        choices = data.get("choices") or []
        if choices:
            content = str((choices[0].get("message") or {}).get("content") or "")
        return CandidateResult(
            model=model,
            content=content,
            latency_ms=latency_ms,
            usage=_usage_from_openai(data),
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000
        return CandidateResult(model=model, latency_ms=latency_ms, error=str(exc))


def _anthropic_complete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
    timeout_s: float,
) -> CandidateResult:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return CandidateResult(
            model=model,
            error="ANTHROPIC_API_KEY is not set",
        )
    base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    system, rest = _split_system(messages)
    payload: dict[str, Any] = {
        "model": _normalize_anthropic_model(model),
        "messages": rest,
        "temperature": temperature,
        "max_tokens": max_tokens if max_tokens is not None else 4096,
    }
    if system:
        payload["system"] = system

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            res = client.post(
                f"{base}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        if res.status_code >= 400:
            return CandidateResult(
                model=model,
                latency_ms=latency_ms,
                error=f"Anthropic HTTP {res.status_code}: {res.text[:500]}",
            )
        data = res.json()
        parts = data.get("content") or []
        text_parts = [
            str(p.get("text", ""))
            for p in parts
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return CandidateResult(
            model=model,
            content="".join(text_parts),
            latency_ms=latency_ms,
            usage=_usage_from_anthropic(data),
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000
        return CandidateResult(model=model, latency_ms=latency_ms, error=str(exc))


def complete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout_s: float = 120.0,
) -> CandidateResult:
    """Run a single chat completion and return a CandidateResult."""
    if _is_anthropic(model):
        return _anthropic_complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    return _openai_complete(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )
