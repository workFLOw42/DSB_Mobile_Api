"""DSB API Integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_CHILD_NAME
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
            raise ConfigEntryNotReady(
                "Could not authenticate with DSB API"
            )
    except DSBError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to DSB API: {err}"
        ) from err

    # Initialize hash store
    child_name = entry.data.get(CONF_CHILD_NAME, "dsb")
    hash_store = HashStore(hass, child_name)
    await hash_store.async_load()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "hash_store": hash_store,
        "coordinator": None,  # Set by sensor.py async_setup_entry
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services once (on first entry)
    if not hass.services.has_service(DOMAIN, "fetch_updates"):
        _register_services(hass)

    # Listen for options updates
    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-level services that work across all entries."""

    async def handle_fetch_updates(call: ServiceCall) -> None:
        """Force an immediate API fetch for all (or one) child."""
        child_filter = call.data.get("child_name", "")
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data.get("coordinator")
            if coordinator is None:
                continue
            if child_filter and coordinator.child_name != child_filter:
                continue
            await coordinator.async_refresh()

    async def handle_reload_schedule(call: ServiceCall) -> None:
        """Reload schedule YAML for all (or one) child."""
        child_filter = call.data.get("child_name", "")
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data.get("coordinator")
            if coordinator is None:
                continue
            if child_filter and coordinator.child_name != child_filter:
                continue
            await hass.async_add_executor_job(coordinator.load_schedule)
            await coordinator.async_refresh()
            _LOGGER.info(
                "Schedule reloaded for %s from %s",
                coordinator.child_name,
                coordinator.schedule_file,
            )

    async def handle_set_hash(call: ServiceCall) -> None:
        """Set a hash value in the correct child's store."""
        child_name = call.data.get("child_name", "")
        key = call.data.get("hash_key", "")
        if not key:
            _LOGGER.warning("set_hash called without hash_key")
            return

        # Find the right hash_store by child_name
        target_store = None
        target_coordinator = None
        for entry_data in hass.data[DOMAIN].values():
            hs = entry_data.get("hash_store")
            if hs and hs.child_name == child_name:
                target_store = hs
                target_coordinator = entry_data.get("coordinator")
                break

        if target_store is None:
            _LOGGER.warning(
                "set_hash: no entry found for child_name=%s", child_name
            )
            return

        if "hash_data" in call.data:
            raw = call.data["hash_data"]
            await target_store.async_set_from_data(key, raw)
            _LOGGER.info(
                "set_hash: child=%s key=%s (computed from %d chars)",
                child_name, key, len(str(raw)),
            )
        else:
            value = call.data.get("hash_value", "")
            await target_store.async_set(key, value)
            _LOGGER.info(
                "set_hash: child=%s key=%s value=%s",
                child_name, key, value,
            )

        if target_coordinator:
            await target_coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN, "fetch_updates", handle_fetch_updates
    )
    hass.services.async_register(
        DOMAIN, "reload_schedule", handle_reload_schedule
    )
    hass.services.async_register(
        DOMAIN, "set_hash", handle_set_hash
    )


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update – reload integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Deregister services when last entry is unloaded
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "fetch_updates")
        hass.services.async_remove(DOMAIN, "reload_schedule")
        hass.services.async_remove(DOMAIN, "set_hash")

    return unload_ok
