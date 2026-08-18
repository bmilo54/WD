from django.db import models
from core.abstract_models import TimeStampedModel
from django.contrib.auth.models import User
from .choices import STATUS_CHOICES, FAIL_REASON_CHOICES, FLOW_CHOICES

# Used when neither the job override nor the user's saved UserConfig sets
# a max_attempts value - keeps a hard ceiling on phone numbers tried so a
# misconfigured job can't loop indefinitely.
DEFAULT_MAX_ATTEMPTS = 10

class AutomationJob(TimeStampedModel):
    """
    This is the automation task create model.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="automation_jobs", blank=True, null=True)
    task_id = models.CharField(verbose_name="Task ID", max_length=255, blank=True, null=True)
    successful_count = models.PositiveIntegerField(verbose_name="Successul Count", default=0)
    total_attempts = models.PositiveIntegerField(verbose_name="Total Attempts", default=0, help_text="Total tried for this automation task")
    status = models.CharField(verbose_name="Status", max_length=50, choices=STATUS_CHOICES, default="pending")
    completed_at = models.DateTimeField(verbose_name="Completed Date & Time", blank=True, null=True)
    error_message = models.TextField(
        verbose_name="Error Message", blank=True, null=True,
        help_text="Summary of the last error, set when the job ends up in a failed/partial state.",
    )

    # Per-run overrides — leave blank to fall back to the user's saved
    # UserConfig defaults. Lets the same user run different jobs with
    # different settings without touching their saved config.
    country = models.ForeignKey(
        'country.Country', on_delete=models.SET_NULL, blank=True, null=True,
        related_name="automation_jobs",
        help_text="Overrides the user's default country for this run only. Leave blank to use their saved default.",
    )
    target_accounts = models.PositiveIntegerField(
        verbose_name="Target Accounts (Override)", blank=True, null=True,
        help_text="Overrides the user's saved target account count for this run only. Leave blank to use their saved default.",
    )
    sms_provider = models.ForeignKey(
        'sms_providers.SMSProvider', on_delete=models.SET_NULL, blank=True, null=True,
        related_name="automation_jobs", verbose_name="SMS Provider (Override)",
        help_text="Overrides the user's default SMS provider for this run only. Leave blank to use their saved default.",
    )
    sms_api_key = models.CharField(
        verbose_name="SMS Provider API Key (Override)", max_length=500, blank=True, null=True,
        help_text="Overrides the user's saved SMS provider API key for this run only. Leave blank to use their saved default.",
    )
    max_price = models.DecimalField(
        verbose_name="Max Price (Override)", max_digits=20, decimal_places=4, blank=True, null=True,
        help_text="Overrides the user's saved max price for this run only. Leave blank to use their saved default.",
    )
    default_password = models.CharField(
        verbose_name="Default Password (Override)", max_length=10, blank=True, null=True,
        help_text="Overrides the user's saved default password for this run only. Leave blank to use their saved default.",
    )
    max_attempts = models.PositiveIntegerField(
        verbose_name="Max Phone Number Attempts (Override)", blank=True, null=True,
        help_text=(
            "Overrides the user's saved max attempts for this run only. "
            "Leave blank to use their saved default, or the system default "
            f"({DEFAULT_MAX_ATTEMPTS}) if they haven't set one either."
        ),
    )

    def __str__(self):
        return f'{self.status} - {self.task_id}'

    class Meta:
        verbose_name = "Automation Job"
        verbose_name_plural = "Automation Jobs"
        ordering = ['-created', ]

    @property
    def _config(self):
        return getattr(self.user, 'userconfig', None) if self.user_id else None

    @property
    def effective_country(self):
        config = self._config
        return self.country or (config.default_country if config else None)

    @property
    def effective_target_accounts(self):
        config = self._config
        if self.target_accounts:
            return self.target_accounts
        return config.target_accounts if config and config.target_accounts else 0

    @property
    def effective_sms_provider(self):
        config = self._config
        return self.sms_provider or (config.sms_provider if config else None)

    @property
    def effective_sms_api_key(self):
        config = self._config
        return self.sms_api_key or (config.sms_api_key if config else None)

    @property
    def effective_max_price(self):
        config = self._config
        return self.max_price if self.max_price is not None else (config.max_price if config else None)

    @property
    def effective_default_password(self):
        config = self._config
        return self.default_password or (config.default_password if config else None)
    
    @property
    def effective_max_attempts(self):
        config = self._config
        if self.max_attempts:
            return self.max_attempts
        if config and config.max_attempts:
            return config.max_attempts
        return DEFAULT_MAX_ATTEMPTS

    @property
    def progress(self):
        target = self.effective_target_accounts
        if target == 0:
            return 0
        return min(int((self.successful_count / target) * 100), 100)

class FlowAttempt(TimeStampedModel):
    """
    This is the flow attempts. One Automation task can have multiple flow attempts.
    """
    job = models.ForeignKey(AutomationJob, on_delete=models.CASCADE, related_name="attempts", blank=True, null=True)
    phone_number = models.CharField(verbose_name="Phone Number", max_length=40, blank=True, null=True)
    activation_id = models.CharField(verbose_name="Activation ID", max_length=50, blank=True, null=True, unique=True)
    status = models.CharField(verbose_name="Flow Status", max_length=10, choices=FLOW_CHOICES)
    fail_reason = models.CharField(verbose_name="Fail Reason", max_length=50, blank=True, null=True, choices=FAIL_REASON_CHOICES)
    error_message = models.TextField(verbose_name="Error Message", blank=True, null=True)

    def __str__(self):
        return f"{0} - {1}".format(self.phone_number, self.status)

    class Meta:
        verbose_name = "Flow Attempt"
        verbose_name_plural = "Flow Attempts"