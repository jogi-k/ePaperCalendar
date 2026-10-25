"""Render the shared family calendar as a one-page month image for the ePaper display.

Layout (landscape, one row per day):
- Header: month name, e.g. "Oktober 2026"
- First column: date as "Weekday, Day" (German short weekday, e.g. "Mo, 5")
- Then one column per person (see app/family_config.py)
- Routing (app/routing.py, rules in app/family_config.py): an event belongs to
  the person/group its title starts with; later occurrences do not count.
  Single-column matches have the leading name removed from the displayed title,
  group matches keep the group and expand to both columns. No times are rendered.
- Single-day events: text in the day's cell. An event valid for two adjacent
  persons (group prefix) is written once, centered over the two merged cells.
- Multi-day events: vertical strip at the right border of the column, spanning
  the covered day rows, with the title rotated 90 degrees. The box width adapts
  to the title: one line if it fits, otherwise two lines. Overlong titles are
  hyphenated across the two lines (compound/syllable boundaries preferred) and
  truncated with an ellipsis only as a last resort.
"""

import io
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from app.family_config import COLUMNS
from app.routing import route_event

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
        route = route_event(event["summary"])
        prepared.append(
            {
                "summary": event["summary"],
                "display": route["display"],
                "start": start,
                "end": end,
                "multi": (end - start).days + 1 >= 2,
                "columns": route["columns"],
                "all_day": event["all_day"],
            }
        )
    prepared.sort(key=lambda ev: (ev["start"], not ev["all_day"]))
    return prepared


def plan_cells(prepared, first):
    """Split single-day events into normal cells and merged two-column cells.

    A single-day event valid for two adjacent persons (a group prefix like LauMi
    or MaPa) is written once, centered over the two merged cells — but only when
    neither column has another entry that day; otherwise the event is rendered
    in each column.
    """
    cells = {}
    merged = {}
    for event in prepared:
        if event["multi"]:
            continue
        d_idx = (event["start"] - first).days
        cols = event["columns"]
        if len(cols) == 2:
            i = COLUMNS.index(cols[0])
            j = COLUMNS.index(cols[1])
            if j == i + 1:
                merged[(d_idx, i)] = event
                continue
        for col in cols:
            cells.setdefault((d_idx, col), []).append(event)
    for (d_idx, i), event in list(merged.items()):
        clash = any(
            key[0] == d_idx and COLUMNS.index(key[1]) in (i, i + 1)
            for key in cells
        )
        if clash:
            del merged[(d_idx, i)]
            for col in event["columns"]:
                cells.setdefault((d_idx, col), []).append(event)
    return cells, merged


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


def draw_cell_text(draw, x0, y0, x1, y1, events, font_size, center=False):
    """Draw event titles in a cell, shrinking the font until all wrapped
    lines of all entries fit the cell height (clipping only beyond the
    9px floor)."""
    pad = 6
    max_w = x1 - x0 - 2 * pad
    size = font_size
    while size > 9:
        font = load_font(size)
        line_h = text_height(draw, font) + 2
        total = sum(len(wrap_text(draw, event["display"], font, max_w)) * line_h + 3 for event in events) - 3
        if y0 + 3 + total <= y1 - 2:
            break
        size -= 1
    font = load_font(size)
    line_h = text_height(draw, font) + 2
    y = y0 + 3
    for event in events:
        for line in wrap_text(draw, event["display"], font, max_w):
            if y + line_h > y1 - 2:
                return
            if center:
                lw = draw.textlength(line, font=font)
                draw.text((x0 + (x1 - x0 - lw) / 2, y), line, font=font, fill=INK)
            else:
                draw.text((x0 + pad, y), line, font=font, fill=INK)
            y += line_h
        y += 3


def _split_candidates(word):
    """Hyphen split positions in a word as (position, score) pairs.

    Only plausible German syllable/compound boundaries are considered — never
    vowel|vowel or consonant|consonant, and never a vowel|consonant split whose
    tail starts with a consonant cluster (unpronounceable, e.g. "Weihnac|htsessen"
    or "Weihnachtse|ssen"). Score 2 for vowel|consonant where the tail starts
    with a single consonant + vowel (compound-like, e.g. "Probe|weekend"), 1 for
    consonant|vowel (syllable-like, e.g. "Weihnachts|essen"). Head and tail
    must each keep at least 4 characters.
    """
    vowels = set("aeiouäöüy")
    out = []
    for k in range(4, len(word) - 3):
        before = word[k - 1].lower()
        after = word[k].lower()
        if (before in vowels) == (after in vowels):
            continue
        if before in vowels:
            if k + 1 < len(word) and word[k + 1].lower() in vowels:
                out.append((k, 2))
        else:
            out.append((k, 1))
    return out


def _two_line_candidates(draw, text, font, max_len):
    """All ways to set the text on two lines that each fit max_len.

    Returns (tier, head_len, lines) tuples: tier 3 = plain word wrap without
    hyphenation; tier 1/2 = one word hyphenated across the lines (score from
    _split_candidates). head_len is the length of the hyphenated head (0 for
    plain wrap) and prefers splits that keep more of the word on the first line.
    """
    cands = []
    plain = wrap_text(draw, text, font, max_len)
    if len(plain) == 2 and all(draw.textlength(line, font=font) <= max_len for line in plain):
        cands.append((3, 0, plain))
    words = text.split()
    for i, word in enumerate(words):
        prefix = " ".join(words[:i])
        suffix = " ".join(words[i + 1:])
        for k, score in _split_candidates(word):
            head = f"{prefix} {word[:k]}-" if prefix else f"{word[:k]}-"
            tail = word[k:] + (f" {suffix}" if suffix else "")
            if draw.textlength(head, font=font) <= max_len and draw.textlength(tail, font=font) <= max_len:
                cands.append((score, k, [head, tail]))
    return cands


def fit_strip_lines(draw, text, font_size, max_len):
    """Fit a strip title into one or two rotated lines.

    One line at the largest fitting font is preferred. Otherwise two lines:
    plain word wrap when possible, else one word hyphenated across the lines.
    Among the hyphenated variants the best split position wins (compound-like
    vowel|consonant boundaries first, then the split keeping more of the word
    on the first line), then the largest font. Truncation with an ellipsis is
    the last resort. Returns (lines, font_size).
    """
    size = font_size
    while size > 8 and draw.textlength(text, font=load_font(size)) > max_len:
        size -= 1
    if draw.textlength(text, font=load_font(size)) <= max_len:
        return [text], size

    best = None  # ((tier, head_len, size), lines, size)
    for size in range(font_size, 7, -1):
        font = load_font(size)
        for tier, head_len, lines in _two_line_candidates(draw, text, font, max_len):
            key = (tier, head_len, size)
            if best is None or key > best[0]:
                best = (key, lines, size)
    if best is not None:
        return best[1], best[2]

    font = load_font(8)  # last resort: two truncated lines
    lines = wrap_text(draw, text, font, max_len)[:2]
    last = lines[-1]
    while last and draw.textlength(last + "…", font=font) > max_len:
        last = last[:-1]
    lines[-1] = (last + "…") if last else "…"
    return lines, 8


def draw_strip(img, draw, x1, y0, y1, text, font_size):
    """Vertical strip at the right border of a column; the box width adapts to
    the title: one line if it fits, otherwise two lines."""
    max_len = (y1 - y0) - 6
    lines, size = fit_strip_lines(draw, text, font_size, max_len)
    font = load_font(size)
    line_h = text_height(draw, font) + 2
    strip_w = len(lines) * line_h + 8
    x0 = x1 - strip_w
    draw.rectangle([x0, y0, x1, y1], fill=STRIP_FILL, outline=INK, width=2)

    rotated = []
    for line in lines:
        tw = draw.textlength(line, font=font)
        th = text_height(draw, font)
        tmp = Image.new("L", (int(tw) + 4, th + 4), STRIP_FILL)
        ImageDraw.Draw(tmp).text((2, 2), line, font=font, fill=INK)
        rotated.append(tmp.rotate(-90, expand=True))  # clockwise: reads top to bottom
    total_w = sum(t.width for t in rotated) + 2 * (len(rotated) - 1)
    x = (x0 + x1) // 2 - total_w // 2
    cy = (y0 + y1) // 2
    for tmp in rotated:
        img.paste(tmp, (x, cy - tmp.height // 2))
        x += tmp.width + 2


def strip_reserve(strips, col, d_idx, max_strip_w):
    """Width to keep clear at a column's right border for a cell on day d_idx:
    covers every strip box spanning that day (strips stack leftwards from the
    right border, so the deepest level sets the reservation)."""
    levels = [level for level, s, e, _ in strips[col] if s <= d_idx <= e]
    if not levels:
        return 0
    return 6 + max(levels) * (max_strip_w + 4) + max_strip_w


def render_month(events, year, month, width=1600, height=1200, tz=None):
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
    f_event = max(9, int(row_h * 0.58))  # font size; draw_cell_text loads and shrinks it per cell
    f_strip = max(9, int(row_h * 0.5))
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    max_strip_w = max(14, 2 * (text_height(probe, load_font(f_strip)) + 2) + 8)  # widest strip: two lines

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
            strips[col].append((level, s_idx, e_idx, event["display"]))

    cells, merged = plan_cells(prepared, first)

    # merged two-column cells (drawn before strips so strips stay on top; the
    # fill covers the middle grid line so the two cells look like one)
    for (d_idx, i), event in merged.items():
        y0 = grid_top + d_idx * row_h
        y1 = y0 + row_h
        x0 = col_edges[i]
        x1 = col_edges[i + 2]
        tx0, tx1 = x0, x1
        # strips of the left column sit at its right edge (middle of the span)
        reserve = strip_reserve(strips, COLUMNS[i], d_idx, max_strip_w)
        if reserve:
            tx1 = min(tx1, col_edges[i + 1] - reserve)
        # strips of the right column sit at the span's right edge
        reserve = strip_reserve(strips, COLUMNS[i + 1], d_idx, max_strip_w)
        if reserve:
            tx1 = min(tx1, x1 - reserve)
        fill = SHADE if days[d_idx].weekday() >= 5 else PAPER
        draw.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=fill)
        draw_cell_text(draw, tx0, y0, tx1, y1, [event], f_event, center=True)

    for col, items in strips.items():
        ci = COLUMNS.index(col)
        for level, s_idx, e_idx, text in items:
            x1 = col_edges[ci + 1] - 6 - level * (max_strip_w + 4)
            y0 = grid_top + s_idx * row_h + 2
            y1 = grid_top + (e_idx + 1) * row_h - 2
            draw_strip(img, draw, x1, y0, y1, text, f_strip)

    # single-day events (text keeps clear of the strip boxes covering the day)
    for (d_idx, col), cell_events in cells.items():
        ci = COLUMNS.index(col)
        x0 = col_edges[ci]
        x1 = col_edges[ci + 1] - strip_reserve(strips, col, d_idx, max_strip_w)
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
        width=int(os.environ.get("EPAPER_WIDTH", "1600")),
        height=int(os.environ.get("EPAPER_HEIGHT", "1200")),
        tz=tz,
    )
    with open(args.out, "wb") as f:
        f.write(buf.getvalue())
    print(f"wrote {args.out}: {year}-{month:02d}, {len(events)} events")


if __name__ == "__main__":
    main()
