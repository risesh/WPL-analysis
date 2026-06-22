import json
import os
import pandas as pd
from load_data import load_all_matches
from player_cache import build_player_map


def load_clean_data():
    all_matches = load_all_matches()

    matches = []
    deliveries = []

    for match_id, data in all_matches:
        info = data["info"]
        teams = info["teams"]
        date = info["dates"][0]
        venue = info.get("venue")

        outcome = info.get("outcome", {})
        winner = outcome.get("winner")
        win_by_runs = outcome.get("by", {}).get("runs")
        win_by_wickets = outcome.get("by", {}).get("wickets")

        matches.append({
            "match_id": match_id,
            "date": date,
            "season": info.get("season"),
            "match_number": info.get("event", {}).get("match_number"),
            "venue": venue,
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
                        "venue": venue,
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

    # Standardize RCB name
    for col in ["team1", "team2", "toss_winner", "winner"]:
        matches_df[col] = matches_df[col].str.replace(
            "Royal Challengers Bengaluru", "Royal Challengers Bangalore", regex=False
        )
    for col in ["batting_team", "bowling_team"]:
        deliveries_df[col] = deliveries_df[col].str.replace(
            "Royal Challengers Bengaluru", "Royal Challengers Bangalore", regex=False
        )

    deliveries_df = deliveries_df.drop_duplicates().reset_index(drop=True)

    deliveries_df["phase"] = pd.cut(
        deliveries_df["over"],
        bins=[-1, 5, 14, 19],
        labels=["Powerplay (0-5)", "Middle (6-14)", "Death (15-19)"],
    )

    all_players = pd.concat([
        deliveries_df["batter"],
        deliveries_df["bowler"],
        deliveries_df["non_striker"],
        deliveries_df["player_out"].dropna(),
        matches_df["player_of_match"].str.split(", ").explode(),
    ]).dropna().unique().tolist()

    kaggle_profiles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_profiles.json")
    kaggle_profiles = {}
    if os.path.exists(kaggle_profiles_path):
        with open(kaggle_profiles_path) as f:
            kaggle_profiles = json.load(f)

    player_map = build_player_map(all_players, kaggle_profiles=kaggle_profiles)

    return matches_df, deliveries_df, player_map
