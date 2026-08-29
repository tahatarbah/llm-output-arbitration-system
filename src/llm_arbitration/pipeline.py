"""Orchestrate generate → synthesize into a full ArbitrateResult."""

from __future__ import annotations

from llm_arbitration.generate import generate_candidates
from llm_arbitration.models import ArbitrateRequest, ArbitrateResult, TokenUsage, new_run_id
from llm_arbitration.synthesize import synthesize


def arbitrate(
    request: ArbitrateRequest | None = None,
    *,
    prompt: str | None = None,
    generator_models: list[str] | None = None,
    arbiter_model: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout_s: float = 120.0,
    persist: bool = False,
    database_url: str | None = None,
) -> ArbitrateResult:
    """
    Run parallel generation then arbiter synthesis.

    Accepts either an ArbitrateRequest or keyword arguments.
    When persist=True, saves the result via the SQLite store.
    """
    if request is None:
        if not prompt or not generator_models or not arbiter_model:
            raise ValueError(
                "Provide ArbitrateRequest or prompt, generator_models, and arbiter_model"
            )
        request = ArbitrateRequest(
            prompt=prompt,
            generator_models=generator_models,
            arbiter_model=arbiter_model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )

    if not request.generator_models:
        raise ValueError("generator_models must not be empty")

    candidates = generate_candidates(
        prompt=request.prompt,
        models=request.generator_models,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout_s=request.timeout_s,
    )

    payload, arbiter_usage, arbiter_latency_ms, arbiter_error = synthesize(
        prompt=request.prompt,
        candidates=candidates,
        arbiter_model=request.arbiter_model,
        temperature=min(request.temperature, 0.3),
        max_tokens=request.max_tokens,
        timeout_s=request.timeout_s,
    )

    usage = TokenUsage()
    for c in candidates:
        usage = usage.add(c.usage)
    usage = usage.add(arbiter_usage)

    result = ArbitrateResult(
        run_id=new_run_id(),
        prompt=request.prompt,
        system_prompt=request.system_prompt,
        generator_models=list(request.generator_models),
        arbiter_model=request.arbiter_model,
        final_answer=payload.final_answer,
        conflicts=payload.conflicts,
        attributions=payload.attributions,
        candidates=candidates,
        usage=usage,
        meta={
            "arbiter_latency_ms": arbiter_latency_ms,
            "arbiter_error": arbiter_error,
        },
    )

    if persist:
        from llm_arbitration.store import RunStore

        store = RunStore(database_url)
        store.save(result)

    return result
