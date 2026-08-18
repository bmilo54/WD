from django.contrib import admin
from .models import AutomationJob, FlowAttempt

class FlowAttemptInline(admin.TabularInline):
    model = FlowAttempt
    extra = 0  # Number of extra empty form rows to show
    fields = ('phone_number', 'activation_id', 'status', 'fail_reason', 'error_message', 'created')
    readonly_fields = ('created',)


@admin.register(AutomationJob)
class AutomationJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_id', 'user', 'status', 'successful_count', 'total_attempts', 'created')
    list_filter = ('status', 'created')
    search_fields = ('task_id', 'user__username')
    inlines = [FlowAttemptInline]


@admin.register(FlowAttempt)
class FlowAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'phone_number', 'status', 'fail_reason', 'created')
    list_filter = ('status', 'fail_reason', 'created')
    search_fields = ('phone_number', 'activation_id', 'job__task_id')
