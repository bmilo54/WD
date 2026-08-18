from django.contrib import admin
from .models import Country

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'country_id', 'is_active']
    search_fields = ('name', 'country_id', )
    list_filter = ['is_active',]
    ordering = ('name',)