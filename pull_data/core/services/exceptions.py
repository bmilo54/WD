"""
Shared exceptions for all SMS providers.

All provider-specific errors should inherit from these generic ones
so that the automation code only needs to catch SMSProviderError
(or its subclasses) regardless of which provider is active.
"""


class SMSProviderError(Exception):
    """Base exception for all SMS provider errors."""
    pass


class SMSNoNumberError(SMSProviderError):
    """Raised when no phone numbers are available for the requested country/service."""
    pass


class SMSInsufficientFundsError(SMSProviderError):
    """Raised when the provider account balance is too low to buy a number."""
    pass


class SMSTimeoutError(SMSProviderError):
    """Raised when waiting for OTP exceeds the configured timeout limit."""
    pass


class SMSProviderNotFoundError(SMSProviderError):
    """Raised when the configured provider slug has no registered implementation."""
    pass
