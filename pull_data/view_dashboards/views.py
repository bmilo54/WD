import logging

from django.views.generic.edit import FormView
from django.views.generic.base import RedirectView, TemplateView, View

from django.utils import timezone
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Count, Prefetch
from django.contrib.auth import login, logout, authenticate

from core.mixins import DashboardMixin
from .forms import DashboardLoginForm
from .utils import get_job_readiness_issues, start_automation_job, JobStartError
from apps.jobs.models import AutomationJob
from apps.country.models import Country

logger = logging.getLogger(__name__)


class LoginView(FormView):
    form_class = DashboardLoginForm
    success_url = reverse_lazy('view_dashboards:dashboard')
    template_name = 'view_dashboards/login.html'

    is_superadmin = False
    is_staff = False

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if self.request.user.is_authenticated:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL does't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        return super(LoginView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(username=username, password=password)

        if user is not None:
            self.is_superadmin = user.groups.filter(name='superadmin').exists()
            self.is_staff = user.groups.filter(name='staff').exists()

            if self.is_superadmin or self.is_staff:
                pass
            else:
                return self.form_invalid(form)

            if user.is_active:
                login(self.request, user)

                return super(LoginView, self).form_valid(form)
            else:
                return self.form_invalid(form)
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        error_len = 0
        error_len += len(form.errors)

        messages.error(self.request, "Please enter a correct username and password")
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super(LoginView, self).get_context_data(**kwargs)
        context['page_title'] = "Login"
        context['selected_page'] = "login"

        return context

    def get_success_url(self):
        messages.success(self.request, "Welcome Back {}.".format(self.request.user))
        if self.is_superadmin:
            return self.success_url

        return super(LoginView, self).get_success_url()

class LogoutView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        if self.is_superadmin or self.is_staff:
            self.url = reverse_lazy('view_dashboards:login')
        else:
            self.url = reverse_lazy('view_dashboards:login')

        return super(LogoutView, self).get_redirect_url(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.is_superadmin = request.user.groups.filter(name='superadmin').exists()
        self.is_staff = request.user.groups.filter(name='staff').exists()
        logout(request)

        return super(LogoutView, self).get(request, *args, **kwargs)

class DashboardPageView(DashboardMixin, TemplateView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not request.user.groups.all():
                messages.error(self.request, "You don't have permissionto access this page.")
                return HttpResponseRedirect(reverse('view_dashboards:login'))

        return super(DashboardPageView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DashboardPageView, self).get_context_data(**kwargs)
        context['page_title'] = "Dashboard"
        context['selected_page'] = "dashboard"
        context['main_nav'] = "dashboard"
        context['hide_breadcrumb'] = True

        jobs = AutomationJob.objects.all()
        context['job_counts'] = {
            'total': jobs.count(),
            'pending': jobs.filter(status='pending').count(),
            'running': jobs.filter(status='running').count(),
            'success': jobs.filter(status='success').count(),
            'partial': jobs.filter(status='partial').count(),
            'failed': jobs.filter(status='failed').count(),
        }
        context['recent_jobs'] = jobs.select_related('user')[:10]

        user_jobs = jobs.filter(user=self.request.user)
        context['current_job'] = user_jobs.first()
        context['has_active_job'] = user_jobs.filter(status__in=['pending', 'running']).exists()
        context['job_ready_issues'] = get_job_readiness_issues(self.request.user)
        context['can_start_job'] = not context['job_ready_issues']

        return context

    def get_template_names(self):
        # Only the superadmin dashboard exists for now; reuse it for any
        # authenticated dashboard user until dedicated staff templates exist.
        self.template_name = "view_dashboards/_group_dashboard/superadmin/dashboard.html"
        return super(DashboardPageView, self).get_template_names()


class StartJobView(DashboardMixin, View):
    """Kicks off a new FacebookRecoveryBot run (using saved defaults, no
    per-run overrides) via Celery from the dashboard's quick-start button."""

    def get(self, request, *args, **kwargs):
        return HttpResponseRedirect(reverse('view_dashboards:dashboard'))

    def post(self, request, *args, **kwargs):
        try:
            job = start_automation_job(request.user)
        except JobStartError as exc:
            if exc.is_conflict:
                messages.warning(request, str(exc))
            else:
                messages.error(request, str(exc))
            return HttpResponseRedirect(reverse('view_dashboards:dashboard'))

        messages.success(request, f"Automation job #{job.id} has been started.")
        return HttpResponseRedirect(reverse('view_dashboards:dashboard'))


class CountriesByProviderView(DashboardMixin, View):
    """
    Returns the countries a given SMS provider supports (i.e. has a
    ProviderCountryMapping for), as JSON, so a "Country" dropdown can
    filter itself down to only that provider's countries. Shared by both
    the UserConfig admin form and the "Customize Automation Job" page.
    """
    def get(self, request, provider_id, *args, **kwargs):
        countries = Country.objects.filter(
            provider_mappings__provider_id=provider_id, is_active=True,
        ).order_by('name').values('id', 'name')
        return JsonResponse({'countries': list(countries)})

