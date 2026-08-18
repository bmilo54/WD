"""
ClaudeOTP Provider
===================
Stub implementation of SMSProviderBase for ClaudeOTP.
"""
import re
import time
import requests
import logging
from core.services.sms_base import SMSProviderBase
from core.services.exceptions import (
    SMSProviderError,
    SMSNoNumberError,
    SMSInsufficientFundsError,
    SMSTimeoutError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://claudeotp.com/api/v1"

class ClaudeOTPClient(SMSProviderBase):
    """
    ClaudeOTP implementation of SMSProviderBase based on their official API Doc.
    """

    # We map our universal service codes to ClaudeOTP's service IDs
    SERVICE_MAP = {
        "FACEBOOK": 544, 
        "GOOGLE": 718,
    }

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Helper to make API requests with the required apikey."""
        url = f"{BASE_URL}{endpoint}"
        
        # All requests must include the apikey parameter
        params = kwargs.pop('params', {})
        params['apikey'] = self.api_key
        
        try:
            response = self.session.request(method, url, params=params, timeout=30, **kwargs)
            response.raise_for_status()
            data = response.json()
            if not data.get("success", True):
                raise SMSProviderError(f"ClaudeOTP Error: {data.get('message', 'Unknown error')}")
            return data
        except requests.HTTPError as exc:
            # `raise_for_status()` fires before we ever look at the response
            # body, and the exception's own message only contains the status
            # code/URL - not WHY the API rejected the request (e.g. a 422
            # almost always comes with a JSON body naming the invalid/missing
            # field). Log that body so failures are actually diagnosable.
            body = None
            if exc.response is not None:
                try:
                    body = exc.response.json()
                except ValueError:
                    body = exc.response.text
            logger.error(f"ClaudeOTP network error: {exc} | Response body: {body}")

            # ClaudeOTP returns HTTP 422 (not a plain "success": false with a
            # 200) when it has no numbers in stock for the requested
            # country/service, e.g.:
            #   {"success": false, "message": "Numbers are out of stock and
            #    being restocked. Please try again in 5 minutes or choose
            #    another country.", "errors": {"order": "..."}}
            # Surface this as SMSNoNumberError (like HeroSMS does for its own
            # NO_NUMBERS code) so callers can tell "temporarily out of stock"
            # apart from a genuine malformed-request/API bug.
            message = ""
            if isinstance(body, dict):
                message = str(body.get("message") or body.get("errors") or "")
            elif isinstance(body, str):
                message = body
            if "out of stock" in message.lower():
                raise SMSNoNumberError(f"ClaudeOTP: {message}") from exc

            raise SMSProviderError(f"Network error: {exc} | Response body: {body}") from exc
        except requests.RequestException as exc:
            logger.error(f"ClaudeOTP network error: {exc}")
            raise SMSProviderError(f"Network error: {exc}") from exc

    def get_balance(self) -> float:
        """GET /profile to get the balance"""
        res = self._request("GET", "/profile")
        balance_str = res.get("data", {}).get("balance", "Rp 0")
        # Assuming balance comes as "Rp 63.276", we need to clean it to float
        clean_str = balance_str.replace("Rp ", "").replace(".", "").replace(",", "")
        try:
            return float(clean_str)
        except ValueError:
            return 0.0

    def get_countries(self) -> list[dict]:
        """GET /services/{service_id}/countries to get the countries"""
        service_id = self.SERVICE_MAP.get("FACEBOOK", 544)
        res = self._request("GET", f"/services/{service_id}/countries")
        
        # The API returns: {"success": true, "data": {"countries": [{"id": 123, "name": "Indonesia"}]}}
        data = res.get("data", {})
        countries_list = data.get("countries", [])
        
        result = []
        for country_data in countries_list:
            if isinstance(country_data, dict):
                c_id = str(country_data.get("id", ""))
                base_name = country_data.get("name", f"Country {c_id}")
                operator = country_data.get("operator", "any")
                price_formatted = country_data.get("price_formatted", "")
                
                # ClaudeOTP splits countries by operator (e.g. telkomsel, indosat)
                # We append the operator and price to the name so they don't overwrite each other in the DB
                name = f"{base_name} ({operator})"
                if price_formatted:
                    name += f" [{price_formatted}]"
                
                if c_id:
                    result.append({"provider_country_id": c_id, "name": name})
                    
        return result

    def get_number(self, country_id: str, service: str, max_price: float = None) -> dict:
        """POST /orders to buy a number"""
        service_id = self.SERVICE_MAP.get(service, service)
        
        # If max_price is provided, we must check the price first since ClaudeOTP 
        # doesn't natively support a maxPrice parameter in the order endpoint.
        if max_price is not None:
            # Fetch the countries for this service to find the price
            res_countries = self._request("GET", f"/services/{service_id}/countries")
            countries_list = res_countries.get("data", {}).get("countries", [])
            
            country_price = None
            for c_data in countries_list:
                if str(c_data.get("id")) == str(country_id):
                    country_price = float(c_data.get("price", 0))
                    break
                    
            if country_price is not None and country_price > float(max_price):
                raise SMSProviderError(f"ClaudeOTP: Price {country_price} exceeds your max_price of {max_price}")

        # The API doc shows passing parameters in the URL for POST, but also mentions form-urlencoded.
        # We will pass them as params which appends them to the URL query string.
        payload = {
            "country": country_id,
            "service_id": service_id
        }
        
        res = self._request("POST", "/orders", data=payload)
        
        # Assuming the response returns the order details in data -> results -> order
        results = res.get("data", {}).get("results", [])
        
        if not results:
            raise SMSNoNumberError(f"No number returned from ClaudeOTP. Raw response: {res}")
            
        order_details = results[0].get("order", {})
        order_id = order_details.get("id")
        phone_number = order_details.get("number", {}).get("value", "")
        
        if not order_id:
            raise SMSNoNumberError(f"Missing order ID. Raw response: {res}")
            
        return {
            "activation_id": str(order_id),
            "phone": phone_number
        }

    def get_status(self, activation_id: str) -> str:
        """We don't strictly need this if we implement wait_for_otp directly via /orders/active"""
        pass

    def _extract_otp_code(self, sms) -> str:
        """
        Extract the numeric OTP code from whatever the 'sms' field returns.
        ClaudeOTP /orders/active returns sms as a LIST of SMS objects:
          [{"id": "678030", "code": "678030", "text": "678030 adalah kode...", ...}]
        Each object has a direct 'code' key with the 6-digit OTP.
        """
        # Case 1: sms is a list — get the first item's 'code' key directly
        if isinstance(sms, list):
            if not sms:
                return ""
            first = sms[0]
            if isinstance(first, dict):
                code = first.get("code") or first.get("value") or first.get("text") or ""
                code = str(code).strip()
                if code.isdigit():
                    return code
                # If the value is a full text (e.g. "678030 adalah kode..."), extract first number
                digits = re.findall(r"\b\d{4,8}\b", code)
                return digits[0] if digits else ""
            return ""

        # Case 2: sms is a dict
        if isinstance(sms, dict):
            raw = sms.get("code") or sms.get("value") or sms.get("text") or ""
        else:
            # Case 3: plain string
            raw = str(sms)

        raw = raw.strip()
        if raw.isdigit():
            return raw

        # Extract a 4–8 digit OTP from text (avoids matching long activation IDs)
        digits = re.findall(r"\b\d{4,8}\b", raw)
        return digits[0] if digits else ""


    def wait_for_otp(self, activation_id: str, poll_interval: int = 5, max_attempts: int = 120) -> str:
        """Poll GET /orders/active until our order receives an SMS"""
        for attempt in range(max_attempts):
            res = self._request("GET", "/orders/active")
            data = res.get("data", {})
            
            # ClaudeOTP returns data as dict with an 'orders' list, or sometimes directly as a list
            if isinstance(data, list):
                orders = data
            else:
                orders = data.get("orders", [])
            
            for order in orders:
                if not isinstance(order, dict):
                    continue
                if str(order.get("id")) == str(activation_id):
                    # Check if sms code is available
                    sms = order.get("sms")
                    if sms:
                        code = self._extract_otp_code(sms)
                        if code:
                            return code
            
            time.sleep(poll_interval)
            
        raise SMSTimeoutError(f"No SMS received for {activation_id} after {max_attempts} attempts.")

    def cancel_number(self, activation_id: str) -> str:
        """DELETE /orders/{order_id}"""
        try:
            self._request("DELETE", f"/orders/{activation_id}")
            return "CANCELLED"
        except SMSProviderError as e:
            return f"Failed to cancel: {e}"

    def confirm_number(self, activation_id: str) -> str:
        """POST /orders/{order_id}/finish"""
        try:
            self._request("POST", f"/orders/{activation_id}/finish")
            return "FINISHED"
        except SMSProviderError as e:
            return f"Failed to finish: {e}"
