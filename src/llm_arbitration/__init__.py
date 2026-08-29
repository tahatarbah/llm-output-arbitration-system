"""LLM output arbitration: generate from many models, synthesize one answer."""

from llm_arbitration.models import ArbitrateRequest, ArbitrateResult
from llm_arbitration.pipeline import arbitrate

__all__ = ["arbitrate", "ArbitrateRequest", "ArbitrateResult"]
__version__ = "0.1.0"
