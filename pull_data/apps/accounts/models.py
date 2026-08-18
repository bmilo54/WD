from django.db import models
from core.abstract_models import TimeStampedModel
from django.contrib.auth.models import User
from apps.jobs.models import FlowAttempt

class FacebookAccount(TimeStampedModel):
    """
    This is the Facebook Account models which client request for retrive
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="facebook_accounts", blank=True, null=True) # Easy To Retrive the User Config fields
    attempt = models.OneToOneField(FlowAttempt, on_delete=models.SET_NULL, blank=True, null=True, related_name="account")
    uid = models.CharField(verbose_name="Facebook UID", max_length=100, blank=True, null=True)
    password = models.CharField(verbose_name="Facebook Password", max_length=10, blank=True, null=True)
    cookies = models.JSONField(verbose_name="Facebook Cookies")
    access_token = models.TextField(verbose_name="Access Token", blank=True, null=True)
    is_active = models.BooleanField(verbose_name="Is Active?", default=True)

    def __str__(self):
        phone_number = self.attempt.phone_number if self.attempt else None
        return f"{self.uid} - {phone_number}"

    @property
    def cookie_string(self):
        """
        Normalizes `cookies` into the "name=value; name=value" export
        format, regardless of how it was originally stored:
          - Legacy rows saved the raw Playwright cookie list (a JSON list
            of dicts), which str()-ifies as Python repr if used directly.
          - Newer rows save the pre-joined "name=value; ..." string.
        Also strips the `locale` cookie (an internal automation detail,
        not something consumers of the export need) even for older rows
        saved before that was filtered out at recovery time.
        """
        cookies = self.cookies

        if isinstance(cookies, list):
            pairs = [
                (c.get('name'), c.get('value'))
                for c in cookies
                if isinstance(c, dict) and c.get('name') != 'locale'
            ]
        elif isinstance(cookies, str):
            pairs = []
            for part in cookies.split(';'):
                part = part.strip()
                if not part or '=' not in part:
                    continue
                name, _, value = part.partition('=')
                if name.strip() == 'locale':
                    continue
                pairs.append((name.strip(), value.strip()))
        else:
            return cookies or ""

        return "; ".join(f"{name}={value}" for name, value in pairs)

    class Meta:
        verbose_name = "Facebook Account"
        verbose_name_plural = "Facebook Accounts"
        ordering = ['-created', ]
        unique_together = [["user", "uid"]]
