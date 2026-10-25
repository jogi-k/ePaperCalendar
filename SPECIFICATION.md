# ePaper Family Calendar — Specification

What the program does and how it behaves. For installing and configuring it (Google account, service account, shared calendar), see [SETUP.md](SETUP.md).

## Overview

A small local web app (Python + Flask) that reads one shared Google calendar ("Family") via a service account and renders it as a **one-page-per-month, grayscale image** for an ePaper display (target panel: INKPLATE 13SPECTRA, 13.3″, E-Ink Spectra 6-color; the render size is configurable via `EPAPER_WIDTH`/`EPAPER_HEIGHT` — 1872×1404 in this setup). It also serves a simple HTML preview and a JSON API for debugging.

## Access design

- **Service account** (JSON key at `GOOGLE_SERVICE_ACCOUNT_KEY`), read-only scope `calendar.readonly`
- Reads the single shared calendar `FAMILY_CALENDAR_ID`
- No OAuth, no user sign-in, tokens never expire
- Recurring events are expanded into individual instances (`singleEvents=true`)
- The Google client uses a **15s timeout**: a hung API call fails fast (the preview shows an error box; `/api/events` and `/calendar.png` return `503`) instead of blocking the request

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_KEY` | `credentials/service-account.json` | Path to the service account JSON key |
| `FAMILY_CALENDAR_ID` | — (required) | Calendar ID of the shared family calendar |
| `EPAPER_WIDTH` / `EPAPER_HEIGHT` | `1600` / `1200` | Render size in px (landscape); set to the panel's native resolution (1872×1404 for the INKPLATE 13SPECTRA in this setup) |
| `TIMEZONE` | `Europe/Zurich` | Local timezone for day assignment and "today" |
| `PORT` | `5000` | HTTP port |
| `DAYS_AHEAD` | `14` | Preview / `/api/events` window in days |

## HTTP API

| Route | Returns |
|---|---|
| `GET /` | HTML preview: table of upcoming events (next `DAYS_AHEAD` days, with times) |
| `GET /api/events` | JSON array of upcoming events |
| `GET /calendar.png?month=YYYY-MM` | PNG month page (default: current month), `image/png` |

All calendar-backed routes call `calendar.events.list` with `timeMin`/`timeMax` covering the relevant range (the month for the image, `DAYS_AHEAD` for preview/API). On failure, `/api/events` and `/calendar.png` return `503` with a JSON error; the preview page renders the error inline.

Event JSON fields: `id`, `summary`, `start`, `end` (ISO 8601; all-day events as plain `date`), `all_day`.

## Rendering pipeline

1. Fetch events overlapping the month (month bounds in `TIMEZONE`, converted to UTC)
2. Assign each event to one or more columns (see routing below)
3. Compute the local day span; clamp to the displayed month
4. Render the page (Pillow, grayscale, mode `L`)

Also runnable headless: `python -m app.render --month 2026-10 --out calendar.png`

## Month layout (the ePaper page)

One page per month, landscape:

- **Header**: month name, e.g. "Oktober 2026" (German month names)
- **Rows**: one per day of the month
- **First column**: date as "Weekday, Day" — German short weekday, e.g. "Mo, 5"
- **Columns** (left to right): `Familie`, `Laurin`, `Milo`, `Conny`, `Jogi`
- **No times** are rendered
- Today's date is highlighted (inverted); weekend rows are shaded

### Event routing

An event belongs to the person or group its title **starts with** — later occurrences of a name do not count. Matching is case-insensitive, on the first word only (word boundary). All family-specific rules live in **`app/family_config.py`**; the generic logic is in `app/routing.py`.

| Title starts with | Column(s) | Displayed title |
|---|---|---|
| `<name> hat Geburtstag` | Familie | `GEB <name>` (always Familie, even if `<name>` is a person) |
| `SSO` | Conny | unchanged |
| `TG` | Laurin | unchanged |
| `CH` | Conny | unchanged |
| `Praxis` | Conny | unchanged |
| `Turbine` | Jogi | unchanged |
| `LauMi` | Laurin + Milo | unchanged (group kept) |
| `MaPa` / `PaMa` | Conny + Jogi | unchanged (group kept) |
| `Mama` | Conny | leading `Mama` removed |
| `Papa` | Jogi | leading `Papa` removed |
| `Laurin` / `Milo` / `Conny` / `Jogi` | that column | leading name removed (e.g. "Milo Filmstart" → "Filmstart") |
| anything else | Familie | unchanged |

Examples: "Milo Filmstart" → Milo column as "Filmstart"; "Turbine Helferessen (Jogi)" → Jogi column, full title (the later "Jogi" does not count); "50 Jahre … Conny Lektorin" → Familie (Conny is not at the start); "LauMi schulfrei" → both the Laurin and Milo columns, title kept.

A single-day event valid for two **adjacent** persons (a group prefix) is written **once, centered over the two merged cells** (the grid line between them is covered). Exception: if one of the two columns has another entry that day, the event is rendered in each column instead.

### Day spans

- All-day events: Google's end date is exclusive → last day = end − 1 day
- Timed events: local (`TIMEZONE`) start day to end day; an end at exactly local midnight counts as the previous day
- Spans are clamped to the displayed month (an event crossing a month boundary appears on both pages, truncated)

### Single-day events

The displayed title (after the routing rewrites above) as text in the day's cell, wrapped to the column width. The font shrinks (down to a 9px floor) so that all entries sharing a cell fit its row height; text is clipped only beyond that. Cell text keeps clear of the multi-day strip boxes covering the same day.

### Multi-day events (2+ days)

A vertical strip at the **right border** of the column, spanning the covered day-rows, with the title **rotated 90°** (reads top to bottom). The box width adapts to the title: an entry that fits on one line gets a **one-line box**; longer titles wrap to **two lines** at the largest workable font — plain word wrap when possible, otherwise one word hyphenated across the lines at a syllable/compound boundary (e.g. "Weihnachtsessen" → "Weihnachts-" / "essen", "TG: Probeweekend" → "TG: Probe-" / "weekend") — and are truncated with "…" only as a last resort. Overlapping strips in one column stack leftwards; cell text on the covered days is narrowed accordingly.

## Project structure

```
ePaperCalendar/
├── main.py                  # entry point (Flask app)
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py          # app factory
│   ├── config.py            # env-based configuration
│   ├── family_config.py     # family-specific rules (columns, aliases, prefixes)
│   ├── routing.py           # generic title -> column routing logic
│   ├── calendar_service.py  # Google Calendar access (service account)
│   ├── render.py            # month-page rendering (Pillow) + CLI
│   ├── routes.py            # /, /api/events, /calendar.png
│   └── templates/index.html # preview page
├── credentials/             # service account key (gitignored)
├── SPECIFICATION.md         # this document
└── SETUP.md                 # human setup guide
```

## Customization

All family-specific rules — column names, group aliases (LauMi, MaPa/PaMa), person aliases (Mama, Papa), special prefixes (SSO, TG, CH, Praxis, Turbine) and the birthday rule — live in **`app/family_config.py`**. Edit that one file to adapt the calendar to another family; the routing logic (`app/routing.py`) and the rendering (`app/render.py`) stay generic.

## Known limitations

- Cell text shrinks to fit its row (9px floor); extremely long titles in busy cells can still clip
- Very long single-word titles in short multi-day strips are hyphenated across two lines; only if even that does not fit are they truncated with "…"
- Grayscale only (no color accents for persons or events), although the target panel supports 6 colors (black, white, yellow, red, blue, green)
- German month/weekday names are hardcoded

## Status

- [x] Google Calendar access via service account
- [x] Web app with preview, JSON API, month image
- [x] Month layout with routing and multi-day strips
- [ ] Push the image to an ePaper display (needs the panel's driver)
- [ ] Scheduled refresh of the display
