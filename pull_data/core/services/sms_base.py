"""
Abstract base class for all SMS provider clients.

Every provider (Hero SMS, Twilio, etc.) must inherit from SMSProviderBase
and implement all abstract methods. This enforces a consistent interface
so the rest of the system never needs to know which provider is active.
"""
from abc import ABC, abstractmethod

from core.services.exceptions import SMSProviderError  # noqa: F401 — re-exported for convenience


class SMSProviderBase(ABC):
    """
    Abstract contract that every SMS provider client must fulfil.

    Usage (from automation code)
    ----------------------------
        from core.services.sms_hub import get_sms_provider

        provider = get_sms_provider(user_config)   # returns the right subclass
        result   = provider.get_number(country_id=4)
        otp      = provider.wait_for_otp(result["activation_id"])
        provider.confirm_number(result["activation_id"])
    """

    def __init__(self, api_key: str):
        """
        Initialise the provider with an API key.

        Parameters
        ----------
        api_key : str
            The user's API key for this provider.
        """
        self.api_key = api_key

    @abstractmethod
    def get_balance(self) -> float:
        """
        Return the current account balance for this provider.

        Returns
        -------
        float
            Balance in the provider's account currency.
        """
        ...

    @abstractmethod
    def get_countries(self) -> list[dict]:
        """
        Fetch the list of supported countries from the provider.
        
        Returns
        -------
        list[dict]
            A list of dictionaries containing at least:
            [{"provider_country_id": "...", "name": "..."}, ...]
        """
        ...

    @abstractmethod
    def get_number(self, country_id: str, service: str, max_price: float = None) -> dict:
        """
        Purchase a virtual phone number from the provider.
        
        Parameters
        ----------
        country_id : str
            The provider-specific country ID.
        service : str
            The universal service code (e.g., 'FACEBOOK').
        max_price : float, optional
            The maximum price to pay for the number.
            
        Returns
        -------
        dict
            Must contain at least:
              {"activation_id": str, "phone": str}
        """
        ...

    @abstractmethod
    def get_status(self, activation_id: str) -> str:
        """
        Check the status of a pending activation.

        Parameters
        ----------
        activation_id : str
            The activation ID returned by get_number().

        Returns
        -------
        str
            Provider-specific status string.
        """
        ...

    @abstractmethod
    def wait_for_otp(
        self,
        activation_id: str,
        poll_interval: int = 5,
        max_attempts: int = 120,
    ) -> str:
        """
        Block and poll until the OTP SMS is received or timeout is reached.

        Parameters
        ----------
        activation_id : str
            The activation ID to poll.
        poll_interval : int
            Seconds between each poll (default: 5).
        max_attempts : int
            Maximum poll attempts before raising SMSTimeoutError.

        Returns
        -------
        str
            The OTP code string received via SMS.
        """
        ...

    @abstractmethod
    def cancel_number(self, activation_id: str) -> str:
        """
        Cancel the activation and request a refund.

        Parameters
        ----------
        activation_id : str
            The activation ID to cancel.

        Returns
        -------
        str
            Provider response string.
        """
        ...

    @abstractmethod
    def confirm_number(self, activation_id: str) -> str:
        """
        Confirm that the OTP was received and used successfully.

        Parameters
        ----------
        activation_id : str
            The activation ID to confirm.

        Returns
        -------
        str
            Provider response string.
        """
        ...
