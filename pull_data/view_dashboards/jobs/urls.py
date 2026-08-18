from django.urls import path

from .views import (
    JobListView,
    JobCreateView,
    JobDetailView,
    JobStatusJsonView,
    JobExportView,
)

from .datatables import JobDatatable

app_name = "jobs"

urlpatterns = [
    path(r'list/', JobListView.as_view(), name="list"),
    path(r'datatable/', JobDatatable.as_view(), name="datatable"),
    path(r'create/', JobCreateView.as_view(), name="create"),
    path(r'detail/<pk>/', JobDetailView.as_view(), name="detail"),
    path(r'<int:pk>/status/', JobStatusJsonView.as_view(), name="status"),
    path(r'<int:pk>/export/', JobExportView.as_view(), name="export"),
]
