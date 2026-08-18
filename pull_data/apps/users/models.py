from django.db import models
from django.contrib.auth.models import User
from apps.country.models import Country
from core.abstract_models import TimeStampedModel

class UserConfig(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, blank=True, null=True)

    # ---------------------------------------------------------------- #
    #  SMS Provider (flexible hub — works with Hero SMS, Twilio, etc.) #
    # ---------------------------------------------------------------- #
    sms_provider = models.ForeignKey(
        'sms_providers.SMSProvider',
        verbose_name="SMS Provider",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        help_text="Select the SMS platform to use for purchasing phone numbers"
    )
    sms_api_key = models.CharField(
        verbose_name="SMS Provider API Key",
        max_length=500,
        blank=True, null=True,
        help_text="Your API key for the selected SMS provider"
    )

    # ---------------------------------------------------------------- #
    #  Automation config                                                #
    # ---------------------------------------------------------------- #
    default_country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        verbose_name="Default Country",
        help_text="Country whose phone numbers will be purchased from the SMS provider"
    )
    max_price = models.DecimalField(
        verbose_name="Max Price",
        max_digits=20, decimal_places=4,
        blank=True, null=True,
        help_text="Maximum price you are willing to pay for a phone number"
    )
    default_password = models.CharField(
        verbose_name="Default Password",
        max_length=10,
        blank=True, null=True
    )
    target_accounts = models.PositiveIntegerField(
        verbose_name="Target Accounts to Retrieve",
        blank=True, null=True
    )
    max_attempts = models.PositiveIntegerField(
        verbose_name="Max Phone Number Attempts",
        blank=True, null=True,
        help_text=(
            "Hard limit on total phone numbers tried per job, across all "
            "attempts, before it stops even if the target account count "
            "hasn't been reached. Leave blank to use the system default (10)."
        ),
    )

    def __str__(self):
        return f"{self.user.username}'s Configuration"

    class Meta:
        verbose_name = "User Configuration"
        verbose_name_plural = "User Configurations"
        ordering = ['-created']