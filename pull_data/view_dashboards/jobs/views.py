from django.views.generic import DetailView, FormView, TemplateView
from django.views.generic.base import View
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import get_object_or_404

from core.mixins import DashboardMixin, GroupRequiredMixin
from apps.jobs.models import AutomationJob
from apps.accounts.models import FacebookAccount
from view_dashboards.utils import start_automation_job, JobStartError, get_job_readiness_issues

from .forms import JobCreateForm
from .filters import JobFilterForm

class JobListView(DashboardMixin, GroupRequiredMixin, TemplateView):
    group_required = ['superadmin']
    template_name = 'view_dashboards/jobs/list.html'
    form_class = JobFilterForm

    def get_context_data(self, **kwargs):
        context = super(JobListView, self).get_context_data(**kwargs)
        context['page_title'] = "Automation Jobs"
        context['selected_page'] = "jobs_list"
        context['main_nav'] = "jobs"
        context['filter_form'] = self.form_class

        return context


class JobCreateView(DashboardMixin, GroupRequiredMixin, FormView):
    """
    "Customize Automation Job" - lets a user override any of their saved
    UserConfig settings for a single run, without changing their saved
    defaults. Any field left blank falls back to the saved UserConfig
    value shown alongside the form.
    """
    group_required = ['superadmin']
    form_class = JobCreateForm
    template_name = 'view_dashboards/jobs/create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Customize Automation Job"
        context['selected_page'] = "jobs_create"
        context['main_nav'] = "jobs"
        context['user_config'] = getattr(self.request.user, 'userconfig', None)
        context['job_ready_issues'] = get_job_readiness_issues(self.request.user)
        context['has_active_job'] = AutomationJob.objects.filter(
            user=self.request.user, status__in=['pending', 'running'],
        ).exists()
        return context

    def form_valid(self, form):
        overrides = {
            'sms_provider': form.cleaned_data.get('sms_provider'),
            'sms_api_key': form.cleaned_data.get('sms_api_key') or None,
            'country': form.cleaned_data.get('country'),
            'target_accounts': form.cleaned_data.get('target_accounts'),
            'max_price': form.cleaned_data.get('max_price'),
            'default_password': form.cleaned_data.get('default_password') or None,
        }

        try:
            job = start_automation_job(self.request.user, **overrides)
        except JobStartError as exc:
            if exc.is_conflict:
                messages.warning(self.request, str(exc))
            else:
                messages.error(self.request, str(exc))
            return self.render_to_response(self.get_context_data(form=form))

        messages.success(self.request, f"Automation job #{job.id} has been started.")
        return HttpResponseRedirect(reverse('view_dashboards:jobs:detail', args=[job.pk]))


class JobDetailView(DashboardMixin, GroupRequiredMixin, DetailView):
    group_required = ['superadmin']
    model = AutomationJob
    template_name = 'view_dashboards/jobs/detail.html'
    context_object_name = 'job'

    def get_queryset(self):
        return AutomationJob.objects.select_related('user', 'country')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object
        context['page_title'] = f"Job #{job.pk}"
        context['selected_page'] = "jobs_list"
        context['main_nav'] = "jobs"
        context['attempts'] = job.attempts.all().order_by('-created')
        context['has_recovered_accounts'] = FacebookAccount.objects.filter(attempt__job=job).exists()

        return context


class JobStatusJsonView(DashboardMixin, GroupRequiredMixin, View):
    group_required = ['superadmin']
    """Lightweight JSON endpoint the job detail page polls for live progress."""

    def get(self, request, *args, **kwargs):
        job = get_object_or_404(AutomationJob, pk=kwargs['pk'])
        return JsonResponse({
            'status': job.status,
            'status_display': job.get_status_display(),
            'successful_count': job.successful_count,
            'total_attempts': job.total_attempts,
            'target_accounts': job.effective_target_accounts,
            'progress': job.progress,
            'is_finished': job.status in ('success', 'partial', 'failed'),
            'error_message': job.error_message,
        })


class JobExportView(DashboardMixin, GroupRequiredMixin, View):
    group_required = ['superadmin']
    """Exports the Facebook accounts recovered by a job as UID|PASSWORD|COOKIE lines."""

    def get(self, request, *args, **kwargs):
        job = get_object_or_404(AutomationJob, pk=kwargs['pk'])
        accounts = FacebookAccount.objects.filter(attempt__job=job).order_by('created')

        lines = [f"{account.uid}|{account.password}|{account.cookie_string}" for account in accounts]
        content = "\n".join(lines)

        response = HttpResponse(content, content_type="text/plain")
        response['Content-Disposition'] = f'attachment; filename="job_{job.pk}_accounts.txt"'
        return response
