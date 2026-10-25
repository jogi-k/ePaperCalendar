# ePaper Family Calendar — Specification

What the program does and how it behaves. For installing and configuring it (Google account, service account, shared calendar), see [SETUP.md](SETUP.md).

## Overview

A small local web app (Python + Flask) that reads one shared Google calendar ("Family") via a service account and renders it as a **one-page-per-month, grayscale image** for an ePaper display (target panel: INKPLATE 13SPECTRA, 13.3″, 1600×1200, E-Ink Spectra 6-color). It also serves a simple HTML preview and a JSON API for debugging.

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
| `EPAPER_WIDTH` / `EPAPER_HEIGHT` | `1600` / `1200` | Render size in px (landscape); defaults match the target panel (INKPLATE 13SPECTRA) |
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

An event goes into the column(s) of the person(s) named in its title:

| Title contains | Column(s) |
|---|---|
| (none of the names) | Familie |
| `Familie` | Familie |
| `Laurin` | Laurin |
| `Milo` | Milo |
| `Conny` | Conny |
| `Jogi` | Jogi |
| `Mama` | Conny |
| `Papa` | Jogi |
| `MaPa` / `PaMa` | Conny + Jogi |
| `LauMi` | Laurin + Milo |

Matching is case-insensitive substring matching on the title. An event matching several names appears in each of those columns. The full title text is rendered as-is.

### Day spans

- All-day events: Google's end date is exclusive → last day = end − 1 day
- Timed events: local (`TIMEZONE`) start day to end day; an end at exactly local midnight counts as the previous day
- Spans are clamped to the displayed month (an event crossing a month boundary appears on both pages, truncated)

### Single-day events

The event title as text in the day's cell, wrapped to the column width. At the default 1600×1200 each cell fits **one line**; longer titles are clipped at the cell edge.

### Multi-day events (2+ days)

A vertical strip at the **right border** of the column, spanning the covered day-rows, with the title **rotated 90°** (reads top to bottom). Overlapping strips in one column stack leftwards. Strip titles are shrunk to fit the covered days and truncated with "…" if still too long.

## Project structure

```
ePaperCalendar/
├── main.py                  # entry point (Flask app)
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py          # app factory
│   ├── config.py            # env-based configuration
│   ├── calendar_service.py  # Google Calendar access (service account)
│   ├── render.py            # month-page rendering (Pillow) + CLI
│   ├── routes.py            # /, /api/events, /calendar.png
│   └── templates/index.html # preview page
├── credentials/             # service account key (gitignored)
├── SPECIFICATION.md         # this document
└── SETUP.md                 # human setup guide
```

## Known limitations

- One line of event text per cell at the default render size (long titles clip)
- Strip titles truncate with "…" on very short multi-day spans
- Grayscale only (no color accents for persons or events), although the target panel supports 6 colors (black, white, yellow, red, blue, green)
- German month/weekday names are hardcoded

## Status

- [x] Google Calendar access via service account
- [x] Web app with preview, JSON API, month image
- [x] Month layout with routing and multi-day strips
- [ ] Push the image to an ePaper display (needs the panel's driver)
- [ ] Scheduled refresh of the display
