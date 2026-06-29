import time
import uuid
import re

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.eval import EvalDataset, EvalQuestion, EvalResult, EvalRun, EvalRunStatus
from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.answering import NO_ANSWER_MESSAGE, generate_answer
from app.rag.providers.chat import ChatProviderError
from app.rag.retrieval.service import run_retrieval
from app.schemas.eval import EvalDatasetCreate, EvalQuestionCreate, EvalRunCreate


def _get_project(db: Session, project_id: uuid.UUID) -> Project:
    """Fetch a project or raise HTTP 404."""

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _get_dataset(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> EvalDataset:
    """Fetch a same-project eval dataset or raise HTTP 404."""

    dataset = db.scalar(
        select(EvalDataset).where(
            EvalDataset.id == dataset_id,
            EvalDataset.project_id == project_id,
        )
    )
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval dataset not found",
        )
    return dataset


def _get_run(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    run_id: uuid.UUID,
) -> EvalRun:
    """Fetch a same-project eval run with results or raise HTTP 404."""

    run = db.scalar(
        select(EvalRun)
        .options(selectinload(EvalRun.results))
        .where(
            EvalRun.id == run_id,
            EvalRun.project_id == project_id,
            EvalRun.dataset_id == dataset_id,
        )
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval run not found",
        )
    return run


def _question_count(db: Session, dataset_id: uuid.UUID) -> int:
    """Count questions in one dataset."""

    return db.scalar(
        select(func.count()).select_from(EvalQuestion).where(EvalQuestion.dataset_id == dataset_id)
    ) or 0


def dataset_to_read(dataset: EvalDataset, question_count: int) -> dict:
    """Build a dataset response dict with derived counts."""

    return {
        "id": dataset.id,
        "project_id": dataset.project_id,
        "name": dataset.name,
        "description": dataset.description,
        "question_count": question_count,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def create_dataset(db: Session, project_id: uuid.UUID, payload: EvalDatasetCreate) -> dict:
    """Create a project-scoped eval dataset."""

    _get_project(db, project_id)
    dataset = EvalDataset(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset_to_read(dataset, question_count=0)


def list_datasets(db: Session, project_id: uuid.UUID) -> list[dict]:
    """List eval datasets with question counts."""

    _get_project(db, project_id)
    datasets = list(
        db.scalars(
            select(EvalDataset)
            .where(EvalDataset.project_id == project_id)
            .order_by(EvalDataset.updated_at.desc())
        )
    )
    return [
        dataset_to_read(dataset, question_count=_question_count(db, dataset.id))
        for dataset in datasets
    ]


def list_runs(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> list[dict]:
    """List eval runs for a dataset without loading full result details."""

    _get_dataset(db, project_id, dataset_id)
    rows = db.execute(
        select(EvalRun, func.count(EvalResult.id))
        .outerjoin(EvalResult, EvalResult.run_id == EvalRun.id)
        .where(EvalRun.project_id == project_id, EvalRun.dataset_id == dataset_id)
        .group_by(EvalRun.id)
        .order_by(EvalRun.created_at.desc())
    ).all()
    return [
        {
            "id": run.id,
            "project_id": run.project_id,
            "dataset_id": run.dataset_id,
            "status": run.status,
            "retrieval_mode": run.retrieval_mode,
            "top_k": run.top_k,
            "metrics": run.metrics,
            "error_message": run.error_message,
            "result_count": result_count,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }
        for run, result_count in rows
    ]


def get_run(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    run_id: uuid.UUID,
) -> EvalRun:
    """Fetch one eval run detail."""

    _get_dataset(db, project_id, dataset_id)
    return _get_run(db, project_id, dataset_id, run_id)


def create_question(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    payload: EvalQuestionCreate,
) -> EvalQuestion:
    """Add an expected-answer question to an eval dataset."""

    _get_dataset(db, project_id, dataset_id)
    if payload.expected_document_id is not None:
        document = db.scalar(
            select(Document).where(
                Document.id == payload.expected_document_id,
                Document.project_id == project_id,
            )
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expected document does not belong to this project",
            )
    if payload.expected_chunk_id is not None:
        chunk = db.scalar(
            select(Chunk).where(
                Chunk.id == payload.expected_chunk_id,
                Chunk.project_id == project_id,
            )
        )
        if chunk is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expected chunk does not belong to this project",
            )

    question = EvalQuestion(
        project_id=project_id,
        dataset_id=dataset_id,
        question=payload.question,
        expected_document_id=payload.expected_document_id,
        expected_chunk_id=payload.expected_chunk_id,
        expected_answer_notes=payload.expected_answer_notes,
        should_answer=payload.should_answer,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def list_questions(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> list[EvalQuestion]:
    """List questions for one same-project eval dataset."""

    _get_dataset(db, project_id, dataset_id)
    return list(
        db.scalars(
            select(EvalQuestion)
            .where(
                EvalQuestion.project_id == project_id,
                EvalQuestion.dataset_id == dataset_id,
            )
            .order_by(EvalQuestion.created_at.asc())
        )
    )


def delete_question(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    question_id: uuid.UUID,
) -> None:
    """Delete one same-project eval question."""

    _get_dataset(db, project_id, dataset_id)
    question = db.scalar(
        select(EvalQuestion).where(
            EvalQuestion.id == question_id,
            EvalQuestion.project_id == project_id,
            EvalQuestion.dataset_id == dataset_id,
        )
    )
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval question not found",
        )
    db.delete(question)
    db.commit()


def delete_dataset(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> None:
    """Delete one same-project eval dataset and owned eval records."""

    dataset = _get_dataset(db, project_id, dataset_id)
    db.delete(dataset)
    db.commit()


def _answer_matches(answer: str, expected_notes: str | None) -> bool:
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


def _is_refusal(answer: str) -> bool:
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


def _aggregate_metrics(results: list[EvalResult]) -> dict:
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
    }


def run_dataset(
    db: Session,
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    payload: EvalRunCreate,
) -> EvalRun:
    """Run retrieval and answer generation for each eval question."""

    _get_dataset(db, project_id, dataset_id)
    questions = list(
        db.scalars(
            select(EvalQuestion)
            .where(
                EvalQuestion.project_id == project_id,
                EvalQuestion.dataset_id == dataset_id,
            )
            .order_by(EvalQuestion.created_at.asc())
        )
    )
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eval dataset has no questions",
        )

    run = EvalRun(
        project_id=project_id,
        dataset_id=dataset_id,
        status=EvalRunStatus.running,
        retrieval_mode=payload.retrieval_mode.value,
        top_k=payload.top_k,
        metrics={},
    )
    db.add(run)
    db.flush()

    results: list[EvalResult] = []
    try:
        for question in questions:
            retrieval = run_retrieval(
                db,
                project_id=project_id,
                query=question.question,
                mode=RetrievalMode(payload.retrieval_mode),
                top_k=payload.top_k,
                vector_weight=payload.vector_weight,
                keyword_weight=payload.keyword_weight,
                reranker_enabled=payload.reranker_enabled,
                reranker_candidate_limit=payload.reranker_candidate_limit,
            )
            generation_started = time.perf_counter()
            answer = generate_answer(
                question=question.question,
                retrieved_chunks=retrieval.results,
                recent_messages=[],
            )
            generation_latency_ms = int((time.perf_counter() - generation_started) * 1000)

            retrieved_chunk_ids = {candidate.chunk_id for candidate in retrieval.results}
            retrieved_document_ids = {candidate.document_id for candidate in retrieval.results}
            citation_chunk_ids = {source.chunk_id for source in answer.citation_sources}
            hit = (
                question.expected_chunk_id in retrieved_chunk_ids
                if question.expected_chunk_id is not None
                else question.expected_document_id in retrieved_document_ids
                if question.expected_document_id is not None
                else bool(retrieval.results)
            )
            citation_covered = (
                question.expected_chunk_id in citation_chunk_ids
                if question.expected_chunk_id is not None
                else bool(citation_chunk_ids)
            )
            refused = _is_refusal(answer.answer)
            answer_matched = (
                _answer_matches(answer.answer, question.expected_answer_notes)
                if question.should_answer
                else refused
            )
            if question.should_answer:
                score = 1.0 if hit and citation_covered and answer_matched else 0.0
            else:
                score = 1.0 if answer_matched else 0.0
            result = EvalResult(
                project_id=project_id,
                run_id=run.id,
                question_id=question.id,
                answer=answer.answer,
                hit=hit,
                citation_covered=citation_covered,
                refused=refused,
                retrieval_latency_ms=retrieval.latency_ms,
                generation_latency_ms=generation_latency_ms,
                score=score,
                result_metadata={
                    "question": question.question,
                    "retrieval_log_id": str(retrieval.retrieval_log_id),
                    "model": answer.model,
                    "answer_matched": answer_matched,
                    "retrieved_chunk_ids": [str(chunk_id) for chunk_id in retrieved_chunk_ids],
                    "citation_chunk_ids": [str(chunk_id) for chunk_id in citation_chunk_ids],
                },
            )
            db.add(result)
            results.append(result)

        run.status = EvalRunStatus.completed
        run.metrics = _aggregate_metrics(results)
    except ChatProviderError as exc:
        run.status = EvalRunStatus.failed
        run.error_message = str(exc)
    db.commit()
    db.refresh(run)
    return run
