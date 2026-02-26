"""Config flow for DSB API integration."""
import logging
import os

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_SCHEDULE_FILE,
    CONF_ENABLE_RAW_SENSOR,
    DEFAULT_SCHEDULE_FILE,
    DEFAULT_ENABLE_RAW_SENSOR,
)
from .dsb import DSB, DSBError

_LOGGER = logging.getLogger(__name__)


class DSBConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DSB API."""

    VERSION = 2

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step – credentials."""
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
                    self._user_data = user_input
                    return await self.async_step_schedule()
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

    async def async_step_schedule(self, user_input=None) -> FlowResult:
        """Handle the schedule file + options step."""
        errors = {}

        if user_input is not None:
            schedule_file = user_input.get(
                CONF_SCHEDULE_FILE, ""
            ).strip()
            enable_raw = user_input.get(
                CONF_ENABLE_RAW_SENSOR, DEFAULT_ENABLE_RAW_SENSOR
            )

            if schedule_file:
                path = self.hass.config.path(schedule_file)
                exists = await self.hass.async_add_executor_job(
                    os.path.exists, path
                )
                if not exists:
                    errors[CONF_SCHEDULE_FILE] = "file_not_found"

            if not errors:
                await self.async_set_unique_id(
                    self._user_data["username"]
                )
                self._abort_if_unique_id_configured()

                data = {
                    **self._user_data,
                    CONF_SCHEDULE_FILE: schedule_file,
                    CONF_ENABLE_RAW_SENSOR: enable_raw,
                }

                title = f"DSB ({self._user_data['username']})"
                if schedule_file:
                    title += f" – {schedule_file}"

                return self.async_create_entry(
                    title=title,
                    data=data,
                )

        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCHEDULE_FILE,
                        default=DEFAULT_SCHEDULE_FILE,
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_RAW_SENSOR,
                        default=DEFAULT_ENABLE_RAW_SENSOR,
                    ): bool,
                }
            ),
            description_placeholders={
                "config_dir": self.hass.config.path(""),
            },
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Options flow to change settings later."""
        return DSBOptionsFlow(config_entry)


class DSBOptionsFlow(config_entries.OptionsFlow):
    """Handle options for DSB API."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            schedule_file = user_input.get(
                CONF_SCHEDULE_FILE, ""
            ).strip()
            enable_raw = user_input.get(
                CONF_ENABLE_RAW_SENSOR, DEFAULT_ENABLE_RAW_SENSOR
            )

            if schedule_file:
                path = self.hass.config.path(schedule_file)
                exists = await self.hass.async_add_executor_job(
                    os.path.exists, path
                )
                if not exists:
                    errors[CONF_SCHEDULE_FILE] = "file_not_found"

            if not errors:
                new_data = {
                    **self._config_entry.data,
                    CONF_SCHEDULE_FILE: schedule_file,
                    CONF_ENABLE_RAW_SENSOR: enable_raw,
                }
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        current_file = self._config_entry.data.get(
            CONF_SCHEDULE_FILE, ""
        )
        current_raw = self._config_entry.data.get(
            CONF_ENABLE_RAW_SENSOR, DEFAULT_ENABLE_RAW_SENSOR
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCHEDULE_FILE,
                        default=current_file,
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_RAW_SENSOR,
                        default=current_raw,
                    ): bool,
                }
            ),
            description_placeholders={
                "config_dir": self.hass.config.path(""),
            },
            errors=errors,
        )