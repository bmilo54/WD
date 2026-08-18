from django.contrib import admin
from .models import UserConfig

@admin.register(UserConfig)
class UserConfigAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_country', 'max_price', 'default_password', 'target_accounts', 'max_attempts')
    search_fields = ('user', 'default_country', 'max_price', 'default_password', 'target_accounts', 'max_attempts')
    list_filter = ('default_country', 'max_price', 'default_password', 'target_accounts', 'max_attempts')
    ordering = ('-created',)

    class Media:
        # Filters "Default Country" down to only the countries supported by
        # the selected "SMS Provider" (see view_dashboards:countries_by_provider).
        js = ('js/custom/provider_country_filter.js',)