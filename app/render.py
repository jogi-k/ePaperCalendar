"""Render the shared family calendar as a one-page month image for the ePaper display.

Layout (landscape, one row per day):
- Header: month name, e.g. "Oktober 2026"
- First column: date as "Weekday, Day" (German short weekday, e.g. "Mo, 5")
- Then one column per person: Familie, Laurin, Milo, Conny, Jogi
- Routing: an event without any person's name goes to "Familie", otherwise into
  the respective column(s). Aliases: Mama -> Conny, Papa -> Jogi,
  MaPa/PaMa -> Conny + Jogi. No times are rendered.
- Single-day events: text in the day's cell.
- Multi-day events: vertical strip at the right border of the column, spanning
  the covered day rows, with the title rotated 90 degrees.
"""

import io
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

COLUMNS = ["Familie", "Laurin", "Milo", "Conny", "Jogi"]

# lowercase alias -> columns it maps to
ALIASES = {
    "mapa": ["Conny", "Jogi"],
    "pama": ["Conny", "Jogi"],
    "mama": ["Conny"],
    "papa": ["Jogi"],
    "laumi": ["Laurin", "Milo"],
}

MONTH_NAMES_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

PAPER = 255
INK = 0
GRID = 200
SHADE = 242
STRIP_FILL = 225

_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
]
_font_cache = {}


def load_font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        font = None
        for directory in _FONT_DIRS:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                font = ImageFont.truetype(path, size)
                break
        if font is None:
            try:
                font = ImageFont.load_default(size)
            except TypeError:
                font = ImageFont.load_default()
        _font_cache[key] = font
    return _font_cache[key]


def text_height(draw, font):
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return bbox[3] - bbox[1]


def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_month(value, tz):
    """'YYYY-MM' string or None (current month in tz) -> (year, month)."""
    if value:
        year_s, month_s = value.split("-")
        return int(year_s), int(month_s)
    now = datetime.now(tz)
    return now.year, now.month


def month_bounds(year, month, tz):
    """UTC datetimes for the local month start and the next month start."""
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def month_days(year, month):
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return [date(year, month, day) for day in range(1, last.day + 1)]


def assign_columns(summary):
    """Map an event title to the columns it belongs to (default: Familie)."""
    text = summary.lower()
    matched = []
    for alias, cols in ALIASES.items():
        if alias in text:
            matched.extend(cols)
    for col in COLUMNS:
        if col.lower() in text:
            matched.append(col)
    return list(dict.fromkeys(matched)) or ["Familie"]


def _local_date(dt, tz):
    if dt.tzinfo is None:
        return dt.date()  # all-day dates are timezone-less calendar dates
    return dt.astimezone(tz).date()


def event_day_span(event, tz):
    """First and last local calendar day an event occupies."""
    start = _local_date(parse_dt(event["start"]), tz)
    end_raw = parse_dt(event["end"])
    if event["all_day"]:
        last = _local_date(end_raw, tz) - timedelta(days=1)  # Google all-day end is exclusive
    else:
        end_local = end_raw if end_raw.tzinfo is None else end_raw.astimezone(tz)
        if (end_local.hour, end_local.minute, end_local.second) == (0, 0, 0):
            last = end_local.date() - timedelta(days=1)
        else:
            last = end_local.date()
    return start, last


def prepare_events(events, year, month, tz):
    """Assign events to columns and day spans, clamped to the displayed month."""
    first = date(year, month, 1)
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    prepared = []
    for event in events:
        start, end = event_day_span(event, tz)
        start = max(start, first)
        end = min(end, last)
        if start > end:
            continue
        prepared.append(
            {
                "summary": event["summary"],
                "start": start,
                "end": end,
                "multi": (end - start).days + 1 >= 2,
                "columns": assign_columns(event["summary"]),
                "all_day": event["all_day"],
            }
        )
    prepared.sort(key=lambda ev: (ev["start"], not ev["all_day"]))
    return prepared


def wrap_text(draw, text, font, max_width):
    lines = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_cell_text(draw, x0, y0, x1, y1, events, font):
    pad = 6
    line_h = text_height(draw, font) + 2
    y = y0 + 3
    for event in events:
        for line in wrap_text(draw, event["summary"], font, x1 - x0 - 2 * pad):
            if y + line_h > y1 - 2:
                return
            draw.text((x0 + pad, y), line, font=font, fill=INK)
            y += line_h
        y += 3


def draw_strip(img, draw, x0, y0, x1, y1, text, font_size):
    """Vertical strip with the title rotated 90 degrees, font shrunk to fit."""
    draw.rectangle([x0, y0, x1, y1], fill=STRIP_FILL, outline=INK, width=2)
    max_len = (y1 - y0) - 10
    size = min(font_size, (x1 - x0) - 6)
    while size > 9 and draw.textlength(text, font=load_font(size)) > max_len:
        size -= 1
    font = load_font(max(8, size))
    if draw.textlength(text, font=font) > max_len:
        while text and draw.textlength(text + "…", font=font) > max_len:
            text = text[:-1]
        text += "…"
    tw = draw.textlength(text, font=font)
    th = text_height(draw, font)
    tmp = Image.new("L", (int(tw) + 4, th + 4), STRIP_FILL)
    ImageDraw.Draw(tmp).text((2, 2), text, font=font, fill=INK)
    tmp = tmp.rotate(-90, expand=True)  # clockwise: reads top to bottom
    img.paste(tmp, ((x0 + x1) // 2 - tmp.width // 2, (y0 + y1) // 2 - tmp.height // 2))


def render_month(events, year, month, width=1872, height=1404, tz=None):
    """Render one month page and return it as a PNG BytesIO."""
    tz = tz or ZoneInfo("Europe/Zurich")
    img = Image.new("L", (width, height), PAPER)
    draw = ImageDraw.Draw(img)

    days = month_days(year, month)
    prepared = prepare_events(events, year, month, tz)

    margin = max(12, width // 78)
    header_h = max(60, height // 13)
    colheader_h = max(34, height // 24)
    date_col_w = max(110, width // 11)
    grid_top = margin + header_h + colheader_h
    n_days = len(days)
    row_h = max(14, (height - grid_top - margin) // n_days)
    grid_bottom = grid_top + row_h * n_days

    person_area = width - 2 * margin - date_col_w
    col_edges = [
        margin + date_col_w + (person_area * i) // len(COLUMNS)
        for i in range(len(COLUMNS) + 1)
    ]

    f_month = load_font(max(20, int(header_h * 0.62)), bold=True)
    f_col = load_font(max(12, int(colheader_h * 0.55)), bold=True)
    f_date = load_font(max(10, int(row_h * 0.6)))
    f_event = load_font(max(9, int(row_h * 0.58)))
    f_strip = max(9, int(row_h * 0.5))
    strip_w = max(14, (col_edges[1] - col_edges[0]) // 14)

    first = days[0]
    today = datetime.now(tz).date()

    # weekend shading
    for idx, day in enumerate(days):
        if day.weekday() >= 5:
            y0 = grid_top + idx * row_h
            draw.rectangle([margin, y0, width - margin, y0 + row_h], fill=SHADE)

    # month name
    title = f"{MONTH_NAMES_DE[month - 1]} {year}"
    tw = draw.textlength(title, font=f_month)
    draw.text(
        ((width - tw) / 2, margin + (header_h - text_height(draw, f_month)) / 2),
        title, font=f_month, fill=INK,
    )

    # column headers
    headers = ["Datum"] + COLUMNS
    spans = [(margin, margin + date_col_w)] + list(zip(col_edges, col_edges[1:]))
    for name, (x0, x1) in zip(headers, spans):
        nw = draw.textlength(name, font=f_col)
        draw.text(
            ((x0 + x1 - nw) / 2, grid_top - colheader_h + (colheader_h - text_height(draw, f_col)) / 2),
            name, font=f_col, fill=INK,
        )

    # grid lines
    xs = [margin, margin + date_col_w] + col_edges[1:]
    for x in xs:
        edge = x in (margin, width - margin)
        draw.line([(x, grid_top - colheader_h), (x, grid_bottom)], fill=INK if edge else GRID, width=2 if edge else 1)
    draw.line([(margin, grid_top - colheader_h), (width - margin, grid_top - colheader_h)], fill=GRID)
    for idx in range(n_days + 1):
        y = grid_top + idx * row_h
        edge = idx in (0, n_days)
        draw.line([(margin, y), (width - margin, y)], fill=INK if edge else GRID, width=2 if edge else 1)

    # multi-day strips (right border of the column, stacked leftwards on overlap)
    levels = {col: [[]] for col in COLUMNS}
    strips = {col: [] for col in COLUMNS}
    for event in prepared:
        if not event["multi"]:
            continue
        s_idx = (event["start"] - first).days
        e_idx = (event["end"] - first).days
        for col in event["columns"]:
            level = 0
            while any(not (e_idx < a or s_idx > b) for a, b in levels[col][level]):
                level += 1
                if level == len(levels[col]):
                    levels[col].append([])
            levels[col][level].append((s_idx, e_idx))
            strips[col].append((level, s_idx, e_idx, event["summary"]))

    for col, items in strips.items():
        ci = COLUMNS.index(col)
        for level, s_idx, e_idx, text in items:
            x1 = col_edges[ci + 1] - 6 - level * (strip_w + 4)
            x0 = x1 - strip_w
            y0 = grid_top + s_idx * row_h + 2
            y1 = grid_top + (e_idx + 1) * row_h - 2
            draw_strip(img, draw, x0, y0, x1, y1, text, f_strip)

    strip_cols = {col for col in COLUMNS if strips[col]}

    # single-day events
    cells = {}
    for event in prepared:
        if event["multi"]:
            continue
        d_idx = (event["start"] - first).days
        for col in event["columns"]:
            cells.setdefault((d_idx, col), []).append(event)
    for (d_idx, col), cell_events in cells.items():
        ci = COLUMNS.index(col)
        x0 = col_edges[ci]
        x1 = col_edges[ci + 1]
        if col in strip_cols:
            x1 -= strip_w + 6
        draw_cell_text(draw, x0, grid_top + d_idx * row_h, x1, grid_top + (d_idx + 1) * row_h, cell_events, f_event)

    # dates (drawn last so the today marker sits on top of the shading)
    for idx, day in enumerate(days):
        y0 = grid_top + idx * row_h
        label = f"{WEEKDAYS_DE[day.weekday()]}, {day.day}"
        x0 = margin + 8
        ty = y0 + (row_h - text_height(draw, f_date)) / 2
        if day == today:
            tw = draw.textlength(label, font=f_date)
            th = text_height(draw, f_date)
            draw.rectangle([x0 - 4, ty - 2, x0 + tw + 4, ty + th + 2], fill=INK)
            draw.text((x0, ty), label, font=f_date, fill=PAPER)
        else:
            draw.text((x0, ty), label, font=f_date, fill=INK)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def main():
    import argparse

    from dotenv import load_dotenv

    from app.calendar_service import fetch_events

    load_dotenv()
    parser = argparse.ArgumentParser(description="Render the family month calendar to a PNG")
    parser.add_argument("--month", help="YYYY-MM (default: current month)")
    parser.add_argument("--out", default="calendar.png")
    args = parser.parse_args()

    tz = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Zurich"))
    year, month = parse_month(args.month, tz)
    time_min, time_max = month_bounds(year, month, tz)
    events = fetch_events(
        calendar_id=os.environ["FAMILY_CALENDAR_ID"],
        key_path=os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "credentials/service-account.json"),
        time_min=time_min,
        time_max=time_max,
        max_results=250,
    )
    buf = render_month(
        events, year, month,
        width=int(os.environ.get("EPAPER_WIDTH", "1872")),
        height=int(os.environ.get("EPAPER_HEIGHT", "1404")),
        tz=tz,
    )
    with open(args.out, "wb") as f:
        f.write(buf.getvalue())
    print(f"wrote {args.out}: {year}-{month:02d}, {len(events)} events")


if __name__ == "__main__":
    main()
