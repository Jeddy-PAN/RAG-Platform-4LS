import pytest

from app.rag.providers.chat import ChatProviderError, ChatProviderResult
from app.services.eval_judge import judge_answer


class StaticJudgeProvider:
    """Minimal provider stub for eval judge parsing tests."""

    def __init__(self, content: str) -> None:
        self.content = content

    def generate_chat_completion(self, messages, temperature=0.1):
        return ChatProviderResult(content=self.content, model="judge-test")


def test_judge_answer_parses_strict_json_verdict() -> None:
    """Judge helper should normalize valid JSON verdicts."""

    result = judge_answer(
        question="What did Sycamore claim?",
        expected_notes="quantum supremacy",
        answer="Sycamore claimed quantum supremacy.",
        should_answer=True,
        provider=StaticJudgeProvider(
            '{"passed": true, "score": 1, "reason": "The answer is grounded."}'
        ),
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.reason == "The answer is grounded."
    assert result.model == "judge-test"


def test_judge_answer_rejects_invalid_json() -> None:
    """Invalid judge responses should raise provider errors for caller handling."""

    with pytest.raises(ChatProviderError, match="invalid JSON"):
        judge_answer(
            question="What did Sycamore claim?",
            expected_notes="quantum supremacy",
            answer="Sycamore claimed quantum supremacy.",
            should_answer=True,
            provider=StaticJudgeProvider("pass"),
        )
