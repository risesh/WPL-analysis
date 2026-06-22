"""
Downloads the "ultimate ball-by-ball cricket dataset" from Kaggle and extracts
enriched player profiles (full name, country, image URL, batting/bowling style,
playing role) keyed by the Cricsheet abbreviated name.

Saves player_profiles.json for use by data.py and dashboard.py.

Run once to build the profile cache; re-run to refresh.

Usage:
    python3 kaggle_data.py

Requires:
    pip install kagglehub pandas
"""

import json
import os
import kagglehub
import pandas as pd

from names import CRICSHEET_ALIASES

DATASET = "ariadaikalam/the-ultimate-ball-by-ball-cricket-dataset"
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_profiles.json")

PLAYER_COLS = {
    "striker": {
        "abbrev": "striker",
        "full_name": "full name_striker",
        "country": "country_striker",
        "image_url": "image url_striker",
        "batting_style": "batting style_striker",
        "bowling_style": "bowling style_striker",
        "playing_role": "playing role_striker",
        "major_teams": "major teams_striker",
    },
    "bowler": {
        "abbrev": "bowler",
        "full_name": "full name_bowler",
        "country": "country_bowler",
        "image_url": "image url_bowler",
        "batting_style": "batting style_bowler",
        "bowling_style": "bowling style_bowler",
        "playing_role": "playing role_bowler",
        "major_teams": "major teams_bowler",
    },
}


READ_COLS = [
    "gender", "event", "striker", "bowler",
    "full name_striker", "country_striker", "image url_striker",
    "batting style_striker", "bowling style_striker",
    "playing role_striker", "major teams_striker",
    "full name_bowler", "country_bowler", "image url_bowler",
    "batting style_bowler", "bowling style_bowler",
    "playing role_bowler", "major teams_bowler",
]

CHUNK_SIZE = 200_000


def main():
    print("Downloading dataset from Kaggle…")
    path = kagglehub.dataset_download(DATASET)
    csv_path = os.path.join(path, "ball_by_ball_data.csv")
    print(f"Reading {csv_path} in chunks (women's matches only)…")

    chunks = []
    total_rows = 0
    kept_rows = 0
    for chunk in pd.read_csv(csv_path, usecols=READ_COLS, chunksize=CHUNK_SIZE, low_memory=False):
        total_rows += len(chunk)
        filtered = chunk[chunk["gender"] == "female"]
        kept_rows += len(filtered)
        if not filtered.empty:
            chunks.append(filtered)
        print(f"  Processed {total_rows:,} rows, kept {kept_rows:,} women's rows…", end="\r")

    print()
    women = pd.concat(chunks, ignore_index=True)
    print(f"Women's cricket rows: {len(women):,}")

    # Show distinct events so we know what's in the data
    print(f"Events: {sorted(women['event'].dropna().unique())}")

    wpl_rows = women[women["event"] == "Women's Premier League"]
    print(f"WPL rows: {len(wpl_rows):,}")

    import math

    def _clean(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return v

    profiles = {}

    for _, cols in PLAYER_COLS.items():
        abbrev_col = cols["abbrev"]
        sub = (
            women[[abbrev_col, cols["full_name"], cols["country"],
                   cols["image_url"], cols["batting_style"],
                   cols["bowling_style"], cols["playing_role"],
                   cols["major_teams"]]]
            .dropna(subset=[abbrev_col, cols["full_name"]])
            .drop_duplicates(subset=[abbrev_col])
            .to_dict("records")
        )
        for rec in sub:
            abbrev = rec[abbrev_col]
            if abbrev in profiles:
                continue
            profiles[abbrev] = {
                "full_name": _clean(rec[cols["full_name"]]),
                "country": _clean(rec[cols["country"]]),
                "image_url": _clean(rec[cols["image_url"]]),
                "batting_style": _clean(rec[cols["batting_style"]]),
                "bowling_style": _clean(rec[cols["bowling_style"]]),
                "playing_role": _clean(rec[cols["playing_role"]]),
                "major_teams": _clean(rec[cols["major_teams"]]),
            }

    # Apply aliases for players whose name changed between datasets
    for new_name, old_name in CRICSHEET_ALIASES.items():
        if new_name not in profiles and old_name in profiles:
            profiles[new_name] = profiles[old_name]

    print(f"\nBuilt profiles for {len(profiles)} unique women cricketers")
    print("Sample entries:")
    for abbrev, p in list(profiles.items())[:5]:
        print(f"  {abbrev!r:20s} -> {p['full_name']!r:30s} ({p['country']}) [{p['playing_role']}]")

    with open(OUT_FILE, "w") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)
    print(f"\nSaved to {OUT_FILE}")


if __name__ == "__main__":
    main()
