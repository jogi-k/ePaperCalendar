# ePaper Family Calendar — Setup Guide

How to set up the project from scratch on a local machine (e.g. a Raspberry Pi). For the program's behavior (layout, routing rules, API), see [SPECIFICATION.md](SPECIFICATION.md).

You need: a Google account and about 15 minutes. No Google Workspace, no payment, no OAuth consent flow.

## 1. Google Cloud project

1. Go to https://console.cloud.google.com and create a project, e.g. `epaper-family-calendar`.
2. In **APIs & Services → Library**, search for **Google Calendar API** and enable it.

## 2. Service account

The app reads the calendar with a service account — no OAuth sign-in and no expiring tokens. (This is why the OAuth user flow is not used: with the consent screen in "Testing" mode, refresh tokens expire after 7 days.)

1. **IAM & Admin → Service Accounts → Create service account**
   - Name: `epaper-family-cal`
   - No extra IAM roles needed — access is granted via calendar sharing, not IAM.
2. Open the service account → **Keys → Add key → Create new key → JSON**.
3. Save the downloaded file in the project as `credentials/service-account.json`.
4. Make sure `.gitignore` contains:

   ```
   credentials/
   .env
   ```

The service account email looks like `epaper-family-cal@<project-id>.iam.gserviceaccount.com`.

## 3. Shared "Family" calendar

One shared calendar is the single source of truth the whole family writes to.

1. Go to https://calendar.google.com and create a new calendar named **Family**.
2. Open its **Settings and sharing**:
   - **Integrate calendar** → copy the **Calendar ID** (e.g. `abc123...@group.calendar.google.com`)
   - **Share with specific people** → add the service account email from step 2 with permission **"See all event details"** (read-only)
3. Everyone in the family adds events to this calendar (it appears in their own Google Calendar as a shared calendar).

Gotcha: without the sharing step, the API returns `404 Not Found` even though authentication itself succeeds.

## 4. Install and run

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
GOOGLE_SERVICE_ACCOUNT_KEY=./credentials/service-account.json
FAMILY_CALENDAR_ID=<calendar-id-from-step-3>
```

Optional settings in `.env`: `EPAPER_WIDTH` / `EPAPER_HEIGHT` (your panel's resolution; the defaults 1600×1200 match the INKPLATE 13SPECTRA), `TIMEZONE` (default `Europe/Zurich`), `PORT` (default 5000), `DAYS_AHEAD` (preview window, default 14).

Then start:

```bash
venv/bin/python main.py
```

## 5. Verify

- http://localhost:5000/ — preview table of upcoming events
- http://localhost:5000/api/events — same data as JSON
- http://localhost:5000/calendar.png — rendered month image for the ePaper

Or render headless: `venv/bin/python -m app.render --month 2026-10 --out calendar.png`

## Troubleshooting

| Symptom | Cause |
|---|---|
| `404 Not Found` from the API | Calendar not shared with the service account email (step 3) |
| `403` / API errors | Google Calendar API not enabled (step 1) |
| `invalid_grant` / auth errors | Wrong key file path in `.env`, or wrong key file |
| Preview shows an error box | Read the message; the API client times out after 15s |
