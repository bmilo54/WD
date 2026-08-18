from django.urls import path, include
from .views import (
    LoginView,
    LogoutView,
    DashboardPageView,
    StartJobView,
    CountriesByProviderView,
)

app_name = "view_dashboards"

urlpatterns = [
    path(r'', DashboardPageView.as_view(), name="dashboard"),
    path(r'login/', LoginView.as_view(), name="login"),
    path(r'logout/', LogoutView.as_view(), name="logout"),
    path(r'jobs/start/', StartJobView.as_view(), name="start_job"),
    path(r'jobs/', include("view_dashboards.jobs.urls", namespace="jobs")),
    path(r'accounts/', include("view_dashboards.accounts.urls", namespace="accounts")),
    path(r'api/countries-by-provider/<int:provider_id>/', CountriesByProviderView.as_view(), name="countries_by_provider",),
]