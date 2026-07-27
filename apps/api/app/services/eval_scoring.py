"""Answer matching, refusal detection, and metrics aggregation for eval runs."""

import re

from app.models.eval import EvalResult
from app.rag.answering import NO_ANSWER_MESSAGE


def answer_matches(answer: str, expected_notes: str | None) -> bool:
    """Check whether answer covers each semicolon-separated expected point."""

    if not expected_notes:
        return True
    answer_text = _normalize_eval_text(answer)
    expected_points = [
        point.strip()
        for point in re.split(r"[;\n]+", expected_notes)
        if point.strip()
    ]
    if not expected_points:
        return True
    return all(_expected_point_matches(answer_text, point) for point in expected_points)


def _expected_point_matches(answer_text: str, expected_point: str) -> bool:
    """Match one expected point using phrase, token, or known bilingual aliases."""

    normalized_point = _normalize_eval_text(expected_point)
    if normalized_point in answer_text:
        return True

    aliases = _EVAL_MATCH_ALIASES.get(normalized_point)
    if aliases and any(_normalize_eval_text(alias) in answer_text for alias in aliases):
        return True

    tokens = _eval_tokens(normalized_point)
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in answer_text)
    required = len(tokens) if len(tokens) <= 2 else len(tokens) - 1
    return matched >= required


def _normalize_eval_text(text: str) -> str:
    """Normalize punctuation and casing for lightweight answer matching."""

    return re.sub(r"\s+", " ", text.casefold()).strip()


def _eval_tokens(text: str) -> list[str]:
    """Extract alphanumeric tokens from expected notes."""

    return re.findall(r"[a-z0-9][a-z0-9_+.-]*", text.casefold())


_EVAL_MATCH_ALIASES = {
    "2019 quantum supremacy": ["2019 年的量子霸权", "2019 年量子霸权", "2019 quantum supremacy"],
    "not break encryption": [
        "不能证明 sycamore 能破解加密",
        "不能证明 sycamore 能够破解加密",
        "不能破解加密",
        "不应被误解为能够破解加密",
        "不得被描述为 sycamore 可以破解加密的证明",
        "不是证明 sycamore 可以破解加密",
        "not proof that sycamore can break encryption",
    ],
    "general-purpose business advantage": ["通用商业优势", "通用的商业优势"],
    "lantern cryptographic agility": [
        "lantern 是后量子密码敏捷性迁移项目",
        "lantern 是后量子密码迁移项目",
        "lantern 聚焦后量子密码迁移",
        "lantern 是内部的后量子迁移项目，负责加密敏捷性",
        "负责加密敏捷性",
        "cryptographic-agility migration",
    ],
    "atlas data indexing": [
        "atlas 是数据平台索引项目",
        "atlas 是一个独立的数据平台索引计划",
        "atlas 聚焦数据索引",
        "数据平台索引和质量指标",
        "atlas owns document ingestion quality metrics",
    ],
    "api reachability": [
        "api 服务是否可达",
        "api服务是否可达",
        "api 服务是否可访问",
        "api 可达",
        "api reachability",
    ],
    "not deepseek ollama embedding": [
        "不是 deepseek、ollama 或 embedding 质量导致",
        "并非由模型提供商故障，如 deepseek、ollama，或嵌入质量所导致",
        "不是由模型提供商故障",
        "不是 deepseek ollama embedding",
        "not caused by deepseek ollama embedding",
        "not model-provider failure",
    ],
    "local embeddings bge-m3": ["local embedding", "local embeddings", "bge-m3", "本地 embedding"],
    "cloud chat": ["cloud chat", "云 chat", "云端 chat", "云模型"],
    "local chat memory latency postponed": [
        "local chat models were postponed",
        "local chat 延后",
        "本地 chat models were postponed",
        "更高的内存和延迟要求",
    ],
    "osprey 433-qubit processor": [
        "osprey 433",
        "433量子比特",
        "433 量子比特",
        "433-qubit",
    ],
    "heron modular scale-out": [
        "heron 与模块化规模扩展",
        "heron 与模块化扩展",
        "heron 则被描述为一种模块化架构",
        "模块化扩展计划绑定",
        "heron is the modular architecture",
        "modular scale-out",
    ],
}


def is_refusal(answer: str) -> bool:
    """Detect local or provider no-answer refusals."""

    lowered = answer.casefold()
    refusal_markers = [
        NO_ANSWER_MESSAGE.casefold(),
        "cannot answer",
        "can't answer",
        "无法回答",
        "无法从当前知识库回答",
        "无法说明",
        "没有相关信息",
        "没有关于",
        "未提及",
    ]
    return any(marker in lowered for marker in refusal_markers)


def aggregate_metrics(results: list[EvalResult]) -> dict:
    """Summarize eval results into portfolio-friendly metrics."""

    count = len(results)
    if count == 0:
        return {
            "question_count": 0,
            "hit_rate": 0.0,
            "citation_coverage_rate": 0.0,
            "answer_match_rate": 0.0,
            "refusal_rate": 0.0,
            "avg_retrieval_latency_ms": 0.0,
        }
    retrieval_latencies = [
        result.retrieval_latency_ms
        for result in results
        if result.retrieval_latency_ms is not None
    ]
    judged_results = [
        result
        for result in results
        if result.result_metadata.get("judge_enabled") is True
        and "judge_passed" in result.result_metadata
    ]
    return {
        "question_count": count,
        "hit_rate": sum(1 for result in results if result.hit) / count,
        "citation_coverage_rate": (
            sum(1 for result in results if result.citation_covered) / count
        ),
        "answer_match_rate": (
            sum(1 for result in results if result.result_metadata.get("answer_matched"))
            / count
        ),
        "refusal_rate": sum(1 for result in results if result.refused) / count,
        "avg_retrieval_latency_ms": (
            sum(retrieval_latencies) / len(retrieval_latencies)
            if retrieval_latencies
            else 0.0
        ),
        "judge_match_rate": (
            sum(1 for result in judged_results if result.result_metadata.get("judge_passed") is True)
            / len(judged_results)
            if judged_results
            else 0.0
        ),
    }
