"""Config flow for DSB API integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .dsb import DSB, DSBError

_LOGGER = logging.getLogger(__name__)


class DSBConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DSB API."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]

            client = DSB(username, password)

            try:
                valid = await self.hass.async_add_executor_job(
                    client.test_connection
                )
                if valid:
                    await self.async_set_unique_id(username)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"DSB ({username})",
                        data=user_input,
                    )
                else:
                    errors["base"] = "invalid_auth"
            except DSBError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )