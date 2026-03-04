# 📋 DSB Mobile API – Home Assistant Integration

<p align="center">
  <img src="https://raw.githubusercontent.com/workFLOw42/DSB_Mobile_Api/main/images/logo-hires.png" alt="DSB Mobile API" width="256">
</p>

<p align="center">
  <a href="https://github.com/workFLOw42/DSB_Mobile_Api/actions/workflows/validate.yml">
    <img src="https://github.com/workFLOw42/DSB_Mobile_Api/actions/workflows/validate.yml/badge.svg" alt="Validate Integration">
  </a>
  <a href="https://github.com/hacs/integration">
    <img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom">
  </a>
  <a href="https://github.com/workFLOw42/DSB_Mobile_Api/releases">
    <img src="https://img.shields.io/github/v/release/workFLOw42/DSB_Mobile_Api" alt="GitHub Release">
  </a>
  <a href="https://github.com/workFLOw42/DSB_Mobile_Api">
    <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json&query=%24.dsb_api.total&label=HACS%20Installs&color=41BDF5" alt="HACS Installs">
  </a>
  <a href="https://github.com/workFLOw42/DSB_Mobile_Api/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  </a>
</p>

<p align="center">
  Custom Home Assistant integration for <a href="https://www.dsbmobile.de/">DSB Mobile</a> – the German school substitution plan system used by many schools in Germany.
</p>

---

## ✨ Features

- 📋 **Schulinfo Sensor** – Daily school announcements, timestamps, and affected classes
- 🎒 **Student Sensor** – Per-student merged schedule combining your timetable with DSB data
- 🔄 **Hash-based change detection** – Sensor state only changes when actual data changes
- 📅 **Calendar sync ready** – Designed for use with Google Calendar or other calendar sync automations
- 🛠 **Services** – `dsb_api.fetch_updates` and `dsb_api.reload_schedule`
- ⚙️ **Fully configurable** – Schedule file and options changeable anytime via UI
- 🧑‍🎓 **Multi-student capable** – Each student gets their own timetable YAML and sensor
- 🐛 **Optional Raw Sensor** – Enable via checkbox for debugging, disable when not needed

---

## 🔧 How It Works

```
DSB Mobile API
    │
    ├──► Schulinfo Sensor (announcements, timestamps, affected classes)
    │
    ├──► Student Sensor (filtered + merged with timetable)
    │       │
    │       ▼
    │    HA Automation ──► Google Calendar / Notifications / Dashboard
    │
    └──► Raw Sensor (optional, all classes, for debugging)
```

The integration fetches substitution data from DSB Mobile and provides it as Home Assistant sensors. When combined with a timetable YAML file, it creates a student-specific sensor that merges the regular schedule with substitution data – showing cancellations, room changes, and substitute teachers.

> **Important**: This integration does **not** poll automatically. You control when data is fetched via Home Assistant automations calling `dsb_api.fetch_updates`.

---

## 📦 Installation

### HACS (recommended)

1. **HACS** → Integrationen → ⋮ → **Custom repositories**
2. Add `https://github.com/workFLOw42/DSB_Mobile_Api` as **Integration**
3. Search for **"DSB Mobile API"** and install
4. Restart Home Assistant
5. Go to **Settings** → **Integrations** → **Add Integration** → search **"DSB API"**
6. Enter your DSB Mobile credentials (school ID + password)
7. Optionally enter your timetable YAML filename
8. Optionally enable the Raw Debug Sensor

### Manual

Copy `custom_components/dsb_api/` to your Home Assistant `config/custom_components/` directory and restart.

---

## ⚙️ Setup

### Step 1: DSB Credentials

Enter the username (school ID) and password you use for the DSB Mobile app.

### Step 2: Settings

| Option | Required | Description |
|---|---|---|
| Schedule filename | No | Your timetable YAML file (e.g. `stundenplan_max.yaml`) |
| Enable Raw Debug Sensor | No | Enables the raw sensor with all classes (for debugging) |

> 💡 **Tip**: You can change both settings anytime via Settings → Integrations → DSB API → **Configure**

---

## 📊 Sensors

### Schulinfo Sensor (always active)

| | |
|---|---|
| **Entity** | `sensor.dsb_schulinfo` |
| **State** | Number of days with info |
| **Unit** | Tage |
| **Icon** | `mdi:bulletin-board` |

<details>
<summary><strong>Attributes</strong></summary>

```yaml
tage:
  "2025-03-15":
    title: "15.3.2025 Montag"
    nachrichten:
      - "Nachrichten zum Tag"
      - "Montag, 15.03.2025, 1. Pause: Treffen der Tutoren in 003"
    stand: "15.03.2025 07:45"
    klassen_betroffen:
      - "5A, 5B"
      - "6C, 6D"
    total_eintraege: 11
    url: "https://light.dsbcontrol.de/..."
  "2025-03-16":
    title: "16.3.2025 Dienstag"
    nachrichten: []
    stand: "15.03.2025 07:45"
dates:
  - "2025-03-15"
  - "2025-03-16"
last_updated: "2025-03-15T07:45:12"
```

</details>

### Student Sensor (when timetable configured)

| | |
|---|---|
| **Entity** | `sensor.dsb_{schueler}_{klasse}_vertretungsplan` |
| **State** | `{change_count}\|{data_hash}` |
| **Unit** | Änderungen |
| **Icon** | `mdi:school` |

The sensor name is auto-generated from `meta.schueler` and `meta.klasse` in your YAML.

#### State Format

```
3|a1b2c3d4
│ │
│ └── MD5 hash (changes only when actual DSB data changes)
└──── Total substitution changes across all days
```

This design ensures automations only trigger when **actual data changes** – not when data is re-fetched but identical.

<details>
<summary><strong>Attributes</strong></summary>

```yaml
days:
  "2025-03-15":
    wochentag: montag
    change_count: 2
    changes:
      - stunde: "3"
        status: entfall
        fach: F2
        raum: "---"
        text: "Klasse abwesend"
    schedule:
      "1":
        fach: E1
        raum: "108"
        lehrer: MUL
        uhrzeit: "08:00-08:45"
        status: normal
      "3":
        fach: F2
        raum: "---"
        lehrer: DUP
        uhrzeit: "09:50-10:35"
        status: entfall
        dsb_text: "Klasse abwesend"
        dsb_art: Entfall
dates:
  - "2025-03-15"
  - "2025-03-16"
klasse: "6D"
schueler: "Max"
schedule_file: "stundenplan_max.yaml"
schedule_raw: { ... }
last_updated: "2025-03-15T07:45:12"
```

</details>

#### Status Values

| Status | Meaning | Calendar Icon |
|---|---|---|
| `normal` | No changes | – |
| `entfall` | Lesson cancelled | 👻 |
| `vertretung` | Substitute teacher | ☢️ |
| `raum_aenderung` | Room changed | ☢️ |
| `betreuung` | Supervised study | ☢️ |

### Raw Debug Sensor (optional)

| | |
|---|---|
| **Entity** | `sensor.dsb_api_raw` |
| **State** | Total entry count |
| **Icon** | `mdi:calendar-text` |
| **Default** | **Disabled** – enable in integration settings |

Contains all parsed entries for all classes without filtering. Useful for debugging filter rules or checking what DSB delivers.

> Enable via Settings → Integrations → DSB API → Configure → ✅ Enable Raw Debug Sensor.

---

## 🛠 Services

| Service | Description |
|---|---|
| `dsb_api.fetch_updates` | Force an immediate API fetch |
| `dsb_api.reload_schedule` | Reload the timetable YAML without restarting HA |

---

## 📅 Timetable YAML

The timetable file describes one student's weekly schedule. Place it in your HA config directory (e.g. `/config/stundenplan_max.yaml`).

<details>
<summary><strong>Full Example</strong></summary>

```yaml
meta:
  klasse: "6D"
  schueler: "Max"
  gruppe: "GRP1"

exclude:
  - fach: "E1"
    lehrer: "SMI"
  - fach: "L2"
  - fach: "Sw"
  - fach: "K"

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

</details>

### Field Reference

| Field | Required | Description | Example |
|---|---|---|---|
| `meta.klasse` | ✅ | Class name – must match DSB data exactly | `"6D"`, `"9B"`, `"Q12"` |
| `meta.schueler` | ✅ | Student name – used for sensor naming | `"Max"`, `"Anna"` |
| `meta.gruppe` | ❌ | Course group (informational only) | `"GRP1"` |
| `exclude[].fach` | ✅ | Subject code to exclude | `"L2"`, `"Sw"` |
| `exclude[].lehrer` | ❌ | Only exclude for this specific teacher | `"SMI"` |
| `stundenplan.<day>.<nr>.fach` | ✅ | Subject code (must match DSB) | `"E1"`, `"M"` |
| `stundenplan.<day>.<nr>.raum` | ✅ | Room number | `"108"`, `"SpH"` |
| `stundenplan.<day>.<nr>.lehrer` | ✅ | Teacher code | `"MUL"`, `"SCH"` |
| `stundenplan.<day>.<nr>.uhrzeit` | ✅ | Time range `HH:MM-HH:MM` | `"08:00-08:45"` |

### How Filtering Works

```
DSB returns: All entries for all classes
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

Each instance gets its own DSB credentials (can be the same school) and its own schedule file.

---

## ⏰ Fetch Scheduling

This integration does **not** poll automatically. Create a Home Assistant automation to call `dsb_api.fetch_updates` at your preferred times.

<details>
<summary><strong>Simple Example</strong></summary>

```yaml
alias: DSB_Fetch
triggers:
  - trigger: time_pattern
    minutes: "/30"
  - trigger: homeassistant
    event: start
    id: ha_start
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: ha_start
        sequence:
          - delay: { seconds: 30 }
          - action: dsb_api.fetch_updates
    default:
      - condition: time
        after: "06:00:00"
        before: "20:00:00"
        weekday: [mon, tue, wed, thu, fri]
      - action: dsb_api.fetch_updates
mode: single
```

</details>

<details>
<summary><strong>Advanced Example (school-day aware)</strong></summary>

```yaml
alias: DSB_Fetch_Schedule
description: >-
  Fetches DSB data with intelligent timing:
  on HA restart, mornings, before lessons, afternoons, and evenings.
  Respects holidays via input_boolean.ferien_status_heute/morgen.
triggers:
  - trigger: homeassistant
    event: start
    id: ha_start
  - trigger: time_pattern
    minutes: "/15"
    id: morning
  - trigger: time
    at: "07:45:00"
    id: pre_lesson
  - trigger: time
    at: "08:30:00"
    id: pre_lesson
  - trigger: time
    at: "15:00:00"
    id: afternoon
  - trigger: time
    at: "19:30:00"
    id: evening
  - trigger: time
    at: "12:00:00"
    id: pre_school
  - trigger: time
    at: "19:00:00"
    id: pre_school
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: ha_start
        sequence:
          - delay: { seconds: 30 }
          - action: dsb_api.fetch_updates
      - conditions:
          - condition: trigger
            id: morning
          - condition: time
            after: "06:29:59"
            before: "07:45:00"
            weekday: [mon, tue, wed, thu, fri]
          - condition: state
            entity_id: input_boolean.ferien_status_heute
            state: "off"
        sequence:
          - action: dsb_api.fetch_updates
      - conditions:
          - condition: trigger
            id: [pre_lesson, afternoon, evening]
          - condition: time
            weekday: [mon, tue, wed, thu, fri]
          - condition: state
            entity_id: input_boolean.ferien_status_heute
            state: "off"
        sequence:
          - action: dsb_api.fetch_updates
      - conditions:
          - condition: trigger
            id: pre_school
          - condition: template
            value_template: >
              {% set is_sunday = now().weekday() == 6 %}
              {% set ferien_heute = states('input_boolean.ferien_status_heute') == 'on' %}
              {% set ferien_morgen = states('input_boolean.ferien_status_morgen') == 'on' %}
              {{ (is_sunday and not ferien_morgen)
                 or (ferien_heute and not ferien_morgen
                     and now().weekday() not in [5, 6]) }}
        sequence:
          - action: dsb_api.fetch_updates
mode: single
```

</details>

---

## 📅 Calendar Sync Example

Combine the student sensor with a calendar sync automation. The trigger only fires when the hash changes (= real data change). Past days are automatically filtered out.

<details>
<summary><strong>Calendar Sync Automation</strong></summary>

```yaml
alias: DSB_Calendar_Sync
triggers:
  - trigger: state
    entity_id: sensor.dsb_max_6d_vertretungsplan
    not_to: [unavailable, unknown]
    id: dsb_update
  - trigger: time
    at: "06:00:00"
    id: daily_fallback
conditions:
  - condition: template
    value_template: >
      {{ state_attr('sensor.dsb_max_6d_vertretungsplan', 'dates') is not none
         and state_attr('sensor.dsb_max_6d_vertretungsplan', 'dates') | length > 0 }}
  - condition: template
    value_template: >
      {% if trigger.id == 'dsb_update' %}
        {{ trigger.from_state.state != trigger.to_state.state }}
      {% else %}
        true
      {% endif %}
actions:
  - variables:
      dsb_dates: >
        {% set all_dates = state_attr('sensor.dsb_max_6d_vertretungsplan', 'dates') or [] %}
        {{ all_dates | select('ge', now().strftime('%Y-%m-%d')) | list }}
  - condition: template
    value_template: "{{ dsb_dates | length > 0 }}"
  - repeat:
      for_each: "{{ dsb_dates }}"
      sequence:
        # Your calendar sync logic here
        # See project Wiki for full Google Calendar example
```

</details>

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  DSB Mobile API Server                               │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (on demand)
                       ▼
┌─────────────────────────────────────────────────────┐
│  DSBCoordinator (no auto-polling)                    │
│  └─ Triggered by: dsb_api.fetch_updates              │
│     └─ Called from: HA Automation                     │
├─────────────────────────────────────────────────────┤
│                      │                               │
│    ┌─────────────────┼─────────────────┐             │
│    ▼                 ▼                 ▼             │
│  Schulinfo      Student Sensor    Raw Sensor         │
│  (always)       (if YAML)        (optional)          │
│                      │                               │
│                      ▼                               │
│              Hash comparison                         │
│              (state change only on real changes)     │
│                      │                               │
│                      ▼                               │
│              Sync Automation → Calendar               │
└─────────────────────────────────────────────────────┘
```

---

## 🔍 Troubleshooting

| Issue | Solution |
|---|---|
| Student sensor not created | Check that schedule YAML exists and `meta.klasse` matches DSB data |
| No changes detected | Verify `meta.klasse` matches exactly (case-sensitive!) |
| Entries for wrong subjects | Add `exclude` rules for subjects the student doesn't take |
| Schedule file not found | File must be in `/config/`, filename must match setup |
| Want to change settings | Settings → Integrations → DSB API → Configure |
| Raw sensor too large | Raw sensor excludes heavy HTML data by default |
| Need raw HTML data | Enable Raw sensor, check attributes, disable when done |
| Sensor state unchanged | Hash only changes on real data changes – working as designed! |
| Past days in calendar | Use date filter in sync automation (see example above) |

<details>
<summary><strong>Enable Debug Logging</strong></summary>

```yaml
logger:
  default: info
  logs:
    custom_components.dsb_api: debug
```

</details>

---

## ❓ FAQ

<details>
<summary><strong>Does this integration poll automatically?</strong></summary>

No. You control when data is fetched via Home Assistant automations calling `dsb_api.fetch_updates`. This is by design to avoid unnecessary API calls.

</details>

<details>
<summary><strong>Can I use this for multiple students?</strong></summary>

Yes! Add the integration multiple times – once per student. Each gets their own timetable YAML, credentials (can be the same school), and sensor.

</details>

<details>
<summary><strong>Why does the sensor state contain a hash?</strong></summary>

The hash enables efficient change detection. Automations (like calendar sync) only trigger when the hash changes – meaning actual DSB data changed. Re-fetching identical data won't cause unnecessary triggers.

</details>

<details>
<summary><strong>My school uses a different substitution system. Will this work?</strong></summary>

This integration only works with [DSB Mobile](https://www.dsbmobile.de/). If your school uses a different system (like Untis, WebUntis, etc.), this integration won't work.

</details>

---

## 🐛 Issues & Feature Requests

[Create an issue](https://github.com/workFLOw42/DSB_Mobile_Api/issues)

---

## 📄 License

[MIT](https://github.com/workFLOw42/DSB_Mobile_Api/blob/main/LICENSE) – © 2025 [workFLOw42](https://github.com/workFLOw42)