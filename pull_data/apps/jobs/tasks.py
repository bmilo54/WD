import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_recovery_job_task(self, job_id: int):
    """
    Runs the Facebook account recovery automation for `job_id` in a Celery
    worker process, so the dashboard view that starts it doesn't have to
    block an HTTP request for the (potentially many minutes) it takes.

    The worker process must run on a machine with an active desktop
    session, since FacebookRecoveryBot launches a non-headless (visible)
    Playwright browser window.
    """
    from apps.jobs.models import AutomationJob
    from core.automation.facebook_recovery import FacebookRecoveryBot

    AutomationJob.objects.filter(id=job_id).update(task_id=self.request.id)

    logger.info(f"[Celery] Starting recovery job {job_id} (task_id={self.request.id})")
    try:
        bot = FacebookRecoveryBot(job_id=job_id)
        bot.start()
    except Exception:
        logger.exception(f"[Celery] Recovery job {job_id} crashed unexpectedly.")
        AutomationJob.objects.filter(id=job_id).update(status="failed")
        raise
