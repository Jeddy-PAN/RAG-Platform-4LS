import json
from dataclasses import dataclass

from app.rag.providers.chat import ChatProviderError, OpenAIChatProvider


@dataclass(frozen=True)
class EvalJudgeResult:
    """Normalized LLM judge verdict for one eval answer."""

    passed: bool
    score: float
    reason: str
    model: str
    raw_response: str


def get_eval_judge_provider() -> OpenAIChatProvider:
    """Build the provider used by optional eval judging."""

    return OpenAIChatProvider.from_settings()


def judge_answer(
    question: str,
    expected_notes: str | None,
    answer: str,
    should_answer: bool,
    provider=None,
) -> EvalJudgeResult:
    """Ask a chat model to judge whether an eval answer satisfies expectations."""

    judge_provider = provider or get_eval_judge_provider()
    response = judge_provider.generate_chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "You are a strict RAG evaluation judge. Return only JSON with "
                    'keys "passed", "score", and "reason". Score must be 0 or 1. '
                    "Judge whether the answer satisfies the expected notes. For "
                    "no-answer questions, pass only if the answer clearly refuses."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Should answer: {should_answer}\n\n"
                    f"Expected notes:\n{expected_notes or ''}\n\n"
                    f"Actual answer:\n{answer}"
                ),
            },
        ],
        temperature=0.0,
    )
    try:
        payload = json.loads(response.content)
        passed = bool(payload["passed"])
        score = float(payload.get("score", 1.0 if passed else 0.0))
        reason = str(payload.get("reason", "")).strip()
    except Exception as exc:
        raise ChatProviderError("Eval judge returned invalid JSON") from exc

    return EvalJudgeResult(
        passed=passed,
        score=max(0.0, min(1.0, score)),
        reason=reason,
        model=response.model,
        raw_response=response.content,
    )
