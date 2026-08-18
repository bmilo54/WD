from django.db.models import DateTimeField
import time
import logging
import uuid

from django import forms
from django.core.cache import cache
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .widgets import CoreImageWidget

logger = logging.getLogger(__name__)

class GroupRequiredMixin(object):
    group_required = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        else:
            user_groups = []

            for group in request.user.groups.values_list('name', flat=True):
                user_groups.append(group)

            if len(set(user_groups).intersection(self.group_required)) <= 0:
                raise PermissionDenied

        return super(GroupRequiredMixin, self).dispatch(request, *args, **kwargs)

class DashboardMixin(LoginRequiredMixin):
    login_url = reverse_lazy('view_dashboards:login')
    redirect_field_name = 'redirect_to'

    is_superadmin = False
    is_staff = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super(DashboardMixin, self).dispatch(request, *args, **kwargs)
        else:
            self.is_superadmin = request.user.groups.filter(name="superadmin").exists()
            self.is_staff = request.user.groups.filter(name="staff").exists()

        return super(DashboardMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DashboardMixin, self).get_context_data(**kwargs)
        context['is_superadmin'] = self.is_superadmin
        context['is_staff'] = self.is_staff

        return context

class FormMixin(object):
    def __init__(self, *args, **kwargs):
        super(FormMixin, self).__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            custom_class = field.widget.attrs.get('class')
            if isinstance(field, forms.DateField):
                field.widget.attrs['class'] = 'datepicker'
                field.widget.attrs['extra_type'] = 'datepicker'
                field.widget.attrs['autocomplete'] = 'off'

            if isinstance(field, forms.DateTimeField):
                field.widget.attrs['class'] = 'datepicker'
                field.widget.attrs['autocomplete'] = 'off'

            if isinstance(field, forms.ChoiceField):
                field.widget.attrs['class'] = 'choice'

            if isinstance(field, forms.ModelChoiceField):
                field.widget.attrs['class'] = 'modelchoice'

    def update_field_required(self, field_name, required):
        self.fields[field_name].required = required
        if isinstance(self.fields[field_name].widget, CoreImageWidget):
            self.fields[field_name].widget.is_required = required

