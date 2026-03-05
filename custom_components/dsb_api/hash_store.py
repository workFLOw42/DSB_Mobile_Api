"""Persistent hash storage for DSB API integration."""
import json
import logging
import os
from typing import Dict

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HashStore:
    """Persistent hash storage per child.

    Stores hashes in .storage/dsb_{child}_hashes.json
    Used by Delta Sync to detect changes in Schulaufgaben/Termine/YAML.
    """

    def __init__(self, hass: HomeAssistant, child_name: str) -> None:
        """Initialize."""
        self._hass = hass
        self._slug = child_name.lower().replace(" ", "_")
        self._path = hass.config.path(
            f".storage/dsb_{self._slug}_hashes.json"
        )
        self._data: Dict[str, str] = {}

    async def async_load(self) -> None:
        """Load hashes from disk."""

        def _load() -> Dict[str, str]:
            if os.path.exists(self._path):
                try:
                    with open(self._path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as exc:
                    _LOGGER.warning(
                        "Could not load hash store %s: %s",
                        self._path,
                        exc,
                    )
            return {}

        self._data = await self._hass.async_add_executor_job(_load)

    async def async_save(self) -> None:
        """Save hashes to disk."""

        def _save() -> None:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)

        await self._hass.async_add_executor_job(_save)

    def get(self, key: str) -> str:
        """Get a hash value."""
        return self._data.get(key, "")

    async def async_set(self, key: str, value: str) -> None:
        """Set a hash value and persist."""
        self._data[key] = value
        await self.async_save()

    def to_dict(self) -> Dict[str, str]:
        """Return all hashes as dict."""
        return dict(self._data)