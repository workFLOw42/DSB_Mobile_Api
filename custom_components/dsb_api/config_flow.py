"""Config flow for DSB API integration."""
import logging
import os

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_CHILD_NAME,
    CONF_CLASS_NAME,
    CONF_SCHEDULE_FILE,
    CONF_ENABLE_RAW_SENSOR,
    DEFAULT_SCHEDULE_FILE,
    DEFAULT_ENABLE_RAW_SENSOR,
)
from .dsb import DSB, DSBError

_LOGGER = logging.getLogger(__name__)


class DSBConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DSB API."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize."""
        self._user_data: dict = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Step 1: Credentials."""
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
                    return await self.async_step_child()
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

    async def async_step_child(self, user_input=None) -> FlowResult:
        """Step 2: Child name + class."""
        if user_input is not None:
            child_name = user_input.get(CONF_CHILD_NAME, "").strip()
            class_name = user_input.get(CONF_CLASS_NAME, "").strip()
            self._user_data[CONF_CHILD_NAME] = child_name
            self._user_data[CONF_CLASS_NAME] = class_name
            return await self.async_step_schedule()

        return self.async_show_form(
            step_id="child",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CHILD_NAME): str,
                    vol.Required(CONF_CLASS_NAME): str,
                }
            ),
        )

    async def async_step_schedule(self, user_input=None) -> FlowResult:
        """Step 3: Schedule file + options."""
        errors = {}

        child_name = self._user_data.get(CONF_CHILD_NAME, "")
        default_file = (
            f"{child_name}_Stundenplan.yaml"
            if child_name
            else DEFAULT_SCHEDULE_FILE
        )

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
                    f"{self._user_data['username']}_{child_name}"
                )
                self._abort_if_unique_id_configured()

                data = {
                    **self._user_data,
                    CONF_SCHEDULE_FILE: schedule_file,
                    CONF_ENABLE_RAW_SENSOR: enable_raw,
                }

                title = (
                    f"DSB ({child_name}"
                    f" {self._user_data.get(CONF_CLASS_NAME, '')})"
                )

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
                        default=default_file,
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_RAW_SENSOR,
                        default=DEFAULT_ENABLE_RAW_SENSOR,
                    ): bool,
                }
            ),
            description_placeholders={
                "config_dir": self.hass.config.path(""),
                "child_name": child_name,
            },
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Options flow."""
        return DSBOptionsFlow()


class DSBOptionsFlow(config_entries.OptionsFlow):
    """Handle options for DSB API."""

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
            child_name = user_input.get(
                CONF_CHILD_NAME,
                self.config_entry.data.get(CONF_CHILD_NAME, ""),
            )
            class_name = user_input.get(
                CONF_CLASS_NAME,
                self.config_entry.data.get(CONF_CLASS_NAME, ""),
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
                    **self.config_entry.data,
                    CONF_SCHEDULE_FILE: schedule_file,
                    CONF_ENABLE_RAW_SENSOR: enable_raw,
                    CONF_CHILD_NAME: child_name,
                    CONF_CLASS_NAME: class_name,
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        current_file = self.config_entry.data.get(
            CONF_SCHEDULE_FILE, ""
        )
        current_raw = self.config_entry.data.get(
            CONF_ENABLE_RAW_SENSOR, DEFAULT_ENABLE_RAW_SENSOR
        )
        current_child = self.config_entry.data.get(CONF_CHILD_NAME, "")
        current_class = self.config_entry.data.get(CONF_CLASS_NAME, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHILD_NAME,
                        default=current_child,
                    ): str,
                    vol.Optional(
                        CONF_CLASS_NAME,
                        default=current_class,
                    ): str,
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