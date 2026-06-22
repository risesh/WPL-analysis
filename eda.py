import pandas as pd
from load_data import load_all_matches

# ── Parse raw data into DataFrames ────────────────────────────────────────────

all_matches = load_all_matches()

matches = []
deliveries = []

for match_id, data in all_matches:
    info = data["info"]
    teams = info["teams"]
    date = info["dates"][0]

    outcome = info.get("outcome", {})
    winner = outcome.get("winner")
    win_by_runs = outcome.get("by", {}).get("runs")
    win_by_wickets = outcome.get("by", {}).get("wickets")

    matches.append({
        "match_id": match_id,
        "date": date,
        "season": info.get("season"),
        "match_number": info.get("event", {}).get("match_number"),
        "venue": info.get("venue"),
        "city": info.get("city"),
        "team1": teams[0],
        "team2": teams[1],
        "toss_winner": info.get("toss", {}).get("winner"),
        "toss_decision": info.get("toss", {}).get("decision"),
        "winner": winner,
        "win_by_runs": win_by_runs,
        "win_by_wickets": win_by_wickets,
        "player_of_match": ", ".join(info.get("player_of_match", [])),
    })

    for innings_idx, innings in enumerate(data.get("innings", [])):
        batting_team = innings["team"]
        bowling_team = teams[1] if batting_team == teams[0] else teams[0]

        for over_data in innings.get("overs", []):
            for delivery in over_data.get("deliveries", []):
                runs = delivery["runs"]
                extras = delivery.get("extras", {})
                wickets = delivery.get("wickets", [])

                deliveries.append({
                    "match_id": match_id,
                    "date": date,
                    "season": info.get("season"),
                    "innings": innings_idx + 1,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "over": over_data["over"],
                    "ball": delivery.get("actual_delivery"),
                    "batter": delivery["batter"],
                    "bowler": delivery["bowler"],
                    "non_striker": delivery["non_striker"],
                    "runs_batter": runs["batter"],
                    "runs_extras": runs["extras"],
                    "runs_total": runs["total"],
                    "is_wide": "wides" in extras,
                    "is_noball": "noballs" in extras,
                    "is_legal": "wides" not in extras and "noballs" not in extras,
                    "is_wicket": len(wickets) > 0,
                    "wicket_kind": wickets[0].get("kind") if wickets else None,
                    "player_out": wickets[0].get("player_out") if wickets else None,
                })

matches_df = pd.DataFrame(matches)
matches_df["date"] = pd.to_datetime(matches_df["date"])

deliveries_df = pd.DataFrame(deliveries)
deliveries_df["date"] = pd.to_datetime(deliveries_df["date"])


# ── Cleaning ──────────────────────────────────────────────────────────────────

# Standardize RCB name across all team columns
for col in ["team1", "team2", "toss_winner", "winner"]:
    matches_df[col] = matches_df[col].str.replace(
        "Royal Challengers Bengaluru", "Royal Challengers Bangalore", regex=False
    )
for col in ["batting_team", "bowling_team"]:
    deliveries_df[col] = deliveries_df[col].str.replace(
        "Royal Challengers Bengaluru", "Royal Challengers Bangalore", regex=False
    )

# Show duplicate delivery rows before dropping
dupe_mask = deliveries_df.duplicated(keep=False)
print("\n=== DUPLICATE DELIVERY ROWS ===")
print(deliveries_df[dupe_mask].sort_values(["match_id", "innings", "over", "ball"]).to_string())

# Drop duplicate delivery rows
deliveries_df = deliveries_df.drop_duplicates().reset_index(drop=True)


# ── 1. Basic shape ────────────────────────────────────────────────────────────

print("=== MATCHES ===")
print(f"Shape: {matches_df.shape}")
print(matches_df.dtypes)
print(matches_df.head())

print("\n=== DELIVERIES ===")
print(f"Shape: {deliveries_df.shape}")
print(deliveries_df.dtypes)
print(deliveries_df.head())


# ── 2. Missing values ─────────────────────────────────────────────────────────

print("\n=== MISSING VALUES — MATCHES ===")
print(matches_df.isnull().sum())

print("\n=== MISSING VALUES — DELIVERIES ===")
print(deliveries_df.isnull().sum())


# ── 3. Duplicates ─────────────────────────────────────────────────────────────

print("\n=== DUPLICATES ===")
print(f"Duplicate match rows:    {matches_df.duplicated().sum()}")
print(f"Duplicate delivery rows: {deliveries_df.duplicated().sum()}")


# ── 4. Distributions ──────────────────────────────────────────────────────────

print("\n=== MATCHES PER SEASON ===")
print(matches_df["season"].value_counts().sort_index())

print("\n=== MATCHES PER TEAM ===")
team_counts = pd.concat([matches_df["team1"], matches_df["team2"]]).value_counts()
print(team_counts)

print("\n=== TOSS DECISIONS ===")
print(matches_df["toss_decision"].value_counts())

print("\n=== WINS PER TEAM ===")
print(matches_df["winner"].value_counts())

print("\n=== WICKET TYPES ===")
print(deliveries_df["wicket_kind"].value_counts())

print("\n=== RUNS PER BALL DISTRIBUTION ===")
print(deliveries_df["runs_batter"].value_counts().sort_index())


# ── 5. No-result matches (both win columns null) ───────────────────────────────

no_result = matches_df[matches_df["win_by_runs"].isna() & matches_df["win_by_wickets"].isna()]
print("\n=== MATCHES WITH NO RESULT/SUPER OVER ===")
print(no_result[["match_id", "date", "season", "team1", "team2", "winner"]])


# ── 6. Matches missing match_number (likely playoffs) ─────────────────────────

no_match_num = matches_df[matches_df["match_number"].isna()]
print("\n=== MATCHES WITHOUT MATCH NUMBER ===")
print(no_match_num[["match_id", "date", "season", "team1", "team2", "winner"]])


# ── 7. Unusual deliveries ─────────────────────────────────────────────────────

five_run_balls = deliveries_df[deliveries_df["runs_batter"] == 5]
print(f"\n=== 5-RUN BATTER DELIVERIES ({len(five_run_balls)}) ===")
print(five_run_balls[["match_id", "date", "batter", "bowler", "runs_batter", "runs_extras", "runs_total", "is_wide", "is_noball"]])