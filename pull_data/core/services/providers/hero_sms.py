"""
Hero SMS Provider
==================
Implements SMSProviderBase for the HeroSMS platform (https://hero-sms.com/api).

HeroSMS uses the same protocol as SMS-Activate:
  Base URL : https://hero-sms.com/stubs/handler_api.php
  Auth     : ?api_key=<YOUR_API_KEY>  (query param on every request)

setStatus codes
---------------
  3  → Request resending of SMS
  6  → Confirm the activation (OTP received and used)
  8  → Cancel the activation (refund)

getStatus response strings
--------------------------
  STATUS_WAIT_CODE       → Waiting for SMS
  STATUS_OK:<code>       → OTP received, code is <code>
  STATUS_CANCEL          → Activation cancelled
  NO_ACTIVATION          → Unknown activation ID
"""

import json
import logging
import time

import requests

from core.services.sms_base import SMSProviderBase
from core.services.exceptions import (
    SMSProviderError,
    SMSNoNumberError,
    SMSInsufficientFundsError,
    SMSTimeoutError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://hero-sms.com/stubs/handler_api.php"
FACEBOOK_SERVICE = "fb"


# ------------------------------------------------------------------ #
#  Hero SMS specific exceptions (inherit from generic ones)           #
# ------------------------------------------------------------------ #

class HeroSMSError(SMSProviderError):
    """Base exception specific to Hero SMS."""
    pass


class HeroSMSNoNumberError(HeroSMSError, SMSNoNumberError):
    pass


class HeroSMSInsufficientFundsError(HeroSMSError, SMSInsufficientFundsError):
    pass


class HeroSMSTimeoutError(HeroSMSError, SMSTimeoutError):
    pass


# ------------------------------------------------------------------ #
#  Client                                                              #
# ------------------------------------------------------------------ #

class HeroSMSClient(SMSProviderBase):
    """
    Hero SMS implementation of SMSProviderBase.

    Usage
    -----
        client = HeroSMSClient(api_key="your_key_here")
        result = client.get_number(country_id=4, service="fb")
        otp    = client.wait_for_otp(result["activation_id"])
        client.confirm_number(result["activation_id"])
    """

    SERVICE_MAP = {
        "FACEBOOK": "fb",
        "GOOGLE": "go",
    }

    def __init__(self, api_key: str):
        if not api_key:
            raise HeroSMSError("HeroSMS api_key must not be empty.")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.params = {"api_key": api_key}  # type: ignore[assignment]

    # -------------------------------------------------------------- #
    #  Internal helpers                                                #
    # -------------------------------------------------------------- #

    def _get(self, action: str, **params) -> str:
        """Perform a GET request and return the raw response text."""
        payload = {"action": action, **params}
        try:
            response = self.session.get(BASE_URL, params=payload, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("HeroSMS request failed: %s", exc)
            raise HeroSMSError(f"Network error when calling HeroSMS: {exc}") from exc

        raw = response.text.strip()
        logger.debug("HeroSMS [%s] → %s", action, raw)
        self._raise_for_api_error(raw)
        return raw

    @staticmethod
    def _raise_for_api_error(raw: str) -> None:
        """Map known HeroSMS error strings to typed exceptions."""
        error_map = {
            "NO_NUMBERS":  HeroSMSNoNumberError("No numbers available for the requested country/service."),
            "NO_BALANCE":  HeroSMSInsufficientFundsError("Insufficient balance in your HeroSMS account."),
            "BAD_KEY":     HeroSMSError("Invalid HeroSMS API key."),
            "BAD_ACTION":  HeroSMSError("Unknown HeroSMS API action."),
            "BAD_SERVICE": HeroSMSError("Unknown service code passed to HeroSMS."),
            "BAD_STATUS":  HeroSMSError("Invalid status code passed to HeroSMS."),
            "NO_ACTIVATION": HeroSMSError("Activation ID not found on HeroSMS."),
            "ERROR_SQL":   HeroSMSError("Internal HeroSMS server error (SQL)."),
        }
        if raw in error_map:
            raise error_map[raw]

    # -------------------------------------------------------------- #
    #  SMSProviderBase implementation                                  #
    # -------------------------------------------------------------- #

    def get_balance(self) -> float:
        """Return account balance. Response: 'ACCESS_BALANCE:12.50'"""
        raw = self._get("getBalance")
        try:
            return float(raw.split(":")[1])
        except (IndexError, ValueError) as exc:
            raise HeroSMSError(f"Unexpected getBalance response: {raw}") from exc

    def get_countries(self) -> list[dict]:
        """Fetch countries from Hero SMS."""
        raw = self._get("getCountries")
        import json
        try:
            data = json.loads(raw)
            result = []
            for key, c_data in data.items():
                try:
                    c_id = str(int(c_data.get('id', key)))
                    name = c_data.get('eng', f"Country {c_id}")
                    result.append({"provider_country_id": c_id, "name": name})
                except ValueError:
                    continue
            return result
        except json.JSONDecodeError:
            raise HeroSMSError("Failed to parse getCountries JSON")

    def get_number(self, country_id: str, service: str = "FACEBOOK", max_price: float = None) -> dict:
        """
        Purchase a virtual phone number via getNumberV2 (JSON response).

        Returns
        -------
        dict
            {"activation_id": str, "phone": str}
        """
        api_service = self.SERVICE_MAP.get(service, service)
        params = {"country": country_id, "service": api_service}
        if max_price is not None:
            params["maxPrice"] = max_price

        raw = self._get("getNumberV2", **params)
        try:
            data = json.loads(raw)
            if "error" in data:
                self._raise_for_api_error(data["error"])
            return {
                "activation_id": str(data["activationId"]),
                "phone": str(data["phoneNumber"]),
            }
        except (json.JSONDecodeError, KeyError) as exc:
            self._raise_for_api_error(raw)
            raise HeroSMSError(f"Unexpected getNumberV2 response: {raw}") from exc

    def get_status(self, activation_id: str) -> str:
        """
        Check activation status.

        Returns e.g. 'STATUS_WAIT_CODE', 'STATUS_OK:123456', 'STATUS_CANCEL'.
        """
        return self._get("getStatus", id=activation_id)

    def set_status(self, activation_id: str, status_code: int) -> str:
        """
        Update activation status.
          3 → Request resending of SMS
          6 → Confirm activation (OTP received)
          8 → Cancel and refund
        """
        return self._get("setStatus", id=activation_id, status=status_code)

    def cancel_number(self, activation_id: str) -> str:
        """Cancel the activation and request a refund (status 8)."""
        return self.set_status(activation_id, status_code=8)

    def confirm_number(self, activation_id: str) -> str:
        """Confirm OTP was received and used (status 6)."""
        return self.set_status(activation_id, status_code=6)

    def wait_for_otp(
        self,
        activation_id: str,
        poll_interval: int = 5,
        max_attempts: int = 120,
    ) -> str:
        """
        Poll until OTP arrives or timeout is reached (~10 min by default).

        Returns
        -------
        str
            The OTP code string.

        Raises
        ------
        HeroSMSTimeoutError
            If no OTP received within max_attempts * poll_interval seconds.
        HeroSMSError
            If the activation is cancelled.
        """
        logger.info("Waiting for OTP on activation_id=%s ...", activation_id)

        for attempt in range(1, max_attempts + 1):
            status = self.get_status(activation_id)
            logger.debug("Poll %d/%d → %s", attempt, max_attempts, status)

            if status.startswith("STATUS_OK:"):
                otp = status.split(":", 1)[1]
                logger.info("OTP received: %s (activation_id=%s)", otp, activation_id)
                return otp

            if status == "STATUS_CANCEL":
                raise HeroSMSError(f"Activation {activation_id} was cancelled by HeroSMS.")

            time.sleep(poll_interval)

        raise HeroSMSTimeoutError(
            f"No OTP received after {max_attempts * poll_interval}s "
            f"for activation_id={activation_id}."
        )
