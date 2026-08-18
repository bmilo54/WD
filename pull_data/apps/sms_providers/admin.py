from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import SMSProvider, ProviderCountryMapping
from core.services.sms_hub import PROVIDER_MAP


@admin.register(SMSProvider)
class SMSProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'website', 'is_active']
    search_fields = ('name', 'slug')
    list_filter = ['is_active']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)
    readonly_fields = ['registered_slugs']

    fieldsets = [
        (None, {
            'fields': ['name', 'slug', 'website', 'is_active'],
        }),
        ('Developer Info', {
            'fields': ['registered_slugs'],
            'description': (
                'The slug you enter above must exactly match one of the '
                'registered slugs below, otherwise the system will raise '
                'an error when trying to use this provider.'
            ),
        }),
    ]

    @admin.display(description="Registered slugs in PROVIDER_MAP")
    def registered_slugs(self, obj):
        slugs = list(PROVIDER_MAP.keys())
        items = "".join(
            f"<li><code style='background:#000; padding:2px 6px; "
            f"border-radius:3px;'>{slug}</code></li>"
            for slug in slugs
        )
        return format_html(
            "<ul style='margin:0; padding-left:18px;'>{}</ul>",
            mark_safe(items)
        )


@admin.register(ProviderCountryMapping)
class ProviderCountryMappingAdmin(admin.ModelAdmin):
    list_display = ['country', 'provider', 'provider_country_id']
    search_fields = ('country__name', 'provider__name', 'provider_country_id')
    list_filter = ['provider']
    ordering = ('country__name', 'provider__name')
