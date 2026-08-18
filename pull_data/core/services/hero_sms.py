"""
DEPRECATED — This module has been restructured.

The Hero SMS client now lives in:
    core/services/providers/hero_sms.py

The hub factory (recommended entry point) lives in:
    core/services/sms_hub.py

Please update your imports:
    # Old
    from core.services.hero_sms import HeroSMSClient, get_client_for_user

    # New
    from core.services.providers.hero_sms import HeroSMSClient
    from core.services.sms_hub import get_sms_provider
"""
# Re-export for backwards compatibility during migration
from core.services.providers.hero_sms import (  # noqa: F401
    HeroSMSClient,
    HeroSMSError,
    HeroSMSNoNumberError,
    HeroSMSInsufficientFundsError,
    HeroSMSTimeoutError,
)
