"""Read events from the shared family calendar using a Google service account."""

from datetime import datetime, timedelta, timezone

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def fetch_events(calendar_id, key_path, time_min=None, time_max=None, days_ahead=14, max_results=50):
    """Return events from the shared calendar as a list of plain dicts.

    Pass explicit time_min/time_max (datetimes) to fetch an arbitrary range,
    e.g. a whole month; otherwise the next `days_ahead` days are returned.
    """
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES
    )
    # explicit timeout: a hung connection fails fast instead of blocking the request
    http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=15))
    service = build("calendar", "v3", http=http, cache_discovery=False)

    now = datetime.now(timezone.utc)
    if time_min is None:
        time_min = now
    if time_max is None:
        time_max = now + timedelta(days=days_ahead)
    time_min = time_min.isoformat()
    time_max = time_max.isoformat()

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for item in result.get("items", []):
        events.append(
            {
                "id": item.get("id"),
                "summary": item.get("summary", "(no title)"),
                "start": item["start"].get("dateTime") or item["start"].get("date"),
                "end": item["end"].get("dateTime") or item["end"].get("date"),
                "all_day": "date" in item["start"],
            }
        )
    return events
