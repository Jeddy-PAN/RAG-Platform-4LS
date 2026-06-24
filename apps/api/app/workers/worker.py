from redis import Redis
from rq import Queue, Worker

from app.core.config import get_settings


def create_worker() -> Worker:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.rq_queue_name, connection=connection)
    return Worker([queue], connection=connection)


def main() -> None:
    worker = create_worker()
    worker.work()


if __name__ == "__main__":
    main()
