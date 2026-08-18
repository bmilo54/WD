from django.db import models
from core.abstract_models import TimeStampedModel

class SMSProvider(TimeStampedModel):
    """
    Represents a supported SMS provider platform (e.g. Hero SMS, Twilio).

    The `slug` field is the machine-readable key used by the service hub
    (core/services/sms_hub.py) to instantiate the correct provider client.

    To add a new provider:
      1. Add a new SMSProvider entry in Django Admin with the correct slug.
      2. Create a new client class in core/services/providers/<slug>.py.
      3. Register the class in PROVIDER_MAP inside core/services/sms_hub.py.
    """
    name = models.CharField(
        verbose_name="Provider Name",
        max_length=100,
        help_text="Human-readable name, e.g. 'Hero SMS'"
    )
    slug = models.SlugField(
        verbose_name="Provider Slug",
        unique=True,
        help_text="Machine-readable key used in code, e.g. 'hero-sms'"
    )
    website = models.URLField(
        verbose_name="Website",
        blank=True, null=True,
        help_text="Optional link to the provider's website"
    )
    is_active = models.BooleanField(
        verbose_name="Is Active?",
        default=True,
        help_text="Only active providers will appear in user configuration"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "SMS Provider"
        verbose_name_plural = "SMS Providers"
        ordering = ['name']


class ProviderCountryMapping(TimeStampedModel):
    """
    Maps a universal Country to a provider-specific ID.
    e.g. Country="Philippines" + Provider="Hero SMS" -> provider_country_id="4"
    """
    provider = models.ForeignKey(SMSProvider, on_delete=models.CASCADE, related_name="country_mappings")
    country = models.ForeignKey('country.Country', on_delete=models.CASCADE, related_name="provider_mappings")
    provider_country_id = models.CharField(
        verbose_name="Provider's Country ID",
        max_length=50,
        help_text="The ID or code used by THIS provider for this country (e.g. '4' or 'PH')"
    )

    class Meta:
        verbose_name = "Provider Country Mapping"
        verbose_name_plural = "Provider Country Mappings"
        unique_together = [['provider', 'country']]
        ordering = ['provider', 'country']

    def __str__(self):
        return f"{self.country.name} on {self.provider.name} ({self.provider_country_id})"
