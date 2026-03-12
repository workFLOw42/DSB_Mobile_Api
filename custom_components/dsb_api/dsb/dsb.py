"""DSB Mobile API Client."""
import json
import logging
from typing import List, Dict, Optional, Any

import requests

_LOGGER = logging.getLogger(__name__)


class DSBError(Exception):
    """Base exception for DSB API errors."""
    pass


class DSBAuthError(DSBError):
    """Authentication error."""
    pass


class DSBConnectionError(DSBError):
    """Connection error."""
    pass


class DSBParseError(DSBError):
    """Parse error."""
    pass


class DSB:
    """DSB Mobile API Client."""

    BASE_URL = "https://mobileapi.dsbcontrol.de/"
    TIMEOUT = 30

    def __init__(self, username: str, password: str):
        self._username: str = username
        self._password: str = password
        self._token: Optional[str] = None

    def get_plans(self, plan_mapping: Optional[Dict[str, str]] = None) -> list:
        """Get substitution plans."""
        from .timetable_objects import Plan
        plan_mapping = plan_mapping or {}
        raw_data = self._get_raw_data("dsbtimetables")
        return [Plan(data, plan_mapping) for data in raw_data]

    def get_news(self) -> list:
        """Get news entries."""
        from .timetable_objects import News
        raw_data = self._get_raw_data("newstab")
        return [News(data) for data in raw_data]

    def get_postings(self) -> list:
        """Get postings/documents."""
        from .timetable_objects import Posting
        raw_data = self._get_raw_data("dsbdocuments")
        return [Posting(data) for data in raw_data]

    def _get_raw_data(self, endpoint: str) -> list:
        """Fetch raw data from API endpoint."""
        try:
            response = requests.get(
                self.BASE_URL + endpoint,
                params={"authid": self._get_auth_token()},
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            return json.loads(response.text)
        except requests.exceptions.HTTPError as e:
            if response.status_code in (401, 403):
                self.invalidate_token()
                raise DSBAuthError(f"Authentication failed: {e}")
            raise DSBConnectionError(f"HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            raise DSBConnectionError(f"Connection error: {e}")
        except json.JSONDecodeError as e:
            raise DSBParseError(f"Invalid JSON response: {e}")

    def _get_auth_token(self) -> str:
        """Get or refresh authentication token."""
        if self._token:
            return self._token
        self._token = self._request_new_token()
        return self._token

    def _request_new_token(self) -> str:
        """Request a new authentication token."""
        params = {
            "user": self._username,
            "password": self._password,
            "bundleid": "de.heinekingmedie.dsbmobile",
            "appversion": 35,
            "osversion": 22,
        }

        try:
            # WICHTIG: "authid?pushid" ist der literal Pfad aus dem Original
            response = requests.get(
                self.BASE_URL + "authid?pushid",
                params=params,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            token = json.loads(response.content)

            if not token or token == "":
                raise DSBAuthError("Invalid credentials - empty token")

            if isinstance(token, str):
                token = token.strip('"')

            return token

        except requests.exceptions.HTTPError as e:
            raise DSBAuthError(f"Failed to authenticate: {e}")
        except requests.exceptions.RequestException as e:
            raise DSBConnectionError(f"Connection failed: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            raise DSBParseError(f"Invalid token response: {e}")

    def invalidate_token(self) -> None:
        """Invalidate the current token."""
        self._token = None

    def test_connection(self) -> bool:
        """Test if credentials are valid and cache the token."""
        try:
            self._token = self._request_new_token()
            return True
        except DSBError:
            return False