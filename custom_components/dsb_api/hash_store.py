"""Persistent hash storage for DSB API integration."""
import hashlib
import json
import logging
import os
import re
from typing import Any, Dict

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# MD5 hex digest is always exactly 32 lowercase hex characters
_EXPECTED_HASH_LEN = 32
_HEX_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class HashStore:
    """Persistent hash storage per child.

    Stores hashes in .storage/dsb_{child}_hashes.json
    Used by Delta Sync to detect changes in Schulaufgaben/Termine/YAML.

    All stored values are guaranteed to be 32-char MD5 hex digests.
    Non-conforming values are either re-hashed or dropped on load.
    """

    def __init__(self, hass: HomeAssistant, child_name: str) -> None:
        """Initialize."""
        self._hass = hass
        self._child_name = child_name
        self._slug = child_name.lower().replace(" ", "_")
        self._path = hass.config.path(
            f".storage/dsb_{self._slug}_hashes.json"
        )
        self._data: Dict[str, str] = {}

    @property
    def child_name(self) -> str:
        """Return the child name this store belongs to."""
        return self._child_name

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_md5(value: str) -> bool:
        """Return True if value looks like a 32-char hex MD5 digest."""
        return bool(_HEX_PATTERN.match(value))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load hashes from disk with validation.

        Values that don't look like MD5 hashes (32 hex chars) are
        dropped and a warning is logged. This handles migration from
        older versions that stored raw data strings.
        """

        def _load() -> Dict[str, str]:
            if not os.path.exists(self._path):
                return {}
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
            except Exception as exc:
                _LOGGER.warning(
                    "Could not load hash store %s: %s", self._path, exc
                )
                return {}

            if not isinstance(raw, dict):
                _LOGGER.warning(
                    "Hash store %s is not a dict – ignoring", self._path
                )
                return {}

            clean: Dict[str, str] = {}
            dirty = False
            for key, value in raw.items():
                if isinstance(value, str) and HashStore._is_valid_md5(value):
                    clean[key] = value
                else:
                    val_len = len(str(value))
                    _LOGGER.warning(
                        "HashStore: dropping '%s' – value is %d chars "
                        "(expected 32-char MD5 hex). "
                        "Re-run initial load to regenerate.",
                        key,
                        val_len,
                    )
                    dirty = True

            if dirty:
                # Rewrite the file without invalid entries
                try:
                    os.makedirs(
                        os.path.dirname(self._path), exist_ok=True
                    )
                    with open(self._path, "w", encoding="utf-8") as fh:
                        json.dump(clean, fh, indent=2)
                    _LOGGER.info(
                        "HashStore: cleaned %s – removed invalid entries",
                        self._path,
                    )
                except Exception as exc:
                    _LOGGER.warning(
                        "HashStore: could not rewrite %s: %s",
                        self._path,
                        exc,
                    )

            return clean

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
        ``sort_keys=True`` first to guarantee deterministic output.

        Always returns exactly 32 lowercase hex characters.
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
        """Store a hash value and persist to disk.

        If *value* doesn't look like a valid MD5 hex digest, it is
        automatically hashed first. This is a safety net for callers
        that accidentally pass raw data instead of a pre-computed hash.
        """
        if not self._is_valid_md5(value):
            original_len = len(value)
            value = self.compute_md5(value)
            _LOGGER.warning(
                "HashStore.async_set('%s'): value was %d chars, "
                "not a valid MD5. Auto-hashed to: %s",
                key,
                original_len,
                value,
            )

        self._data[key] = value
        await self.async_save()

    async def async_set_from_data(self, key: str, data: Any) -> None:
        """Compute MD5 from *data*, store and persist.

        This is the preferred method – always produces a clean 32-char
        hash. Bypasses the validation in async_set since we know the
        output of compute_md5 is valid.
        """
        hash_value = self.compute_md5(data)
        _LOGGER.debug("Hash for '%s': %s", key, hash_value)
        self._data[key] = hash_value
        await self.async_save()

    # ------------------------------------------------------------------
    # Delta-sync helpers
    # ------------------------------------------------------------------

    def has_changed(self, key: str, data: Any) -> bool:
        """Return True if the MD5 of *data* differs from the stored hash."""
        return self.compute_md5(data) != self._data.get(key, "")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, str]:
        """Return a shallow copy of all stored hashes."""
        return dict(self._data)