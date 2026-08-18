from django.views.generic import ListView, DetailView, FormView, TemplateView
from django.views.generic.base import View
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import get_object_or_404

from core.mixins import DashboardMixin, GroupRequiredMixin
from apps.accounts.models import FacebookAccount
from .filters import FacebookAccountFilterForm

class FacebookAccountListView(GroupRequiredMixin, DashboardMixin, TemplateView):
    group_required = ['superadmin']
    template_name = 'view_dashboards/accounts/list.html'
    form_class = FacebookAccountFilterForm

    def get_context_data(self, **kwargs):
        context = super(FacebookAccountListView, self).get_context_data(**kwargs)
        context['page_title'] = "Facebook Account | List"
        context['title'] = "Facebook Account List"
        context['main_nav'] = "accounts"
        context['filter_form'] = self.form_class

        return context

    def get(self, request, *args, **kwargs):
        if '_export_accounts' in request.GET:
            accounts = FacebookAccount.objects.filter(is_active=True).order_by('created')
            lines = []
            for account in accounts:
                lines.append(f"{account.uid}|{account.password}|{account.cookie_string}")
            content = "\n".join(lines)
            response = HttpResponse(content, content_type="text/plain")
            response['Content-Disposition'] = 'attachment; filename="facebook_accounts.txt"'

            return response
        else:
            return super(FacebookAccountListView, self).get(request, *args, **kwargs)
