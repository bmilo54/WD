from django import forms

from apps.country.models import Country
from apps.sms_providers.models import SMSProvider


class JobCreateForm(forms.Form):
    """
    Optional per-run overrides for a new AutomationJob - i.e. "customize
    this job" settings. Leaving any field blank falls back to the user's
    saved UserConfig default for that setting at run time.
    """
    sms_provider = forms.ModelChoiceField(
        label="SMS Provider (override)",
        queryset=SMSProvider.objects.all(),
        required=False,
        help_text="Leave blank to use your saved default SMS provider.",
    )
    sms_api_key = forms.CharField(
        label="SMS Provider API Key (override)",
        required=False,
        help_text="Leave blank to use your saved default API key.",
    )
    country = forms.ModelChoiceField(
        label="Country (override)",
        queryset=Country.objects.filter(is_active=True),
        required=False,
        help_text="Leave blank to use your saved default country.",
    )
    target_accounts = forms.IntegerField(
        label="Target Accounts (override)",
        min_value=1,
        required=False,
        help_text="Leave blank to use your saved default target account count.",
    )
    max_price = forms.DecimalField(
        label="Max Price (override)",
        min_value=0,
        required=False,
        help_text="Leave blank to use your saved default max price.",
    )
    default_password = forms.CharField(
        label="Default Password (override)",
        max_length=10,
        required=False,
        help_text="Leave blank to use your saved default password.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
