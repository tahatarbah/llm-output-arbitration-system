from pathlib import Path
import tempfile

from llm_arbitration.models import (
    ArbitrateResult,
    Attribution,
    CandidateResult,
    TokenUsage,
)
from llm_arbitration.store import RunStore
from llm_arbitration.synthesize import _extract_json, _to_payload


def main() -> None:
    raw = (
        '{"final_answer":"hi","conflicts":[],'
        '"attributions":[{"model":"m","contribution":"c"}]}'
    )
    payload = _to_payload(_extract_json(raw))
    assert payload.final_answer == "hi"

    db = Path(tempfile.mkdtemp()) / "t.db"
    store = RunStore(f"sqlite:///{db.as_posix()}")
    result = ArbitrateResult(
        prompt="p",
        generator_models=["a"],
        arbiter_model="b",
        final_answer="ans",
        candidates=[CandidateResult(model="a", content="x")],
        attributions=[Attribution(model="a", contribution="x")],
        usage=TokenUsage(total_tokens=1),
    )
    store.save(result)
    got = store.get(result.run_id)
    assert got is not None and got.final_answer == "ans"
    assert store.list_runs()[0].run_id == result.run_id
    print("smoke ok")


if __name__ == "__main__":
    main()
