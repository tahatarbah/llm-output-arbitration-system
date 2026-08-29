"""Parallel fan-out generation across multiple models."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from llm_arbitration.models import CandidateResult
from llm_arbitration.providers import complete


def generate_candidates(
    *,
    prompt: str,
    models: list[str],
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout_s: float = 120.0,
) -> list[CandidateResult]:
    """Call each model in parallel; preserve input model order in the result."""
    if not models:
        return []

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    results_by_model: dict[str, CandidateResult] = {}

    def _run(model: str) -> CandidateResult:
        return complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )

    with ThreadPoolExecutor(max_workers=min(len(models), 8)) as pool:
        futures = {pool.submit(_run, model): model for model in models}
        for future in as_completed(futures):
            model = futures[future]
            try:
                results_by_model[model] = future.result()
            except Exception as exc:  # noqa: BLE001
                results_by_model[model] = CandidateResult(
                    model=model,
                    content=None,
                    error=str(exc),
                )

    return [results_by_model[m] for m in models]
