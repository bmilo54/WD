import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Playwright's sync API runs its own asyncio event loop internally (even
# though it's used from regular synchronous code) and registers it as the
# current thread's loop. Since FacebookRecoveryBot's worker thread is that
# same thread, Django's ORM sees "a running event loop" on every save()/
# create() call made after a Playwright browser is launched and refuses to
# run, raising "You cannot call this from an async context - use a thread
# or sync_to_async." This isn't actually an unsafe concurrent-access
# scenario (the Celery worker runs one job at a time, --pool=solo), so it's
# safe to disable Django's check here - same fix already applied to the
# `run_recovery_job` management command, just also needed for the Celery
# worker process, which doesn't go through that command.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

app = Celery("pull_data")

# Read CELERY_* settings from Django's settings.py.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every installed app (e.g. apps/jobs/tasks.py).
app.autodiscover_tasks()
