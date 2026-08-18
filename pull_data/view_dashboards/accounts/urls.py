from django.urls import path

from .views import (
    FacebookAccountListView,
)

from .datatables import FacebookAccountDatatable

app_name = "accounts"

urlpatterns = [
    path(r'list/', FacebookAccountListView.as_view(), name="list"),
    path(r'datatable/', FacebookAccountDatatable.as_view(), name="datatable"),
]