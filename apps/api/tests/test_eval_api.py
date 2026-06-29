from app.models.eval import EvalDataset, EvalQuestion, EvalResult, EvalRunStatus
from app.models.retrieval import RetrievalLog
import app.services.eval as eval_service
from app.services.eval import _answer_matches
from app.rag.providers.chat import ChatProviderResult
from tests.retrieval_test_helpers import seed_retrieval_chunk


class FakeEvalChatProvider:
    def generate_chat_completion(self, messages, temperature=0.1):
        """Return deterministic eval answers without external API calls."""

        return ChatProviderResult(
            content="Google Sycamore claimed quantum supremacy in 2019.",
            model="fake-eval-chat",
        )


class FakeNoAnswerChatProvider:
    def generate_chat_completion(self, messages, temperature=0.1):
        """Return a deterministic Chinese no-answer response."""

        return ChatProviderResult(
            content="根据所提供的知识库内容，无法说明公司本季度的销售收入。",
            model="fake-no-answer-chat",
        )


class FakeJudgeChatProvider:
    """Return a normal answer first, then a deterministic judge verdict."""

    def __init__(self) -> None:
        self.calls = 0

    def generate_chat_completion(self, messages, temperature=0.1):
        self.calls += 1
        if self.calls == 1:
            return ChatProviderResult(
                content="Sycamore made a narrow 2019 quantum supremacy claim.",
                model="fake-answer",
            )
        return ChatProviderResult(
            content='{"passed": true, "score": 1.0, "reason": "Covers the expected claim."}',
            model="fake-judge",
        )


class FakeBrokenJudgeChatProvider(FakeJudgeChatProvider):
    """Return invalid judge JSON after a valid generated answer."""

    def generate_chat_completion(self, messages, temperature=0.1):
        self.calls += 1
        if self.calls == 1:
            return ChatProviderResult(
                content="Sycamore made a narrow 2019 quantum supremacy claim.",
                model="fake-answer",
            )
        return ChatProviderResult(content="not json", model="fake-judge")


def test_eval_api_creates_dataset_and_question(api_client, sqlite_session_factory) -> None:
    """Eval API should create project-scoped datasets and questions."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-create",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset_response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Quantum Basics", "description": "Smoke eval set"},
    )

    assert dataset_response.status_code == 201
    dataset = dataset_response.json()
    assert dataset["name"] == "Quantum Basics"
    assert dataset["question_count"] == 0

    question_response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
            "should_answer": True,
        },
    )

    assert question_response.status_code == 201
    question = question_response.json()
    assert question["question"] == "What did Google Sycamore claim in 2019?"
    assert question["expected_document_id"] == str(document_id)
    assert question["expected_chunk_id"] == str(chunk_id)

    list_response = api_client.get(f"/api/projects/{project_id}/eval/datasets")
    assert list_response.status_code == 200
    assert list_response.json()[0]["question_count"] == 1


def test_eval_api_runs_dataset_and_records_metrics(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval runner should store per-question results and aggregate metrics."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-run",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Quantum Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    )

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeEvalChatProvider(),
    )

    run_response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "hybrid", "top_k": 3},
    )

    assert run_response.status_code == 201
    run = run_response.json()
    assert run["status"] == EvalRunStatus.completed
    assert run["metrics"]["question_count"] == 1
    assert run["metrics"]["hit_rate"] == 1.0
    assert run["metrics"]["citation_coverage_rate"] == 1.0
    assert run["metrics"]["answer_match_rate"] == 1.0
    assert run["metrics"]["refusal_rate"] == 0.0
    assert run["results"][0]["hit"] is True
    assert run["results"][0]["citation_covered"] is True
    assert run["results"][0]["answer_matched"] is True
    assert run["results"][0]["retrieval_latency_ms"] >= 0

    with sqlite_session_factory() as db:
        assert db.query(EvalDataset).count() == 1
        assert db.query(EvalQuestion).count() == 1
        assert db.query(EvalResult).count() == 1


def test_eval_api_passes_reranker_options_to_retrieval(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval runs should be able to compare retrieval with reranking enabled."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-rerank",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Reranker Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    )

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeEvalChatProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={
            "retrieval_mode": "hybrid",
            "top_k": 3,
            "reranker_enabled": True,
            "reranker_candidate_limit": 10,
        },
    )

    assert response.status_code == 201
    with sqlite_session_factory() as db:
        log = db.query(RetrievalLog).one()
        assert log.retrieval_metadata["reranker_enabled"] is True
        assert log.retrieval_metadata["reranker"] == "keyword_overlap"


def test_eval_api_can_run_llm_judge(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval runs should optionally store LLM judge verdicts and metrics."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-judge",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Judge Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    )

    provider = FakeJudgeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )
    monkeypatch.setattr(eval_service, "get_eval_judge_provider", lambda: provider, raising=False)

    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "hybrid", "top_k": 3, "judge_enabled": True},
    )

    assert response.status_code == 201
    run = response.json()
    result_metadata = run["results"][0]["result_metadata"]
    assert run["metrics"]["judge_match_rate"] == 1.0
    assert result_metadata["judge_enabled"] is True
    assert result_metadata["judge_passed"] is True
    assert result_metadata["judge_score"] == 1.0
    assert result_metadata["judge_reason"] == "Covers the expected claim."


def test_eval_api_records_judge_errors_without_failing_run(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Invalid judge output should be recorded while preserving the eval run."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-judge-error",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Judge Error Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    )

    provider = FakeBrokenJudgeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )
    monkeypatch.setattr(eval_service, "get_eval_judge_provider", lambda: provider, raising=False)

    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "hybrid", "top_k": 3, "judge_enabled": True},
    )

    assert response.status_code == 201
    run = response.json()
    result_metadata = run["results"][0]["result_metadata"]
    assert run["status"] == EvalRunStatus.completed
    assert result_metadata["judge_enabled"] is True
    assert "judge_error" in result_metadata


def test_eval_api_lists_and_gets_run_history(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval API should expose run history and per-run details."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-history",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        other_project, _, _ = seed_retrieval_chunk(
            db,
            "eval-history-other",
            "Other project content.",
            [0.2] * 1024,
        )
        db.commit()
        project_id = project.id
        other_project_id = other_project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "History Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeEvalChatProvider(),
    )

    first_run = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "hybrid", "top_k": 3},
    ).json()
    second_run = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "keyword", "top_k": 5},
    ).json()

    list_response = api_client.get(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs"
    )
    detail_response = api_client.get(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs/{second_run['id']}"
    )
    cross_project_response = api_client.get(
        f"/api/projects/{other_project_id}/eval/datasets/{dataset['id']}/runs/{first_run['id']}"
    )

    assert list_response.status_code == 200
    runs = list_response.json()
    assert {run["id"] for run in runs} == {second_run["id"], first_run["id"]}
    assert runs[0]["result_count"] == 1
    assert "results" not in runs[0]
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == second_run["id"]
    assert detail["results"][0]["question"] == "What did Google Sycamore claim in 2019?"
    assert cross_project_response.status_code == 404


def test_eval_api_lists_and_deletes_questions_and_datasets(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval API should list/delete questions and delete datasets with owned runs."""

    with sqlite_session_factory() as db:
        project, document, chunk = seed_retrieval_chunk(
            db,
            "eval-manage",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        other_project, _, _ = seed_retrieval_chunk(
            db,
            "eval-manage-other",
            "Other project content.",
            [0.2] * 1024,
        )
        db.commit()
        project_id = project.id
        other_project_id = other_project.id
        document_id = document.id
        chunk_id = chunk.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Manage Eval"},
    ).json()
    question_one = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "What did Google Sycamore claim in 2019?",
            "expected_document_id": str(document_id),
            "expected_chunk_id": str(chunk_id),
            "expected_answer_notes": "quantum supremacy",
        },
    ).json()
    question_two = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={"question": "Second question"},
    ).json()

    list_response = api_client.get(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions"
    )
    cross_delete_question = api_client.delete(
        f"/api/projects/{other_project_id}/eval/datasets/{dataset['id']}/questions/{question_one['id']}"
    )
    delete_question = api_client.delete(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions/{question_two['id']}"
    )
    list_after_delete = api_client.get(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions"
    )

    assert list_response.status_code == 200
    assert [question["id"] for question in list_response.json()] == [
        question_one["id"],
        question_two["id"],
    ]
    assert cross_delete_question.status_code == 404
    assert delete_question.status_code == 204
    assert [question["id"] for question in list_after_delete.json()] == [question_one["id"]]

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeEvalChatProvider(),
    )
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "hybrid", "top_k": 3},
    )

    cross_delete_dataset = api_client.delete(
        f"/api/projects/{other_project_id}/eval/datasets/{dataset['id']}"
    )
    delete_dataset = api_client.delete(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}"
    )
    list_datasets = api_client.get(f"/api/projects/{project_id}/eval/datasets")

    assert cross_delete_dataset.status_code == 404
    assert delete_dataset.status_code == 204
    assert list_datasets.json() == []
    with sqlite_session_factory() as db:
        assert db.query(EvalDataset).count() == 0
        assert db.query(EvalQuestion).count() == 0
        assert db.query(EvalResult).count() == 0


def test_eval_api_rejects_empty_dataset_run(api_client, sqlite_session_factory) -> None:
    """Eval runner should reject datasets without questions."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "eval-empty",
            "Google Sycamore claimed quantum supremacy in 2019.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Empty Eval"},
    ).json()

    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "keyword", "top_k": 3},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Eval dataset has no questions"


def test_eval_api_detects_chinese_no_answer_refusal(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Eval runner should count Chinese no-answer responses as refusals."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "eval-refusal",
            "This document is about quantum computing only.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Refusal Eval"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "quantum computing 文档是否说明了公司本季度的销售收入？",
            "should_answer": False,
        },
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeNoAnswerChatProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "keyword", "top_k": 3},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["metrics"]["refusal_rate"] == 1.0
    assert run["metrics"]["answer_match_rate"] == 1.0
    assert run["results"][0]["refused"] is True
    assert run["results"][0]["answer_matched"] is True
    assert run["results"][0]["score"] == 1.0


def test_answer_matching_handles_multilingual_eval_notes() -> None:
    """Answer matching should handle semicolon notes and common Chinese equivalents."""

    sycamore_answer = (
        "Google 的 Sycamore 处理器与 2019 年的量子霸权声明相关，"
        "不应该被误解为通用商业优势，也不能证明 Sycamore 能破解加密。"
    )
    lantern_answer = (
        "Project Lantern 是后量子密码敏捷性迁移项目；"
        "Project Atlas 是数据平台索引项目，负责文档摄取质量指标。"
    )
    support_answer = (
        "LSR-104 建议先检查 API 服务是否可达，确认 /health 能正常响应；"
        "它不是 DeepSeek、Ollama 或 embedding 质量导致的。"
    )

    assert _answer_matches(
        sycamore_answer,
        "Sycamore; 2019 quantum supremacy; not break encryption",
    )
    assert _answer_matches(
        lantern_answer,
        "Lantern cryptographic agility; Atlas data indexing",
    )
    assert _answer_matches(
        support_answer,
        "API reachability; /health; not DeepSeek Ollama embedding",
    )


def test_answer_matching_handles_real_chinese_eval_answers() -> None:
    """Answer matching should accept real provider wording from local eval runs."""

    sycamore_answer = (
        "Google 的 Sycamore 在这些资料中与 2019 年的量子霸权声明"
        "（quantum supremacy claim）相关。这个成果不应被误解为通用商业优势，"
        "也不应被误解为能够破解加密。"
    )
    lantern_answer = (
        "Project Lantern 是内部的后量子迁移项目，负责加密敏捷性，包括库存管理、"
        "密钥交换、证书轮换及支持文档。Project Atlas 是一个独立的数据平台索引计划，"
        "主导文档摄入质量指标，不涉及加密标准。"
    )
    support_answer = (
        "根据 LSR-104 的记录，页面报 failed to fetch 时，建议首先检查 API 服务是否可访问。"
        "具体措施是重启 API 服务，并确认 /health 端点能够正常响应后再进行测试。"
        "该问题并非由模型提供商故障，如 DeepSeek、Ollama，或嵌入质量所导致。"
    )
    ibm_answer = (
        "IBM Osprey 是一款 433 量子比特的超导处理器，主要用于规模演示。"
        "IBM Heron 则被描述为一种模块化架构，专门与模块化扩展计划绑定。"
    )

    assert _answer_matches(
        sycamore_answer,
        "Sycamore; 2019 quantum supremacy; not break encryption",
    )
    assert _answer_matches(
        lantern_answer,
        "Lantern cryptographic agility; Atlas data indexing",
    )
    assert _answer_matches(
        support_answer,
        "API reachability; /health; not DeepSeek Ollama embedding",
    )
    assert _answer_matches(
        ibm_answer,
        "Osprey 433-qubit processor; Heron modular scale-out",
    )
