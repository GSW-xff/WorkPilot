from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from workpilot.api import build_service
from workpilot.config import Settings
from workpilot.workflows.activities import TaskActivities
from workpilot.workflows.temporal import TaskWorkflow


async def run_worker() -> None:
    settings = Settings.from_env()
    if not settings.database_url:
        raise RuntimeError("WORKPILOT_DATABASE_URL is required for a separate worker")
    if not settings.temporal_target:
        raise RuntimeError("WORKPILOT_TEMPORAL_TARGET is required for the worker")

    client = await Client.connect(settings.temporal_target)
    service, _adapter = build_service(settings=settings)
    activities = TaskActivities(service)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[TaskWorkflow],
        activities=[
            activities.advance_task,
            activities.approve_task,
            activities.reject_task,
            activities.pause_task,
            activities.resume_task,
            activities.cancel_task,
        ],
    )
    try:
        await worker.run()
    finally:
        service.repository.close()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
