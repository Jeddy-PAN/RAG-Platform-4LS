from app.workers.enqueue import enqueue_ingestion_job


def test_enqueue_ingestion_job_passes_ids_to_rq(monkeypatch) -> None:
    """Worker enqueue boundary should pass job, project, and document IDs."""

    calls = {}

    class FakeRedis:
        @classmethod
        def from_url(cls, url: str):
            calls["redis_url"] = url
            return "redis-connection"

    class FakeQueue:
        def __init__(self, name: str, connection):
            calls["queue_name"] = name
            calls["connection"] = connection

        def enqueue(self, task_path: str, job_id: str, project_id: str, document_id: str):
            calls["task_path"] = task_path
            calls["job_id"] = job_id
            calls["project_id"] = project_id
            calls["document_id"] = document_id

    monkeypatch.setattr("app.workers.enqueue.Redis", FakeRedis)
    monkeypatch.setattr("app.workers.enqueue.Queue", FakeQueue)

    enqueue_ingestion_job("job-1", "project-1", "document-1")

    assert calls == {
        "redis_url": "redis://redis:6379/0",
        "queue_name": "default",
        "connection": "redis-connection",
        "task_path": "app.workers.tasks.ingest_document",
        "job_id": "job-1",
        "project_id": "project-1",
        "document_id": "document-1",
    }
