from __future__ import annotations

import os

import structlog
from redis import Redis
from rq import Worker, Queue, Connection

LOG_LEVEL = os.getenv("RUNNER_LOG_LEVEL", "info").lower()
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
)
logger = structlog.get_logger()


def main() -> None:
    redis_url = os.getenv("RUNNER_REDIS_URL", "redis://runner-redis:6379/0")
    queue_name = os.getenv("RUNNER_QUEUE_NAME", "default")
    logger.info("worker.start", redis_url=redis_url, queue=queue_name)

    redis = Redis.from_url(redis_url)
    with Connection(redis):
        queue = Queue(name=queue_name)
        worker = Worker([queue])
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
