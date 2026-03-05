"""Persistent hash storage for DSB API integration."""
import hashlib
import json
import logging
import os
from typing import Any, Dict

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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load hashes from disk."""

        def _load() -> Dict[str, str]:
            if os.path.exists(self._path):
                try:
                    with open(self._path, "r", encoding="utf-8") as fh:
                        return json.load(fh)
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
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)

        await self._hass.async_add_executor_job(_save)

    # ------------------------------------------------------------------
    # Hash computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_md5(data: Any) -> str:
        """Compute MD5 hex-digest from any JSON-serialisable input.

        Strings are hashed directly; everything else is serialised with
        ``sort_keys=True`` first to guarantee deterministic output for
        dicts whose key order may vary.
        """
        if not isinstance(data, str):
            data = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Getters / setters
    # ------------------------------------------------------------------

    def get(self, key: str) -> str:
        """Return the stored hash for *key* (empty string if missing)."""
        return self._data.get(key, "")

    async def async_set(self, key: str, value: str) -> None:
        """Store a pre-computed hash value and persist to disk."""
        self._data[key] = value
        await self.async_save()

    async def async_set_from_data(self, key: str, data: Any) -> None:
        """Compute MD5 from *data*, store and persist."""
        hash_value = self.compute_md5(data)
        _LOGGER.debug("Hash for '%s': %s", key, hash_value)
        await self.async_set(key, hash_value)

    # ------------------------------------------------------------------
    # Delta-sync helpers
    # ------------------------------------------------------------------

    def has_changed(self, key: str, data: Any) -> bool:
        """Return ``True`` if the MD5 of *data* differs from the stored hash."""
        return self.compute_md5(data) != self._data.get(key, "")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, str]:
        """Return a shallow copy of all stored hashes."""
        return dict(self._data)