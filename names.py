"""
Single source of truth for all WPL player name mappings.

Three types of names exist across the datasets:
  - auction_name  : colloquial name used in auction articles (wpl_auction_data.csv)
  - abbrev        : Cricsheet abbreviated name used in match JSONs and player_profiles.json
  - kaggle_abbrev : abbreviated name as it appears in the Kaggle ball-by-ball CSV

This module defines every mapping between these forms so the pipeline scripts
never embed name constants of their own.

Pipeline execution order:
  1. kaggle_data.py       → builds player_profiles.json  (uses CRICSHEET_ALIASES)
  2. build_auction_data.py → builds wpl_auction_data.csv  (uses AUCTION_NAME_MAP)
  3. sync_names.py        → syncs match files + profile keys + generates player_name_map.csv
                            (uses ABBREV_RENAMES, STALE_PROFILE_KEYS, MANUAL_AUCTION_NAMES)
"""

import re


def norm_name(s: str) -> str:
    """Lowercase + collapse whitespace. Used for case/space-insensitive comparisons."""
    return re.sub(r"\s+", " ", s.strip().lower())


# ── Auction name normalisation ────────────────────────────────────────────────
# Maps any variant/typo/old-name that may appear in the raw auction text files
# → the canonical auction name (Cricinfo 2025/26 is authoritative).
# Used by build_auction_data.py when parsing the raw text files.

AUCTION_NAME_MAP: dict[str, str] = {
    # Marriage name changes
    "Danni Wyatt":              "Danni Wyatt-Hodge",
    "Danni Waytt":              "Danni Wyatt-Hodge",   # typo in 2024 source
    "Natalie Sciver-Brunt":     "Nat Sciver-Brunt",
    "Shabnam MD":               "Shabnam Shakil",

    # Preferred / official cricket name
    "Amelia Kerr":              "Melie Kerr",
    "Millicent Illingworth":    "Milly Illingworth",

    # Full name from Cricinfo 2025/26 (older sources used abbreviated forms)
    "D Hemalatha":              "Dayalan Hemalatha",
    "S Meghana":                "Sabbhineni Meghana",
    "Sabbineni Meghana":        "Sabbhineni Meghana",  # spelling error in 2024 source
    "S Yashasri":               "Soppadhandi Yashasri",
    "G Trisha":                 "Gongadi Trisha",
    "G. Trisha":                "Gongadi Trisha",
    "Trisha Poojitha":          "Gongadi Trisha",
    "S Sajana":                 "Sajeevan Sajana",
    "Sajana S":                 "Sajeevan Sajana",
    "Keerthana Balakrishnan":   "Sathyamoorthy Keerthana",

    # Name order corrected to Cricinfo 2025/26 standard
    "Vrinda Dinesh":            "Dinesh Vrinda",

    # Typo / spelling fixes
    "Chole Tryon":              "Chloe Tryon",
    "Asha Shobana":             "Asha Sobhana",
    "Ashwani Kumai":            "Ashwani Kumari",
    "Maia Boucher":             "Maia Bouchier",
    "Raghvi Bisht":             "Raghvi Bist",
    "Jasia Akther":             "Jasia Akhter",
    "Komalpreet Kour":          "Komalpreet Kaur",
    "Sneha Deepti":             "Sneha Deepthi",
}


# ── Cricsheet abbreviated-name renames ───────────────────────────────────────
# Maps an old Cricsheet abbreviated name → the current one, for players whose
# surname changed (e.g. marriage) after some match files were created.
# Applied to player_profiles.json keys and to all wpl_json/ match files by sync_names.py.

ABBREV_RENAMES: dict[str, str] = {
    "DN Wyatt": "DN Wyatt-Hodge",
}

# Stale abbreviated keys to remove from player_profiles.json.
# These exist because the Kaggle dataset was built with an older name;
# after applying CRICSHEET_ALIASES in kaggle_data.py the new key is present,
# but the old key may linger if the profile was already written.
STALE_PROFILE_KEYS: set[str] = {
    "NR Sciver",
}


# ── Abbrev → auction name overrides ──────────────────────────────────────────
# Used by sync_names.py when building player_name_map.csv.
# Needed when fuzzy matching fails because:
#   - Kaggle's full_name diverges too much from the auction colloquial name
#   - No Kaggle profile exists for the player
#   - Kaggle mapped the abbreviation to a different (often male) cricketer
#     of the same initials (e.g. "S Rana" → "Sachin Rana" in men's cricket)

MANUAL_AUCTION_NAMES: dict[str, str] = {
    "NR Sciver-Brunt": "Nat Sciver-Brunt",
    "AB Kaur":          "Amanjot Kaur",
    "DB Sharma":        "Deepti Sharma",
    "GM Harris":        "Grace Harris",
    "LK Bell":          "Lauren Bell",
    "MC Patel":         "Monica Patel",
    "MS Kashyap":       "Mannat Kashyap",
    "RP Yadav":         "Radha Yadav",
    "SJ Bryce":         "Sarah Bryce",
    "SS Pawar":         "Sahana Pawar",
    # Kaggle maps these abbreviations to a male cricketer in the WPL context
    "S Rana":           "Sneh Rana",
    "SR Patil":         "Shreyanka Patil",
    # No Kaggle profile — inferred from team membership in match files
    "A Soni":           "Ayushi Soni",
    "AB Sharma":        "Anushka Sharma",
    "GJ Naik":          "Gautami Naik",
    "NSS Sharma":       "Nandani Sharma",
}


# ── Profile overrides ─────────────────────────────────────────────────────────
# Corrects entries in player_profiles.json for two types of problems:
#   1. Kaggle dataset has the wrong (male) cricketer for this abbreviation —
#      the profile exists but belongs to a different person entirely. We fix
#      the name and null out fields that are definitely wrong.
#   2. The player has no Kaggle profile at all. We insert a minimal entry so
#      the dashboard shows the correct name rather than the abbreviation.
# Applied by sync_names.py's update_profiles().
# Format: {abbrev: {field: value}}. None values clear the existing field.

PROFILE_OVERRIDES: dict[str, dict] = {
    # Wrong male cricketer profiles — Kaggle's metadata lookup collided with
    # a male cricketer of the same abbreviated name in women's match records
    "S Rana": {
        "full_name":     "Sneh Rana",
        "bowling_style": None,   # was "Right arm Medium fast" (Sachin Rana's style)
        "playing_role":  None,   # was "Bowler"
        "major_teams":   None,   # was Haryana/KKR/etc. (men's teams)
        "image_url":     None,   # was a male cricketer's headshot
    },
    "SR Patil": {
        "full_name":     "Shreyanka Patil",
        "bowling_style": None,   # was "Right arm Fast medium" (Sadashiv Patil's style)
        "major_teams":   None,   # was Maharashtra (men's team)
    },
    # Known by cricket name, not legal surname
    "H Kaur":     {"full_name": "Harmanpreet Kaur"},
    # No Kaggle profile — insert minimal entries so the dashboard shows full names
    "A Soni":     {"full_name": "Ayushi Soni"},
    "AB Sharma":  {"full_name": "Anushka Sharma"},
    "GJ Naik":    {"full_name": "Gautami Naik"},
    "NSS Sharma": {"full_name": "Nandani Sharma"},
}


# ── Kaggle dataset aliases ────────────────────────────────────────────────────
# Maps the current Cricsheet abbreviated name → the older name as it appears
# in the Kaggle ball-by-ball CSV. Used by kaggle_data.py so that profile lookups
# work for players who changed their surname between dataset releases.

CRICSHEET_ALIASES: dict[str, str] = {
    "NR Sciver-Brunt": "NR Sciver",
    "DN Wyatt-Hodge":  "DN Wyatt",
}