"""DSB API Integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .dsb import DSB, DSBError
from .hash_store import HashStore

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DSB API from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    username = entry.data.get("username")
    password = entry.data.get("password")
    client = DSB(username, password)

    try:
        valid = await hass.async_add_executor_job(client.test_connection)
        if not valid:
            raise ConfigEntryNotReady("Could not authenticate with DSB API")
    except DSBError as err:
        raise ConfigEntryNotReady(f"Could not connect to DSB API: {err}") from err

    # Initialize hash store
    child_name = entry.data.get("child_name", "dsb")
    hash_store = HashStore(hass, child_name)
    await hash_store.async_load()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "hash_store": hash_store,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update – reload integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok