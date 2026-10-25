from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from zoneinfo import ZoneInfo

from app.calendar_service import fetch_events
from app.render import month_bounds, parse_month, render_month

bp = Blueprint("main", __name__)


def _load_events():
    return fetch_events(
        calendar_id=current_app.config["FAMILY_CALENDAR_ID"],
        key_path=current_app.config["SERVICE_ACCOUNT_KEY"],
        days_ahead=current_app.config["DAYS_AHEAD"],
    )


def _display_time(event):
    try:
        dt = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
    except ValueError:
        return event["start"]
    if event["all_day"]:
        return dt.strftime("%a %d.%m.")
    return dt.strftime("%a %d.%m. %H:%M")


@bp.route("/")
def index():
    try:
        events = _load_events()
        for event in events:
            event["start_display"] = _display_time(event)
        error = None
    except Exception as exc:  # surface setup problems (missing key, wrong calendar id) in the preview
        events, error = [], str(exc)
    return render_template(
        "index.html",
        events=events,
        error=error,
        days_ahead=current_app.config["DAYS_AHEAD"],
    )


@bp.route("/api/events")
def api_events():
    try:
        return jsonify(_load_events())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@bp.route("/calendar.png")
def calendar_png():
    try:
        tz = ZoneInfo(current_app.config["TIMEZONE"])
        year, month = parse_month(request.args.get("month"), tz)
        time_min, time_max = month_bounds(year, month, tz)
        events = fetch_events(
            calendar_id=current_app.config["FAMILY_CALENDAR_ID"],
            key_path=current_app.config["SERVICE_ACCOUNT_KEY"],
            time_min=time_min,
            time_max=time_max,
            max_results=250,
        )
        buf = render_month(
            events, year, month,
            width=current_app.config["EPAPER_WIDTH"],
            height=current_app.config["EPAPER_HEIGHT"],
            tz=tz,
        )
        return send_file(buf, mimetype="image/png")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503
