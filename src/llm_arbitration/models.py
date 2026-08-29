"""Pydantic schemas for arbitration requests and results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_run_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class CandidateResult(BaseModel):
    model: str
    content: str | None = None
    latency_ms: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    error: str | None = None


class Attribution(BaseModel):
    model: str
    contribution: str


class ArbitrateRequest(BaseModel):
    prompt: str
    generator_models: list[str]
    arbiter_model: str
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_s: float = 120.0


class ArbitrateResult(BaseModel):
    run_id: str = Field(default_factory=new_run_id)
    prompt: str
    system_prompt: str | None = None
    generator_models: list[str]
    arbiter_model: str
    final_answer: str
    conflicts: list[str] = Field(default_factory=list)
    attributions: list[Attribution] = Field(default_factory=list)
    candidates: list[CandidateResult] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    created_at: datetime = Field(default_factory=utc_now)
    meta: dict[str, Any] = Field(default_factory=dict)


class SynthesisPayload(BaseModel):
    """Expected JSON shape from the arbiter model."""

    final_answer: str
    conflicts: list[str] = Field(default_factory=list)
    attributions: list[Attribution] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    prompt: str
    arbiter_model: str
    generator_models: list[str]
    created_at: datetime
    final_answer_preview: str
