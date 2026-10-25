# ePaper Family Calendar — Specification

Chosen access design: **Path A — Google service account + one shared "Family" calendar**.

Why this path:

- No OAuth consent dance, no test users, no expiring tokens
- The app runs fully headless — ideal for a local web app feeding an ePaper display
- One shared calendar is the single source of truth for the whole family

## 1. Google Cloud project

1. Go to https://console.cloud.google.com and create a project, e.g. `epaper-family-calendar`.
2. In **APIs & Services → Library**, search for **Google Calendar API** and enable it.

## 2. Service account

1. **IAM & Admin → Service Accounts → Create service account**
   - Name: `epaper-family-cal`
   - No extra IAM roles needed — access is granted via calendar sharing, not IAM.
2. Open the service account → **Keys → Add key → Create new key → JSON**.
3. A JSON file downloads. Save it in this project as:

   ```
   credentials/service-account.json
   ```

4. Add to `.gitignore`:

   ```
   credentials/
   .env
   ```

The service account email looks like:

```
epaper-family-cal@<project-id>.iam.gserviceaccount.com
```

## 3. Shared "Family" calendar

1. Go to https://calendar.google.com and create a new calendar named **Family**.
2. Open its **Settings and sharing**:
   - **Integrate calendar** → copy the **Calendar ID** (e.g. `abc123...@group.calendar.google.com`)
   - **Share with specific people** → add the service account email from step 2 with permission **"See all event details"** (read-only)
3. Store the Calendar ID — the app needs it. Suggested `.env`:

   ```
   GOOGLE_SERVICE_ACCOUNT_KEY=./credentials/service-account.json
   FAMILY_CALENDAR_ID=<calendar-id-from-above>
   ```

Without the sharing step the API returns `404 Not Found`, even though authentication itself succeeds.

## 4. How the app reads events

- Authenticate with the JSON key server-side (Python: `google-api-python-client` + `google-auth`)
- Call `calendar.events.list` on `FAMILY_CALENDAR_ID` with `timeMin`/`timeMax` covering the rendered month (or the next `DAYS_AHEAD` days for the preview/API)
- Recurring events are expanded into individual instances (`singleEvents=true`)
- Read-only access is sufficient for the display
- The Google client uses a 15s timeout: if the API hangs, requests fail fast (the preview shows an error box; `/api/events` and `/calendar.png` return 503) instead of blocking

## 5. Family workflow

Everyone adds events to the shared **Family** calendar. From each family member's own Google Calendar it shows up as a shared/subscribed calendar. Syncing from personal calendars can be added later if needed.

## Not chosen: OAuth2 user flow

Skipped on purpose. With the OAuth consent screen in "Testing" mode, refresh tokens expire after 7 days (weekly re-consent), and each consenting user only exposes their own calendar. The service account path avoids both issues.

## 6. Web app stack

**Python + Flask** (chosen over Next.js): the app runs locally — most likely on a Raspberry Pi — where the ePaper ecosystem (Waveshare/Inky display drivers, Pillow image rendering) is Python-first. The official `google-api-python-client` covers the calendar access, and Flask is more than enough for the simple preview page.

## 7. Run the app

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in FAMILY_CALENDAR_ID
.venv/bin/python main.py
```

- Preview page: http://localhost:5000/ (HTML table of upcoming events)
- JSON API: http://localhost:5000/api/events
- Month image (ePaper): http://localhost:5000/calendar.png?month=YYYY-MM

Status: verified working — `/api/events` returns the live events from the shared family calendar.

## 8. ePaper month layout

One page per month (`app/render.py`, Pillow, grayscale), served at `/calendar.png?month=YYYY-MM` (default: current month) or rendered via CLI:

```bash
.venv/bin/python -m app.render --month 2026-10 --out calendar.png
```

- Header: month name (e.g. "Oktober 2026")
- Rows: one per day; first column shows the date as "Weekday, Day" (German short weekday, e.g. "Mo, 5")
- Columns: Familie, Laurin, Milo, Conny, Jogi
- Routing: no name in the title -> Familie, otherwise the matching column(s).
  Aliases: Mama -> Conny, Papa -> Jogi, MaPa/PaMa -> Conny + Jogi, LauMi -> Laurin + Milo
- No times; single-day events as text in the day's cell
- Multi-day events: vertical strip at the right border of the column spanning the covered
  days (clamped to the shown month), title rotated 90°; overlapping strips in one column
  stack leftwards; strip titles are shrunk to fit the covered days and truncated with "…" if needed
- Single-day cell text: wrapped to the column width; at 1872x1404 each cell fits one
  line, longer titles are clipped at the cell edge
- Today's date is highlighted; weekend rows are shaded
- Default render size 1872x1404 (landscape, grayscale); set EPAPER_WIDTH / EPAPER_HEIGHT /
  TIMEZONE in `.env` to match your panel

## Next steps

- [x] Scaffold the web app (Python/Flask — `main.py`, `app/`, `requirements.txt`)
- [x] Implement an `/api/events` endpoint that reads the calendar via the service account
- [x] Build the ePaper rendering view (Pillow → PNG: `app/render.py`, `/calendar.png`)
- [ ] Refresh the ePaper display from the app on a schedule
