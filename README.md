# DSB Mobile API – Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/workFLOw42/DSB_Mobile_Api/actions/workflows/validate.yml/badge.svg)](https://github.com/workFLOw42/DSB_Mobile_Api/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Custom Home Assistant integration for [DSB Mobile](https://www.dsbmobile.de/) – the German school substitution plan system used by many schools in Germany.

## Features

- 📋 **Raw Sensor** – All substitution data for all classes
- 🎒 **Student Sensor** – Per-student merged schedule combining your timetable with DSB data
- 🔄 **Hash-based change detection** – Sensor state only changes when actual data changes (prevents unnecessary automation triggers)
- 📅 **Calendar sync ready** – Designed for use with Google Calendar or other calendar sync automations
- 🛠 **Services** – `dsb_api.fetch_updates` and `dsb_api.reload_schedule`
- ⚙️ **Fully configurable** – Schedule file selectable during setup and changeable anytime via Options
- 🧑‍🎓 **Multi-student capable** – Each student gets their own timetable YAML and sensor

## How It Works

```
DSB Mobile API ──► Raw Sensor (all classes, all entries)
       │
       ▼
Your Timetable YAML ──► Student Sensor (filtered + merged)
       │
       ▼
HA Automation ──► Google Calendar / Notifications / Dashboard
```

The integration fetches substitution data from DSB Mobile and provides it as
Home Assistant sensors. When combined with a timetable YAML file, it creates
a student-specific sensor that merges the regular schedule with substitution
data – showing cancellations, room changes, and substitute teachers.

## Installation

### HACS (recommended)

1. Open HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/workFLOw42/DSB_Mobile_Api` as **Integration**
3. Search for **"DSB Mobile API"** and install
4. Restart Home Assistant
5. Go to Settings → Integrations → **Add Integration** → search "DSB API"
6. Enter your DSB Mobile credentials (school ID + password)
7. Optionally enter your timetable YAML filename

### Manual

Copy `custom_components/dsb_api/` to your Home Assistant
`config/custom_components/` directory and restart.

## Setup

### Step 1: DSB Credentials

Enter the username (school ID) and password you use for the DSB Mobile app.

### Step 2: Timetable File (optional)

Enter the filename of your timetable YAML file. The file must be placed in
your Home Assistant config directory (`/config/`).

Leave empty to use only the raw sensor without student-specific features.

> 💡 **Tip**: You can change the schedule file anytime via
> Settings → Integrations → DSB API → **Configure**

## Timetable YAML

The timetable file is a simple YAML that describes one student's weekly
schedule. Place it in your HA config directory (e.g. `/config/stundenplan_max.yaml`).

### Structure

```yaml
# ─── Student Info ───
meta:
  klasse: "6D"           # Class name (must match DSB data exactly!)
  schueler: "Max"        # Student name (used for sensor naming)
  gruppe: "GRP1"         # Course group (informational)

# ─── Exclude Rules (optional) ───
# Filter out subjects/teachers not relevant for this student.
# Useful when DSB shows entries for the whole class but the student
# is in a specific course group (e.g. French instead of Latin).
exclude:
  - fach: "E1"           # Exclude English...
    lehrer: "SMI"        # ...only when taught by teacher SMI
  - fach: "L2"           # Always exclude Latin (student takes French)
  - fach: "Sw"           # Exclude swimming
  - fach: "K"            # Exclude Catholic religion

# ─── Weekly Timetable ───
# Keys: montag, dienstag, mittwoch, donnerstag, freitag
# Lesson numbers as strings, each with: fach, raum, lehrer, uhrzeit
stundenplan:
  montag:
    "1": { fach: E1,  raum: "108", lehrer: MUL, uhrzeit: "08:00-08:45" }
    "2": { fach: E1,  raum: "108", lehrer: MUL, uhrzeit: "08:45-09:30" }
    "3": { fach: F2,  raum: "008", lehrer: DUP, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "008", lehrer: DUP, uhrzeit: "10:35-11:20" }
    "5": { fach: Ku,  raum: "003", lehrer: WEB, uhrzeit: "11:35-12:20" }
    "6": { fach: Ku,  raum: "003", lehrer: WEB, uhrzeit: "12:20-13:05" }
  dienstag:
    "1": { fach: NT,  raum: "026", lehrer: FIS, uhrzeit: "08:00-08:45" }
    "2": { fach: D,   raum: "008", lehrer: BER, uhrzeit: "08:45-09:30" }
    "3": { fach: D,   raum: "008", lehrer: BER, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "109", lehrer: MAR, uhrzeit: "10:35-11:20" }
    "5": { fach: M,   raum: "102", lehrer: SCH, uhrzeit: "11:35-12:20" }
    "7": { fach: E1,  raum: "109", lehrer: MUL, uhrzeit: "13:05-13:50" }
    "8": { fach: E1,  raum: "109", lehrer: MUL, uhrzeit: "13:50-14:35" }
  mittwoch:
    "1": { fach: D,   raum: "008", lehrer: BER, uhrzeit: "08:00-08:45" }
    "2": { fach: D,   raum: "008", lehrer: BER, uhrzeit: "08:45-09:30" }
    "3": { fach: Eth, raum: "009", lehrer: HOF, uhrzeit: "09:50-10:35" }
    "4": { fach: Eth, raum: "009", lehrer: HOF, uhrzeit: "10:35-11:20" }
    "5": { fach: Bio, raum: "127", lehrer: MEY, uhrzeit: "11:35-12:20" }
    "6": { fach: Bio, raum: "127", lehrer: MEY, uhrzeit: "12:20-13:05" }
  donnerstag:
    "1": { fach: M,   raum: "110", lehrer: SCH, uhrzeit: "08:00-08:45" }
    "2": { fach: M,   raum: "110", lehrer: SCH, uhrzeit: "08:45-09:30" }
    "3": { fach: G,   raum: "008", lehrer: KLE, uhrzeit: "09:50-10:35" }
    "4": { fach: G,   raum: "008", lehrer: KLE, uhrzeit: "10:35-11:20" }
    "5": { fach: Sp,  raum: "SpH", lehrer: WAG, uhrzeit: "11:35-12:20" }
    "6": { fach: Sp,  raum: "SpH", lehrer: WAG, uhrzeit: "12:20-13:05" }
  freitag:
    "1": { fach: Mu,  raum: "113", lehrer: BAC, uhrzeit: "08:00-08:45" }
    "2": { fach: Mu,  raum: "113", lehrer: BAC, uhrzeit: "08:45-09:30" }
    "3": { fach: F2,  raum: "008", lehrer: DUP, uhrzeit: "09:50-10:35" }
    "4": { fach: F2,  raum: "008", lehrer: DUP, uhrzeit: "10:35-11:20" }
    "5": { fach: M,   raum: "008", lehrer: SCH, uhrzeit: "11:35-12:20" }
    "6": { fach: M,   raum: "008", lehrer: SCH, uhrzeit: "12:20-13:05" }
```

### Field Reference

| Field | Required | Description | Example |
|---|---|---|---|
| `meta.klasse` | ✅ | Class name – must match DSB data exactly | `"6D"`, `"9B"`, `"Q12"` |
| `meta.schueler` | ✅ | Student name – used for sensor naming | `"Max"`, `"Anna"` |
| `meta.gruppe` | ❌ | Course group (informational only) | `"GRP1"` |
| `exclude[].fach` | ✅ | Subject code to exclude | `"L2"`, `"Sw"` |
| `exclude[].lehrer` | ❌ | Only exclude for this specific teacher | `"SMI"` |
| `stundenplan.<day>.<nr>.fach` | ✅ | Subject code (must match DSB) | `"E1"`, `"M"`, `"D"` |
| `stundenplan.<day>.<nr>.raum` | ✅ | Room number | `"108"`, `"SpH"` |
| `stundenplan.<day>.<nr>.lehrer` | ✅ | Teacher code (3-letter) | `"MUL"`, `"SCH"` |
| `stundenplan.<day>.<nr>.uhrzeit` | ✅ | Time range `HH:MM-HH:MM` | `"08:00-08:45"` |

### How Filtering Works

```
DSB returns: All entries for class "6D"
    │
    ▼
meta.klasse: "6D" ──► Only entries matching "6D" pass through
    │
    ▼
exclude rules ──► Remove entries for subjects/teachers
                   the student doesn't have
    │
    ▼
Schedule merge ──► Compare with timetable, detect:
                   • Cancellations (Entfall)
                   • Room changes (Raum-Änderung)
                   • Substitute teachers (Vertretung)
                   • Supervised study (Betreuung)
```

### Multiple Students

Create separate YAML files and add the integration multiple times:

```
/config/stundenplan_max.yaml     → sensor.dsb_max_6d_vertretungsplan
/config/stundenplan_anna.yaml    → sensor.dsb_anna_9b_vertretungsplan
```

Each instance gets its own DSB credentials (can be the same school)
and its own schedule file.

## Sensors

### Raw Sensor

| | |
|---|---|
| Entity | `sensor.dsb_api_raw` |
| State | Number of total substitution entries |
| Attributes | `entries`, `days`, `last_updated` |

### Student Sensor

| | |
|---|---|
| Entity | `sensor.dsb_{schueler}_{klasse}_vertretungsplan` |
| State | `{change_count}\|{data_hash}` |
| Attributes | `days`, `dates`, `schedule_raw`, `klasse`, `schueler`, `last_updated` |

#### State Format

```
3|a1b2c3d4
│ │
│ └── MD5 hash of all DSB data (changes only when data changes)
└──── Total substitution changes across all days
```

This design ensures automations only trigger when **actual data changes** –
not when data is re-fetched but identical.

#### Days Attribute Structure

```json
{
  "2025-03-15": {
    "wochentag": "montag",
    "change_count": 2,
    "changes": [
      {
        "stunde": "3",
        "status": "entfall",
        "fach": "F2",
        "raum": "---",
        "text": "Klasse abwesend"
      }
    ],
    "schedule": {
      "1": {
        "fach": "E1",
        "raum": "108",
        "lehrer": "MUL",
        "uhrzeit": "08:00-08:45",
        "status": "normal"
      },
      "3": {
        "fach": "F2",
        "raum": "---",
        "lehrer": "DUP",
        "uhrzeit": "09:50-10:35",
        "status": "entfall",
        "dsb_text": "Klasse abwesend",
        "dsb_art": "Entfall"
      }
    }
  }
}
```

## Services

| Service | Description |
|---|---|
| `dsb_api.fetch_updates` | Force an immediate API fetch |
| `dsb_api.reload_schedule` | Reload the timetable YAML without restarting HA |

## Fetch Scheduling

This integration does **not** poll automatically. You control when data
is fetched by calling `dsb_api.fetch_updates` from a Home Assistant automation.

This gives you full control over API usage and timing.

### Simple Example

```yaml
alias: DSB_Fetch
triggers:
  - trigger: time_pattern
    minutes: "/30"
conditions:
  - condition: time
    after: "06:00:00"
    before: "20:00:00"
    weekday: [mon, tue, wed, thu, fri]
actions:
  - action: dsb_api.fetch_updates
mode: single
```

### Advanced Example (school-day aware)

```yaml
alias: DSB_Fetch_Schedule
description: >-
  Fetches DSB data on school days with intelligent timing:
  morning, before lessons, afternoon, and evening.
triggers:
  # Morning phase (every 15 min)
  - trigger: time_pattern
    minutes: "/15"
    id: morning
  # Before first lesson
  - trigger: time
    at: "07:45:00"
    id: pre_lesson
  # Afternoon (hourly)
  - trigger: time
    at: "15:00:00"
    id: afternoon
  - trigger: time
    at: "16:00:00"
    id: afternoon
  - trigger: time
    at: "17:00:00"
    id: afternoon
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
            id: [pre_lesson, afternoon, evening]
          - condition: time
            weekday: [mon, tue, wed, thu, fri]
        sequence:
          - action: dsb_api.fetch_updates
mode: single
```

## Calendar Sync Example

Combine the student sensor with a calendar sync automation:

```yaml
alias: DSB_Calendar_Sync
triggers:
  - trigger: state
    entity_id: sensor.dsb_max_6d_vertretungsplan
    not_to: [unavailable, unknown]
conditions:
  - condition: template
    value_template: >
      {{ trigger.from_state.state != trigger.to_state.state }}
actions:
  # Your calendar sync logic here
  # The trigger only fires when the hash changes = real data change
```

## Troubleshooting

| Issue | Solution |
|---|---|
| Student sensor not created | Check that schedule YAML exists and `meta.klasse` matches DSB data |
| No changes detected | Verify `meta.klasse` matches exactly (case-sensitive!) |
| Entries for wrong subjects | Add `exclude` rules for subjects the student doesn't take |
| Schedule file not found | File must be in `/config/`, filename must match what you entered during setup |
| Want to change schedule file | Settings → Integrations → DSB API → Configure |

### Logs

Enable debug logging for detailed information:

```yaml
logger:
  default: info
  logs:
    custom_components.dsb_api: debug
```

## License

[MIT](LICENSE)