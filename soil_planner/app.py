"""
Soil Program Planner - single-screen Streamlit dashboard for the Soil Conservation Office.
Leads with the recommendation and the main insights, then the evidence, then the explorer.

Run from the repository root:
    python -m streamlit run soil_planner/app.py

Every number shown here comes from soil_planner/soil_tool.py, the same functions the notebook
notebooks/Soil_Program_Planner.ipynb calls, so the app and the notebook show the same figures.
Nothing is typed in. The extra soil and practice data in the county panel are display only:
they enter no score, ranking or evidence table.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from soil_planner import soil_tool as tool  # noqa: E402

st.set_page_config(page_title="Soil Program Planner — Iowa", layout="wide", initial_sidebar_state="collapsed")


# ----------------------------------------------------------------------------------
# Cached engine calls. Every cached function takes only hashable arguments.
# ----------------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """Iowa corn and soybean rows with the deployment drought penalty (one period, all years)."""
    return tool.compute_penalties(tool.load_iowa_with_lon(), split=False)


@st.cache_data(show_spinner=False)
def load_split() -> pd.DataFrame:
    """Held-out version: normals never cross the train/test boundary."""
    return tool.compute_penalties(load_data(), split=True)


@st.cache_data(show_spinner=False)
def county_stats(crop: str, sev: int) -> pd.DataFrame:
    return tool.county_drought_stats(load_data(), crop, sev)


@st.cache_data(show_spinner=False)
def deployment_scores(crop: str) -> pd.DataFrame:
    return tool.deployment_penalty_scores(load_data(), crop)


@st.cache_data(show_spinner=False)
def priority(crop: str) -> pd.DataFrame:
    return tool.priority_list(deployment_scores(crop))


@st.cache_data(show_spinner=False)
def report_card(fips: str, crop: str, sev: int) -> dict:
    return tool.county_report_card(load_data(), fips, crop, sev)


@st.cache_data(show_spinner=False)
def reasons(fips: str, crop: str) -> list:
    return tool.priority_reasons(load_data(), deployment_scores(crop), fips, crop)


@st.cache_data(show_spinner=False)
def soil_context(fips: str) -> pd.DataFrame:
    return tool.soil_context(load_data(), fips)


@st.cache_data(show_spinner=False)
def practices_context(fips: str) -> pd.DataFrame:
    return tool.practices_context(fips)


@st.cache_data(show_spinner=False)
def ranking_evidence() -> dict:
    return tool.penalty_ranking_results(load_split())


@st.cache_data(show_spinner=False)
def storage_evidence() -> pd.DataFrame:
    table, _ = tool.penalty_storage_results(load_split())
    return table


@st.cache_data(show_spinner=False)
def earlier_storage_evidence() -> pd.DataFrame:
    return tool.storage_effect_results(load_data())


@st.cache_data(show_spinner=False)
def earlier_ranking_evidence() -> dict:
    return tool.ranking_test_results(load_data())


@st.cache_data(show_spinner=False)
def county_index() -> pd.DataFrame:
    """fips <-> county name, sorted by name."""
    return (load_data()[[tool.COL_FIPS, tool.COL_COUNTY]].drop_duplicates(tool.COL_FIPS)
            .sort_values(tool.COL_COUNTY).reset_index(drop=True))


# ----------------------------------------------------------------------------------
# Labels
# ----------------------------------------------------------------------------------
FIRST_YEAR, LAST_YEAR = tool.TRAIN_YEARS.start, tool.TEST_YEARS.stop - 1
ALL_YEARS = f"{FIRST_YEAR}–{LAST_YEAR}"
TRAIN_LABEL = f"{tool.TRAIN_YEARS.start}–{tool.TRAIN_YEARS.stop - 1}"
TEST_LABEL = f"{tool.TEST_YEARS.start}–{tool.TEST_YEARS.stop - 1}"
D2_LABEL = next(k for k, v in tool.DROUGHT_DEFS.items() if v == tool.SEV_D2)
ACCENT, MUTED = "#2F5D3A", "#9e9e9e"

MAP_CAPTIONS = {
    "drought_penalty_pct": "The drought penalty is how much more a county lost in its drought years than in its own "
                           "nearby normal years, measured against the rest of Iowa in the same year; a more negative "
                           "value means drought hurt that county more.",
    "drought_share": "Drought frequency is the share of the county's reported years that counted as drought years "
                     "under the selected definition.",
    "drought_loss_pct": "Drought-year loss is the county's average yield shortfall in its drought years, relative to "
                        "its own long-run trend.",
    tool.COL_AWS: "Soil water storage is the plant-available water the top 100 cm of the county's soil can hold; "
                  "it does not change over time.",
}

PRIORITY_COLUMNS = {
    "rank": "rank", tool.COL_FIPS: "FIPS", tool.COL_COUNTY: "county", "penalty_score": "drought penalty (%)",
    "drought_years_used": "drought years behind score", "confidence": "confidence",
    "drought_years_total": "drought years (all)", tool.COL_AWS: "soil water storage (mm)",
}

ROW_COLUMNS = {
    tool.COL_YEAR: "year", tool.COL_YIELD: "yield (bu/acre)", tool.COL_REL_STATE: "yield vs state median (%)",
    "normal_baseline": "normal baseline vs state (%)", "drought_penalty": "drought penalty (%)",
    tool.COL_ANOM: "yield anomaly vs own trend (%)", "severity_label": "worst drought category",
    "in_drought": "drought year", tool.COL_WEEKS_D2: "weeks at D2+", tool.COL_DSCI: "mean drought index (0-500)",
    tool.COL_PRECIP_ANOM: "season rain vs normal (%)", tool.COL_HEAT: "days at or above 35 °C",
}


def _flat_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Join MultiIndex column levels so st.dataframe can show a pivoted table."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" · ".join(str(x) for x in col if str(x)) for col in out.columns]
    return out.reset_index()


def clicked_fips(event, stats: pd.DataFrame):
    """County clicked on the map, from the st.plotly_chart selection event, or None.
    The choropleth trace's point order is the row order of `stats`."""
    try:
        points = event.selection.points
    except AttributeError:
        points = (event or {}).get("selection", {}).get("points", []) if isinstance(event, dict) else []
    if not points:
        return None
    p = points[0]
    if p.get("location"):
        return str(p["location"])
    idx = p.get("point_index", p.get("point_number"))
    if idx is None or idx >= len(stats):
        return None
    return str(stats.iloc[int(idx)][tool.COL_FIPS])


def fmt_soil(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        if isinstance(r["county"], str):
            rows.append({"soil property": r["variable"], "this county": r["county"], "Iowa": r["iowa_median"], "percentile": ""})
        else:
            d = int(r["decimals"])
            rows.append({"soil property": r["variable"], "this county": f"{r['county']:.{d}f} {r['unit']}",
                         "Iowa": f"median {r['iowa_median']:.{d}f} {r['unit']}", "percentile": f"{r['percentile']:.0f}"})
    return pd.DataFrame(rows)


def fmt_practices(df: pd.DataFrame) -> pd.DataFrame:
    y0, y1 = int(df["first_year"].iloc[0]), int(df["last_year"].iloc[0])
    return pd.DataFrame({
        "practice": df["variable"],
        f"{y0}": [f"{v:.1%}" for v in df["county_first"]],
        f"Iowa median {y0}": [f"{v:.1%}" for v in df["iowa_median_first"]],
        f"{y1}": [f"{v:.1%}" for v in df["county_last"]],
        f"Iowa median {y1}": [f"{v:.1%}" for v in df["iowa_median_last"]],
        f"change {y0}→{y1}": [f"{v:+.1f} pp" for v in df["change_pp"]],
    })


def hit_rate_caption(hm: dict, k: int) -> str:
    """The headline tile scale: hit rate and chance translated to counts out of the priority list."""
    return (f"About {round(hm['hit_rate'] * k)} of every {k} flagged counties were among the hardest hit, "
            f"vs {round(hm['chance'] * k)} by chance")


def placebo_clean(summary: pd.DataFrame, crop: str) -> bool:
    """Broad placebo (non-D2+ counties, all test years) for the penalty score includes chance on both metrics."""
    p = summary[(summary["crop"] == crop) & (summary["test"] == tool.PLACEBO_ALL)
                & (summary["score"] == "penalty_score")].set_index("metric")
    return bool(p.loc["spearman", "_lo"] <= 0 <= p.loc["spearman", "_hi"]
                and p.loc["top_third_hit", "_lo"] <= tool.TOP_SHARE <= p.loc["top_third_hit", "_hi"])


def proof_chart(summary: pd.DataFrame, selected_crop: str) -> go.Figure:
    """Held-out top-third hit rate per crop, dot with 95% whisker, chance line."""
    fig = go.Figure()
    chance = None
    for c_label, c in tool.CROPS.items():
        hm = tool.headline_metrics(summary, c)
        chance = hm["chance"]
        color = ACCENT if c == selected_crop else MUTED
        fig.add_trace(go.Scatter(
            x=[c_label], y=[hm["hit_rate"]], mode="markers+text", name=c_label, showlegend=False,
            marker=dict(size=14, color=color),
            error_y=dict(type="data", symmetric=False, array=[hm["hi"] - hm["hit_rate"]],
                         arrayminus=[hm["hit_rate"] - hm["lo"]], color=color, thickness=2, width=10),
            text=[f"{hm['hit_rate']:.0%}"], textposition="middle right", textfont=dict(color=color),
            hovertemplate=f"{c_label}: %{{y:.2f}} [{hm['lo']:.2f}, {hm['hi']:.2f}], {hm['n_years']} test years<extra></extra>"))
    fig.add_hline(y=chance, line_dash="dash", line_color="grey", annotation_text="chance", annotation_position="top left")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis=dict(range=[0, 0.7], title="Share of flagged counties among the hardest hit", tickformat=".0%"),
                      xaxis=dict(title=""), title=dict(text=f"Held-out test, {TEST_LABEL} drought years: top-third hit rate with 95% range",
                                                       font_size=14))
    return fig


# ----------------------------------------------------------------------------------
# Header and controls (every section below responds to these)
# ----------------------------------------------------------------------------------
with st.spinner("Loading the Iowa data and computing drought penalties…"):
    ia = load_data()
n_counties = ia[tool.COL_FIPS].nunique()
data_years = f"{int(ia[tool.COL_YEAR].min())}–{int(ia[tool.COL_YEAR].max())}"

st.title("Soil Program Planner — Iowa corn and soybeans")
st.markdown("For the Soil Conservation Office: each winter, before the next season's program sign-ups, decide which "
            "counties get priority for soil-program outreach and funding to cut drought losses. "
            f"Data: {n_counties} Iowa counties, {data_years}.")
st.caption("Method, evidence, limits and data sources are at the bottom of the page.")

c1, c2, c3 = st.columns([1, 1.4, 2])
crop_label = c1.radio("Crop", list(tool.CROPS), horizontal=True)
def_label = c2.radio("Drought definition", list(tool.DROUGHT_DEFS), horizontal=True)
metric_label = c3.selectbox("Map metric", list(tool.METRICS))
crop = tool.CROPS[crop_label]
sev = tool.DROUGHT_DEFS[def_label]
metric_col = tool.METRICS[metric_label]

# ----------------------------------------------------------------------------------
# Shared computations for the selected crop
# ----------------------------------------------------------------------------------
dep = deployment_scores(crop)
top = priority(crop)
with st.spinner("Running the held-out test (first load only)…"):
    rk = ranking_evidence()
hm = tool.headline_metrics(rk["summary"], crop)
std = top[top["confidence"] == tool.CONFIDENCE_STANDARD]
low = top[top["confidence"] == tool.CONFIDENCE_LOWER]
n_std, n_low = len(std), len(low)
first = top.iloc[0]

# ----------------------------------------------------------------------------------
# 1. Recommendation
# ----------------------------------------------------------------------------------
st.success(
    f"**Recommendation for this winter's sign-ups ({crop_label}):** Start outreach in the **{n_std} priority counties "
    f"with standard confidence**. Verify the **{n_low} lower-confidence counties** with local staff before committing "
    f"funds. Pair any program with a before-and-after comparison of funded and unfunded counties, so next year you'll "
    f"know whether it worked.")
st.markdown(f"**Standard-confidence priority counties, in ranking order:** "
            + ", ".join(n.replace(" County", "") for n in std[tool.COL_COUNTY]) + ".")

# ----------------------------------------------------------------------------------
# 2. Insight cards
# ----------------------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
with k1.container(border=True):
    st.markdown("**Where drought hits hardest**")
    st.markdown(f"The {len(top)} counties in the top third by drought penalty are flagged for {crop_label.lower()}; "
                f"{first[tool.COL_COUNTY]} ranks first with a penalty of {first['penalty_score']:+.1f}%, "
                f"built on {int(first['drought_years_used'])} drought years.")
with k2.container(border=True):
    st.markdown("**How sure we are**")
    st.markdown(f"{hit_rate_caption(hm, len(top))}, in {hm['n_years']} held-out test years ({TEST_LABEL}). "
                f"Range from resampling years: {hm['lo']:.0%} to {hm['hi']:.0%}.")
with k3.container(border=True):
    st.markdown("**What doesn't drive it**")
    st.markdown("Soil water storage and organic matter didn't clearly separate counties in drought, so don't target "
                "programs by soil type alone.")

# ----------------------------------------------------------------------------------
# 3. Scorecard and 4. proof chart
# ----------------------------------------------------------------------------------
# Row 1 is computed from penalty_ranking_results (headline_metrics / placebo_clean). The storage and organic-matter rows
# are fixed text summarising notebooks 03 and 05 (storage: every drought-year range included zero) and notebook 07
# (organic matter: pre-registered decision rule gave "no clear effect" for both crops). The Nebraska row summarises
# notebook 06 (pre-registered feasibility gate: 13-18 dryland counties, below the pre-set minimum of 20).
scorecard = pd.DataFrame([
    ["Drought-penalty ranking on unseen years",
     f"Beats chance ({crop_label} hit rate {hm['hit_rate']:.0%} vs {hm['chance']:.0%}, {hm['n_years']} test years)"],
    ["Placebo check (drought-free counties)", "Clean" if placebo_clean(rk["summary"], crop) else "Not clean (see Evidence details)"],
    ["Soil water storage", "No clear effect"],
    ["Organic matter (pre-registered)", "No clear effect"],
    ["Nebraska replication (pre-registered)", "Not testable: too few rain-fed counties"],
], columns=["What we tested", "Result"])
sc_col, chart_col = st.columns([2, 3])
with sc_col:
    st.markdown("**What we tested**")
    st.table(scorecard.set_index("What we tested"))
with chart_col:
    st.plotly_chart(proof_chart(rk["summary"], crop), width="stretch")

# ----------------------------------------------------------------------------------
# 5. Explorer: map, county panel, priority list
# ----------------------------------------------------------------------------------
st.divider()
st.markdown("### Explore the counties")
left, right = st.columns([3, 2])
stats = county_stats(crop, sev)
idx = county_index()
names = idx[tool.COL_COUNTY].tolist()
name_to_fips = dict(zip(idx[tool.COL_COUNTY], idx[tool.COL_FIPS]))
fips_to_name = dict(zip(idx[tool.COL_FIPS], idx[tool.COL_COUNTY]))
priority_fips = set(top[tool.COL_FIPS])

with left:
    n_blank = int(stats[metric_col].isna().sum())
    clicked = None
    if n_blank == len(stats):
        st.info(f"No {crop_label.lower()} county has a value for \"{metric_label}\" under {def_label}. "
                f"Try the other drought definition or another metric.")
    else:
        fig = tool.make_map(stats, metric_col, metric_label, crop_label, def_label)
        is_priority = stats[tool.COL_FIPS].isin(priority_fips).to_numpy()      # same row order as the trace
        fig.update_traces(marker_line_width=np.where(is_priority, 2.2, 0.5),
                          marker_line_color=np.where(is_priority, "#222222", "white"))
        fig.update_layout(height=520, title_font_size=15)
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                                key=f"map_{crop}_{sev}_{metric_col}")
        clicked = clicked_fips(event, stats)
        blank_txt = (f"Blank counties have no score for this setting ({n_blank} here)." if n_blank
                     else "Blank counties would have no score for this setting; every county has one here.")
        st.caption(f"{MAP_CAPTIONS[metric_col]} {blank_txt} Priority counties have a dark outline. "
                   "Click a county to open it in the panel on the right.")

default_county = first[tool.COL_COUNTY]
if st.session_state.get("county_crop") != crop:
    st.session_state["county_crop"] = crop
    st.session_state["county_select"] = default_county
    st.session_state["last_click"] = None
if clicked and clicked in fips_to_name and clicked != st.session_state.get("last_click"):
    st.session_state["last_click"] = clicked
    st.session_state["county_select"] = fips_to_name[clicked]
if st.session_state.get("county_select") not in name_to_fips:
    st.session_state["county_select"] = default_county

with right:
    county = st.selectbox("County", names, key="county_select")
    fips = name_to_fips[county]
    row = stats[stats[tool.COL_FIPS] == fips]
    if row.empty:
        st.info(f"No Iowa {crop_label.lower()} yields are reported for {county}.")
    else:
        row = row.iloc[0]
        has_score = not np.isnan(row["drought_penalty_pct"])
        n_scored = int(stats["drought_penalty_pct"].notna().sum())
        on_list = fips in priority_fips
        st.markdown(f"**{county}** — {crop_label}, {def_label}" + (" · **priority county**" if on_list else ""))

        m1, m2 = st.columns(2)
        m1.metric("Drought penalty", f"{row['drought_penalty_pct']:+.1f}%" if has_score else "no score",
                  help=f"Mean drought penalty over the county's drought years ({def_label}) with a penalty, all years "
                       f"{ALL_YEARS}. Negative = loses more than its own normal in drought.")
        m2.metric("Rank among Iowa counties", f"{int(row['penalty_rank'])} of {n_scored}" if has_score else "—",
                  help="1 = largest penalty among the counties with a score, for this crop and drought definition.")
        m3, m4 = st.columns(2)
        m3.metric("Drought years behind the score", int(row["penalty_years_used"]),
                  help=f"Drought years with a usable penalty; {int(row['drought_years'])} drought years in all under {def_label}.")
        m4.metric("Confidence", row["confidence"],
                  help=f"'{tool.CONFIDENCE_LOWER}' when fewer than {tool.LOW_CONFIDENCE_YEARS} drought years are behind the score.")
        if not has_score:
            st.info(f"{county} has only {int(row['penalty_years_used'])} drought year(s) with a penalty under {def_label}; "
                    f"a score needs at least {tool.MIN_D2_YEARS_FOR_SCORE}. Switch to the other drought definition to see a score.")
        st.caption(f"Drought years ({def_label}): {row['drought_year_list'] or 'none'}.")

        st.markdown("**Soil context**")
        try:
            st.dataframe(fmt_soil(soil_context(fips)), hide_index=True, width="stretch",
                         column_config={"percentile": st.column_config.TextColumn(
                             "percentile", help="Share of Iowa counties at or below this county's value (0-100).")})
        except FileNotFoundError:
            st.info("Extra soil properties file not found (soil_planner/extra_data/iowa_soil_extra.csv).")

        st.markdown("**Current practices**")
        try:
            st.dataframe(fmt_practices(practices_context(fips)), hide_index=True, width="stretch")
        except FileNotFoundError:
            st.info("Practice shares file not found (soil_planner/extra_data/iowa_conservation_practices.csv).")
        st.caption(tool.DATA_NOTE)

        if on_list:
            st.markdown("**Why this county is on the priority list**")
            for r in reasons(fips, crop):
                st.markdown(f"- {r}")
            st.markdown(tool.PRACTICES_NOTE)

        with st.expander(f"Year-by-year: {county}, {crop_label}"):
            card = report_card(fips, crop, sev)
            st.plotly_chart(tool.anomaly_bar(card["rows"], county, crop_label, def_label), width="stretch")
            rows = card["rows"].rename(columns=ROW_COLUMNS).round(1)
            st.dataframe(rows, hide_index=True, width="stretch",
                         column_config={"year": st.column_config.NumberColumn(format="%d")})

# priority list
no_score = dep.loc[~dep["has_score"], tool.COL_COUNTY].tolist()
st.markdown(f"**Priority list — {crop_label}: top {len(top)} of {int(dep['has_score'].sum())} scored counties** "
            f"(no score for {len(no_score)}: {', '.join(no_score) if no_score else 'none'})")
st.caption(f"Counties in the top third by drought penalty, all years {ALL_YEARS}, {D2_LABEL}, largest penalty first. "
           f"This list does not change with the drought definition selected above.")
view = (top[list(PRIORITY_COLUMNS)].rename(columns=PRIORITY_COLUMNS)
        .round({"drought penalty (%)": 1, "soil water storage (mm)": 0}).astype({"rank": int}))
st.dataframe(view, hide_index=True, width="stretch", height=min(38 + 35 * len(view), 450),
             column_config={"drought penalty (%)": st.column_config.NumberColumn(format="%+.1f"),
                            "soil water storage (mm)": st.column_config.NumberColumn(format="%.0f"),
                            "FIPS": st.column_config.TextColumn()})
st.markdown("Scores built on few drought years are less reliable; verify these counties with local information. "
            f"*({n_low} of {len(top)} {crop_label.lower()} counties above are marked '{tool.CONFIDENCE_LOWER}': "
            f"fewer than {tool.LOW_CONFIDENCE_YEARS} drought years behind the score.)*")
st.download_button("Download the priority list (CSV)", data=view.to_csv(index=False).encode("utf-8"),
                   file_name=f"priority_list_{crop.lower()}_{FIRST_YEAR}_{LAST_YEAR}.csv", mime="text/csv")

# ----------------------------------------------------------------------------------
# 6. Details, collapsed
# ----------------------------------------------------------------------------------
st.divider()
with st.expander("Evidence details", expanded=False):
    st.subheader(f"Does the drought-penalty score hold up on years it never saw? ({TRAIN_LABEL} → {TEST_LABEL})")
    st.markdown(
        f"Three scores were built from {TRAIN_LABEL} only: the drought-penalty score, drought frequency and soil "
        f"water storage. Each was then asked to rank counties in the {TEST_LABEL} drought years. **Spearman** is the "
        "rank correlation between the score and the actual drought penalty that year, signed so positive means the "
        "score got the order right (chance 0). **Top-third hit rate** is the share of the highest-priority third of "
        "counties that really were in the worst-losing third (chance about 0.33). Ranges come from resampling test "
        "years. The two placebo columns repeat the test where it should find nothing: in years with no drought "
        "anywhere in Iowa, and on the non-drought counties of every test year.")
    for c_label, c in tool.CROPS.items():
        info = rk["test_years"][c]
        st.markdown(f"**{c_label}** — test years with at least {tool.MIN_COUNTIES_PER_YEAR} drought counties: "
                    + ", ".join(f"{y} ({n})" for y, n in info["usable"].items())
                    + f". Years with no drought county (used for the first placebo): "
                    + (", ".join(map(str, info["zero_drought"])) or "none") + ".")
        st.dataframe(tool.ranking_summary_table(rk["summary"], c).reset_index(), hide_index=True, width="stretch")
    real = rk["summary"][rk["summary"]["test"] == tool.REAL_TEST]
    beats = real[real["range_above_chance"]]
    st.markdown("**Computed verdict.** Score / metric combinations whose whole range sits above chance on held-out "
                "drought years: " + ("; ".join(f"{r.crop.lower()} {r.score} ({r.metric})" for r in beats.itertuples())
                                      if len(beats) else "none") + ".")

    st.subheader("Does soil water storage go with smaller drought penalties?")
    st.markdown(
        f"For each year with at least {tool.MIN_COUNTIES_PER_YEAR} drought counties, the slope of the drought penalty "
        f"on storage across those counties, in percentage points per extra {tool.AWS_UNIT:.0f} mm of storage, "
        "averaged over years with a range from resampling years. Positive would mean more storage, smaller penalty. "
        "The placebo columns run the same regression on non-drought county-years, where a real buffering effect "
        "should not appear.")
    with st.spinner("Estimating the storage effect (first load only)…"):
        step2 = storage_evidence()
    step2_view = (step2.drop(columns=["_mean", "_lo", "_hi"])
                  .pivot(index=["crop", "spec"], columns="kind",
                         values=["estimate [95% range]", "n_years", "county_years", "years +/-", "excludes_zero"])
                  .swaplevel(axis=1).sort_index(axis=1, level=0, sort_remaining=False)[["drought", "placebo"]])
    st.dataframe(_flat_columns(step2_view), hide_index=True, width="stretch")
    n_dr = int((step2["kind"] == "drought").sum())
    n_excl = int(((step2["kind"] == "drought") & step2["excludes_zero"]).sum())
    n_excl_pl = int(((step2["kind"] == "placebo") & step2["excludes_zero"]).sum())
    st.markdown(f"**Computed verdict.** {n_excl} of {n_dr} drought-year storage estimates have a range that excludes "
                f"zero; placebo estimates excluding zero: {n_excl_pl}.")

    st.subheader("Earlier attempts and why we moved on")
    st.markdown(
        "The first storage estimate (notebook 03) used the dataset's own yield anomaly, a trend fitted on all "
        "years and therefore in-sample, and found no clear effect. The first held-out ranking test (notebook 04) "
        f"built scores on a {TRAIN_LABEL} trend and failed: no score beat chance, and the scores \"predicted\" "
        "losses even in years with no drought, because the trend extrapolated unevenly across the state and "
        "counties with a bad early record did better later regardless of weather. The drought-penalty score "
        "above was designed to fix that and was then tested once.")
    with st.spinner("Recomputing the earlier estimates (first load only)…"):
        storage03 = earlier_storage_evidence()
        rank04 = earlier_ranking_evidence()
    st.markdown(f"**Notebook 03: in-sample storage estimate (pp of yield anomaly per +{tool.AWS_UNIT:.0f} mm, "
                "drought years)**")
    st.dataframe(storage03[["crop", "specification", "estimate [95% range]", "drought years", "range excludes zero"]],
                 hide_index=True, width="stretch")
    st.markdown("**Notebook 04: held-out test of trend-based scores (none beat chance)**")
    st.dataframe(rank04["summary"], hide_index=True, width="stretch")
    st.markdown("**Notebook 04: its failed placebo, years with no drought county.** A score that works should "
                "show nothing here.")
    st.dataframe(rank04["placebo"], hide_index=True, width="stretch")

    st.divider()
    st.markdown(tool.METHODS_NOTE)

with st.expander("Limits", expanded=False):
    st.markdown(tool.LIMITS_NOTE)

with st.expander("Next steps", expanded=False):
    st.markdown(tool.NEXT_STEPS_NOTE)

with st.expander("About this tool and data sources", expanded=False):
    st.markdown(
        f"**Data.** USDA NASS county yields, U.S. Drought Monitor weekly maps, NOAA ACIS weather and NRCS SSURGO soil, "
        f"combined in the Data to Harvest hackathon master dataset: {n_counties} Iowa counties, {data_years}, corn and "
        f"soybeans, rainfed. **Context data** in the county panel: extra surface-soil properties from the September 2026 "
        f"SSURGO release (USDA NRCS Soil Data Access) and conservation-practice shares from the USDA Census of "
        f"Agriculture, 2017 and 2022. These are shown for context only and enter no score or test.\n\n"
        f"**Ranking.** The priority list and the default map use the drought penalty computed on all years {ALL_YEARS}, "
        f"with the {D2_LABEL.split(' ')[0]} definition.\n\n"
        f"**Test.** The evidence section shows the held-out test that validated the method: scores built on {TRAIN_LABEL} "
        f"only, checked on the {TEST_LABEL} drought years they had never seen.\n\n"
        f"`notebooks/Soil_Program_Planner.ipynb` shows the same analysis as a report."
    )
    st.markdown(tool.DATA_CREDITS)
