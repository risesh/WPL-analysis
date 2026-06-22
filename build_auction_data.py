"""
Parses raw WPL auction text files → wpl_auction_data.csv in a single pass.

Input files (Auction data/):
  2023 all players.txt          ESPN Cricinfo article (narrative sentences)
  2024 sold and unsold players.txt  India TV News (list format, no base prices)
  2025 all players.txt          Cricinfo structured table (tab-separated)
  2026 all players.txt          Cricinfo structured table (tab-separated)

Output:
  wpl_auction_data.csv          player_name, team, season, status,
                                 base_price_lakh, price_lakh, role

Name normalisation is applied inline (via AUCTION_NAME_MAP from names.py)
so the output CSV always uses canonical player names.

Run order in the pipeline:
  1. kaggle_data.py  (builds player_profiles.json)
  2. THIS SCRIPT     (builds wpl_auction_data.csv)
  3. sync_names.py   (syncs match files + generates player_name_map.csv)
"""

import csv
import os
import re
from collections import Counter
from difflib import get_close_matches

from names import AUCTION_NAME_MAP, norm_name

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Auction data")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wpl_auction_data.csv")

TEAM_MAP = {
    "royal challengers bangalore": "RCB",
    "royal challengers bengaluru": "RCB",
    "rcb": "RCB", "rcb-w": "RCB",
    "mumbai indians": "MI", "mi": "MI", "mi-w": "MI",
    "gujarat giants": "GG", "gg": "GG", "gg-w": "GG",
    "delhi capitals": "DC", "dc": "DC", "dc-w": "DC",
    "up warriorz": "UPW", "upw": "UPW", "upw-w": "UPW",
}

STATUS_PRIORITY = {"sold": 0, "retained": 1, "unsold": 2}


def normalize_team(s: str) -> str | None:
    k = s.strip().lower()
    return TEAM_MAP.get(k, None if k in ("-", "") else s.strip())


def parse_price_str(s: str) -> float | None:
    if not s:
        return None
    s = re.sub(r"(?i)inr\s*", "", s).strip().lower()
    m = re.search(r"([\d.]+)\s*crore", s)
    if m:
        return round(float(m.group(1)) * 100, 2)
    m = re.search(r"([\d.]+)\s*lakh", s)
    if m:
        return round(float(m.group(1)), 2)
    return None


def sanity_check_price(p: float | None) -> float | None:
    """WPL max price is ~350 lakh. If parsed value > 1000, the unit was stated wrong."""
    return round(p / 100, 2) if p and p > 1000 else p


def is_portrait_line(line: str) -> bool:
    low = line.lower()
    return "portrait" in low or "headshot" in low


def canonical_name(raw: str) -> str:
    return AUCTION_NAME_MAP.get(raw.strip(), raw.strip())


# ── 2023 ──────────────────────────────────────────────────────────────────────

def parse_2023() -> list[dict]:
    fp = os.path.join(BASE_DIR, "2023 all players.txt")
    with open(fp) as f:
        lines = [l.rstrip("\n") for l in f]

    records = []
    mode = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "2023 wpl auction sold" in line.lower():
            mode = "sold"
            continue
        if "2023 wpl auction unsold" in line.lower():
            mode = "unsold"
            continue

        if mode == "sold":
            m = re.match(
                r"(.+?)\s*\(Base price INR\s*([\d.]+\s*(?:crore|lakh))\)\s*"
                r"sold to\s*(.+?)\s*for\s*(?:INR\s*)?([\d.]+\s*(?:crore|lakh))",
                line, re.IGNORECASE,
            )
            if m:
                records.append({
                    "player_name": canonical_name(m.group(1)),
                    "team": normalize_team(m.group(3).strip()),
                    "season": 2023, "status": "sold",
                    "base_price_lakh": parse_price_str(m.group(2)),
                    "price_lakh": sanity_check_price(parse_price_str(m.group(4))),
                    "role": None,
                })
                continue

            # Simran Shaikh has no base price in the source
            m = re.match(
                r"(.+?)\s+sold to\s+(.+?)\s+for\s+(?:INR\s*)?([\d.]+\s*(?:crore|lakh))",
                line, re.IGNORECASE,
            )
            if m:
                records.append({
                    "player_name": canonical_name(m.group(1)),
                    "team": normalize_team(m.group(2).strip()),
                    "season": 2023, "status": "sold",
                    "base_price_lakh": None,
                    "price_lakh": sanity_check_price(parse_price_str(m.group(3))),
                    "role": None,
                })

        elif mode == "unsold":
            m = re.match(
                r"(.+?)\s*\(Base price INR\s*([\d.]+\s*(?:crore|lakh))\)",
                line, re.IGNORECASE,
            )
            if m:
                records.append({
                    "player_name": canonical_name(m.group(1)),
                    "team": None,
                    "season": 2023, "status": "unsold",
                    "base_price_lakh": parse_price_str(m.group(2)),
                    "price_lakh": None,
                    "role": None,
                })

    return records


# ── 2024 ──────────────────────────────────────────────────────────────────────

def parse_2024() -> list[dict]:
    fp = os.path.join(BASE_DIR, "2024 sold and unsold players.txt")
    with open(fp) as f:
        lines = [l.rstrip("\n") for l in f]

    records = []
    mode = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "list of players sold" in line.lower():
            mode = "sold"
            continue
        if "list of unsold players" in line.lower():
            mode = "unsold"
            continue

        if mode == "sold":
            m = re.match(
                r"(.+?)\s*-\s*INR\s*([\d.]+)\s*(Lakh|Crore)\s*\((\w+)\)",
                line, re.IGNORECASE,
            )
            if m:
                val = float(m.group(2))
                unit = m.group(3).lower()
                price = round(val * 100 if unit == "crore" else val, 2)
                records.append({
                    "player_name": canonical_name(m.group(1)),
                    "team": normalize_team(m.group(4)),
                    "season": 2024, "status": "sold",
                    "base_price_lakh": None,
                    "price_lakh": sanity_check_price(price),
                    "role": None,
                })

        elif mode == "unsold":
            name = re.sub(r"\s*\([^)]+\)\s*$", "", line).strip()
            if name:
                records.append({
                    "player_name": canonical_name(name),
                    "team": None,
                    "season": 2024, "status": "unsold",
                    "base_price_lakh": None,
                    "price_lakh": None,
                    "role": None,
                })

    return records


# ── 2025 / 2026 table format ──────────────────────────────────────────────────

def parse_table_file(filepath: str, season: int) -> list[dict]:
    """
    Parse Cricinfo-style tab-separated auction/squad pages.
    Each player block: [portrait line?] → name → [NEW?] → TEAM TYPE BASE SOLD row.
    Players without NEW are retained; those with NEW are newly bought.
    Prices in the source are in crore; multiplied ×100 to store as lakh.
    """
    with open(filepath) as f:
        lines = [l.rstrip("\n") for l in f]

    records = []
    i = 0

    if lines and "Players" in lines[0]:
        i += 1  # skip header row

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or is_portrait_line(stripped):
            i += 1
            continue

        # A pure 4-field tab row without a preceding name is an orphan data line
        if len(line.split("\t")) == 4:
            i += 1
            continue

        player_name = canonical_name(stripped)
        i += 1

        is_new = False
        if i < len(lines) and lines[i].strip() == "NEW":
            is_new = True
            i += 1

        while i < len(lines) and (not lines[i].strip() or is_portrait_line(lines[i])):
            i += 1

        if i < len(lines):
            parts = lines[i].split("\t")
            if len(parts) == 4:
                team_raw, role, base_raw, sold_raw = [p.strip() for p in parts]
                team = normalize_team(team_raw)
                sold_low = sold_raw.lower()

                if sold_low in ("unsold", "tba", ""):
                    status = "unsold"
                    price = None
                else:
                    try:
                        price = round(float(sold_raw) * 100, 2)
                        status = "sold" if is_new else "retained"
                    except ValueError:
                        status = "unsold"
                        price = None

                base = None
                if base_raw and base_raw != "-":
                    try:
                        base = round(float(base_raw) * 100, 2)
                    except ValueError:
                        pass

                records.append({
                    "player_name": player_name,
                    "team": team,
                    "season": season,
                    "status": status,
                    "base_price_lakh": base,
                    "price_lakh": price,
                    "role": role or None,
                })
                i += 1

    return records


# ── Retention 2023 → 2024 ─────────────────────────────────────────────────────

def build_retained_2024(sold_2023: list[dict], all_2024: list[dict]) -> list[dict]:
    """
    The 2024 source only lists players re-auctioned that year.
    Any 2023 sold player absent from the 2024 file was retained at the same price.
    Fuzzy matching (cutoff 0.85) handles minor name variations between source files.
    """
    pool_names = [norm_name(r["player_name"]) for r in all_2024]
    pool_set = set(pool_names)

    retained = []
    for r in sold_2023:
        n = norm_name(r["player_name"])
        if n in pool_set:
            continue
        if get_close_matches(n, pool_names, n=1, cutoff=0.85):
            continue
        retained.append({
            "player_name": r["player_name"],
            "team": r["team"],
            "season": 2024,
            "status": "retained",
            "base_price_lakh": None,
            "price_lakh": r["price_lakh"],
            "role": None,
        })
    return retained


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    After name normalisation, a player may have multiple records for the same season
    (e.g. a retained inference AND a newly auctioned record under a name variant).
    Keep the record with the highest-priority status: sold > retained > unsold.
    """
    from collections import defaultdict
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["player_name"], r["season"])].append(r)

    kept, removed = [], []
    for (_, _), group in groups.items():
        if len(group) == 1:
            kept.extend(group)
            continue
        best_status = min({r["status"] for r in group}, key=lambda s: STATUS_PRIORITY.get(s, 99))
        winners = [r for r in group if r["status"] == best_status]
        losers  = [r for r in group if r["status"] != best_status]
        kept.append(winners[0])
        removed.extend(winners[1:] + losers)

    order = {id(r): i for i, r in enumerate(records)}
    kept.sort(key=lambda r: (r["season"], order.get(id(r), 0)))
    return kept, removed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    r2023 = parse_2023()
    r2024 = parse_2024()
    r2025 = parse_table_file(os.path.join(BASE_DIR, "2025 all players.txt"), 2025)
    r2026 = parse_table_file(os.path.join(BASE_DIR, "2026 all players.txt"), 2026)

    retained_2024 = build_retained_2024(
        sold_2023=[r for r in r2023 if r["status"] == "sold"],
        all_2024=r2024,
    )

    all_records = r2023 + r2024 + retained_2024 + r2025 + r2026
    clean, removed = deduplicate(all_records)

    fieldnames = ["player_name", "team", "season", "status", "base_price_lakh", "price_lakh", "role"]
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in clean:
            writer.writerow({k: rec.get(k, "") or "" for k in fieldnames})

    print(f"Written {len(clean)} records → {OUTPUT_PATH}")
    if removed:
        print(f"Removed {len(removed)} duplicate records (status deduplication):")
        for r in removed:
            print(f"  {r['player_name']:35s} season={r['season']} status={r['status']}")

    print("\nSeason counts:", dict(sorted(Counter(r["season"] for r in clean).items())))
    print("Status counts:", dict(sorted(Counter(r["status"] for r in clean).items())))

    print(f"\n── 2024 retained ({len(retained_2024)} players) ──")
    for r in sorted(retained_2024, key=lambda x: (x["team"] or "", x["player_name"])):
        print(f"  {r['player_name']:30s} {r['team']:4s}  {r['price_lakh']} lakh")

    print("\n── Spot-checks ──")
    checks = {
        "Smriti Mandhana": [2023, 2024, 2025, 2026],
        "Jemimah Rodrigues": [2023, 2024, 2025, 2026],
        "Simran Shaikh": [2023, 2024, 2025, 2026],
        "Annabel Sutherland": [2023, 2024, 2025, 2026],
        "Danni Wyatt-Hodge": [2023, 2024, 2025, 2026],
    }
    for name, seasons in checks.items():
        rows = [r for r in clean if norm_name(r["player_name"]) == norm_name(name)]
        found = {r["season"]: f"{r['team']} {r['status']} {r['price_lakh']}" for r in rows}
        print(f"  {name}:")
        for s in seasons:
            print(f"    {s}: {found.get(s, 'MISSING')}")


if __name__ == "__main__":
    main()