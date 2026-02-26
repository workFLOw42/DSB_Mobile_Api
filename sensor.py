"""DSB API Sensor for Home Assistant – intelligent scheduling."""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .dsb import DSB, DSBError

_LOGGER = logging.getLogger(__name__)

# Polling interval stays at 1 minute – the coordinator decides
# internally whether an actual API call is needed.
POLL_INTERVAL = timedelta(minutes=1)

SCHEDULE_FILENAME = "SFG_Stundenplan.yaml"

WOCHENTAG_MAP = {
    0: "montag",
    1: "dienstag",
    2: "mittwoch",
    3: "donnerstag",
    4: "freitag",
}

# Minutes before lesson start to trigger a fetch
PRE_LESSON_MINUTES = 15

# Morning phase: fetch every 15 minutes in this window
# Ends at 07:44 to avoid overlap with first pre-lesson fetch at 07:45 [1]
MORNING_START = "06:30"
MORNING_END = "07:44"

# Final fetch time on school days (for alarm clock automation)
EVENING_FETCH_TIME = "19:30"

# Weekend/holiday: fetch at these times on the day before school resumes
PRE_SCHOOL_TIMES = ("12:00", "19:00")


# ──────────────────────────────────────────────
#  Helper Functions
# ──────────────────────────────────────────────


def _load_schedule(hass: HomeAssistant) -> Dict[str, Any]:
    """Load schedule YAML from /config/SFG_Stundenplan.yaml."""
    path = hass.config.path(SCHEDULE_FILENAME)
    _LOGGER.debug("Looking for schedule at: %s", path)
    if not os.path.exists(path):
        _LOGGER.warning("Schedule file not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        _LOGGER.info(
            "Schedule loaded from %s (%d bytes)",
            path,
            os.path.getsize(path),
        )
        return data or {}
    except Exception as exc:
        _LOGGER.error("Error loading schedule from %s: %s", path, exc)
        return {}


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
    """Parse 'Stunde' field into individual lesson numbers.

    '5'     -> ['5']
    '5 - 6' -> ['5', '6']
    """
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
    """Filter entries for a specific class and apply exclude rules.

    Samuel is in group ANT [2] so entries for E1 with teacher YOU
    are excluded via the exclude rules from SFG_Stundenplan.yaml.
    """
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
    """Find the best matching DSB entry for a specific lesson.

    Uses scoring: +20 for teacher match, +10 for exact subject match,
    +5 for partial subject match. Teacher matching uses the known
    teachers from SFG_Stundenplan.yaml (e.g. ANT for E1 [2]).
    """
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
    dsb_raum = str(entry.get("Raum", "")).strip()
    if dsb_raum and dsb_raum != "---" and dsb_raum != plan_raum:
        return "raum_aenderung"
    return "vertretung"


def _merge_schedule_with_dsb(
    schedule_day: Dict[str, Any],
    dsb_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge one day of the timetable with DSB substitution entries."""
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
            "changes": None,
        }

        dsb_match = _find_dsb_for_stunde(
            stunde,
            dsb_entries,
            plan_info.get("fach", ""),
            plan_info.get("lehrer", "?"),
        )

        if dsb_match:
            status = _determine_status(dsb_match, plan_info.get("raum", ""))
            result["status"] = status
            result["dsb_text"] = dsb_match.get("Text", "")
            result["dsb_art"] = dsb_match.get("Art", "")
            result["vertreter"] = dsb_match.get("Vertreter", "")
            result["changes"] = dsb_match

            if status == "entfall":
                result["raum"] = "---"
            elif status in ("raum_aenderung", "vertretung", "betreuung"):
                dsb_raum = str(dsb_match.get("Raum", "---")).strip()
                if dsb_raum and dsb_raum != "---":
                    result["original_raum"] = plan_info.get("raum", "?")
                    result["raum"] = dsb_raum

        merged[stunde] = result

    return merged


def _time_str(h: int, m: int) -> str:
    """Format hour/minute as HH:MM."""
    return f"{h:02d}:{m:02d}"


# ──────────────────────────────────────────────
#  Coordinator with intelligent scheduling
# ──────────────────────────────────────────────


class DSBCoordinator(DataUpdateCoordinator):
    """Coordinator for DSB API data updates with smart fetch timing.

    Fetch schedule on school days:
    - Morning phase (06:30–07:44): every 15 minutes
    - Pre-lesson: 15 min before each lesson start [1]
    - Afternoon (after last lesson until 19:29): hourly at minute 0
    - Evening: final fetch at 19:30 (for alarm clock automation)

    Weekend/holiday:
    - No fetches except day before school resumes (12:00, 19:00)
    """

    def __init__(self, hass: HomeAssistant, client: DSB) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="DSB API",
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self._force_next_update = False
        self._schedule_data: Dict[str, Any] = {}
        self._schedule_loaded = False
        self._last_fetch_key: Optional[Tuple] = None

    # ── schedule access ──

    def load_schedule(self) -> None:
        """Load or reload the schedule YAML."""
        self._schedule_data = _load_schedule(self.hass)
        self._schedule_loaded = bool(self._schedule_data)
        if self._schedule_loaded:
            meta = self._schedule_data.get("meta", {})
            _LOGGER.info(
                "Schedule loaded: %s (%s)",
                meta.get("schueler", "?"),
                meta.get("klasse", "?"),
            )
        else:
            _LOGGER.warning("Schedule could not be loaded")

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

    # ── intelligent scheduling ──

    def _get_fetch_times_for_day(self, wochentag: str) -> Set[str]:
        """Calculate fetch times: 15 min before each lesson on this day.

        Based on the timetable from SFG_Stundenplan.yaml [1].
        E.g. Monday: 07:45, 08:30, 09:35, 10:20, 11:20, 12:05
        Tuesday (with lessons 7+8): adds 12:50, 13:35
        """
        schedule_day = self.stundenplan.get(wochentag, {})
        fetch_times: Set[str] = set()

        for stunde_info in schedule_day.values():
            uhrzeit = str(stunde_info.get("uhrzeit", ""))
            start_str = uhrzeit.split("-")[0].strip()
            if not start_str or ":" not in start_str:
                continue
            try:
                h, m = int(start_str[:2]), int(start_str[3:5])
                fetch_dt = datetime.now().replace(
                    hour=h, minute=m, second=0
                ) - timedelta(minutes=PRE_LESSON_MINUTES)
                fetch_times.add(_time_str(fetch_dt.hour, fetch_dt.minute))
            except (ValueError, IndexError):
                continue

        return fetch_times

    def _get_last_lesson_end(self, wochentag: str) -> str:
        """Get the end time of the last lesson on this day."""
        schedule_day = self.stundenplan.get(wochentag, {})
        latest = "13:05"

        for stunde_info in schedule_day.values():
            uhrzeit = str(stunde_info.get("uhrzeit", ""))
            parts = uhrzeit.split("-")
            if len(parts) == 2:
                end_str = parts[1].strip()
                if end_str > latest:
                    latest = end_str

        return latest

    def _is_ferien_heute(self) -> bool:
        """Check holiday status using existing HA input_boolean."""
        state = self.hass.states.get("input_boolean.ferien_status_heute")
        return state is not None and state.state == "on"

    def _is_ferien_morgen(self) -> bool:
        """Check tomorrow's holiday status."""
        state = self.hass.states.get("input_boolean.ferien_status_morgen")
        return state is not None and state.state == "on"

    def _should_fetch(self, now: datetime) -> bool:
        """Determine whether to make an actual API call right now.

        Timeline on a school day (e.g. Tuesday with lessons 1-5,7-8) [1]:
          06:30 06:45 07:00 07:15 07:30    Morning phase (every 15 min)
          07:45 08:30 09:35 10:20 11:20    Pre-lesson (15 min before start)
          12:50 13:35                       Pre-lesson (lessons 7+8)
          15:00 16:00 17:00 18:00 19:00    Afternoon (hourly)
          19:30                             Final evening fetch
        """
        # Prevent double-fetch in the same minute
        fetch_key = (now.date(), now.hour, now.minute)
        if self._last_fetch_key == fetch_key:
            return False

        wochentag = WOCHENTAG_MAP.get(now.weekday())
        zeit = _time_str(now.hour, now.minute)
        is_weekend = wochentag is None
        is_ferien = self._is_ferien_heute()

        # ── WEEKEND or HOLIDAY ──
        if is_weekend or is_ferien:
            # Sunday before a school Monday
            if is_weekend and now.weekday() == 6:
                if not self._is_ferien_morgen():
                    return zeit in PRE_SCHOOL_TIMES
            # Last day of holiday (weekday) before school resumes
            elif not is_weekend and is_ferien:
                if not self._is_ferien_morgen():
                    return zeit in PRE_SCHOOL_TIMES
            return False

        # ── SCHOOL DAY: Morning phase (06:30–07:44, every 15 min) ──
        if MORNING_START <= zeit <= MORNING_END:
            if now.minute in (0, 15, 30, 45):
                return True

        # ── SCHOOL DAY: Pre-lesson fetches (15 min before each lesson) ──
        fetch_times = self._get_fetch_times_for_day(wochentag)
        if zeit in fetch_times:
            return True

        # ── SCHOOL DAY: Afternoon phase (hourly at :00) ──
        last_end = self._get_last_lesson_end(wochentag)
        if last_end <= zeit < EVENING_FETCH_TIME:
            if now.minute == 0:
                return True

        # ── SCHOOL DAY: Final evening fetch at 19:30 ──
        if zeit == EVENING_FETCH_TIME:
            return True

        return False

    # ── refresh ──

    async def async_force_refresh(self) -> None:
        """Force an immediate data refresh (manual trigger)."""
        self._force_next_update = True
        await self.async_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from DSB API based on intelligent schedule."""
        now = datetime.now()

        if not self._schedule_loaded:
            await self.hass.async_add_executor_job(self.load_schedule)

        # Decide whether to actually call the API
        if (
            self.data is not None
            and not self._force_next_update
            and not self._should_fetch(now)
        ):
            return self.data

        self._force_next_update = False
        self._last_fetch_key = (now.date(), now.hour, now.minute)

        _LOGGER.debug("Fetching DSB data at %s", now.strftime("%H:%M"))

        try:
            plans = await self.hass.async_add_executor_job(
                self.client.get_plans
            )

            all_entries: List[Dict[str, Any]] = []
            all_days: List[Dict[str, Any]] = []

            for plan in plans:
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

            # Deduplicate
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

    coordinator = DSBCoordinator(hass, client)
    await hass.async_add_executor_job(coordinator.load_schedule)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = [
        DSBRawSensor(coordinator),
    ]

    if coordinator.schedule:
        entities.append(DSBStudentSensor(coordinator))
        _LOGGER.info(
            "Student sensor 'sensor.sfg_dsb_vertretungsplan' created for %s (%s)",
            coordinator.schedule.get("meta", {}).get("schueler", "?"),
            coordinator.klasse,
        )
    else:
        _LOGGER.warning(
            "No schedule at %s – student sensor not created",
            hass.config.path(SCHEDULE_FILENAME),
        )

    async_add_entities(entities)

    # ── Services ──

    async def handle_manual_refresh(call: ServiceCall) -> None:
        """Force an immediate API call."""
        await coordinator.async_force_refresh()

    async def handle_reload_schedule(call: ServiceCall) -> None:
        """Reload SFG_Stundenplan.yaml without HA restart."""
        await hass.async_add_executor_job(coordinator.load_schedule)
        await coordinator.async_refresh()
        _LOGGER.info("Schedule reloaded from %s", SCHEDULE_FILENAME)

    hass.services.async_register(
        DOMAIN, "fetch_updates", handle_manual_refresh
    )
    hass.services.async_register(
        DOMAIN, "reload_schedule", handle_reload_schedule
    )


# ──────────────────────────────────────────────
#  Sensor 1: Raw (all classes, all days)
# ──────────────────────────────────────────────


class DSBRawSensor(CoordinatorEntity, SensorEntity):
    """All raw DSB substitution data."""

    def __init__(self, coordinator: DSBCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "dsb_api_raw"
        self._attr_name = "DSB API Raw"
        self._attr_icon = "mdi:calendar-text"

    @property
    def native_value(self) -> int:
        if self.coordinator.data:
            return self.coordinator.data.get("count", 0)
        return 0

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "entries": self.coordinator.data.get("entries", []),
            "days": self.coordinator.data.get("days", []),
            "last_updated": self.coordinator.data.get("last_updated"),
        }


# ──────────────────────────────────────────────
#  Sensor 2: Student – single sensor, date-keyed
# ──────────────────────────────────────────────


class DSBStudentSensor(CoordinatorEntity, SensorEntity):
    """Per-student sensor with date-keyed merged schedules.

    Combines the timetable from SFG_Stundenplan.yaml with
    DSB substitution data. Each date delivered by DSB
    becomes a key in the ``days`` attribute.

    Samuel is in group ANT (Frau Antritt) [2] with E1 in
    rooms 108/109. The exclude rules filter out entries
    for group YOU, L2, Sw, K, and Ev based on the class
    schedule [1].

    The native_value includes a hash over all raw DSB fields
    so the state only changes when actual data changes – not
    on every fetch. This prevents unnecessary calendar syncs [5].
    """

    # Fields used for computing the data hash
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

    def __init__(self, coordinator: DSBCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "sfg_dsb_vertretungsplan"
        self._attr_name = "SFG DSB Vertretungsplan"
        self._attr_icon = "mdi:school"

    # ── internals ──

    def _get_filtered_by_date(
        self,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """DSB entries filtered for this student, grouped by date."""
        if not self.coordinator.data:
            return {}
        all_entries = self.coordinator.data.get("entries", [])
        filtered = _filter_for_klasse(
            all_entries,
            self.coordinator.klasse,
            self.coordinator.exclude_rules,
        )
        return _entries_by_date(filtered)

    def _build_days(self) -> Dict[str, Any]:
        """Build the complete days dict with merged schedules."""
        filtered_by_date = self._get_filtered_by_date()

        all_dates: Set[str] = set(filtered_by_date.keys())
        if self.coordinator.data:
            for day_data in self.coordinator.data.get("days", []):
                date_str = str(day_data.get("date", ""))[:10]
                if date_str:
                    all_dates.add(date_str)

        days: Dict[str, Any] = {}

        for date_str in sorted(all_dates):
            wochentag = _date_to_wochentag(date_str)
            schedule_day = self.coordinator.stundenplan.get(wochentag, {})

            if not schedule_day:
                continue

            dsb_entries = filtered_by_date.get(date_str, [])
            merged = _merge_schedule_with_dsb(schedule_day, dsb_entries)

            changes = [
                {
                    "stunde": st,
                    "status": info["status"],
                    "fach": info["fach"],
                    "raum": info.get("raum", ""),
                    "original_raum": info.get("original_raum", ""),
                    "vertreter": info.get("vertreter", ""),
                    "text": info.get("dsb_text", ""),
                }
                for st, info in merged.items()
                if info.get("status", "normal") != "normal"
            ]

            days[date_str] = {
                "wochentag": wochentag,
                "schedule": merged,
                "changes": changes,
                "change_count": len(changes),
            }

        return days

    def _compute_data_hash(self) -> str:
        """Compute a hash over all relevant raw DSB fields for this student.

        Uses all raw DSB entry fields:
        Klasse(n), Stunde, Vertreter, Fach, Raum, (Lehrer), (Le.) nach, Art, Text

        The hash only changes when the actual substitution data changes,
        not when last_updated or other metadata changes. This prevents
        the calendar sync automation from triggering unnecessarily [5].
        """
        filtered_by_date = self._get_filtered_by_date()

        # Build a list of all relevant entry data for hashing
        hash_entries = []
        for date_str in sorted(filtered_by_date.keys()):
            for entry in filtered_by_date[date_str]:
                hash_entry = {"_date": date_str}
                for field in self._HASH_FIELDS:
                    hash_entry[field] = str(entry.get(field, ""))
                hash_entries.append(hash_entry)

        # Also include all dates DSB provides (even without entries
        # for this student) so we detect date shifts (e.g. DSB
        # switches from today/tomorrow to tomorrow/day-after)
        all_dates: Set[str] = set()
        if self.coordinator.data:
            for day_data in self.coordinator.data.get("days", []):
                date_str = str(day_data.get("date", ""))[:10]
                if date_str:
                    all_dates.add(date_str)

        hash_input = json.dumps(
            {
                "dates": sorted(all_dates),
                "entries": hash_entries,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

        return hashlib.md5(hash_input.encode("utf-8")).hexdigest()[:8]

    # ── sensor properties ──

    @property
    def native_value(self) -> str:
        days = self._build_days()
        total = sum(d.get("change_count", 0) for d in days.values())
        data_hash = self._compute_data_hash()
        return f"{total}|{data_hash}"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        days = self._build_days()
        return {
            "days": days,
            "dates": sorted(days.keys()),
            "schedule_raw": self.coordinator.stundenplan,
            "klasse": self.coordinator.klasse,
            "schueler": self.coordinator.schedule.get("meta", {}).get(
                "schueler", ""
            ),
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
        }

    @property
    def unit_of_measurement(self) -> str:
        return "Änderungen"