"""ARQ worker settings entrypoint.

Keep this module self-contained: ARQ inspects class attributes on the settings
class itself (subclass attribute lookup can miss parent class attrs depending
on how arq walks __dict__).
"""

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.workers import tasks as job_module


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [
        job_module.process_event_stream,
        job_module.compute_dau_job,
        job_module.compute_funnel_job,
        job_module.compute_retention_job,
        job_module.cleanup_job,
    ]
    cron_jobs = [
        cron(
            job_module.process_event_stream,
            second={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
        cron(job_module.compute_dau_job, minute={5}),
        cron(job_module.compute_funnel_job, minute={10}),
        cron(job_module.compute_retention_job, hour={2}, minute={15}),
        cron(job_module.cleanup_job, hour={3}, minute={30}),
    ]
    on_startup = job_module.startup
    on_shutdown = job_module.shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 300
