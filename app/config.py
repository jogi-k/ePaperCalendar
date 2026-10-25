import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SERVICE_ACCOUNT_KEY = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_KEY", "credentials/service-account.json"
    )
    FAMILY_CALENDAR_ID = os.environ.get("FAMILY_CALENDAR_ID", "")
    DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "14"))
    PORT = int(os.environ.get("PORT", "5000"))
    EPAPER_WIDTH = int(os.environ.get("EPAPER_WIDTH", "1872"))
    EPAPER_HEIGHT = int(os.environ.get("EPAPER_HEIGHT", "1404"))
    TIMEZONE = os.environ.get("TIMEZONE", "Europe/Zurich")
