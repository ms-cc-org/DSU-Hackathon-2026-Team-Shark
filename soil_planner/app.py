"""
Soil Program Planner - single-screen Streamlit dashboard for the Soil Conservation Office.

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
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from soil_planner import soil_tool as tool  # noqa: E402

st.set_page_config(page_title="Soil Program Planner — Iowa", layout="wide")


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
    """Soil context rows as display strings."""
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


# ----------------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------------
with st.spinner("Loading the Iowa data and computing drought penalties…"):
    ia = load_data()
n_counties = ia[tool.COL_FIPS].nunique()
data_years = f"{int(ia[tool.COL_YEAR].min())}–{int(ia[tool.COL_YEAR].max())}"

st.title("Soil Program Planner — Iowa corn and soybeans")
st.markdown("For the Soil Conservation Office: each winter, before the next season's program sign-ups, decide which "
            "counties get priority for soil-program outreach and funding to cut drought losses. "
            f"Data: {n_counties} Iowa counties, {data_years}.")
with st.expander("What we found", expanded=True):
    st.markdown(tool.HEADLINE)

# ----------------------------------------------------------------------------------
# Controls row
# ----------------------------------------------------------------------------------
c1, c2, c3 = st.columns([1, 1.4, 2])
crop_label = c1.radio("Crop", list(tool.CROPS), horizontal=True)
def_label = c2.radio("Drought definition", list(tool.DROUGHT_DEFS), horizontal=True)
metric_label = c3.selectbox("Map metric", list(tool.METRICS))
crop = tool.CROPS[crop_label]
sev = tool.DROUGHT_DEFS[def_label]
metric_col = tool.METRICS[metric_label]

# ----------------------------------------------------------------------------------
# Sidebar: About
# ----------------------------------------------------------------------------------
with st.sidebar:
    st.subheader("About")
    st.markdown(
        f"**Data.** USDA NASS county yields, U.S. Drought Monitor weekly maps, NOAA ACIS weather and NRCS SSURGO soil, "
        f"combined in the Data to Harvest hackathon master dataset: {n_counties} Iowa counties, {data_years}, corn and "
        f"soybeans, rainfed. **Context data** in the county panel: extra surface-soil properties from the September 2026 "
        f"SSURGO release (USDA NRCS Soil Data Access) and conservation-practice shares from the USDA Census of "
        f"Agriculture, 2017 and 2022. These are shown for context only and enter no score or test.\n\n"
        f"**Ranking.** The priority list and the default map use the drought penalty computed on all years {ALL_YEARS}, "
        f"with the {D2_LABEL.split(' ')[0]} definition.\n\n"
        f"**Test.** The Evidence tab shows the held-out test that validated the method: scores built on {TRAIN_LABEL} "
        f"only, checked on the {TEST_LABEL} drought years they had never seen.\n\n"
        f"`notebooks/Soil_Program_Planner.ipynb` shows the same analysis as a report."
    )
    st.markdown(tool.DATA_CREDITS)

# ----------------------------------------------------------------------------------
# Tiles for the selected crop
# ----------------------------------------------------------------------------------
dep = deployment_scores(crop)
top = priority(crop)
with st.spinner("Running the held-out test (first load only)…"):
    rk = ranking_evidence()
hm = tool.headline_metrics(rk["summary"], crop)
n_lower = int((top["confidence"] == tool.CONFIDENCE_LOWER).sum())

t1, t2, t3, t4 = st.columns(4)
t1.metric("Priority counties", len(top),
          help=f"{crop_label}: top third of the {int(dep['has_score'].sum())} scored counties by drought penalty, "
               f"{D2_LABEL}, all years {ALL_YEARS}.")
t2.metric("Held-out top-third hit rate", f"{hm['hit_rate']:.0%}",
          delta=f"{100 * (hm['hit_rate'] - hm['chance']):+.0f} pp vs {hm['chance']:.0%} chance",
          help=f"Share of the counties the {TRAIN_LABEL} penalty score put in the top third that really were in the "
               f"worst-losing third in {TEST_LABEL} drought years. Range from resampling test years: "
               f"{hm['lo']:.0%} to {hm['hi']:.0%}.")
t2.caption(f"About {round(hm['hit_rate'] * len(top))} of every {len(top)} flagged counties were among the hardest hit, "
           f"vs {round(hm['chance'] * len(top))} by chance")
t3.metric("Test years", hm["n_years"],
          help=f"{TEST_LABEL} drought years with at least {tool.MIN_COUNTIES_PER_YEAR} drought counties with a penalty.")
t4.metric("Lower-confidence priority counties", n_lower,
          help=f"Priority counties whose score rests on fewer than {tool.LOW_CONFIDENCE_YEARS} drought years.")

# ----------------------------------------------------------------------------------
# Main row: map (left) and county panel (right)
# ----------------------------------------------------------------------------------
left, right = st.columns([3, 2])
stats = county_stats(crop, sev)
idx = county_index()
names = idx[tool.COL_COUNTY].tolist()
name_to_fips = dict(zip(idx[tool.COL_COUNTY], idx[tool.COL_FIPS]))
fips_to_name = dict(zip(idx[tool.COL_FIPS], idx[tool.COL_COUNTY]))

with left:
    n_blank = int(stats[metric_col].isna().sum())
    clicked = None
    if n_blank == len(stats):
        st.info(f"No {crop_label.lower()} county has a value for \"{metric_label}\" under {def_label}. "
                f"Try the other drought definition or another metric.")
    else:
        fig = tool.make_map(stats, metric_col, metric_label, crop_label, def_label)
        fig.update_layout(height=520, title_font_size=15)
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                                key=f"map_{crop}_{sev}_{metric_col}")
        clicked = clicked_fips(event, stats)
        blank_txt = (f"Blank counties have no score for this setting ({n_blank} here)." if n_blank
                     else "Blank counties would have no score for this setting; every county has one here.")
        st.caption(f"{MAP_CAPTIONS[metric_col]} {blank_txt} Click a county to open it in the panel on the right.")

# county selection state: default = top priority county for the crop; map click overrides; selectbox overrides
default_county = top.iloc[0][tool.COL_COUNTY]
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
        on_list = fips in set(top[tool.COL_FIPS])
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

# ----------------------------------------------------------------------------------
# Priority list
# ----------------------------------------------------------------------------------
st.divider()
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
            f"*({n_lower} of {len(top)} {crop_label.lower()} counties above are marked '{tool.CONFIDENCE_LOWER}': "
            f"fewer than {tool.LOW_CONFIDENCE_YEARS} drought years behind the score.)*")
st.download_button("Download the priority list (CSV)", data=view.to_csv(index=False).encode("utf-8"),
                   file_name=f"priority_list_{crop.lower()}_{FIRST_YEAR}_{LAST_YEAR}.csv", mime="text/csv")

# ----------------------------------------------------------------------------------
# Evidence and Limits
# ----------------------------------------------------------------------------------
tab_evidence, tab_limits = st.tabs(["Evidence", "Limits"])

with tab_evidence:
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

    with st.expander("Earlier attempts and why we moved on", expanded=False):
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

with tab_limits:
    st.subheader("Limits of this evidence")
    st.markdown(tool.LIMITS_NOTE)
    st.divider()
    st.markdown(tool.NEXT_STEPS_NOTE)
