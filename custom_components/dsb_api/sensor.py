"""Service handlers for the DSB API integration."""
import json
import logging
from typing import Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .hash_store import HashStore

_LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

SERVICE_SET_HASH = "set_hash"

SCHEMA_SET_HASH = vol.Schema(
    {
        vol.Required("child_name"): cv.string,
        vol.Required("hash_key"): cv.string,
        vol.Exclusive("hash_value", "hash_source"): cv.string,
        vol.Exclusive("hash_data", "hash_source"): vol.Any(
            cv.string, list, dict
        ),
    }
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_hash_store(hass: HomeAssistant, child_name: str) -> HashStore:
    """Return the HashStore instance for *child_name*.

    Creates and caches one store per child inside ``hass.data[DOMAIN]``.
    """
    stores: Dict[str, HashStore] = hass.data.setdefault(DOMAIN, {}).setdefault(
        "hash_stores", {}
    )
    slug = child_name.lower().replace(" ", "_")

    if slug not in stores:
        stores[slug] = HashStore(hass, child_name)

    return stores[slug]


# ------------------------------------------------------------------
# Service handlers
# ------------------------------------------------------------------


async def async_handle_set_hash(call: ServiceCall) -> None:
    """Handle ``dsb_api.set_hash``.

    Accepts **either** a pre-computed ``hash_value`` string **or** raw
    ``hash_data`` (any JSON-serialisable type).  When ``hash_data`` is
    provided the MD5 is computed server-side so the YAML script never
    needs the non-existent Jinja2 ``hash`` filter.
    """
    hass = call.hass  # type: ignore[attr-defined]
    child_name: str = call.data["child_name"]
    hash_key: str = call.data["hash_key"]

    store = _get_hash_store(hass, child_name)
    await store.async_load()

    if "hash_data" in call.data:
        # --- New: raw data in → MD5 computed here ---
        raw = call.data["hash_data"]
        await store.async_set_from_data(hash_key, raw)
        _LOGGER.info(
            "dsb_api.set_hash  child=%s  key=%s  (computed from data)",
            child_name,
            hash_key,
        )
    else:
        # --- Legacy: pre-computed hash string ---
        hash_value: str = call.data["hash_value"]
        await store.async_set(hash_key, hash_value)
        _LOGGER.info(
            "dsb_api.set_hash  child=%s  key=%s  value=%s",
            child_name,
            hash_key,
            hash_value,
        )


async def async_handle_get_hash(call: ServiceCall) -> Dict[str, str]:
    """Handle ``dsb_api.get_hash`` – return all hashes for a child."""
    hass = call.hass  # type: ignore[attr-defined]
    child_name: str = call.data["child_name"]

    store = _get_hash_store(hass, child_name)
    await store.async_load()
    return store.to_dict()


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register all DSB API services."""

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HASH,
        async_handle_set_hash,
        schema=SCHEMA_SET_HASH,
    )

    hass.services.async_register(
        DOMAIN,
        "get_hash",
        async_handle_get_hash,
        schema=vol.Schema(
            {
                vol.Required("child_name"): cv.string,
            }
        ),
    )

    _LOGGER.debug("DSB API services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister all DSB API services."""
    hass.services.async_remove(DOMAIN, SERVICE_SET_HASH)
    hass.services.async_remove(DOMAIN, "get_hash")
    _LOGGER.debug("DSB API services removed")