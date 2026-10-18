"""
Shared pieces of the Soil Program Planner app: cached engine calls, session-state keys, labels and formatting
helpers used by the entrypoint (soil_planner/app.py) and the pages in soil_planner/pages_app/.

Every number shown in the app comes from soil_planner/soil_tool.py, the same functions the notebook
notebooks/Soil_Program_Planner.ipynb calls, so the app and the notebook show the same figures.
Nothing is typed in. The extra soil and practice data in the county panel are display only:
they enter no score, ranking or evidence table.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from soil_planner import soil_tool as tool  # noqa: E402

# ----------------------------------------------------------------------------------
# Session-state keys. The entrypoint's radios write KEY_CROP and KEY_DEF on every run, so the selection is the
# same on every page and survives page switches; pages read it through selection().
# ----------------------------------------------------------------------------------
KEY_CROP = "crop_label"
KEY_DEF = "def_label"
KEY_METRIC = "map_metric"          # County explorer: map metric selectbox
KEY_COUNTY = "county_select"       # County explorer: selected county (name)
KEY_COUNTY_CROP = "county_crop"    # County explorer: crop the selected county was chosen for
KEY_LAST_CLICK = "last_click"      # County explorer: last map click already handled (fips)
KEY_N_FUND = "n_fund"              # This winter's plan: "Counties we can fund this winter" slider, read by County explorer

# Page files, relative to the entrypoint (st.Page in app.py, st.page_link in the pages).
PAGE_PLAN = "pages_app/plan.py"
PAGE_EXPLORER = "pages_app/county_explorer.py"
PAGE_EVIDENCE = "pages_app/evidence.py"
PAGE_STORY = "pages_app/story.py"
PAGE_LIMITS = "pages_app/limits.py"
PAGE_ABOUT = "pages_app/about.py"


def selection() -> tuple[str, str, str, int]:
    """Crop and drought definition from the shared controls: (crop label, crop code, definition label, severity)."""
    crop_label = st.session_state.get(KEY_CROP) or next(iter(tool.CROPS))
    def_label = st.session_state.get(KEY_DEF) or next(iter(tool.DROUGHT_DEFS))
    return crop_label, tool.CROPS[crop_label], def_label, tool.DROUGHT_DEFS[def_label]


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


def top_n(crop: str, n: int) -> pd.DataFrame:
    """The top `n` counties of OUR deployment ranking (deployment_penalty_scores order, as priority_list uses it),
    with the same columns as priority_list. priority_list() is top_n() at the tested top third."""
    scores = deployment_scores(crop)
    n_scored = int(scores["has_score"].sum())
    return tool.priority_list(scores, share=min(int(n), n_scored) / n_scored)


def n_fund(crop: str) -> int:
    """Counties to fund, from the slider on This winter's plan; the tested top third until the slider is moved."""
    return int(st.session_state.get(KEY_N_FUND) or len(priority(crop)))


@st.cache_data(show_spinner=False)
def bushel_scores(crop: str) -> pd.DataFrame:
    """Teammate's descriptive bushel scores (soil_priority_extras), one row per county. Read-only context:
    nothing here enters our ranking. Raises if the module or the acres column is missing."""
    import soil_priority_extras as extras  # noqa: PLC0415  (imported as `extras`, never as `st`)
    d = extras.add_bushel_losses(tool.load_iowa_with_lon(), split=False)
    return extras.bushel_priority_scores(d, crop)


@st.cache_data(show_spinner=False)
def bushel_shares(crop: str, fips: tuple) -> tuple | None:
    """(share of Iowa's expected bushels lost per year, share of Iowa's harvested acres) for the counties `fips`,
    both from soil_priority_extras. None if the import or the computation fails, so the page shows nothing."""
    try:
        scores = bushel_scores(crop).set_index(tool.COL_FIPS)
        sel = scores.loc[[f for f in fips if f in scores.index]]
        total_bu, total_acres = scores["bu_lost_per_year"].sum(), scores["avg_acres"].sum()
        if not (total_bu > 0 and total_acres > 0):
            return None
        return float(sel["bu_lost_per_year"].sum() / total_bu), float(sel["avg_acres"].sum() / total_acres)
    except Exception:  # noqa: BLE001 - descriptive extra; any failure means "show nothing"
        return None


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


# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------
def flat_columns(df: pd.DataFrame) -> pd.DataFrame:
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
