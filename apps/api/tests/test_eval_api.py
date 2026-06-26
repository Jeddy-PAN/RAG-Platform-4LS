from app.models.eval import EvalDataset, EvalQuestion, EvalResult, EvalRunStatus
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
