from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from django_datatables_view.base_datatable_view import BaseDatatableView

from core.mixins import GroupRequiredMixin, DashboardMixin
from apps.jobs.models import AutomationJob
from apps.accounts.models import FacebookAccount

class JobDatatable(GroupRequiredMixin, DashboardMixin, BaseDatatableView):
    group_required = ['superadmin']
    model = AutomationJob
    columns = [
        'pk',
        'task_id',
        'user',
        'status',
        'successful_count',
        'total_attempts',
        'created',
        'actions',
    ]
    order_columns = columns

    def get_initial_queryset(self):
        self.initial_queryset = self.model.objects.all()
        return self.initial_queryset

    def render_column(self, row, column):
        if column == 'created':
            return timezone.localtime(row.created).strftime('%d-%m-%Y %I:%M %p')
        elif column == 'user':
            return row.user.username
        elif column == 'status':
            if row.status == 'success':
                return '<span class="badge bg-success">Success</span>'
            elif row.status == 'failed':
                return '<span class="badge bg-danger">Failed</span>'
            elif row.status == 'running':
                return '<span class="badge bg-primary">Running</span>'
            elif row.status == 'partial':
                return '<span class="badge bg-warning text-dark">Partial</span>'
            else:
                return '<span class="badge bg-secondary">Unknown</span>'
        elif column == 'actions':
            detail_url = reverse('view_dashboards:jobs:detail', kwargs={'pk': row.pk})

            action_html = ""
            if self.is_superadmin:
                menu_items = f'<li><a class="dropdown-item text-primary" href="{detail_url}">Detail</a></li>'

            action_html = f"""
                <div class="dropdown select-dropdown btn-action dropdown-custom">
                    <button class="dropdown-toggle bg-transparent text-secondary fs-15" data-bs-toggle="dropdown" aria-expanded="false">
                        Action
                    </button>

                    <ul class="dropdown-menu dropdown-menu-end bg-white border-0 box-shadow rounded-10" data-simplebar>
                        {menu_items}
                    </ul>
                </div>
            """
            return mark_safe(action_html)
        else:
            return super(JobDatatable, self).render_column(row, column)

    def filter_queryset(self, qs):
        search = self.request.POST.get('search[value]', None)
        if search:
            query = (
                Q(user__username__icontains=search) |
                Q(task_id__icontains=search)
            )
            qs = qs.filter(query)

        return qs