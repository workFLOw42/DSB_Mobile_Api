# DSB Mobile API – Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Custom Home Assistant integration for [DSB Mobile](https://www.dsbmobile.de/) – the German school substitution plan system.

## Features

- 📋 **Raw Sensor** – All substitution data for all classes
- 🎒 **Student Sensor** – Per-student merged schedule with your timetable YAML
- 🔄 **Hash-based change detection** – State only changes when actual data changes
- 📅 **Google Calendar sync ready** – Designed for use with calendar sync automations
- 🛠 **Services** – `dsb_api.fetch_updates` and `dsb_api.reload_schedule`
- ⚙️ **Configurable** – Schedule file selectable during setup and changeable via Options

## Installation

### HACS (recommended)

1. Open HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/workFLOw42/DSB_Mobile_Api` as **Integration**
3. Search for **"DSB Mobile API"** and install
4. Restart Home Assistant
5. Go to Settings → Integrations → **Add Integration** → "DSB API"
6. Enter your DSB Mobile credentials
7. Optionally enter your timetable YAML filename

### Manual

Copy `custom_components/dsb_api/` to your HA `config/custom_components/` directory.

## Setup

### Step 1: Credentials

Enter your DSB Mobile username (school ID) and password.

### Step 2: Timetable (optional)

Enter the filename of your timetable YAML file (e.g. `mein_stundenplan.yaml`).
The file must be placed in your Home Assistant config directory (`/config/`).

Leave empty to use only the raw sensor without student-specific schedule merging.

> **Tip**: You can change the schedule file later via  
> Settings → Integrations → DSB API → **Configure**

## Timetable YAML Format

Create a YAML file in your HA config directory (e.g. `/config/mein_stundenplan.yaml`):

```yaml
meta:
  klasse: "6D"           # Class name (must match DSB exactly)
  schueler: "Max"        # Student name (used for sensor naming)
  gruppe: "ANT"          # Group/course identifier (informational)

# Exclude rules: filter out subjects/teachers not relevant for this student
# Useful when DSB shows entries for the whole class but the student
# is in a specific course group (e.g. French instead of Latin)
exclude:
  - fach: "E1"           # Exclude subject E1...
    lehrer: "YOU"         # ...but only when taught by teacher YOU
  - fach: "L2"           # Exclude Latin (student takes French)
  - fach: "Sw"           # Exclude swimming
  - fach: "K"            # Exclude Catholic religion
  - fach: "Ev"           # Exclude Evangelical religion

# Full weekly timetable
# Keys: montag, dienstag, mittwoch, donnerstag, freitag
# Each lesson needs: fach, raum, lehrer, uhrzeit
stundenplan:
  montag:
    "1": { fach: E1,  raum: "108",  lehrer: ANT, uhrzeit: "08:00-08:45" }
    "2": { fach: E1,  raum: "108",  lehrer: ANT, uhrzeit: "08:45-09:30" }
    "3": { fach: F2,  raum: "008",  lehrer: KRU, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "008",  lehrer: KRU, uhrzeit: "10:35-11:20" }
    "5": { fach: Ku,  raum: "N003", lehrer: KUB, uhrzeit: "11:35-12:20" }
    "6": { fach: Ku,  raum: "N003", lehrer: KUB, uhrzeit: "12:20-13:05" }
  dienstag:
    "1": { fach: NT,  raum: "026",  lehrer: PEI, uhrzeit: "08:00-08:45" }
    "2": { fach: D,   raum: "008",  lehrer: GEN, uhrzeit: "08:45-09:30" }
    "3": { fach: D,   raum: "008",  lehrer: GEN, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "109",  lehrer: USE, uhrzeit: "10:35-11:20" }
    "5": { fach: M,   raum: "102",  lehrer: GEI, uhrzeit: "11:35-12:20" }
    "7": { fach: E1,  raum: "109",  lehrer: ANT, uhrzeit: "13:05-13:50" }
    "8": { fach: E1,  raum: "109",  lehrer: ANT, uhrzeit: "13:50-14:35" }
  mittwoch:
    "1": { fach: D,   raum: "008",  lehrer: GEN, uhrzeit: "08:00-08:45" }
    "2": { fach: D,   raum: "008",  lehrer: GEN, uhrzeit: "08:45-09:30" }
    "3": { fach: Eth, raum: "009",  lehrer: SÖK, uhrzeit: "09:50-10:35" }
    "4": { fach: Eth, raum: "009",  lehrer: SÖK, uhrzeit: "10:35-11:20" }
    "5": { fach: Bio, raum: "127",  lehrer: BIC, uhrzeit: "11:35-12:20" }
    "6": { fach: Bio, raum: "127",  lehrer: BIC, uhrzeit: "12:20-13:05" }
  donnerstag:
    "1": { fach: M,   raum: "110",  lehrer: GEI, uhrzeit: "08:00-08:45" }
    "2": { fach: M,   raum: "110",  lehrer: GEI, uhrzeit: "08:45-09:30" }
    "3": { fach: G,   raum: "008",  lehrer: BRE, uhrzeit: "09:50-10:35" }
    "4": { fach: G,   raum: "008",  lehrer: BRE, uhrzeit: "10:35-11:20" }
    "5": { fach: Sp,  raum: "SpH",  lehrer: BÜR, uhrzeit: "11:35-12:20" }
    "6": { fach: Sp,  raum: "SpH",  lehrer: BÜR, uhrzeit: "12:20-13:05" }
  freitag:
    "1": { fach: Mu,  raum: "113",  lehrer: NYN, uhrzeit: "08:00-08:45" }
    "2": { fach: Mu,  raum: "113",  lehrer: NYN, uhrzeit: "08:45-09:30" }
    "3": { fach: F2,  raum: "008",  lehrer: KRU, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "008",  lehrer: KRU, uhrzeit: "10:35-11:20" }
    "5": { fach: M,   raum: "008",  lehrer: GEI, uhrzeit: "11:35-12:20" }
    "6": { fach: M,   raum: "008",  lehrer: GEI, uhrzeit: "12:20-13:05" }
```

### Field Reference

| Field | Description | Example |
|---|---|---|
| `meta.klasse` | Class name, must match DSB data exactly | `"6D"` |
| `meta.schueler` | Student name (for sensor naming) | `"Max"` |
| `meta.gruppe` | Course group (informational) | `"ANT"` |
| `exclude[].fach` | Subject code to exclude | `"L2"` |
| `exclude[].lehrer` | Optional: only exclude for this teacher | `"YOU"` |
| `stundenplan.<day>.<nr>` | Lesson definition | see above |
| `fach` | Subject code (must match DSB) | `E1`, `M`, `D` |
| `raum` | Room number | `"108"` |
| `lehrer` | Teacher code | `ANT` |
| `uhrzeit` | Time range (HH:MM-HH:MM) | `"08:00-08:45"` |

## Sensors

| Sensor | State | Description |
|---|---|---|
| `sensor.dsb_api_raw` | Entry count | All raw substitution entries in attributes |
| `sensor.dsb_max_6d_vertretungsplan` | `{changes}\|{hash}` | Student-specific merged schedule |

The student sensor name is auto-generated from `meta.schueler` and `meta.klasse`.

### State Format

The student sensor state uses format `{change_count}|{data_hash}`:
- **change_count**: Total substitution changes across all days
- **data_hash**: MD5 hash of all DSB data – only changes when actual data changes

This design prevents unnecessary automation triggers when data is re-fetched but unchanged.

## Services

| Service | Description |
|---|---|
| `dsb_api.fetch_updates` | Force an immediate API fetch |
| `dsb_api.reload_schedule` | Reload the timetable YAML without HA restart |

## Fetch Scheduling

This integration does **not** poll automatically. Create a Home Assistant
automation to call `dsb_api.fetch_updates` at your preferred times.

### Example Automation

```yaml
alias: DSB_Fetch_Schedule
triggers:
  # Morning: every 15 min from 06:30
  - trigger: time_pattern
    minutes: "/15"
    id: morning
  # Before lessons
  - trigger: time
    at: "07:45:00"
    id: pre_lesson
  # Evening
  - trigger: time
    at: "19:30:00"
    id: evening
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: morning
          - condition: time
            after: "06:29:59"
            before: "07:45:00"
            weekday: [mon, tue, wed, thu, fri]
        sequence:
          - action: dsb_api.fetch_updates
      - conditions:
          - condition: trigger
            id: pre_lesson
          - condition: time
            weekday: [mon, tue, wed, thu, fri]
        sequence:
          - action: dsb_api.fetch_updates
      - conditions:
          - condition: trigger
            id: evening
          - condition: time
            weekday: [mon, tue, wed, thu, fri]
        sequence:
          - action: dsb_api.fetch_updates
mode: single
```

## License

[MIT](LICENSE)