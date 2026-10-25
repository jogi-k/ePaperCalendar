"""Family-specific configuration for the ePaper family calendar.

All family-specific rules live here so the rest of the app stays generic and
other families can adapt the tool by editing this one file:

- column names
- group prefixes (kept in the displayed title, expanded to both columns)
- person aliases (removed from the displayed title)
- special prefixes (assigned to a specific person, kept in the title)
- the birthday rule ("<name> hat Geburtstag" -> "GEB <name>", family column)
"""

# Column headers, left to right (the first column of the page is the date column)
COLUMNS = ["Familie", "Laurin", "Milo", "Conny", "Jogi"]

# Fallback column for entries without a clear person or group
DEFAULT_COLUMN = "Familie"

# Leading group tokens -> the columns they expand to (group kept in the title)
GROUP_PREFIXES = {
    "LauMi": ["Laurin", "Milo"],
    "MaPa": ["Conny", "Jogi"],
    "PaMa": ["Conny", "Jogi"],
}

# Leading person aliases -> their column (alias removed from the displayed title)
PERSON_ALIASES = {
    "Mama": "Conny",
    "Papa": "Jogi",
}

# Leading special tokens -> assigned person (token kept in the displayed title)
SPECIAL_PREFIXES = {
    "SSO": "Conny",
    "TG": "Laurin",
    "CH": "Conny",
    "Praxis": "Conny",
    "Turbine": "Jogi",
}

# Birthday rule: "<name> hat Geburtstag" is displayed as "GEB <name>" and always
# placed in the default column, even if the name is a person's name
BIRTHDAY_PATTERN = "hat Geburtstag"
BIRTHDAY_PREFIX = "GEB"
