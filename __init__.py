"""DSB API Integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .dsb import DSB, DSBError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DSB API from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    username = entry.data.get("username")
    password = entry.data.get("password")

    client = DSB(username, password)

    # Test connection BEFORE forwarding to platforms
    try:
        valid = await hass.async_add_executor_job(client.test_connection)
        if not valid:
            raise ConfigEntryNotReady(
                "Could not authenticate with DSB API"
            )
    except DSBError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to DSB API: {err}"
        ) from err

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok