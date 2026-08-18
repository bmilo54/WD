from django.contrib import admin
from .models import FacebookAccount

@admin.register(FacebookAccount)
class FacebookAccountAdmin(admin.ModelAdmin):
    list_display = ('uid', 'password', 'is_active', 'created')
    list_filter = ['is_active',]
    ordering = ['-created',]
