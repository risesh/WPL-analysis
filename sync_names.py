"""
Syncs Cricsheet abbreviated-name changes across player_profiles.json and
wpl_json/ match files, then generates player_name_map.csv as the join bridge
between all three datasets.

Steps:
  1. player_profiles.json  – rename stale abbreviated keys, remove superseded keys
  2. wpl_json/ match files – replace old abbreviated names everywhere
                             (player lists, delivery batter/bowler/fielder, registry)
  3. player_name_map.csv   – maps abbrev → full_name → auction_name

Run order in the pipeline:
  1. kaggle_data.py        (builds player_profiles.json)
  2. build_auction_data.py (builds wpl_auction_data.csv)
  3. THIS SCRIPT
"""

import csv
import json
import os
from difflib import get_close_matches

from names import (
    ABBREV_RENAMES,
    MANUAL_AUCTION_NAMES,
    PROFILE_OVERRIDES,
    STALE_PROFILE_KEYS,
    norm_name,
)

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILES_PATH = os.path.join(BASE, "player_profiles.json")
MATCH_DIR     = os.path.join(BASE, "wpl_json")
AUCTION_CSV   = os.path.join(BASE, "wpl_auction_data.csv")
MAP_CSV       = os.path.join(BASE, "player_name_map.csv")


# ── 1. Update player_profiles.json ───────────────────────────────────────────

def update_profiles() -> dict:
    with open(PROFILES_PATH) as f:
        profiles = json.load(f)

    changed, removed, overridden = [], [], []

    for old, new in ABBREV_RENAMES.items():
        if old in profiles:
            profiles[new] = profiles.pop(old)
            changed.append(f"  renamed {old!r} → {new!r}")

    for key in STALE_PROFILE_KEYS:
        if key in profiles:
            profiles.pop(key)
            removed.append(f"  removed stale key {key!r}")

    for abbrev, fields in PROFILE_OVERRIDES.items():
        entry = profiles.setdefault(abbrev, {})
        for field, value in fields.items():
            if value is None:
                entry.pop(field, None)
            else:
                entry[field] = value
        overridden.append(f"  patched {abbrev!r}: {list(fields)}")

    with open(PROFILES_PATH, "w") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)

    print("player_profiles.json:")
    for m in changed + removed + overridden:
        print(m)
    if not changed and not removed and not overridden:
        print("  (no changes needed)")

    return profiles


# ── 2. Update wpl_json/ match files ──────────────────────────────────────────

def _replace_in_obj(obj, rename_map: dict):
    """Recursively replace player names in both dict keys and string values."""
    if isinstance(obj, str):
        return rename_map.get(obj, obj)
    if isinstance(obj, list):
        return [_replace_in_obj(v, rename_map) for v in obj]
    if isinstance(obj, dict):
        return {rename_map.get(k, k): _replace_in_obj(v, rename_map) for k, v in obj.items()}
    return obj


def update_match_files() -> None:
    files_changed = []
    for fname in sorted(os.listdir(MATCH_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(MATCH_DIR, fname)
        with open(fpath) as f:
            raw = f.read()

        # Use JSON-encoded form to avoid false positives where old name is a
        # prefix of the new name (e.g. "DN Wyatt" matches inside "DN Wyatt-Hodge")
        if not any(f'"{old}"' in raw for old in ABBREV_RENAMES):
            continue

        with open(fpath) as f:
            match = json.load(f)

        updated = _replace_in_obj(match, ABBREV_RENAMES)

        with open(fpath, "w") as f:
            json.dump(updated, f, separators=(",", ":"))

        files_changed.append(fname)

    print(f"\nwpl_json/ match files updated: {len(files_changed)}")
    for f in files_changed:
        print(f"  {f}")


# ── 3. Build player_name_map.csv ─────────────────────────────────────────────

def build_name_map(profiles: dict) -> None:
    """
    Matches every abbreviated player name found in match JSONs to their
    full name (from player_profiles.json) and their auction name (from
    wpl_auction_data.csv). Matching strategy:
      1. Manual override (MANUAL_AUCTION_NAMES) — highest priority
      2. Exact match on full_name or abbrev
      3. Fuzzy match (cutoff 0.80) on full_name
      4. Last-name token match as a last resort
    """
    with open(AUCTION_CSV) as f:
        auction_rows = list(csv.DictReader(f))
    auction_names = sorted(set(r["player_name"] for r in auction_rows if r["player_name"]))
    auction_norms = {norm_name(n): n for n in auction_names}

    # Collect every abbreviated name that appears in the match files
    match_abbrevs: set[str] = set()
    for fname in os.listdir(MATCH_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(MATCH_DIR, fname)) as f:
            match = json.load(f)
        for _, players in match["info"].get("players", {}).items():
            match_abbrevs.update(players)
        for inning in match.get("innings", []):
            for over in inning.get("overs", []):
                for d in over.get("deliveries", []):
                    match_abbrevs.add(d["batter"])
                    match_abbrevs.add(d["bowler"])
                    for w in d.get("wickets", []):
                        for fi in w.get("fielders", []):
                            match_abbrevs.add(fi.get("name", ""))
    match_abbrevs.discard("")

    rows, unmatched = [], []
    for abbrev in sorted(match_abbrevs):
        if abbrev in MANUAL_AUCTION_NAMES:
            profile = profiles.get(abbrev, {})
            rows.append({
                "abbrev": abbrev,
                "full_name": profile.get("full_name") or abbrev,
                "auction_name": MANUAL_AUCTION_NAMES[abbrev],
            })
            continue

        profile = profiles.get(abbrev, {})
        full_name = profile.get("full_name") or abbrev

        auction_name = (
            auction_norms.get(norm_name(full_name))
            or auction_norms.get(norm_name(abbrev))
        )

        if not auction_name:
            close = get_close_matches(norm_name(full_name), auction_norms.keys(), n=1, cutoff=0.80)
            if close:
                auction_name = auction_norms[close[0]]

        if not auction_name:
            last = norm_name(full_name).split()[-1]
            # Use word-level match, not substring, to avoid "dean" matching "deandra"
            candidates = [n for nn, n in auction_norms.items() if last in nn.split()]
            if len(candidates) == 1:
                auction_name = candidates[0]

        rows.append({
            "abbrev": abbrev,
            "full_name": full_name,
            "auction_name": auction_name or "",
        })
        if not auction_name:
            unmatched.append(abbrev)

    with open(MAP_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["abbrev", "full_name", "auction_name"])
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for r in rows if r["auction_name"])
    print(f"\nplayer_name_map.csv: {matched}/{len(rows)} players matched to auction data")
    if unmatched:
        print(f"  No auction match for ({len(unmatched)}):")
        for n in unmatched:
            print(f"    {n}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    profiles = update_profiles()
    update_match_files()
    build_name_map(profiles)
    print("\nDone.")