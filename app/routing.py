"""Route event titles to calendar columns.

The logic is generic; all family-specific data (column names, aliases, special
prefixes, the birthday rule) lives in app/family_config.py.
"""

import re

from app import family_config as config


def _prefix_match(text, token):
    """Case-insensitive match of token at the very start of text (word boundary)."""
    return re.match(rf"^\s*{re.escape(token)}\b", text, re.IGNORECASE)


def route_event(summary):
    """Return {"columns": [...], "display": ...} for an event title.

    Rules, in order:
    1. "<name> hat Geburtstag"  -> "GEB <name>" in the default column
    2. special leading token    -> assigned person, title kept as-is
    3. leading group token      -> both columns, group kept in the title
    4. leading person alias     -> one column, alias removed from the title
    5. leading person name      -> one column, name removed from the title
    6. anything else            -> default column, title kept as-is
    """
    title = summary.strip()
    persons = [c for c in config.COLUMNS if c != config.DEFAULT_COLUMN]

    # 1. birthday rule (overrides everything, even person names)
    marker = f" {config.BIRTHDAY_PATTERN}"
    if title.lower().endswith(marker.lower()):
        name = title[: -len(marker)].strip()
        return {
            "columns": [config.DEFAULT_COLUMN],
            "display": f"{config.BIRTHDAY_PREFIX} {name}".strip(),
        }

    # 2. special prefixes: assigned to a person, but not removed
    for token, column in config.SPECIAL_PREFIXES.items():
        if _prefix_match(title, token):
            return {"columns": [column], "display": title}

    # 3. group prefixes: kept in the title, expanded to both columns
    for token, columns in config.GROUP_PREFIXES.items():
        if _prefix_match(title, token):
            return {"columns": list(columns), "display": title}

    # 4./5. person aliases and names: removed from the displayed title
    for token, column in config.PERSON_ALIASES.items():
        match = _prefix_match(title, token)
        if match:
            display = title[match.end():].strip(" -:,") or title
            return {"columns": [column], "display": display}
    for person in persons:
        match = _prefix_match(title, person)
        if match:
            display = title[match.end():].strip(" -:,") or title
            return {"columns": [person], "display": display}

    # 6. default column
    return {"columns": [config.DEFAULT_COLUMN], "display": title}
