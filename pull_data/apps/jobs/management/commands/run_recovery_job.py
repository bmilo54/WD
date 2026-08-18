import os
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.jobs.models import AutomationJob
from core.automation.facebook_recovery import FacebookRecoveryBot

class Command(BaseCommand):
    help = 'Run the Facebook Recovery Playwright automation. Pass a job_id, or use --create <username> to auto-create a new job.'

    def add_arguments(self, parser):
        parser.add_argument('job_id', type=int, nargs='?', help='The ID of an existing AutomationJob to run')
        parser.add_argument('--create', type=str, metavar='USERNAME', help='Auto-create a new job for this username and run it')

    def handle(self, *args, **options):
        job_id = options.get('job_id')
        username = options.get('create')

        if not job_id and not username:
            self.stdout.write(self.style.ERROR("Please provide a job_id or use --create <username>"))
            self.stdout.write("  Examples:")
            self.stdout.write("    python manage.py run_recovery_job 1")
            self.stdout.write("    python manage.py run_recovery_job --create admin")
            return

        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User '{username}' not found."))
                return

            job = AutomationJob.objects.create(user=user)
            job_id = job.id
            self.stdout.write(self.style.SUCCESS(f"Created new AutomationJob #{job_id} for user '{username}'."))

        self.stdout.write(f"Starting Facebook Recovery for Job {job_id}...")
        bot = FacebookRecoveryBot(job_id=job_id)
        bot.start()
        self.stdout.write(self.style.SUCCESS(f"Finished job {job_id}. Check database for results."))
