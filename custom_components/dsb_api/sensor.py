"""DSB API Sensor for Home Assistant – scheduling via HA automations."""
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    CONF_CHILD_NAME,
    CONF_CLASS_NAME,
    CONF_SCHEDULE_FILE,
    CONF_ENABLE_RAW_SENSOR,
    DEFAULT_ENABLE_RAW_SENSOR,
)
from .dsb import DSB, DSBError
from .hash_store import HashStore

_LOGGER = logging.getLogger(__name__)

# Recorder attribute size limit (HA default: 16384 bytes)
_MAX_ATTR_SIZE = 16384
# Safety margin – aim for 14KB to leave room for JSON encoding overhead
_TARGET_ATTR_SIZE = 14000

WOCHENTAG_MAP = {
    0: "montag",
    1: "dienstag",
    2: "mittwoch",
    3: "donnerstag",
    4: "freitag",
}


# ──────────────────────────────────────────────
#  Helper: Slugify
# ──────────────────────────────────────────────
def _slugify(text: str) -> str:
    """Create a slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[äÄ]", "ae", text)
    text = re.sub(r"[öÖ]", "oe", text)
    text = re.sub(r"[üÜ]", "ue", text)
    text = re.sub(r"[ß]", "ss", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text


# ──────────────────────────────────────────────
#  Helper: Attribute size check
# ──────────────────────────────────────────────
def _attrs_size(attrs: Dict[str, Any]) -> int:
    """Estimate JSON-encoded size of attributes dict."""
    try:
        return len(json.dumps(attrs, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _warn_if_too_large(sensor_name: str, attrs: Dict[str, Any]) -> None:
    """Log a warning if attributes exceed the target size."""
    size = _attrs_size(attrs)
    if size > _TARGET_ATTR_SIZE:
        _LOGGER.warning(
            "%s attributes are %d bytes (target: %d, limit: %d). "
            "Consider reducing data or excluding from recorder.",
            sensor_name,
            size,
            _TARGET_ATTR_SIZE,
            _MAX_ATTR_SIZE,
        )


# ──────────────────────────────────────────────
#  Helper Functions
# ──────────────────────────────────────────────
def _load_schedule(hass: HomeAssistant, filename: str) -> Dict[str, Any]:
    """Load schedule YAML from HA config directory."""
    if not filename:
        return {}
    path = hass.config.path(filename)
    # Validate path stays within config directory
    resolved = os.path.realpath(path)
    config_dir = os.path.realpath(hass.config.config_dir)
    if not resolved.startswith(config_dir + os.sep) and resolved != config_dir:
        _LOGGER.error(
            "Schedule file path escapes config directory: %s", filename
        )
        return {}
    _LOGGER.debug("Looking for schedule at: %s", path)
    if not os.path.exists(path):
        _LOGGER.warning("Schedule file not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        _LOGGER.info(
            "Schedule loaded from %s (%d bytes)", path, os.path.getsize(path)
        )
        return data or {}
    except Exception as exc:
        _LOGGER.error("Error loading schedule from %s: %s", path, exc)
        return {}


def _extract_lehrer_profil(stundenplan: Dict[str, Any]) -> List[str]:
    """Extract unique teacher codes from the timetable."""
    lehrer: Set[str] = set()
    for day_data in stundenplan.values():
        if isinstance(day_data, dict):
            for stunde_data in day_data.values():
                if isinstance(stunde_data, dict):
                    code = stunde_data.get("lehrer", "")
                    if code:
                        lehrer.add(code)
    return sorted(lehrer)


def _deduplicate_entries(
    entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove duplicate entries based on key fields."""
    seen: Set[Tuple] = set()
    unique: List[Dict[str, Any]] = []
    for entry in entries:
        key = (
            str(entry.get("Klasse(n)", "")),
            str(entry.get("Stunde", "")),
            str(entry.get("Fach", "")),
            str(entry.get("(Lehrer)", "")),
            str(entry.get("Art", "")),
            str(entry.get("_date", "")),
        )
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def _parse_stunde_range(stunde_str: str) -> List[str]:
    """Parse 'Stunde' field: '5' -> ['5'], '5 - 6' -> ['5', '6']."""
    stunde_str = str(stunde_str).strip()
    match = re.match(r"(\d+)\s*-\s*(\d+)", stunde_str)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        return [str(i) for i in range(start, end + 1)]
    if stunde_str.isdigit():
        return [stunde_str]
    return []


def _matches_exclude(
    entry: Dict[str, Any], exclude_rules: List[Dict]
) -> bool:
    """Check if a DSB entry matches any exclude rule."""
    entry_fach = str(entry.get("Fach", "")).strip().upper()
    entry_lehrer = str(entry.get("(Lehrer)", "")).strip().upper()
    for rule in exclude_rules:
        rule_fach = str(rule.get("fach", "")).strip().upper()
        rule_lehrer = str(rule.get("lehrer", "")).strip().upper()
        if rule_fach and rule_fach == entry_fach:
            if rule_lehrer:
                if rule_lehrer == entry_lehrer:
                    return True
            else:
                return True
    return False


def _filter_for_klasse(
    entries: List[Dict[str, Any]],
    klasse: str,
    exclude_rules: List[Dict],
) -> List[Dict[str, Any]]:
    """Filter entries for a specific class and apply exclude rules."""
    filtered = []
    for entry in entries:
        klassen_str = str(entry.get("Klasse(n)", ""))
        klassen_list = [k.strip() for k in klassen_str.split(",")]
        if klasse not in klassen_list:
            continue
        if _matches_exclude(entry, exclude_rules):
            _LOGGER.debug(
                "Excluded: Fach=%s Lehrer=%s",
                entry.get("Fach"),
                entry.get("(Lehrer)"),
            )
            continue
        filtered.append(entry)
    return filtered


def _entries_by_date(
    entries: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group entries by _date field (YYYY-MM-DD)."""
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        date_str = str(entry.get("_date", ""))[:10]
        if date_str:
            by_date.setdefault(date_str, []).append(entry)
    return by_date


def _date_to_wochentag(date_str: str) -> str:
    """Convert YYYY-MM-DD to German weekday name."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return WOCHENTAG_MAP.get(dt.weekday(), "")
    except ValueError:
        return ""


def _find_dsb_for_stunde(
    stunde: str,
    dsb_entries: List[Dict[str, Any]],
    plan_fach: str,
    plan_lehrer: str,
) -> Optional[Dict[str, Any]]:
    """Find the best matching DSB entry for a specific lesson."""
    candidates = []
    for entry in dsb_entries:
        if stunde in _parse_stunde_range(entry.get("Stunde", "")):
            candidates.append(entry)
    if not candidates:
        return None
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    for entry in candidates:
        score = 0
        e_fach = str(entry.get("Fach", "")).strip().upper()
        e_lehrer = str(entry.get("(Lehrer)", "")).strip().upper()
        if e_fach == plan_fach.upper():
            score += 10
        elif plan_fach.upper() in e_fach or e_fach in plan_fach.upper():
            score += 5
        if plan_lehrer and plan_lehrer not in ("?", ""):
            if e_lehrer == plan_lehrer.upper():
                score += 20
        if score > best_score:
            best_score = score
            best = entry
    return best


def _is_entfall(entry: Dict[str, Any]) -> bool:
    """Check if a DSB entry indicates cancellation."""
    art = str(entry.get("Art", "")).strip().lower()
    le_nach = str(entry.get("(Le.) nach", "") or "").strip().lower()
    text = str(entry.get("Text", "")).lower()
    return (
        art == "entfall"
        or "entfall" in le_nach
        or "entfällt" in text
        or "entfall" in text
    )


def _determine_status(entry: Dict[str, Any], plan_raum: str) -> str:
    """Determine lesson status from a DSB entry."""
    if _is_entfall(entry):
        return "entfall"
    art = str(entry.get("Art", "")).strip().lower()
    if art == "betreuung":
        return "betreuung"
    if art == "verlegung":
        return "verlegung"
    dsb_raum = str(entry.get("Raum", "")).strip()
    if dsb_raum and dsb_raum != "---" and dsb_raum != plan_raum:
        return "raum_aenderung"
    return "vertretung"


def _merge_schedule_with_dsb(
    schedule_day: Dict[str, Any],
    dsb_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge one day of the timetable with DSB substitution entries.

    Returns a slim dict per stunde – no raw DSB match data.
    """
    merged: Dict[str, Any] = {}
    for stunde, plan_info in schedule_day.items():
        result = {
            "fach": plan_info.get("fach", "?"),
            "raum": plan_info.get("raum", "?"),
            "lehrer": plan_info.get("lehrer", "?"),
            "uhrzeit": plan_info.get("uhrzeit", "?"),
            "status": "normal",
            "original_raum": None,
            "vertreter": None,
            "dsb_text": None,
            "dsb_art": None,
        }
        dsb_match = _find_dsb_for_stunde(
            stunde,
            dsb_entries,
            plan_info.get("fach", ""),
            plan_info.get("lehrer", "?"),
        )
        if dsb_match:
            status = _determine_status(
                dsb_match, plan_info.get("raum", "")
            )
            result["status"] = status
            result["dsb_text"] = dsb_match.get("Text", "")
            result["dsb_art"] = dsb_match.get("Art", "")
            result["vertreter"] = dsb_match.get("Vertreter", "")
            if status == "entfall":
                result["raum"] = "---"
            elif status in (
                "raum_aenderung",
                "vertretung",
                "betreuung",
                "verlegung",
            ):
                dsb_raum = str(dsb_match.get("Raum", "---")).strip()
                if dsb_raum and dsb_raum != "---":
                    result["original_raum"] = plan_info.get("raum", "?")
                    result["raum"] = dsb_raum
        merged[stunde] = result
    return merged


# ──────────────────────────────────────────────
#  Coordinator – no auto-polling, service-driven
# ──────────────────────────────────────────────
class DSBCoordinator(DataUpdateCoordinator):
    """Coordinator for DSB API data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DSB,
        schedule_file: str,
        hash_store: HashStore,
        child_name: str = "",
    ) -> None:
        super().__init__(
            hass, _LOGGER, name="DSB API", update_interval=None
        )
        self.client = client
        self._schedule_file = schedule_file
        self._schedule_data: Dict[str, Any] = {}
        self._schedule_loaded = False
        self.hash_store = hash_store
        self._child_name = child_name

    @property
    def child_name(self) -> str:
        return self._child_name

    @property
    def schedule_file(self) -> str:
        return self._schedule_file

    def load_schedule(self) -> None:
        """Load or reload the schedule YAML."""
        self._schedule_data = _load_schedule(
            self.hass, self._schedule_file
        )
        self._schedule_loaded = bool(self._schedule_data)
        if self._schedule_loaded:
            meta = self._schedule_data.get("meta", {})
            _LOGGER.info(
                "Schedule loaded: %s (%s) from %s",
                meta.get("schueler", "?"),
                meta.get("klasse", "?"),
                self._schedule_file,
            )
        elif self._schedule_file:
            _LOGGER.warning(
                "Schedule could not be loaded from %s",
                self._schedule_file,
            )

    @property
    def schedule(self) -> Dict[str, Any]:
        return self._schedule_data

    @property
    def klasse(self) -> str:
        return self._schedule_data.get("meta", {}).get("klasse", "")

    @property
    def exclude_rules(self) -> List[Dict]:
        return self._schedule_data.get("exclude", [])

    @property
    def stundenplan(self) -> Dict[str, Any]:
        return self._schedule_data.get("stundenplan", {})

    @property
    def config_block(self) -> Dict[str, Any]:
        """Return YAML config for automations.

        Lean version for sensor attributes – no stundenplan, no hashes,
        no exclude rules. Keeps ConfigSensor under 16KB.
        """
        schedule = self._schedule_data
        stundenplan = schedule.get("stundenplan", {})
        return {
            "meta": schedule.get("meta", {}),
            "zeitraum": schedule.get("zeitraum", {}),
            "sensoren": schedule.get("sensoren", {}),
            "ogts": schedule.get("ogts", {}),
            "termine_filter": schedule.get("termine_filter", {}),
            "emojis": schedule.get("emojis", {}),
            "kurzstunden": schedule.get("kurzstunden", {}),
            "lehrer_profil": _extract_lehrer_profil(stundenplan),
        }

    @property
    def config_block_full(self) -> Dict[str, Any]:
        """Full config for direct Python access – NOT in sensor attrs.

        Includes exclude rules and hashes. Only used by coordinator
        internals or future Python-based automations.
        """
        cfg = dict(self.config_block)
        cfg["exclude"] = self._schedule_data.get("exclude", [])
        cfg["hashes"] = self.hash_store.to_dict()
        return cfg

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from DSB API."""
        now = datetime.now()
        if not self._schedule_loaded and self._schedule_file:
            await self.hass.async_add_executor_job(self.load_schedule)
        _LOGGER.info("Fetching DSB data at %s", now.strftime("%H:%M:%S"))
        try:
            plans = await self.hass.async_add_executor_job(
                self.client.get_plans
            )
            all_entries: List[Dict[str, Any]] = []
            all_days: List[Dict[str, Any]] = []
            all_raw_tables: List[Dict[str, Any]] = []
            for plan in plans:
                all_raw_tables.extend(plan.raw_tables)
                for day in plan.days:
                    day_entries: List[Dict[str, Any]] = []
                    for entry in day.entries:
                        try:
                            entry_dict = entry.to_dict()
                            all_entries.append(entry_dict)
                            day_entries.append(entry_dict)
                        except Exception as exc:
                            _LOGGER.debug(
                                "Error converting entry: %s", exc
                            )
                    all_days.append(
                        {
                            "date": (
                                day.date.isoformat()
                                if day.date
                                else None
                            ),
                            "entries": day_entries,
                            "count": len(day_entries),
                        }
                    )
            all_entries = _deduplicate_entries(all_entries)
            for day_data in all_days:
                day_data["entries"] = _deduplicate_entries(
                    day_data["entries"]
                )
                day_data["count"] = len(day_data["entries"])
            return {
                "entries": all_entries,
                "days": all_days,
                "count": len(all_entries),
                "day_count": len(all_days),
                "raw_tables": all_raw_tables,
                "raw_table_count": len(all_raw_tables),
                "last_updated": now.isoformat(),
            }
        except DSBError as err:
            _LOGGER.error("DSB API Error: %s", err)
            raise UpdateFailed(f"DSB API Error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error: %s", err)
            if self.data:
                return self.data
            raise UpdateFailed(f"Unexpected error: {err}") from err


# ──────────────────────────────────────────────
#  Sensor Setup
# ──────────────────────────────────────────────
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DSB API sensors from config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]
    hash_store = data["hash_store"]

    schedule_file = config_entry.options.get(
        CONF_SCHEDULE_FILE,
        config_entry.data.get(CONF_SCHEDULE_FILE, ""),
    )
    enable_raw = config_entry.options.get(
        CONF_ENABLE_RAW_SENSOR,
        config_entry.data.get(
            CONF_ENABLE_RAW_SENSOR, DEFAULT_ENABLE_RAW_SENSOR
        ),
    )

    child_name_cfg = config_entry.data.get(CONF_CHILD_NAME, "")
    coordinator = DSBCoordinator(
        hass, client, schedule_file, hash_store, child_name_cfg
    )

    # Store coordinator in hass.data for service handlers
    hass.data[DOMAIN][config_entry.entry_id]["coordinator"] = coordinator

    if schedule_file:
        await hass.async_add_executor_job(coordinator.load_schedule)

    await coordinator.async_config_entry_first_refresh()

    child_name = config_entry.options.get(
        CONF_CHILD_NAME,
        config_entry.data.get(CONF_CHILD_NAME, ""),
    )
    class_name = config_entry.options.get(
        CONF_CLASS_NAME,
        config_entry.data.get(CONF_CLASS_NAME, ""),
    )

    entities: list[SensorEntity] = []

    # 1) Schulinfo – always
    entities.append(
        DSBSchulInfoSensor(
            coordinator, config_entry, child_name, class_name
        )
    )

    # 2) Raw – optional debug
    if enable_raw:
        entities.append(
            DSBRawSensor(
                coordinator, config_entry, child_name, class_name
            )
        )
        _LOGGER.info("Raw debug sensor enabled")

    # 3) Student – if schedule loaded
    if coordinator.schedule:
        entities.append(
            DSBStudentSensor(
                coordinator, config_entry, child_name, class_name
            )
        )
        _LOGGER.info(
            "Student sensor created for %s (%s) using %s",
            child_name,
            class_name,
            schedule_file,
        )
    elif schedule_file:
        _LOGGER.warning(
            "Schedule file '%s' configured but could not be loaded",
            schedule_file,
        )

    # 4) Config – if schedule loaded
    if coordinator.schedule:
        entities.append(
            DSBConfigSensor(
                coordinator, config_entry, child_name, class_name
            )
        )

    # 5) Hash – always
    entities.append(
        DSBHashSensor(
            coordinator, config_entry, child_name, hash_store
        )
    )

    async_add_entities(entities)

    # Services are registered in __init__.py at integration level


# ──────────────────────────────────────────────
#  Sensor 1: Schulinfo
# ──────────────────────────────────────────────
class DSBSchulInfoSensor(CoordinatorEntity, SensorEntity):
    """School info sensor – daily announcements and metadata."""

    def __init__(
        self,
        coordinator: DSBCoordinator,
        config_entry: ConfigEntry,
        child_name: str,
        class_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_schulinfo"
        slug = (
            _slugify(f"dsb {child_name} schulinfo")
            if child_name
            else "dsb_schulinfo"
        )
        self.entity_id = f"sensor.{slug}"
        self._attr_name = (
            f"DSB {child_name} Schulinfo"
            if child_name
            else "DSB Schulinfo"
        )
        self._attr_icon = "mdi:bulletin-board"

    def _build_schulinfo(self) -> Dict[str, Any]:
        if not self.coordinator.data:
            return {}
        raw_tables = self.coordinator.data.get("raw_tables", [])
        info_by_date: Dict[str, Any] = {}
        for table in raw_tables:
            date_str = str(table.get("date", ""))[:10]
            if not date_str:
                continue
            info_lines = []
            for info_row in table.get("info", []):
                line = " ".join(
                    str(cell).strip()
                    for cell in info_row
                    if str(cell).strip()
                )
                if line:
                    info_lines.append(line)
            stand = ""
            for head in table.get("mon_heads", []):
                if "Stand:" in str(head):
                    parts = str(head).split("Stand:")
                    if len(parts) > 1:
                        stand = parts[1].strip()
            info_by_date[date_str] = {
                "title": table.get("title", ""),
                "nachrichten": info_lines,
                "stand": stand,
                "klassen_betroffen": table.get("class_groups", []),
                "total_eintraege": table.get("total_rows", 0),
                "url": table.get("url", ""),
            }
        return info_by_date

    @property
    def native_value(self) -> int:
        return len(self._build_schulinfo())

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        info = self._build_schulinfo()
        attrs = {
            "tage": info,
            "dates": sorted(info.keys()),
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
        }
        _warn_if_too_large("SchulInfoSensor", attrs)
        return attrs

    @property
    def unit_of_measurement(self) -> str:
        return "Tage"


# ──────────────────────────────────────────────
#  Sensor 2: Raw (optional, for debugging)
# ──────────────────────────────────────────────
class DSBRawSensor(CoordinatorEntity, SensorEntity):
    """All raw DSB data – for debugging. Disabled by default."""

    def __init__(
        self,
        coordinator: DSBCoordinator,
        config_entry: ConfigEntry,
        child_name: str,
        class_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_raw"
        slug = (
            _slugify(f"dsb {child_name} raw")
            if child_name
            else "dsb_raw"
        )
        self.entity_id = f"sensor.{slug}"
        self._attr_name = (
            f"DSB {child_name} Raw"
            if child_name
            else "DSB API Raw"
        )
        self._attr_icon = "mdi:calendar-text"
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int:
        if self.coordinator.data:
            return self.coordinator.data.get("count", 0)
        return 0

    def _slim_raw_tables(self) -> List[Dict[str, Any]]:
        raw_tables = self.coordinator.data.get("raw_tables", [])
        slim = []
        for table in raw_tables:
            slim.append(
                {
                    "url": table.get("url"),
                    "date": table.get("date"),
                    "title": table.get("title"),
                    "info": table.get("info", []),
                    "mon_heads": table.get("mon_heads", []),
                    "headers": table.get("headers", []),
                    "class_groups": table.get("class_groups", []),
                    "total_rows": table.get("total_rows", 0),
                }
            )
        return slim

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "entries": self.coordinator.data.get("entries", []),
            "days": self.coordinator.data.get("days", []),
            "day_count": self.coordinator.data.get("day_count", 0),
            "raw_tables": self._slim_raw_tables(),
            "raw_table_count": self.coordinator.data.get(
                "raw_table_count", 0
            ),
            "last_updated": self.coordinator.data.get("last_updated"),
        }


# ──────────────────────────────────────────────
#  Sensor 3: Student – date-keyed merged schedules
# ──────────────────────────────────────────────
class DSBStudentSensor(CoordinatorEntity, SensorEntity):
    """Per-student sensor with date-keyed merged schedules.

    Slim attributes to stay under 16KB:
    - No raw 'changes' DSB match data
    - No config block (on DSBConfigSensor)
    - No changes list (only change_count)
    - schedule_raw kept (needed by automations)
    """

    _HASH_FIELDS = (
        "Klasse(n)",
        "Stunde",
        "Vertreter",
        "Fach",
        "Raum",
        "(Lehrer)",
        "(Le.) nach",
        "Art",
        "Text",
    )

    def __init__(
        self,
        coordinator: DSBCoordinator,
        config_entry: ConfigEntry,
        child_name: str,
        class_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._child_name = child_name
        self._class_name = class_name
        slug = _slugify(
            f"dsb {child_name} {class_name} vertretungsplan"
        )
        self._attr_unique_id = f"{config_entry.entry_id}_{slug}"
        self.entity_id = f"sensor.{slug}"
        self._attr_name = (
            f"DSB {child_name} {class_name} Vertretungsplan"
        )
        self._attr_icon = "mdi:school"
        # Cache to avoid recomputing on every property access
        self._cached_data_ref: Any = None
        self._cached_filtered: Dict[str, List[Dict[str, Any]]] = {}
        self._cached_days: Dict[str, Any] = {}
        self._cached_hash: str = ""

    def _ensure_cache(self) -> None:
        """Recompute cached values if coordinator data has changed."""
        if self.coordinator.data is self._cached_data_ref:
            return
        self._cached_data_ref = self.coordinator.data
        self._cached_filtered = self._compute_filtered_by_date()
        self._cached_days = self._compute_days(self._cached_filtered)
        self._cached_hash = self._compute_data_hash(
            self._cached_filtered
        )

    def _compute_filtered_by_date(
        self,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not self.coordinator.data:
            return {}
        all_entries = self.coordinator.data.get("entries", [])
        filtered = _filter_for_klasse(
            all_entries,
            self.coordinator.klasse,
            self.coordinator.exclude_rules,
        )
        return _entries_by_date(filtered)

    def _compute_days(
        self, filtered_by_date: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        all_dates: Set[str] = set(filtered_by_date.keys())
        if self.coordinator.data:
            for day_data in self.coordinator.data.get("days", []):
                date_str = str(day_data.get("date", ""))[:10]
                if date_str:
                    all_dates.add(date_str)
        days: Dict[str, Any] = {}
        for date_str in sorted(all_dates):
            wochentag = _date_to_wochentag(date_str)
            schedule_day = self.coordinator.stundenplan.get(
                wochentag, {}
            )
            if not schedule_day:
                continue
            dsb_entries = filtered_by_date.get(date_str, [])
            merged = _merge_schedule_with_dsb(
                schedule_day, dsb_entries
            )
            change_count = sum(
                1
                for info in merged.values()
                if info.get("status", "normal") != "normal"
            )
            days[date_str] = {
                "wochentag": wochentag,
                "schedule": merged,
                "change_count": change_count,
            }
        return days

    def _compute_data_hash(
        self, filtered_by_date: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """Short hash for state change detection."""
        hash_entries = []
        for date_str in sorted(filtered_by_date.keys()):
            for entry in filtered_by_date[date_str]:
                hash_entry = {"_date": date_str}
                for field in self._HASH_FIELDS:
                    hash_entry[field] = str(entry.get(field, ""))
                hash_entries.append(hash_entry)
        all_dates: Set[str] = set()
        if self.coordinator.data:
            for day_data in self.coordinator.data.get("days", []):
                date_str = str(day_data.get("date", ""))[:10]
                if date_str:
                    all_dates.add(date_str)
        hash_input = json.dumps(
            {"dates": sorted(all_dates), "entries": hash_entries},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.md5(
            hash_input.encode("utf-8")
        ).hexdigest()[:8]

    @property
    def native_value(self) -> str:
        self._ensure_cache()
        total = sum(
            d.get("change_count", 0)
            for d in self._cached_days.values()
        )
        return f"{total}|{self._cached_hash}"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        self._ensure_cache()
        days = self._cached_days
        attrs = {
            "days": days,
            "dates": sorted(days.keys()),
            "schedule_raw": self.coordinator.stundenplan,
            "klasse": self.coordinator.klasse,
            "schueler": self._child_name,
            "schedule_file": self.coordinator.schedule_file,
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
        }
        _warn_if_too_large("StudentSensor", attrs)
        return attrs

    @property
    def unit_of_measurement(self) -> str:
        return "Änderungen"


# ──────────────────────────────────────────────
#  Sensor 4: Config (YAML config for automations)
# ──────────────────────────────────────────────
class DSBConfigSensor(CoordinatorEntity, SensorEntity):
    """Exposes YAML config for automations.

    Lean – no stundenplan, no hashes, no exclude rules.
    Those live on StudentSensor (schedule_raw) and HashSensor.
    """

    def __init__(
        self,
        coordinator: DSBCoordinator,
        config_entry: ConfigEntry,
        child_name: str,
        class_name: str,
    ) -> None:
        super().__init__(coordinator)
        slug = _slugify(f"dsb {child_name} config")
        self._attr_unique_id = f"{config_entry.entry_id}_config"
        self.entity_id = f"sensor.{slug}"
        self._attr_name = f"DSB {child_name} Config"
        self._attr_icon = "mdi:cog"

    @property
    def native_value(self) -> str:
        """Hash of config – changes when YAML is reloaded."""
        cfg = self.coordinator.config_block
        cfg_json = json.dumps(
            cfg, sort_keys=True, ensure_ascii=False
        )
        return hashlib.md5(
            cfg_json.encode("utf-8")
        ).hexdigest()[:8]

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        cfg = self.coordinator.config_block
        attrs = {
            "meta": cfg.get("meta", {}),
            "zeitraum": cfg.get("zeitraum", {}),
            "sensoren": cfg.get("sensoren", {}),
            "ogts": cfg.get("ogts", {}),
            "termine_filter": cfg.get("termine_filter", {}),
            "emojis": cfg.get("emojis", {}),
            "lehrer_profil": cfg.get("lehrer_profil", []),
            "kurzstunden": cfg.get("kurzstunden", {}),
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
        }
        _warn_if_too_large("ConfigSensor", attrs)
        return attrs


# ──────────────────────────────────────────────
#  Sensor 5: Hash Sensor (for automation triggers)
# ──────────────────────────────────────────────
class DSBHashSensor(CoordinatorEntity, SensorEntity):
    """Exposes stored hashes for automation triggers.

    Each attribute value is exactly 32 chars (MD5 hex) or empty.
    Total attribute size: ~200 bytes – well under 16KB.
    """

    _MAX_HASH_DISPLAY_LEN = 32

    def __init__(
        self,
        coordinator: DSBCoordinator,
        config_entry: ConfigEntry,
        child_name: str,
        hash_store: HashStore,
    ) -> None:
        super().__init__(coordinator)
        self._store = hash_store
        slug = _slugify(f"dsb {child_name} hashes")
        self._attr_unique_id = f"{config_entry.entry_id}_hashes"
        self.entity_id = f"sensor.{slug}"
        self._attr_name = f"DSB {child_name} Hashes"
        self._attr_icon = "mdi:hashtag"

    def _safe_hash(self, key: str) -> str:
        """Return stored hash, truncated as safety net."""
        value = self._store.get(key)
        if not value:
            return ""
        if len(value) > self._MAX_HASH_DISPLAY_LEN:
            _LOGGER.warning(
                "Hash '%s' is %d chars (expected %d). "
                "Delete .storage/dsb_*_hashes.json and re-run "
                "initial load.",
                key,
                len(value),
                self._MAX_HASH_DISPLAY_LEN,
            )
            return value[:self._MAX_HASH_DISPLAY_LEN]
        return value

    @property
    def native_value(self) -> str:
        """Composite hash – triggers automations on change."""
        all_hashes = "|".join(
            f"{k}={v}"
            for k, v in sorted(self._store.to_dict().items())
        )
        if all_hashes:
            return hashlib.md5(all_hashes.encode()).hexdigest()[:8]
        return "empty"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Only 3 known keys + last_updated. ~200 bytes total."""
        return {
            "exams": self._safe_hash("exams"),
            "termine": self._safe_hash("termine"),
            "yaml": self._safe_hash("yaml"),
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
        }