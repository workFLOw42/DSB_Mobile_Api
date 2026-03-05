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

| Sensor | Description | Icon |
|---|---|---|
| **Vertretungsplan** | Per-student substitution plan with merged timetable | 🏫 |
| **Schulinfo** | Daily school announcements and metadata | 📋 |
| **Raw Sensor** | All raw DSB data for debugging (optional) | 📊 |

### Core Features

- 🧒 **Child name & class in setup flow** – determines entity IDs and sensor naming
- 📅 **YAML timetable support** – provide a custom timetable file for schedule merging
- 🔄 **Manual fetch** – data is fetched on demand via `dsb_api.fetch_updates` service
- 🔃 **Live schedule reload** – reload timetable YAML via `dsb_api.reload_schedule` without restarting HA
- 🏷️ **Smart sensor naming** – entity IDs follow `sensor.dsb_[child]_[class]_vertretungsplan` pattern
- 👨‍👩‍👧‍👦 **Multi-child support** – add the integration multiple times, one per child
- 🔐 **Secure authentication** – DSB Mobile API credentials validated at setup
- 📏 **Recorder-safe** – raw debug sensor disabled by default to avoid large attributes
- 🔑 **Persistent hash storage** – change detection hashes stored per child for automation use

### Schedule Merging

When a YAML timetable is provided, the integration merges the regular timetable with DSB substitution data. Each lesson gets a status:

| Status | Meaning |
|---|---|
| `normal` | No changes – regular lesson |
| `vertretung` | Substitution teacher or room change |
| `entfall` | Lesson cancelled |
| `verlegung` | Lesson moved from/to another slot |
| `raum_aenderung` | Room changed |
| `betreuung` | Supervised study period |

The timetable supports split classes (e.g. two language groups, religion/ethics groups, or gender-separated sports) through an exclude list that filters out lessons not relevant to the specific student [1].

---

## 📦 Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Click **⋮** (top right) → **Custom repositories**
3. Add `https://github.com/workFLOw42/DSB_Mobile_Api` as **Integration**
4. Search for **DSB Mobile API** and install
5. Restart Home Assistant

### Manual Installation

1. Download the [latest release](https://github.com/workFLOw42/DSB_Mobile_Api/releases)
2. Copy the `custom_components/dsb_api` folder to your `config/custom_components/` directory
3. Restart Home Assistant

---

## ⚙️ Configuration

### Initial Setup (3 Steps)

**Step 1 – Credentials:**

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **DSB Mobile API**
3. Enter your DSB Mobile credentials:

| Field | Description | Example |
|---|---|---|
| **Username** | School ID for DSB Mobile | `12345` |
| **Password** | Password for DSB Mobile | `••••••••` |

**Step 2 – Child / Student:**

4. Enter a **name or short code** and the **class**:

| Field | Description | Example |
|---|---|---|
| **Child name** | Short code for the student | `MAX` |
| **Class** | Class name as shown in DSB | `7B` |

This determines entity IDs and the default timetable filename:

| Input | Entity ID | Schedule File |
|---|---|---|
| `MAX` + `7B` | `sensor.dsb_max_7b_vertretungsplan` | `MAX_Stundenplan.yaml` |
| `LISA` + `5A` | `sensor.dsb_lisa_5a_vertretungsplan` | `LISA_Stundenplan.yaml` |

> ⚠️ **Entity IDs are set during initial setup and cannot be changed later.**

**Step 3 – Schedule Settings:**

5. Optionally provide a **timetable YAML file** (must be in your HA config directory)
6. Optionally enable the **Raw Debug Sensor**

### Multiple Children

Add the integration once per child:

1. **Settings** → **Devices & Services** → **Add Integration** → **DSB Mobile API**
2. Use the **same credentials** but a **different child name and class**
3. Each child gets its own set of sensors with unique entity IDs

### Options

1. Go to **Settings** → **Devices & Services**
2. Find **DSB Mobile API** and click **Configure**
3. Change child name, class, schedule file, or raw sensor toggle

---

## 📅 Timetable YAML

The integration can load a custom YAML timetable from your HA config directory. This enables merging the regular timetable with DSB substitution data.

### Basic Structure

```yaml
meta:
  schueler: "MAX"
  klasse: "7B"
  jahrgangsstufe: 7
  schule: "myschool"

exclude:
  - fach: "L2"           # Student takes French, not Latin
  - fach: "K"            # Student has Ethics, not Catholic Religion
  - fach: "Ev"           # Student has Ethics, not Evangelical Religion
  - fach: "Sw"           # Student has male sports (Sm)
  - fach: "E1"
    lehrer: "SMI"        # Student is in the other English group

stundenplan:
  montag:
    "1": { fach: E1, raum: "108", lehrer: MUL, uhrzeit: "08:00-08:45" }
    "2": { fach: E1, raum: "108", lehrer: MUL, uhrzeit: "08:45-09:30" }
    # ...
  dienstag:
    # ...
```

### Extended Structure (for automation integration)

The YAML can include additional blocks used by calendar sync automations:

```yaml
zeitraum:
  start: "2026-02-04"
  ende: "2026-07-31"

sensoren:
  schulaufgaben: "sensor.myschool_max_schulaufgaben"
  termine: "sensor.myschool_max_termine"
  vertretungsplan: "sensor.dsb_max_7b_vertretungsplan"

ogts:
  betreuung: "Jane Doe"
  montag:     { start: "13:05", ende: "16:00" }
  donnerstag: { start: "13:05", ende: "16:00" }

termine_filter:
  include_keywords:
    - "7."
    - "7B"
    - "Unterstufe"
  exclude_keywords:
    - "Q12"
    - "Q13"
    - "Abitur"
  ferien_keyword: "ferien"
  feiertag_keywords:
    - "unterrichtsfrei"
    - "Buß- und Bettag"
    - "Christi Himmelfahrt"

emojis:
  schulaufgabe: "✒️"
  ogts: "📝"
  schultermin: "🏫"
  ferien: "🏖️"
  feiertag: "🎇"
  kurzstunden: "🌞"
  vertretung: "☢️"
  entfall: "👻"
```

### Exclude Rules

Schools often split classes into groups for languages, religion/ethics, or sports. The exclude list filters out lessons that don't apply to the specific student [1]:

| Example | Reason |
|---|---|
| `fach: "L2"` | Student takes French, not Latin |
| `fach: "K"` | Student has Ethics, not Catholic Religion |
| `fach: "Sw"` | Student has male sports |
| `fach: "E1", lehrer: "SMI"` | Student is in the other English group |

### Reload Without Restart

After editing the YAML, reload it without restarting HA:

```yaml
service: dsb_api.reload_schedule
```

---

## 🔄 Fetching Data

This integration uses **manual fetch only** (no automatic polling). To fetch data:

### Via Service Call

```yaml
service: dsb_api.fetch_updates
```

### Via Automation

```yaml
automation:
  - alias: "Fetch DSB data every 15 minutes on school mornings"
    trigger:
      - platform: time_pattern
        minutes: /15
    condition:
      - condition: time
        after: "06:45:00"
        before: "14:00:00"
      - condition: state
        entity_id: input_boolean.ferien_status_heute
        state: "off"
    action:
      - service: dsb_api.fetch_updates
```

### Via Developer Tools

Go to **Developer Tools** → **Services** → search for `dsb_api.fetch_updates` → **Call Service**

---

## 📊 Sensor Details

### Vertretungsplan Sensor

**State:** `2|a3f8c2d1` (change count + data hash – state only changes when actual data changes)

**Attributes:**

```yaml
days:
  "2026-03-05":
    wochentag: donnerstag
    schedule:
      "1":
        fach: M
        raum: "110"
        lehrer: GEI
        uhrzeit: 08:00-08:45
        status: normal
        vertreter: null
        dsb_text: null
        dsb_art: null
      "3":
        fach: G
        raum: "008"
        lehrer: BRE
        uhrzeit: 09:50-10:35
        status: entfall
        vertreter: null
        dsb_text: "G (BRE) 3. Std. entfällt"
        dsb_art: Entfall
    changes:
      - stunde: "3"
        status: entfall
        fach: G
        text: "G (BRE) 3. Std. entfällt"
    change_count: 1
dates:
  - "2026-03-05"
schedule_raw:
  montag:
    "1": { fach: E1, raum: "108", lehrer: MUL, uhrzeit: "08:00-08:45" }
    # ...
config:
  meta: { schueler: MAX, klasse: 7B, ... }
  zeitraum: { start: "2026-02-04", ende: "2026-07-31" }
  ogts: { ... }
  lehrer_profil: [MUL, GEI, BRE, ...]
  emojis: { ... }
hashes:
  exams: "a1b2c3d4"
  termine: "e5f6g7h8"
  yaml: "i9j0k1l2"
klasse: "7B"
schueler: "MAX"
schedule_file: "MAX_Stundenplan.yaml"
last_updated: "2026-03-05T07:45:00"
```

### Schulinfo Sensor

**State:** `2` (number of days with info)

**Attributes:**

```yaml
tage:
  "2026-03-05":
    title: "Vertretungsplan Donnerstag 05.03.2026"
    nachrichten:
      - "Bitte beachten Sie die geänderten Pausenzeiten."
    stand: "05.03.2026 07:30"
    klassen_betroffen: ["5A", "6D", "7B", "10B"]
    total_eintraege: 12
dates:
  - "2026-03-05"
last_updated: "2026-03-05T07:45:00"
```

---

## 🔑 Hash Storage

The integration provides persistent hash storage for change detection in automations. Hashes are stored per child in `.storage/dsb_[child]_hashes.json`.

### Set a Hash

```yaml
service: dsb_api.set_hash
data:
  child_name: "MAX"
  hash_key: "exams"       # exams, termine, or yaml
  hash_value: "a1b2c3d4"
```

### Read Hashes

Hashes are exposed in the Vertretungsplan sensor attributes:

```yaml
{{ state_attr('sensor.dsb_max_7b_vertretungsplan', 'hashes').exams }}
{{ state_attr('sensor.dsb_max_7b_vertretungsplan', 'hashes').termine }}
{{ state_attr('sensor.dsb_max_7b_vertretungsplan', 'hashes').yaml }}
```

---

## 🏠 Dashboard Examples

### Today's Changes Card (Markdown)

```yaml
type: markdown
title: 📋 Vertretungsplan Heute
content: >
  {% set today = now().strftime('%Y-%m-%d') %}
  {% set days = state_attr('sensor.dsb_max_7b_vertretungsplan', 'days') %}
  {% set day = days.get(today, {}) %}
  {% set changes = day.get('changes', []) %}
  {% if changes | length > 0 %}
  {% for c in changes %}
  - **{{ c.stunde }}. Std.** {{ c.fach }}: {{ c.status }}
    {% if c.text %}– {{ c.text }}{% endif %}
  {% endfor %}
  {% else %}
  Keine Änderungen heute ✅
  {% endif %}
```

### School Announcements Card (Markdown)

```yaml
type: markdown
title: 📢 Schulnachrichten
content: >
  {% set info = state_attr('sensor.dsb_max_schulinfo', 'tage') %}
  {% for date, data in info.items() %}
  **{{ date }}** (Stand: {{ data.stand }})
  {% for msg in data.nachrichten %}
  - {{ msg }}
  {% endfor %}
  {% endfor %}
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| **Login fails** | Verify credentials at [dsbmobile.de](https://www.dsbmobile.de/) |
| **No data after setup** | Call `dsb_api.fetch_updates` manually |
| **Schedule not loaded** | Check file exists in `/config/` and call `dsb_api.reload_schedule` |
| **Wrong lessons shown** | Review exclude rules in your YAML – check split class groups [1] |
| **Sensor shows 0 changes** | This is correct if there are no substitutions today |
| **Entity ID wrong** | Entity IDs are set at setup – delete & re-add integration |

### Enable Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.dsb_api: debug
```

---

## 📋 Changelog

### v3.0.0

- 🧒 **Child name & class in setup flow** – determines entity IDs and default schedule filename
- 👨‍👩‍👧‍👦 **Multi-child support** – add integration multiple times with different children
- 🏷️ **Smart sensor naming** – `sensor.dsb_[child]_[class]_vertretungsplan`
- 🔑 **Persistent hash storage** – `dsb_api.set_hash` service for automation change detection
- 📝 **Extended YAML support** – ogts, termine_filter, emojis, zeitraum blocks
- 🔧 **Config data in sensor** – full YAML config exposed as `config` attribute
- 🧑‍🏫 **Automatic teacher profile** – `lehrer_profil` computed from timetable
- 🔀 **Verlegung status** – lesson relocations now detected separately
- 🐛 **Fixed**: OptionsFlow compatibility with HA 2024.x+

### v2.2.4

- Stability improvements

### v2.2.0

- Schedule YAML support
- Exclude rules for split classes
- Manual fetch via service

### v1.0.0

- Initial release

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🙏 Credits

- Built for [Home Assistant](https://www.home-assistant.io/)
- Data provided by [DSB Mobile](https://www.dsbmobile.de/) by heinekingmedia GmbH
- Inspired by [ha-deutsche-ferien](https://github.com/workFLOw42/ha-deutsche-ferien) and [Elternportal_API](https://github.com/workFLOw42/Elternportal_API)