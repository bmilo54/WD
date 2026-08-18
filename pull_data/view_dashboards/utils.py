from django.conf import settings

# Maps an AutomationJob override field name to the UserConfig field it falls
# back to, when the two names differ (e.g. job.country -> config.default_country).
_OVERRIDE_TO_CONFIG_FIELD = {
    'sms_provider': 'sms_provider',
    'sms_api_key': 'sms_api_key',
    'country': 'default_country',
    'target_accounts': 'target_accounts',
}


def get_job_readiness_issues(user, overrides=None):
    """
    Returns a list of human-readable reasons a new job can't be started yet.

    `overrides` is an optional dict of AutomationJob override field names
    (e.g. {'sms_provider': <SMSProvider>, 'country': <Country>, ...}) that
    haven't been saved to the job yet - e.g. the values a user just typed
    into the "customize this job" form. When provided, a field only counts
    as missing if it's blank in BOTH the override and the saved UserConfig,
    so overrides can fill in gaps in an otherwise-incomplete saved config.
    """
    overrides = overrides or {}
    issues = []

    config = getattr(user, 'userconfig', None)
    if not config and not any(overrides.values()):
        return ["Automation settings have not been configured yet."]

    def effective(field):
        value = overrides.get(field)
        if value:
            return value
        config_field = _OVERRIDE_TO_CONFIG_FIELD[field]
        return getattr(config, config_field, None) if config else None

    if not effective('sms_provider'):
        issues.append("No SMS provider selected.")
    if not effective('sms_api_key'):
        issues.append("SMS provider API key is missing.")
    if not effective('country'):
        issues.append("Default country is not selected.")
    if not effective('target_accounts'):
        issues.append("Target account count is not set.")
    if not getattr(settings, 'CAPSOLVER_API_KEY', ''):
        issues.append("CapSolver API key is not configured.")

    return issues


def start_automation_job(user, **overrides):
    """
    Creates an AutomationJob for `user` and enqueues the Celery task to run it.

    `overrides` are optional per-run AutomationJob field overrides (country,
    target_accounts, sms_provider, sms_api_key, max_price, default_password)
    - leave any of them out/None to use the user's saved UserConfig defaults
    for that setting.

    Raises `JobStartError` if the user isn't ready to start a job, already
    has one in progress, or the task queue can't be reached.
    """
    from apps.jobs.models import AutomationJob

    issues = get_job_readiness_issues(user, overrides=overrides)
    if issues:
        raise JobStartError("Cannot start a new job: " + " ".join(issues))

    if AutomationJob.objects.filter(user=user, status__in=['pending', 'running']).exists():
        raise JobStartError("You already have an automation job in progress.", is_conflict=True)

    from celery.utils import uuid as celery_uuid
    from apps.jobs.tasks import run_recovery_job_task

    task_id = celery_uuid()
    job = AutomationJob.objects.create(
        user=user, task_id=task_id, status="pending", **overrides,
    )

    try:
        run_recovery_job_task.apply_async(args=[job.id], task_id=task_id)
    except Exception as exc:
        job.delete()
        raise JobStartError(
            "Could not start the automation job — the task queue (Celery/Redis) may not be running."
        ) from exc

    return job


class JobStartError(Exception):
    def __init__(self, message, is_conflict=False):
        super().__init__(message)
        self.is_conflict = is_conflict
