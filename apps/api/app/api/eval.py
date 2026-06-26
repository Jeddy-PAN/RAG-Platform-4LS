import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.eval import (
    EvalDatasetCreate,
    EvalDatasetRead,
    EvalQuestionCreate,
    EvalQuestionRead,
    EvalResultRead,
    EvalRunCreate,
    EvalRunRead,
)
from app.services import eval as eval_service


router = APIRouter(prefix="/api/projects/{project_id}/eval", tags=["eval"])


@router.post(
    "/datasets",
    response_model=EvalDatasetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    project_id: uuid.UUID,
    payload: EvalDatasetCreate,
    db: Session = Depends(get_db),
):
    """Create a project-scoped eval dataset."""

    return eval_service.create_dataset(db, project_id, payload)


@router.get("/datasets", response_model=list[EvalDatasetRead])
def list_datasets(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """List project-scoped eval datasets."""

    return eval_service.list_datasets(db, project_id)


@router.post(
    "/datasets/{dataset_id}/questions",
    response_model=EvalQuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    payload: EvalQuestionCreate,
    db: Session = Depends(get_db),
):
    """Add a question to an eval dataset."""

    return eval_service.create_question(db, project_id, dataset_id, payload)


@router.post(
    "/datasets/{dataset_id}/runs",
    response_model=EvalRunRead,
    status_code=status.HTTP_201_CREATED,
)
def run_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    payload: EvalRunCreate,
    db: Session = Depends(get_db),
) -> EvalRunRead:
    """Run a synchronous eval for one dataset."""

    run = eval_service.run_dataset(db, project_id, dataset_id, payload)
    return EvalRunRead(
        id=run.id,
        project_id=run.project_id,
        dataset_id=run.dataset_id,
        status=run.status,
        retrieval_mode=run.retrieval_mode,
        top_k=run.top_k,
        metrics=run.metrics,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        results=[
            EvalResultRead(
                id=result.id,
                question_id=result.question_id,
                question=str(result.result_metadata.get("question", "")),
                answer=result.answer,
                hit=result.hit,
                citation_covered=result.citation_covered,
                refused=result.refused,
                answer_matched=bool(result.result_metadata.get("answer_matched")),
                retrieval_latency_ms=result.retrieval_latency_ms,
                generation_latency_ms=result.generation_latency_ms,
                score=result.score,
                result_metadata=result.result_metadata,
            )
            for result in run.results
        ],
    )
