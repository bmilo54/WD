from django.utils import timezone
from django.db.models import Q
from django_datatables_view.base_datatable_view import BaseDatatableView

from core.mixins import GroupRequiredMixin, DashboardMixin
from apps.accounts.models import FacebookAccount

class FacebookAccountDatatable(DashboardMixin, GroupRequiredMixin, BaseDatatableView):
    group_required = ['superadmin']
    model = FacebookAccount
    columns = [
        'pk',
        'uid',
        'password',
        'is_active',
        'created',
    ]

    def get_initial_queryset(self):
        return self.model.objects.all().order_by('-created')

    def render_column(self, row, column):
        if column == 'created':
            return timezone.localtime(row.created).strftime('%d-%m-%Y %I:%M %p')
        elif column == 'is_active':
            if row.is_active:
                return f'<span class="badge bg-success fs-14 px-3 py-2">Active</span>'
            else:
                return f'<span class="badge bg-danger fs-14 px-3 py-2">Inactive</span>'
        else:
            return super(FacebookAccountDatatable, self).render_column(row, column)

    def filter_queryset(self, qs):
        search = self.request.POST.get('search[value]', None)
        if search:
            query = (
                Q(uid__icontains=search) |
                Q(password__icontains=search)
            )
            qs = qs.filter(query)

        return qs