"""
SMS Provider Hub
=================
Central factory that resolves the correct SMS provider client
based on the user's configuration (UserConfig.sms_provider.slug).

To add a new provider
----------------------
  1. Add a new SMSProvider row in Django Admin (set a unique slug).
  2. Create core/services/providers/<slug>.py with a class inheriting
     from SMSProviderBase.
  3. Import and register that class in PROVIDER_MAP below.
  4. Done — no changes needed anywhere else in the codebase.
"""
import logging

from core.services.sms_base import SMSProviderBase
from core.services.exceptions import SMSProviderError, SMSProviderNotFoundError
from core.services.providers.hero_sms import HeroSMSClient
from core.services.providers.claude_otp import ClaudeOTPClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Provider registry                                                   #
#  slug (matches SMSProvider.slug in DB) → client class               #
# ------------------------------------------------------------------ #
PROVIDER_MAP: dict[str, type[SMSProviderBase]] = {
    "hero-sms": HeroSMSClient,
    "claude-otp": ClaudeOTPClient,  # Just added this one!
    # Future providers — just add an entry here:
    # "twilio": TwilioClient,
}


def get_sms_provider(user_config) -> SMSProviderBase:
    """
    Return the correct SMS provider client for the given UserConfig.

    Parameters
    ----------
    user_config : apps.users.models.UserConfig
        The user's configuration, must have:
          - sms_provider  (FK to SMSProvider, carries the .slug)
          - sms_api_key   (str, the API key for that provider)

    Returns
    -------
    SMSProviderBase
        An initialised provider client ready to use.

    Raises
    ------
    SMSProviderError
        If sms_provider or sms_api_key is not configured.
    SMSProviderNotFoundError
        If the provider slug has no registered implementation.
    """
    if not user_config.sms_provider:
        raise SMSProviderError(
            f"User '{user_config.user.username}' has no SMS provider configured."
        )

    slug = user_config.sms_provider.slug

    if slug not in PROVIDER_MAP:
        raise SMSProviderNotFoundError(
            f"No implementation found for SMS provider slug '{slug}'. "
            f"Registered providers: {list(PROVIDER_MAP.keys())}"
        )

    if not user_config.sms_api_key:
        raise SMSProviderError(
            f"User '{user_config.user.username}' has no API key configured "
            f"for provider '{user_config.sms_provider.name}'."
        )

    client_class = PROVIDER_MAP[slug]
    logger.debug(
        "Resolved SMS provider for user '%s': %s",
        user_config.user.username,
        client_class.__name__,
    )
    return client_class(api_key=user_config.sms_api_key)
