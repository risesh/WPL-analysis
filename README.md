# WPL Analytics Dashboard

An interactive cricket analytics dashboard for the **Women's Premier League (WPL)**, built with Python and Streamlit. Explore batting and bowling performance, team trends, upsets, auction data, and more — across all four WPL seasons (2022/23 through 2025/26).

## Try it out

> **[Launch the Dashboard →](https://wpl-analysis.streamlit.app/)**

No installation needed — runs entirely in your browser.

---

## What's inside

**Overall Analysis**
- Season champions with win-loss records
- Venue breakdown: dismissal types, economy rates, top performers
- Team & season trends: runs, wickets, win margins
- Upsets & close finishes: matches where the lower-ranked team won after the round-robin, and last-ball/last-over thrillers
- Extras leaders: most wides and no-balls given per bowler

**Batter Comparison**
- Interactive scatter plot — batting average vs strike rate
- Filter by venue, opposition team, batting phase (powerplay / middle / death)
- Bubble size = runs scored; colour-coded by franchise

**Bowler Comparison**
- Bowling average vs strike rate scatter plot
- Filter by venue, opposition, min wickets / min matches / min balls bowled

**Batter Deep Dive**
- Full profile: photo, country, playing role, batting & bowling style
- Contract value and total earnings across selected seasons
- Weaknesses tab: dismissal types, bowler matchup table (filterable by opposition)
- Strengths tab: best matchups by strike rate
- Run distribution, phase breakdown, venue performance, run-out analysis

**Bowler Deep Dive**
- Full profile with contract value
- Wicket types, batter matchup table (filterable by opposition)
- Extras analysis by over, phase breakdown, venue economy

---

## Data sources

| Source | What it provides |
|---|---|
| [Cricsheet](https://cricsheet.org) | Ball-by-ball match data (JSON), 88 matches, 20 000+ deliveries |
| [Kaggle — Ultimate Ball-by-Ball Dataset](https://www.kaggle.com/datasets/ariadaikalam/the-ultimate-ball-by-ball-cricket-dataset) | Player full names, photos, countries, batting/bowling styles |
| WPL auction records (manually compiled) | Contract values per season (2023–2026) |

---

## Run locally

```bash
git clone https://github.com/your-username/wpl-analysis.git
cd wpl-analysis
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard.py
```

The `wpl_json/` match data and `player_profiles.json` are already included in the repo — no extra downloads needed to run the dashboard.

### Optional: rebuild player profiles

If you want to refresh player metadata from the Kaggle dataset (requires a Kaggle API key):

```bash
python kaggle_data.py      # downloads ~4 GB, extracts women's profiles → player_profiles.json
python sync_names.py       # syncs name changes across datasets, rebuilds player_name_map.csv
```

---

## Project structure

```
dashboard.py          # Streamlit app — all pages and charts
data.py               # Data loading, cleaning, player map construction
load_data.py          # Reads wpl_json/ match files
player_cache.py       # Builds abbrev-name → profile mapping
kaggle_data.py        # One-time script: downloads Kaggle data, builds player_profiles.json
sync_names.py         # Syncs player name changes across datasets
player_profiles.json  # Pre-built player profile cache (photo URLs, countries, styles)
player_name_map.csv   # Maps Cricsheet names → auction names
wpl_auction_data.csv  # Contract prices per player per season
wpl_json/             # 89 Cricsheet match JSON files
requirements.txt
```