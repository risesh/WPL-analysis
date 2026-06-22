import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_clean_data

st.set_page_config(page_title="WPL Dashboard", layout="wide", page_icon="🏏")


# ── Data ──────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading match data…")
def get_data():
    return load_clean_data()

matches_df, deliveries_df, player_map = get_data()


@st.cache_data(show_spinner=False)
def load_auction_map():
    """Returns {abbrev: {auction_season_int: {price_lakh, status, team}}}."""
    base = os.path.dirname(os.path.abspath(__file__))
    nm_path = os.path.join(base, "player_name_map.csv")
    au_path = os.path.join(base, "wpl_auction_data.csv")
    if not os.path.exists(nm_path) or not os.path.exists(au_path):
        return {}

    nm = pd.read_csv(nm_path)
    au = pd.read_csv(au_path)
    abbrev_to_auction = dict(zip(nm["abbrev"], nm["auction_name"]))

    sold = au[au["status"].isin(["sold", "retained"]) & au["price_lakh"].notna()]
    auction_by_name: dict = {}
    for _, row in sold.iterrows():
        name = row["player_name"]
        season = int(row["season"])
        auction_by_name.setdefault(name, {})[season] = {
            "price_lakh": float(row["price_lakh"]),
            "status": row["status"],
            "team": row["team"],
        }

    return {
        abbrev: auction_by_name[auction_name]
        for abbrev, auction_name in abbrev_to_auction.items()
        if auction_name in auction_by_name
    }

auction_map = load_auction_map()


def _to_auction_season(wpl_season):
    """'2022/23' → 2023  (WPL seasons run in the second calendar year)."""
    return int(str(wpl_season).split("/")[0]) + 1

def fmt_price(lakhs):
    if lakhs >= 100:
        return f"₹{lakhs / 100:.1f} Cr"
    return f"₹{int(lakhs)}L"

def player_earnings(abbrev, sel_seasons):
    """Return (total_str, latest_str, latest_auction_season) for the sidebar selection."""
    data = auction_map.get(abbrev, {})
    auction_seasons = {_to_auction_season(s) for s in sel_seasons}
    relevant = {s: v for s, v in data.items() if s in auction_seasons}
    if not relevant:
        return None, None, None
    total = sum(v["price_lakh"] for v in relevant.values())
    latest_s = max(relevant.keys())
    return fmt_price(total), fmt_price(relevant[latest_s]["price_lakh"]), latest_s


# ── Name helpers ──────────────────────────────────────────────────────────────

def full(abbrev):
    """Abbreviated name → full name (falls back to abbrev if not found)."""
    return player_map.get(abbrev, {}).get("full_name", abbrev) or abbrev

def player_image(abbrev):
    return player_map.get(abbrev, {}).get("image_url")

def map_names(df, cols):
    """Return a copy of df with the given player-name columns mapped to full names."""
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].map(full)
    return out

def _wrap(text, width=15):
    words = str(text).split()
    lines, line, n = [], [], 0
    for w in words:
        if n + len(w) > width and line:
            lines.append(" ".join(line))
            line, n = [w], len(w)
        else:
            line.append(w)
            n += len(w) + (1 if line else 0)
    if line:
        lines.append(" ".join(line))
    return "<br>".join(lines)

def _shorten(name):
    """Reduce to first + last name and always split onto two lines with <br>."""
    parts = str(name).split()
    if len(parts) == 1:
        return name
    return f"{parts[0]}<br>{parts[-1]}"

def wrap_col(df, col, width=15, shorten=False):
    """Wrap long x-axis labels with <br> so they stack instead of rotating.
    Pass shorten=True for player name columns to always show first/last on two lines."""
    out = df.copy()
    if col in out.columns:
        out[col] = out[col].astype(str).map(
            _shorten if shorten else lambda t: _wrap(t, width)
        )
    return out


# ── Stat helpers ──────────────────────────────────────────────────────────────

def batter_summary(player, df):
    b = df[df["batter"] == player]
    runs = int(b["runs_batter"].sum())
    balls = int((~b["is_wide"]).sum())
    dismissals = int((df["player_out"] == player).sum())
    return {
        "matches": b["match_id"].nunique(),
        "runs": runs, "balls": balls, "dismissals": dismissals,
        "sr": round(runs / balls * 100, 1) if balls else 0,
        "avg": round(runs / dismissals, 1) if dismissals else "—",
        "fours": int((b["runs_batter"] == 4).sum()),
        "sixes": int((b["runs_batter"] == 6).sum()),
    }

def bowler_summary(player, df):
    b = df[df["bowler"] == player]
    wickets = int(b[b["is_wicket"] & (b["wicket_kind"] != "run out")].shape[0])
    legal = int(b["is_legal"].sum())
    runs = int(b["runs_total"].sum())
    overs = legal / 6
    return {
        "matches": b["match_id"].nunique(),
        "wickets": wickets, "legal_balls": legal, "runs_conceded": runs,
        "economy": round(runs / overs, 2) if overs else 0,
        "avg": round(runs / wickets, 1) if wickets else "—",
        "sr": round(legal / wickets, 1) if wickets else "—",
        "wides": int(b["is_wide"].sum()),
        "noballs": int(b["is_noball"].sum()),
    }


# ── Team colours ──────────────────────────────────────────────────────────────

TEAM_COLORS = {
    "Gujarat Giants":               "#F26522",  # orange
    "Royal Challengers Bangalore":  "#CC0000",  # red
    "Mumbai Indians":               "#004BA0",  # blue
    "UP Warriorz":                  "#F5C518",  # yellow
    "Delhi Capitals":               "#17B3DE",  # light blue
}


# ── Bar chart helper ──────────────────────────────────────────────────────────

def _bar(*args, **kwargs):
    """px.bar wrapper that adds data labels to every bar chart.
    Stacked bars get centred inside labels; all others get outside labels."""
    kwargs.setdefault("text_auto", True)
    fig = px.bar(*args, **kwargs)
    if kwargs.get("barmode") == "stack":
        fig.update_traces(textposition="inside", insidetextanchor="middle", textfont_size=11)
    else:
        fig.update_traces(textposition="outside", cliponaxis=False, textfont_size=11)
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

page = st.sidebar.radio("Navigate", ["Overall Analysis", "Batter Comparison", "Bowler Comparison", "Batter Deep Dive", "Bowler Deep Dive"], label_visibility="collapsed")
st.sidebar.divider()
seasons = sorted(matches_df["season"].unique())
sel_seasons = st.sidebar.multiselect("Filter by Season", seasons, default=seasons)

mf = matches_df[matches_df["season"].isin(sel_seasons)]
df = deliveries_df[deliveries_df["season"].isin(sel_seasons)]


# ═══════════════════════════════════════════════════════════════════════════════
# OVERALL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Overall Analysis":
    st.title("WPL — Overall Analysis")

    # Season champion cards — always show last 4 seasons, unaffected by season filter
    last4_seasons = sorted(matches_df["season"].unique())[-4:]
    champ_cols = st.columns(4)
    for col, season in zip(champ_cols, last4_seasons):
        season_mf = matches_df[matches_df["season"] == season].sort_values("date")
        playoffs = season_mf[season_mf["match_number"].isna()]
        if not playoffs.empty and playoffs.iloc[-1]["winner"]:
            champ = playoffs.iloc[-1]["winner"]
            played = season_mf[(season_mf["team1"] == champ) | (season_mf["team2"] == champ)]
            wins = int((played["winner"] == champ).sum())
            losses = int((played["winner"] != champ).sum())
            color = TEAM_COLORS.get(champ, "#ffffff")
            col.markdown(
                f'<p style="font-size:0.85rem;color:rgba(250,250,250,0.6);margin-bottom:0.1rem;">{season} Champion</p>'
                f'<p style="font-size:1.6rem;font-weight:700;color:{color};margin:0;line-height:1.2;">{champ}</p>'
                f'<p style="font-size:0.85rem;color:#21c354;margin-top:0.25rem;">↑ W{wins} – L{losses}</p>',
                unsafe_allow_html=True,
            )

    st.divider()

    t_venue, t_team, t_upsets, t_extras = st.tabs(
        ["Venue", "Teams & Seasons", "Upsets & Close Finishes", "Extras Leaders"]
    )

    # ── Venue tab ─────────────────────────────────────────────────────────────
    with t_venue:
        wick = df[df["is_wicket"] & df["wicket_kind"].notna()]
        d_counts = wick.groupby(["venue", "wicket_kind"]).size().reset_index(name="n")
        d_counts["pct"] = (
            d_counts["n"] / d_counts.groupby("venue")["n"].transform("sum") * 100
        ).round(1)
        pivot = d_counts.pivot(index="wicket_kind", columns="venue", values="pct").fillna(0)
        pivot.index.name = "Dismissal Type"
        pivot.columns.name = None

        def _short_venue(v):
            name, *rest = v.rsplit(",", 1)
            name, city = name.strip(), rest[0].strip() if rest else ""
            if "Ekana" in name:
                return f"Ekana Stadium, {city}"
            if "DY Patil" in name or "Dr DY" in name:
                return f"DY Patil, {city}"
            return name

        pivot.columns = [_short_venue(c) for c in pivot.columns]

        # Normalise each column independently so every stadium gets its own gradient
        pivot_norm = pivot.apply(
            lambda col: (col - col.min()) / (col.max() - col.min())
            if col.max() != col.min() else pd.Series(0.0, index=col.index)
        )
        fig_heat = go.Figure(go.Heatmap(
            z=pivot_norm.values,
            x=pivot_norm.columns.tolist(),
            y=pivot_norm.index.tolist(),
            text=pivot.values,
            texttemplate="%{text:.1f}",
            textfont=dict(size=13),
            colorscale="YlOrRd",
            showscale=False,
            xgap=2,
            ygap=2,
        ))
        fig_heat.update_layout(
            title="Dismissal Type % by Venue",
            xaxis=dict(title="", side="top"),
            yaxis=dict(title="", autorange="reversed"),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        inn_scores = df.groupby(["match_id", "venue", "innings"])["runs_total"].sum().reset_index()
        avg_inn = inn_scores.groupby(["venue", "innings"])["runs_total"].mean().round(1).reset_index()
        avg_inn["innings"] = avg_inn["innings"].map({1: "1st Innings", 2: "2nd Innings"})
        fig2 = _bar(wrap_col(avg_inn, "venue"), x="venue", y="runs_total", color="innings", barmode="group",
                      title="Avg Score by Venue & Innings",
                      labels={"venue": "", "runs_total": "Avg Runs", "innings": "Innings"})
        fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
        st.plotly_chart(fig2, width="stretch")

        venues = sorted(df["venue"].dropna().unique())
        sel_venue = st.selectbox("Select Venue", ["All"] + venues)
        vdf = df if sel_venue == "All" else df[df["venue"] == sel_venue]
        vmf = mf if sel_venue == "All" else mf[mf["match_id"].isin(vdf["match_id"].unique())]
        venue_label = "All Venues" if sel_venue == "All" else sel_venue

        with st.container(border=True):
            vc1, vc2 = st.columns(2)
            with vc1:
                td = vmf[vmf["winner"].notna()].copy()
                td["toss_won_match"] = td["toss_winner"] == td["winner"]
                ts = td.groupby(["toss_decision", "toss_won_match"]).size().reset_index(name="count")
                ts["toss_won_match"] = ts["toss_won_match"].map({True: "Won Match", False: "Lost Match"})
                fig_toss = _bar(ts, x="toss_decision", y="count", color="toss_won_match", barmode="group",
                                title="Toss Impact by Decision",
                                labels={"toss_decision": "Decision", "count": "Matches", "toss_won_match": "Result"})
                st.plotly_chart(fig_toss, width="stretch")

            vc3, vc4 = st.columns(2)
            with vc3:
                fig_runs = px.histogram(vmf[vmf["win_by_runs"].notna()], x="win_by_runs", nbins=20,
                                        title="Wins by Runs — Margin Distribution",
                                        labels={"win_by_runs": "Winning Margin (runs)"})
                st.plotly_chart(fig_runs, width="stretch")
            with vc4:
                fig_wkts = px.histogram(vmf[vmf["win_by_wickets"].notna()], x="win_by_wickets", nbins=10,
                                        title="Wins by Wickets — Margin Distribution",
                                        labels={"win_by_wickets": "Winning Margin (wickets)"})
                st.plotly_chart(fig_wkts, width="stretch")

            st.subheader(f"Top Batters / Bowlers at {venue_label}")
            max_matches = int(vdf["match_id"].nunique()) or 1

            c1, c2 = st.columns(2)
            with c1:
                bat_metric = st.radio("Batter metric", ["Runs", "Strike Rate", "Average"],
                                      horizontal=True, key="bat_venue_metric", label_visibility="collapsed")
                min_bat_m = st.slider("Min matches (batters)", 0, max_matches, 1,
                                      key="bat_venue_min_matches")
                bt = vdf.groupby("batter").agg(
                    runs=("runs_batter", "sum"),
                    balls=("is_wide", lambda x: (~x).sum()),
                ).reset_index()
                d_v = (vdf[vdf["is_wicket"] & vdf["player_out"].notna()]
                       .groupby("player_out").size().reset_index(name="dismissals")
                       .rename(columns={"player_out": "batter"}))
                bt = bt.merge(d_v, on="batter", how="left")
                bt["dismissals"] = bt["dismissals"].fillna(0).astype(int)
                bat_matches = vdf.groupby("batter")["match_id"].nunique().reset_index(name="matches")
                bt = bt.merge(bat_matches, on="batter", how="left")
                bt["matches"] = bt["matches"].fillna(0).astype(int)
                bt = bt[bt["balls"] >= 12].copy()
                bt = bt[bt["matches"] >= min_bat_m]
                bt["sr"]  = (bt["runs"] / bt["balls"] * 100).round(1)
                bt["avg"] = (bt["runs"] / bt["dismissals"].replace(0, float("nan"))).round(1)

                if bat_metric == "Runs":
                    y_col, y_label = "runs", "Runs"
                    bt_plot = bt.sort_values("runs", ascending=False).head(12)
                elif bat_metric == "Strike Rate":
                    y_col, y_label = "sr", "Strike Rate"
                    bt_plot = bt.sort_values("sr", ascending=False).head(12)
                else:
                    y_col, y_label = "avg", "Average"
                    bt_plot = bt.dropna(subset=["avg"]).sort_values("avg", ascending=False).head(12)

                bt_plot = wrap_col(map_names(bt_plot, ["batter"]), "batter", shorten=True)
                fig3 = _bar(bt_plot, x="batter", y=y_col,
                            title=f"Top Batters at {venue_label} — {y_label}",
                            labels={"batter": "", y_col: y_label})
                fig3.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
                st.plotly_chart(fig3, width="stretch")

            with c2:
                bowl_metric = st.radio("Bowler metric", ["Economy", "Strike Rate", "Average"],
                                       horizontal=True, key="bowl_venue_metric", label_visibility="collapsed")
                min_bow_m = st.slider("Min matches (bowlers)", 0, max_matches, 1,
                                      key="bowl_venue_min_matches")
                bw = vdf.groupby("bowler").agg(
                    runs=("runs_total", "sum"),
                    balls=("is_legal", "sum"),
                ).reset_index()
                wk_v = (vdf[vdf["is_wicket"] & (vdf["wicket_kind"] != "run out")]
                        .groupby("bowler").size().reset_index(name="wickets"))
                bw = bw.merge(wk_v, on="bowler", how="left")
                bw["wickets"] = bw["wickets"].fillna(0).astype(int)
                bow_matches = vdf.groupby("bowler")["match_id"].nunique().reset_index(name="matches")
                bw = bw.merge(bow_matches, on="bowler", how="left")
                bw["matches"] = bw["matches"].fillna(0).astype(int)
                bw = bw[bw["balls"] >= 12].copy()
                bw = bw[bw["matches"] >= min_bow_m]
                bw["economy"] = (bw["runs"] / (bw["balls"] / 6)).round(2)
                bw["sr"]  = (bw["balls"] / bw["wickets"].replace(0, float("nan"))).round(1)
                bw["avg"] = (bw["runs"] / bw["wickets"].replace(0, float("nan"))).round(1)

                if bowl_metric == "Economy":
                    y_col, y_label = "economy", "Economy"
                    bw_plot = bw.sort_values("economy").head(12)
                elif bowl_metric == "Strike Rate":
                    y_col, y_label = "sr", "Bowling SR"
                    bw_plot = bw.dropna(subset=["sr"]).sort_values("sr").head(12)
                else:
                    y_col, y_label = "avg", "Bowling Average"
                    bw_plot = bw.dropna(subset=["avg"]).sort_values("avg").head(12)

                bw_plot = wrap_col(map_names(bw_plot, ["bowler"]), "bowler", shorten=True)
                fig4 = _bar(bw_plot, x="bowler", y=y_col,
                            title=f"Top Bowlers at {venue_label} — {y_label}",
                            labels={"bowler": "", y_col: y_label})
                fig4.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
                st.plotly_chart(fig4, width="stretch")

    # ── Teams & Seasons tab ───────────────────────────────────────────────────
    with t_team:
        wins = mf[mf["winner"].notna()].groupby(["season", "winner"]).size().reset_index(name="wins")
        played = pd.concat([
            mf[["season", "team1"]].rename(columns={"team1": "team"}),
            mf[["season", "team2"]].rename(columns={"team2": "team"}),
        ]).groupby(["season", "team"]).size().reset_index(name="played")
        rec = wins.merge(played, left_on=["season", "winner"], right_on=["season", "team"])
        rec["win_pct"] = (rec["wins"] / rec["played"] * 100).round(1)
        fig = _bar(rec, x="season", y="win_pct", color="team", barmode="group",
                     color_discrete_map=TEAM_COLORS,
                     title="Win % per Team per Season",
                     labels={"season": "Season", "win_pct": "Win %", "team": "Team"})
        st.plotly_chart(fig, width="stretch")

        st.subheader("Player of the Match Leaderboard")
        pom = (
            mf["player_of_match"].str.split(", ").explode()
            .value_counts().head(15).reset_index()
        )
        pom.columns = ["player", "awards"]
        pom = wrap_col(map_names(pom, ["player"]), "player", shorten=True)
        fig5 = _bar(pom, x="player", y="awards",
                      labels={"player": "", "awards": "Awards"},
                      title="Top Player of the Match Winners")
        fig5.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
        st.plotly_chart(fig5, width="stretch")

    # ── Upsets tab ────────────────────────────────────────────────────────────
    with t_upsets:
        st.caption(
            "**Upset definition:** a match played after every team has faced every other team "
            "at least once (first round-robin complete), where the team ranked lower by wins "
            "at that point in the season won. Matches where both teams had equal wins are excluded."
        )

        def _compute_upsets(completed):
            from itertools import combinations
            rows = []
            for season, sdf in completed.groupby("season"):
                sdf = sdf.sort_values(["date", "match_number"]).reset_index(drop=True)
                teams = sorted(set(sdf["team1"]) | set(sdf["team2"]))
                all_pairs = {frozenset([a, b]) for a, b in combinations(teams, 2)}
                pairs_seen = set()
                cum_wins = {t: 0 for t in teams}
                rr_done = False
                for _, row in sdf.iterrows():
                    t1, t2, winner = row["team1"], row["team2"], row["winner"]
                    w1, w2 = cum_wins[t1], cum_wins[t2]
                    was_rr_done = rr_done
                    pairs_seen.add(frozenset([t1, t2]))
                    cum_wins[winner] += 1
                    if not rr_done and pairs_seen >= all_pairs:
                        rr_done = True
                    if was_rr_done and w1 != w2:
                        if (winner == t1 and w1 < w2) or (winner == t2 and w2 < w1):
                            loser = t2 if winner == t1 else t1
                            rows.append({
                                "date": row["date"], "season": season,
                                "winner": winner, "loser": loser,
                                "winner_wins": w1 if winner == t1 else w2,
                                "loser_wins": w2 if winner == t1 else w1,
                                "win_by_runs": row["win_by_runs"],
                                "win_by_wickets": row["win_by_wickets"],
                            })
            return pd.DataFrame(rows)

        upsets = _compute_upsets(mf[mf["winner"].notna()])

        close = mf[
            (mf["win_by_runs"] <= 7) | (mf["win_by_wickets"] <= 2)
        ].copy()
        close["loser"] = close.apply(
            lambda r: r["team2"] if r["winner"] == r["team1"] else r["team1"], axis=1
        )

        def _top(series):
            if series.empty:
                return "—", 0
            vc = series.value_counts()
            return vc.index[0], int(vc.iloc[0])

        upset_team, upset_count = _top(upsets["winner"] if not upsets.empty else pd.Series(dtype=str))
        cf_win_team, cf_win_count = _top(close["winner"].dropna())
        cf_loss_team, cf_loss_count = _top(close["loser"].dropna())

        m1, m2, m3 = st.columns(3)
        m1.metric("Most Upset Wins", upset_team, f"{upset_count} upsets")
        m2.metric("Most Close Finish Wins", cf_win_team, f"{cf_win_count} wins")
        m3.metric("Most Close Finish Losses", cf_loss_team, f"-{cf_loss_count} losses")

        st.subheader("Upsets")
        st.dataframe(upsets.reset_index(drop=True), width="stretch")

        st.subheader("Close Finishes (≤7 runs or ≤2 wickets)")
        st.dataframe(
            close.sort_values("date")[
                ["date", "season", "team1", "team2", "winner", "win_by_runs", "win_by_wickets"]
            ].reset_index(drop=True),
            width="stretch",
        )

    # ── Extras tab ────────────────────────────────────────────────────────────
    with t_extras:
        ext = df.groupby("bowler").agg(
            wides=("is_wide", "sum"),
            noballs=("is_noball", "sum"),
            balls=("is_legal", "sum"),
        ).reset_index()
        ext["extras"] = ext["wides"] + ext["noballs"]
        ext["extras_per_over"] = (ext["extras"] / (ext["balls"] / 6)).round(2)
        ext = ext[ext["balls"] >= 30].sort_values("extras", ascending=False)

        col1, col2 = st.columns(2)
        with col1:
            top15 = ext.head(15).copy()
            top15["full_name"] = top15["bowler"].map(full)
            plot15 = wrap_col(map_names(top15, ["bowler"]), "bowler", shorten=True)
            fig = _bar(plot15, x="bowler", y=["wides", "noballs"], barmode="stack",
                         title="Most Extras Given (min 30 legal balls)",
                         labels={"bowler": "", "value": "Count", "variable": "Type"})
            fig.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            for trace in fig.data:
                if trace.name == "wides":
                    trace.customdata = top15[["noballs", "extras", "full_name"]].values
                    trace.hovertemplate = (
                        "<b>%{customdata[2]}</b><br>"
                        "Wides: %{y}<br>No Balls: %{customdata[0]}<br>"
                        "Total Extras: %{customdata[1]}<extra></extra>"
                    )
                elif trace.name == "noballs":
                    trace.customdata = top15[["wides", "extras", "full_name"]].values
                    trace.hovertemplate = (
                        "<b>%{customdata[2]}</b><br>"
                        "Wides: %{customdata[0]}<br>No Balls: %{y}<br>"
                        "Total Extras: %{customdata[1]}<extra></extra>"
                    )
            st.plotly_chart(fig, width="stretch")
        with col2:
            fig2 = _bar(wrap_col(map_names(ext.sort_values("extras_per_over", ascending=False).head(15), ["bowler"]), "bowler", shorten=True),
                          x="bowler", y="extras_per_over",
                          title="Extras per Over",
                          labels={"bowler": "", "extras_per_over": "Extras / Over"})
            fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig2, width="stretch")


# ═══════════════════════════════════════════════════════════════════════════════
# BATTER DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Batter Deep Dive":
    batters = sorted(df["batter"].unique(), key=full)
    top_scorer = df.groupby("batter")["runs_batter"].sum().idxmax()
    default_batter = batters.index(top_scorer) if top_scorer in batters else 0

    hdr = st.columns([5, 1])
    with hdr[0]:
        sel = st.selectbox("Select Batter", batters, index=default_batter, format_func=full)
    with hdr[1]:
        img = player_image(sel)
        if img:
            st.image(img, width=179)

    stats = batter_summary(sel, df)
    st.title(full(sel))
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Matches", stats["matches"])
    m2.metric("Runs", stats["runs"])
    m3.metric("Balls Faced", stats["balls"])
    m4.metric("Strike Rate", stats["sr"])
    m5.metric("Average", stats["avg"])
    m6.metric("4s / 6s", f"{stats['fours']} / {stats['sixes']}")

    total_str, latest_str, latest_s = player_earnings(sel, sel_seasons)
    if total_str:
        st.subheader("Contract Value")
        ec1, ec2, *_ = st.columns(6)
        ec1.metric("Total Earnings", total_str)
        ec2.metric(f"Latest Contract ({latest_s})", latest_str)
    st.divider()

    bd = df[df["batter"] == sel]
    dismissed = df[df["player_out"] == sel]

    t_weak, t_strength, t_runs, t_phase, t_venue, t_runout = st.tabs(
        ["Weaknesses", "Strengths", "Run Distribution", "Phase Breakdown",
         "Venue Performance", "Run Outs"]
    )

    # ── Weaknesses ────────────────────────────────────────────────────────────
    with t_weak:
        c1, c2 = st.columns(2)
        with c1:
            dkind = dismissed["wicket_kind"].value_counts().reset_index()
            dkind.columns = ["kind", "count"]
            fig = px.pie(dkind, names="kind", values="count", title="How They Get Out")
            st.plotly_chart(fig, width="stretch")
        with c2:
            top_b = dismissed["bowler"].value_counts().head(10).reset_index()
            top_b.columns = ["bowler", "dismissals"]
            fig2 = _bar(wrap_col(map_names(top_b, ["bowler"]), "bowler", shorten=True), x="bowler", y="dismissals",
                          title="Bowlers Who Dismissed Them Most",
                          labels={"bowler": "", "dismissals": "Dismissals"})
            fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig2, width="stretch")

        opp_opts_b = ["All teams"] + sorted(bd["bowling_team"].dropna().unique())
        opp_sel_b = st.selectbox("Filter by opposition", opp_opts_b, key="batter_opp_filter")
        bd_mu = bd if opp_sel_b == "All teams" else bd[bd["bowling_team"] == opp_sel_b]
        dis_mu = dismissed if opp_sel_b == "All teams" else dismissed[dismissed["bowling_team"] == opp_sel_b]

        mu = bd_mu.groupby("bowler").agg(
            runs=("runs_batter", "sum"),
            balls=("is_wide", lambda x: (~x).sum()),
        ).reset_index()
        d_by_b = dis_mu.groupby("bowler").size().reset_index(name="dismissals")
        mu = mu.merge(d_by_b, on="bowler", how="left")
        mu["dismissals"] = mu["dismissals"].fillna(0).astype(int)
        mu["avg"] = (mu["runs"] / mu["dismissals"].replace(0, float("nan"))).round(1)
        mu["sr"] = (mu["runs"] / mu["balls"] * 100).round(1)
        mu = mu[mu["balls"] >= 6].sort_values("sr")
        st.subheader("Bowler Matchup (min 6 balls faced) — sorted by Strike Rate")
        st.dataframe(map_names(mu, ["bowler"]).reset_index(drop=True), width="stretch")

    # ── Strengths ─────────────────────────────────────────────────────────────
    with t_strength:
        c1, c2 = st.columns(2)
        with c1:
            dom = bd.groupby("bowler").agg(
                runs=("runs_batter", "sum"),
                balls=("is_wide", lambda x: (~x).sum()),
            ).reset_index()
            dom = dom[dom["balls"] >= 6].copy()
            dom["sr"] = (dom["runs"] / dom["balls"] * 100).round(1)
            dom = wrap_col(map_names(dom.sort_values("sr", ascending=False).head(12), ["bowler"]), "bowler", shorten=True)
            fig = _bar(dom, x="bowler", y="sr", color="runs",
                         color_continuous_scale="Greens",
                         title="Bowlers They Dominate (highest SR, min 6 balls)",
                         labels={"bowler": "", "sr": "Strike Rate", "runs": "Runs"})
            fig.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig, width="stretch")
        with c2:
            vst = bd.groupby("venue").agg(
                runs=("runs_batter", "sum"),
                balls=("is_wide", lambda x: (~x).sum()),
            ).reset_index()
            vst = vst[vst["balls"] >= 12].copy()
            vst["sr"] = (vst["runs"] / vst["balls"] * 100).round(1)
            fig2 = _bar(wrap_col(vst.sort_values("sr", ascending=False), "venue"), x="venue", y="sr",
                          color="runs", color_continuous_scale="Greens",
                          title="Best Venues by Strike Rate (min 12 balls)",
                          labels={"venue": "", "sr": "Strike Rate", "runs": "Runs"})
            fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig2, width="stretch")

    # ── Run Distribution ──────────────────────────────────────────────────────
    with t_runs:
        c1, c2 = st.columns([2, 1])
        with c1:
            rd = bd["runs_batter"].value_counts().sort_index().reset_index()
            rd.columns = ["runs", "count"]
            fig = _bar(rd, x="runs", y="count", title="Runs Per Ball Distribution",
                         labels={"runs": "Runs on Ball", "count": "Count"})
            st.plotly_chart(fig, width="stretch")
        with c2:
            total_legal = int((~bd["is_wide"]).sum())
            dot = int((bd["runs_batter"] == 0).sum())
            bnd = int(bd["runs_batter"].isin([4, 6]).sum())
            st.metric("Dot Ball %", f"{round(dot/total_legal*100,1) if total_legal else 0}%")
            st.metric("Boundary %", f"{round(bnd/total_legal*100,1) if total_legal else 0}%")
            st.metric("Fours", stats["fours"])
            st.metric("Sixes", stats["sixes"])

    # ── Phase Breakdown ───────────────────────────────────────────────────────
    with t_phase:
        ph = bd.groupby("phase", observed=True).agg(
            runs=("runs_batter", "sum"),
            balls=("is_wide", lambda x: (~x).sum()),
        ).reset_index()
        ph["sr"] = (ph["runs"] / ph["balls"] * 100).round(1)
        c1, c2 = st.columns(2)
        with c1:
            fig = _bar(ph, x="phase", y="runs", title="Runs by Phase",
                         labels={"phase": "", "runs": "Runs"})
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig2 = _bar(ph, x="phase", y="sr", color="sr",
                          color_continuous_scale="RdYlGn",
                          title="Strike Rate by Phase",
                          labels={"phase": "", "sr": "Strike Rate"})
            st.plotly_chart(fig2, width="stretch")

    # ── Venue Performance ─────────────────────────────────────────────────────
    with t_venue:
        vst = bd.groupby("venue").agg(
            runs=("runs_batter", "sum"),
            balls=("is_wide", lambda x: (~x).sum()),
        ).reset_index()
        vst = vst[vst["balls"] >= 6].copy()
        vst["sr"] = (vst["runs"] / vst["balls"] * 100).round(1)
        fig = _bar(wrap_col(vst.sort_values("runs", ascending=False), "venue"), x="venue", y="runs",
                     color="sr", color_continuous_scale="RdYlGn",
                     title="Runs by Venue (colour = Strike Rate)",
                     labels={"venue": "", "runs": "Runs", "sr": "SR"})
        fig.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
        st.plotly_chart(fig, width="stretch")

    # ── Run Outs ──────────────────────────────────────────────────────────────
    with t_runout:
        ro_s = df[
            (df["player_out"] == sel) & (df["wicket_kind"] == "run out") &
            (df["batter"] == sel)
        ]
        ro_ns = df[
            (df["player_out"] == sel) & (df["wicket_kind"] == "run out") &
            (df["non_striker"] == sel)
        ]
        c1, c2 = st.columns(2)
        c1.metric("Run Outs as Striker", len(ro_s))
        c2.metric("Run Outs as Non-Striker", len(ro_ns))
        if len(ro_s) + len(ro_ns) > 0:
            all_ro = pd.concat([ro_s.assign(role="Striker"), ro_ns.assign(role="Non-Striker")])
            st.dataframe(
                all_ro[["date", "batting_team", "bowling_team", "over", "ball", "bowler", "role"]]
                .reset_index(drop=True),
                width="stretch",
            )
        else:
            st.info(f"No run outs recorded for {full(sel)} in selected seasons.")


# ═══════════════════════════════════════════════════════════════════════════════
# BOWLER DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Bowler Deep Dive":
    bowlers = sorted(df["bowler"].unique(), key=full)
    top_wicket_taker = (
        df[df["is_wicket"] & (df["wicket_kind"] != "run out")]
        .groupby("bowler")["is_wicket"].sum()
        .idxmax()
    )
    default_bowler = bowlers.index(top_wicket_taker) if top_wicket_taker in bowlers else 0

    hdr = st.columns([5, 1])
    with hdr[0]:
        sel = st.selectbox("Select Bowler", bowlers, index=default_bowler, format_func=full)
    with hdr[1]:
        img = player_image(sel)
        if img:
            st.image(img, width=179)

    stats = bowler_summary(sel, df)
    st.title(full(sel))
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Matches", stats["matches"])
    m2.metric("Wickets", stats["wickets"])
    m3.metric("Economy", stats["economy"])
    m4.metric("Average", stats["avg"])
    m5.metric("Bowling SR", stats["sr"])
    m6.metric("Extras (W / NB)", f"{stats['wides']} / {stats['noballs']}")

    total_str, latest_str, latest_s = player_earnings(sel, sel_seasons)
    if total_str:
        st.subheader("Contract Value")
        ec1, ec2, *_ = st.columns(6)
        ec1.metric("Total Earnings", total_str)
        ec2.metric(f"Latest Contract ({latest_s})", latest_str)
    st.divider()

    bw = df[df["bowler"] == sel]
    wick_del = bw[bw["is_wicket"] & (bw["wicket_kind"] != "run out")]

    # Pre-compute batter matchup used across tabs
    bv = bw.groupby("batter").agg(
        runs=("runs_batter", "sum"),
        balls=("is_wide", lambda x: (~x).sum()),
    ).reset_index()
    d_by_b = wick_del.groupby("batter").size().reset_index(name="dismissals")
    bv = bv.merge(d_by_b, on="batter", how="left")
    bv["dismissals"] = bv["dismissals"].fillna(0).astype(int)
    bv = bv[bv["balls"] >= 6].copy()
    bv["avg"] = (bv["runs"] / bv["dismissals"].replace(0, float("nan"))).round(1)
    bv["sr"] = (bv["runs"] / bv["balls"] * 100).round(1)

    t_match, t_strength, t_extras, t_phase, t_venue = st.tabs(
        ["Wickets & Matchups", "Strengths", "Extras Analysis",
         "Phase Breakdown", "Venue Performance"]
    )

    # ── Wickets & Matchups ────────────────────────────────────────────────────
    with t_match:
        c1, c2 = st.columns(2)
        with c1:
            dkind = wick_del["wicket_kind"].value_counts().reset_index()
            dkind.columns = ["kind", "count"]
            fig = px.pie(dkind, names="kind", values="count", title="Wicket Types")
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig2 = _bar(wrap_col(map_names(bv.sort_values("runs", ascending=False).head(12), ["batter"]), "batter", shorten=True),
                          x="batter", y="runs", color="sr",
                          color_continuous_scale="Reds",
                          title="Batters Who Score Most Against Them",
                          labels={"batter": "", "runs": "Runs", "sr": "SR"})
            fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig2, width="stretch")

        opp_opts_bw = ["All teams"] + sorted(bw["batting_team"].dropna().unique())
        opp_sel_bw = st.selectbox("Filter by opposition", opp_opts_bw, key="bowler_opp_filter")
        if opp_sel_bw == "All teams":
            bv_table = bv
        else:
            bw_opp = bw[bw["batting_team"] == opp_sel_bw]
            wd_opp = wick_del[wick_del["batting_team"] == opp_sel_bw]
            bv_table = bw_opp.groupby("batter").agg(
                runs=("runs_batter", "sum"),
                balls=("is_wide", lambda x: (~x).sum()),
            ).reset_index()
            d_by_b_opp = wd_opp.groupby("batter").size().reset_index(name="dismissals")
            bv_table = bv_table.merge(d_by_b_opp, on="batter", how="left")
            bv_table["dismissals"] = bv_table["dismissals"].fillna(0).astype(int)
            bv_table = bv_table[bv_table["balls"] >= 6].copy()
            bv_table["avg"] = (bv_table["runs"] / bv_table["dismissals"].replace(0, float("nan"))).round(1)
            bv_table["sr"] = (bv_table["runs"] / bv_table["balls"] * 100).round(1)
        st.subheader("Batter Matchup (min 6 balls)")
        st.dataframe(map_names(bv_table.sort_values("runs", ascending=False), ["batter"]).reset_index(drop=True),
                     width="stretch")

    # ── Strengths ─────────────────────────────────────────────────────────────
    with t_strength:
        c1, c2 = st.columns(2)
        with c1:
            top_d = wick_del["batter"].value_counts().head(10).reset_index()
            top_d.columns = ["batter", "dismissals"]
            fig = _bar(wrap_col(map_names(top_d, ["batter"]), "batter", shorten=True), x="batter", y="dismissals",
                         color="dismissals", color_continuous_scale="Greens",
                         title="Batters Dismissed Most",
                         labels={"batter": "", "dismissals": "Dismissals"})
            fig.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig, width="stretch")
        with c2:
            v_s = bw.groupby("venue").agg(
                runs=("runs_total", "sum"), balls=("is_legal", "sum"), wickets=("is_wicket", "sum")
            ).reset_index()
            v_s = v_s[v_s["balls"] >= 12].copy()
            v_s["economy"] = (v_s["runs"] / (v_s["balls"] / 6)).round(2)
            fig2 = _bar(wrap_col(v_s.sort_values("economy"), "venue"), x="venue", y="economy",
                          color="wickets", title="Best Venues by Economy (min 12 balls)",
                          labels={"venue": "", "economy": "Economy", "wickets": "Wickets"})
            fig2.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
            st.plotly_chart(fig2, width="stretch")

        st.subheader("Runs Conceded Per Ball Distribution")
        rc = bw["runs_total"].value_counts().sort_index().reset_index()
        rc.columns = ["runs", "count"]
        fig3 = _bar(rc, x="runs", y="count",
                      labels={"runs": "Runs Conceded on Ball", "count": "Count"})
        st.plotly_chart(fig3, width="stretch")

    # ── Extras ────────────────────────────────────────────────────────────────
    with t_extras:
        total = len(bw)
        c1, c2, c3 = st.columns(3)
        c1.metric("Wides", stats["wides"],
                  delta=f"{round(stats['wides']/total*100,1) if total else 0}% of balls")
        c2.metric("No Balls", stats["noballs"])
        c3.metric("Total Extras", stats["wides"] + stats["noballs"])

        ext_over = bw.groupby("over").agg(
            wides=("is_wide", "sum"), noballs=("is_noball", "sum")
        ).reset_index()
        fig = _bar(ext_over, x="over", y=["wides", "noballs"], barmode="group",
                     title="Extras by Over",
                     labels={"over": "Over", "value": "Count", "variable": "Type"})
        st.plotly_chart(fig, width="stretch")

    # ── Phase Breakdown ───────────────────────────────────────────────────────
    with t_phase:
        ph = bw.groupby("phase", observed=True).agg(
            runs=("runs_total", "sum"),
            wickets=("is_wicket", "sum"),
            balls=("is_legal", "sum"),
        ).reset_index()
        ph["economy"] = (ph["runs"] / (ph["balls"] / 6)).round(2)
        c1, c2 = st.columns(2)
        with c1:
            fig = _bar(ph, x="phase", y="economy", color="economy",
                         color_continuous_scale="RdYlGn_r",
                         title="Economy by Phase",
                         labels={"phase": "", "economy": "Economy"})
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig2 = _bar(ph, x="phase", y="wickets", title="Wickets by Phase",
                          labels={"phase": "", "wickets": "Wickets"})
            st.plotly_chart(fig2, width="stretch")

    # ── Venue Performance ─────────────────────────────────────────────────────
    with t_venue:
        v_s = bw.groupby("venue").agg(
            runs=("runs_total", "sum"), balls=("is_legal", "sum"), wickets=("is_wicket", "sum")
        ).reset_index()
        v_s = v_s[v_s["balls"] >= 6].copy()
        v_s["economy"] = (v_s["runs"] / (v_s["balls"] / 6)).round(2)
        fig = _bar(wrap_col(v_s.sort_values("economy"), "venue"), x="venue", y="economy",
                     color="wickets", title="Economy by Venue (colour = Wickets)",
                     labels={"venue": "", "economy": "Economy", "wickets": "Wickets"})
        fig.update_xaxes(tickangle=0, automargin=True, tickfont=dict(size=13))
        st.plotly_chart(fig, width="stretch")


# ═══════════════════════════════════════════════════════════════════════════════
# BATTER COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Batter Comparison":
    st.title("Batter Comparison")

    all_venues = sorted(df["venue"].dropna().unique())
    all_teams  = sorted(set(mf["team1"]) | set(mf["team2"]))

    f1, f2 = st.columns(2)
    sel_venue = f1.selectbox("Stadium", ["All"] + all_venues)
    sel_opp   = f2.selectbox("Opponent", ["All"] + all_teams)

    bdf = df.copy()
    if sel_venue != "All":
        bdf = bdf[bdf["venue"] == sel_venue]
    if sel_opp != "All":
        bdf = bdf[bdf["bowling_team"] == sel_opp]

    agg = bdf.groupby("batter").agg(
        runs=("runs_batter", "sum"),
        balls=("is_wide", lambda x: (~x).sum()),
        matches=("match_id", "nunique"),
        team=("batting_team", lambda x: x.mode()[0]),
    ).reset_index()

    d_counts = (
        bdf[bdf["is_wicket"] & bdf["player_out"].notna()]
        .groupby("player_out").size()
        .reset_index(name="dismissals")
        .rename(columns={"player_out": "batter"})
    )
    agg = agg.merge(d_counts, on="batter", how="left")
    agg["dismissals"] = agg["dismissals"].fillna(0).astype(int)

    max_balls       = int(agg["balls"].max())   if not agg.empty else 50
    max_runs_val    = int(agg["runs"].max())     if not agg.empty else 50
    max_matches_val = int(agg["matches"].max())  if not agg.empty else 1

    s1, s2, s3 = st.columns(3)
    min_balls       = s1.slider("Min balls faced",  0, max_balls,       min(50, max_balls),       step=1, key="bc_min_balls")
    min_runs_val    = s2.slider("Min runs scored",  0, max_runs_val,    min(50, max_runs_val),    step=1, key="bc_min_runs")
    min_matches_val = s3.slider("Min matches",      0, max_matches_val, min(1,  max_matches_val), step=1, key="bc_min_matches")

    agg = agg[
        (agg["balls"]   >= min_balls) &
        (agg["runs"]    >= min_runs_val) &
        (agg["matches"] >= min_matches_val)
    ].copy()
    agg["sr"]  = (agg["runs"] / agg["balls"] * 100).round(1)
    agg["avg"] = (agg["runs"] / agg["dismissals"].replace(0, float("nan"))).round(1)
    agg["name"] = agg["batter"].map(full)
    plot = agg.dropna(subset=["avg"])

    fig = px.scatter(
        plot,
        x="sr", y="avg",
        size="runs", size_max=45,
        color="team",
        color_discrete_map=TEAM_COLORS,
        hover_name="name",
        hover_data={"sr": ":.1f", "avg": ":.1f", "runs": True,
                    "balls": True, "dismissals": True, "team": False, "batter": False, "name": False},
        custom_data=["batter"],
        title="Batter Comparison — Strike Rate vs Average (bubble size = runs)",
        labels={"sr": "Strike Rate", "avg": "Average", "runs": "Runs", "team": "Team"},
    )
    mean_sr  = plot["sr"].mean()
    mean_avg = plot["avg"].mean()
    fig.add_vline(x=mean_sr,  line_dash="dot", line_color="gray", opacity=0.5,
                  annotation_text=f"Avg SR {mean_sr:.0f}", annotation_position="top right")
    fig.add_hline(y=mean_avg, line_dash="dot", line_color="gray", opacity=0.5,
                  annotation_text=f"Avg {mean_avg:.0f}", annotation_position="bottom right")

    sr_pad  = max((plot["sr"].max()  - plot["sr"].min())  * 0.12, 5)
    avg_pad = max((plot["avg"].max() - plot["avg"].min()) * 0.12, 2)
    sr_lo,  sr_hi  = max(0, plot["sr"].min()  - sr_pad),  plot["sr"].max()  + sr_pad
    avg_lo, avg_hi = max(0, plot["avg"].min() - avg_pad), plot["avg"].max() + avg_pad
    # Top-right = best batters (high SR + high avg) → green
    fig.add_shape(type="rect", x0=mean_sr, x1=sr_hi,  y0=mean_avg, y1=avg_hi,
                  fillcolor="green", opacity=0.08, line_width=0, layer="below")
    # Bottom-left = worst batters (low SR + low avg) → red
    fig.add_shape(type="rect", x0=sr_lo,   x1=mean_sr, y0=avg_lo,  y1=mean_avg,
                  fillcolor="red",   opacity=0.08, line_width=0, layer="below")
    fig.update_xaxes(range=[sr_lo,  sr_hi])
    fig.update_yaxes(range=[avg_lo, avg_hi])
    fig.update_layout(height=620)

    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="batter_scatter")

    selected_batters = []
    if event and event.selection and event.selection.points:
        for pt in event.selection.points:
            cd = pt.get("customdata")
            if cd:
                selected_batters.append(cd[0])

    table_data = plot[plot["batter"].isin(selected_batters)] if selected_batters else plot

    st.caption(f"Showing {len(plot)} batters — min {min_balls} balls, {min_runs_val} runs, {min_matches_val} match(es). "
               f"Dotted lines = group averages for selected filters.")
    if selected_batters:
        st.info(f"Filtered to: **{', '.join(full(b) for b in selected_batters)}** — click empty area to clear")
    with st.expander("Full data table", expanded=bool(selected_batters)):
        st.dataframe(
            map_names(table_data[["batter", "team", "matches", "runs", "balls",
                            "dismissals", "avg", "sr"]].sort_values("runs", ascending=False),
                      ["batter"]).reset_index(drop=True),
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BOWLER COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Bowler Comparison":
    st.title("Bowler Comparison")

    all_venues = sorted(df["venue"].dropna().unique())
    all_teams  = sorted(set(mf["team1"]) | set(mf["team2"]))

    f1, f2 = st.columns(2)
    sel_venue = f1.selectbox("Stadium", ["All"] + all_venues)
    sel_opp   = f2.selectbox("Opponent", ["All"] + all_teams)

    bdf = df.copy()
    if sel_venue != "All":
        bdf = bdf[bdf["venue"] == sel_venue]
    if sel_opp != "All":
        bdf = bdf[bdf["batting_team"] == sel_opp]

    agg = bdf.groupby("bowler").agg(
        runs=("runs_total", "sum"),
        legal=("is_legal", "sum"),
        matches=("match_id", "nunique"),
        team=("bowling_team", lambda x: x.mode()[0]),
    ).reset_index()

    wkts = (
        bdf[bdf["is_wicket"] & (bdf["wicket_kind"] != "run out")]
        .groupby("bowler").size()
        .reset_index(name="wickets")
    )
    agg = agg.merge(wkts, on="bowler", how="left")
    agg["wickets"] = agg["wickets"].fillna(0).astype(int)

    max_wkts    = int(agg["wickets"].max()) if not agg.empty else 1
    max_matches = int(agg["matches"].max()) if not agg.empty else 1
    max_balls   = int(agg["legal"].max())   if not agg.empty else 6

    s1, s2, s3 = st.columns(3)
    min_wkts    = s1.slider("Min wickets",      0, max_wkts,    min(3,  max_wkts),    step=1, key="bwc_min_wkts")
    min_matches = s2.slider("Min matches",      0, max_matches, min(3,  max_matches), step=1, key="bwc_min_matches")
    min_balls   = s3.slider("Min balls bowled", 0, max_balls,   min(30, max_balls),   step=1, key="bwc_min_balls")

    agg = agg[
        (agg["wickets"] >= min_wkts) &
        (agg["matches"] >= min_matches) &
        (agg["legal"]   >= min_balls)
    ].copy()
    agg["bowl_avg"] = (agg["runs"] / agg["wickets"]).round(1)
    agg["bowl_sr"]  = (agg["legal"] / agg["wickets"]).round(1)
    agg["economy"]  = (agg["runs"] / (agg["legal"] / 6)).round(2)
    agg["name"] = agg["bowler"].map(full)

    fig = px.scatter(
        agg,
        x="bowl_sr", y="bowl_avg",
        size="wickets", size_max=45,
        color="team",
        color_discrete_map=TEAM_COLORS,
        hover_name="name",
        hover_data={"bowl_sr": ":.1f", "bowl_avg": ":.1f", "wickets": True,
                    "runs": True, "matches": True, "team": False, "bowler": False, "name": False},
        custom_data=["bowler"],
        title="Bowler Comparison — Bowling SR vs Average (bubble size = wickets)",
        labels={"bowl_sr": "Bowling Strike Rate", "bowl_avg": "Bowling Average",
                "wickets": "Wickets", "team": "Team"},
    )
    mean_sr  = agg["bowl_sr"].mean()
    mean_avg = agg["bowl_avg"].mean()
    fig.add_vline(x=mean_sr,  line_dash="dot", line_color="gray", opacity=0.5,
                  annotation_text=f"Avg SR {mean_sr:.0f}", annotation_position="top right")
    fig.add_hline(y=mean_avg, line_dash="dot", line_color="gray", opacity=0.5,
                  annotation_text=f"Avg {mean_avg:.0f}", annotation_position="top left")

    sr_pad  = max((agg["bowl_sr"].max()  - agg["bowl_sr"].min())  * 0.12, 3)
    avg_pad = max((agg["bowl_avg"].max() - agg["bowl_avg"].min()) * 0.12, 2)
    sr_lo,  sr_hi  = max(0, agg["bowl_sr"].min()  - sr_pad),  agg["bowl_sr"].max()  + sr_pad
    avg_lo, avg_hi = max(0, agg["bowl_avg"].min() - avg_pad), agg["bowl_avg"].max() + avg_pad
    # Bottom-left = best bowlers (low bowling SR + low avg) → green
    fig.add_shape(type="rect", x0=sr_lo,   x1=mean_sr, y0=avg_lo,  y1=mean_avg,
                  fillcolor="green", opacity=0.08, line_width=0, layer="below")
    # Top-right = worst bowlers (high bowling SR + high avg) → red
    fig.add_shape(type="rect", x0=mean_sr, x1=sr_hi,  y0=mean_avg, y1=avg_hi,
                  fillcolor="red",   opacity=0.08, line_width=0, layer="below")
    fig.update_xaxes(range=[sr_lo,  sr_hi])
    fig.update_yaxes(range=[avg_lo, avg_hi])
    fig.update_layout(height=620)

    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="bowler_scatter")

    selected_bowlers = []
    if event and event.selection and event.selection.points:
        for pt in event.selection.points:
            cd = pt.get("customdata")
            if cd:
                selected_bowlers.append(cd[0])

    table_data = agg[agg["bowler"].isin(selected_bowlers)] if selected_bowlers else agg

    st.caption(f"Showing {len(agg)} bowlers "
               f"(min {min_wkts} wkts · min {min_matches} matches · min {min_balls} balls bowled). "
               f"Bottom-left quadrant = best performers. Dotted lines = group averages.")
    if selected_bowlers:
        st.info(f"Filtered to: **{', '.join(full(b) for b in selected_bowlers)}** — click empty area to clear")
    with st.expander("Full data table", expanded=bool(selected_bowlers)):
        st.dataframe(
            map_names(table_data[["bowler", "team", "matches", "wickets", "runs",
                               "legal", "economy", "bowl_avg", "bowl_sr"]]
                      .sort_values("wickets", ascending=False),
                      ["bowler"])
            .rename(columns={
                "bowler":   "Bowler",
                "team":     "Team",
                "matches":  "Matches",
                "wickets":  "Wickets",
                "runs":     "Runs Conceded",
                "legal":    "Balls Bowled",
                "economy":  "Economy",
                "bowl_avg": "Bowl Avg",
                "bowl_sr":  "Bowl SR",
            })
            .reset_index(drop=True),
            use_container_width=True,
        )
