"""
soil_priority_extras.py - companion to soil_tool.py (put it in the same folder, soil_planner/).

Adds, without changing any existing soil_tool number:
  1. An acres-weighted priority score: expected BUSHELS lost per year.
  2. An ABSOLUTE drought penalty (each county vs its own nearby normal years, NOT vs the Iowa median).
  3. A "how many counties can we fund" selector: funded_counties() / funding_sentence().
  4. Rank uncertainty: a plausible rank range and the chance each county is in the funded set.
  5. A held-out test of the new score on 2016-2025, against a "just rank by acres" baseline.
  6. A map with the funded counties outlined, and one sentence for the office (OFFICE_STATEMENT).

Everything is historical and descriptive. Nothing here estimates what a soil program would do.
Drought = D2+ (max_drought_severity >= 3), the same definition soil_tool uses for its penalty.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import spearmanr

try:
    from soil_planner import soil_tool as st
except ImportError:                       # running from inside soil_planner/
    import soil_tool as st

COL_ACRES = "acres_harvested"
COL_APEN = "abs_penalty_pct"              # drought-year yield vs the county's own normal, approx %, NOT relative to Iowa
COL_LOSS_BU = "loss_bu"                   # bushels lost in one drought county-year (shortfall x acres), NaN otherwise
_DERIVED_X = ["n_normal_abs", "normal_log_abs", "x_log_abs", COL_APEN, COL_LOSS_BU]

# ordering rules the office can choose from: column -> sort ascending?
RANK_BY = {
    "Expected bushels lost per year": ("bu_lost_per_year", False),
    "Absolute drought penalty (%)": ("abs_penalty_pct", True),
    "Relative drought penalty (% vs Iowa)": ("rel_penalty_pct", True),
}
EXTRA_METRICS = {   # map menu: label -> (column, colour scale, symmetric around 0?)
    "Expected bushels lost per year (acres-weighted)": ("bu_lost_per_year", "OrRd", False),
    "Absolute drought penalty (% below own normal)": ("abs_penalty_pct", "RdYlGn", True),
    "Relative drought penalty (% vs Iowa)": ("rel_penalty_pct", "RdYlGn", True),
}

OFFICE_STATEMENT = (
    "This tool shows which Iowa counties lost the most corn and soybean yield in past droughts, in percent and in "
    "bushels, and how sure we are of each county's rank; it does not show that a soil program would reduce those "
    "losses, which would take a funded-versus-unfunded comparison."
)


# ----------------------------------------------------------------------------------
# 1-2. Absolute penalty and bushel losses per drought county-year
# ----------------------------------------------------------------------------------
def add_bushel_losses(ia: pd.DataFrame, split: bool = False) -> pd.DataFrame:
    """soil_tool.compute_penalties() plus an ABSOLUTE penalty and bushel loss per drought county-year.

    absolute penalty: log(yield) minus the mean log(yield) of the county's OTHER non-D2+ years within
      +/- WINDOW years (same window rule as soil_tool, but without subtracting the statewide median).
    loss_bu: max(0, normal yield - actual yield) x acres_harvested, on drought rows only (NaN elsewhere).
    split=False: all 26 years (deployment). split=True: normals never cross the 2015/2016 boundary (held-out test).
    """
    if COL_ACRES not in ia.columns:
        raise KeyError(f"{COL_ACRES!r} not in the data; it is needed for bushel weighting")
    d = st.compute_penalties(ia.drop(columns=[c for c in _DERIVED_X if c in ia.columns]), split=split)
    tmp = d.copy()
    tmp[st.COL_R] = tmp["log_yield"]                       # same machinery, no state-median subtraction
    pen = pd.concat([st._local_penalties(tmp[tmp[st.COL_CROP] == c]).assign(**{st.COL_CROP: c})
                     for c in st.CROPS.values()])
    pen = pen.rename(columns={"n_normal": "n_normal_abs", "normal_log": "normal_log_abs", "x_log": "x_log_abs"})
    d = d.merge(pen, on=[st.COL_CROP, st.COL_FIPS, st.COL_YEAR], how="left")
    d[COL_APEN] = 100 * (np.exp(d["x_log_abs"]) - 1)
    shortfall = d[st.COL_YIELD] * (np.exp(-d["x_log_abs"]) - 1)        # normal yield - actual yield, bu/acre
    d[COL_LOSS_BU] = (shortfall.clip(lower=0) * d[COL_ACRES]).where(d["is_d2"])
    return d


def bushel_priority_scores(d: pd.DataFrame, crop: str) -> pd.DataFrame:
    """One row per county. `d` comes from add_bushel_losses(ia, split=False).

    bu_lost_per_year = (share of reported years in D2+) x (mean bushels lost in its D2+ years that have a valid
    baseline). NaN with fewer than MIN_D2_YEARS_FOR_SCORE such years. rank 1 = most bushels lost per year.
    """
    sub = d[d[st.COL_CROP] == crop]

    def _one(g):
        valid = g[g["is_d2"] & g[COL_LOSS_BU].notna()]
        ok = len(valid) >= st.MIN_D2_YEARS_FOR_SCORE
        freq = g["is_d2"].sum() / g[st.COL_YEAR].nunique()
        return pd.Series({
            st.COL_COUNTY: g[st.COL_COUNTY].iloc[0],
            "years_reported": g[st.COL_YEAR].nunique(),
            "drought_years_total": int(g["is_d2"].sum()),
            "drought_years_used": len(valid),
            "avg_acres": g[COL_ACRES].mean(),
            "avg_yield": g[st.COL_YIELD].mean(),
            "freq_drought": freq,
            "bu_lost_per_drought_year": valid[COL_LOSS_BU].mean() if ok else np.nan,
            "bu_lost_per_year": freq * valid[COL_LOSS_BU].mean() if ok else np.nan,
            COL_APEN: valid[COL_APEN].mean() if ok else np.nan,
        })

    out = sub.groupby(st.COL_FIPS).apply(_one, include_groups=False).reset_index()
    rel = st.deployment_penalty_scores(d, crop)[[st.COL_FIPS, "penalty_score"]].rename(columns={"penalty_score": "rel_penalty_pct"})
    out = out.merge(rel, on=st.COL_FIPS, how="left")
    out["has_score"] = out["bu_lost_per_year"].notna()
    out["rank"] = out["bu_lost_per_year"].rank(ascending=False, method="first", na_option="keep")
    tot = out["bu_lost_per_year"].sum()
    out["share_of_state_loss"] = out["bu_lost_per_year"] / tot if tot > 0 else np.nan
    out["confidence"] = st.confidence_label(out["drought_years_used"], out["has_score"])
    out["crop"] = crop
    return out.sort_values("rank", na_position="last").reset_index(drop=True)


# ----------------------------------------------------------------------------------
# 3. Budget selector
# ----------------------------------------------------------------------------------
def funded_counties(scores: pd.DataFrame, n_fund: int, rank_by: str = "Expected bushels lost per year"):
    """Top n_fund scored counties under the chosen ordering rule (a key of RANK_BY).
    Returns (table, summary). The summary always measures coverage in expected bushels lost per year,
    so different ordering rules can be compared on the same yardstick."""
    col, ascending = RANK_BY[rank_by]
    s = scores[scores["has_score"] & scores[col].notna()].sort_values(col, ascending=ascending)
    n_fund = int(min(max(int(n_fund), 1), len(s)))
    top = s.head(n_fund).reset_index(drop=True)
    total_bu = scores["bu_lost_per_year"].sum()
    summary = {
        "n_fund": n_fund, "n_scored": len(s), "rank_by": rank_by,
        "share_of_state_loss": float(top["bu_lost_per_year"].sum() / total_bu) if total_bu > 0 else np.nan,
        "acres": float(top["avg_acres"].sum()),
        "share_of_acres": float(top["avg_acres"].sum() / s["avg_acres"].sum()),
        "n_lower_confidence": int((top["confidence"] == st.CONFIDENCE_LOWER).sum()),
    }
    return top, summary


def funding_sentence(summary: dict, crop_label: str) -> str:
    s = summary
    txt = (f"Funding the top {s['n_fund']} of {s['n_scored']} scored {crop_label.lower()} counties (ordered by "
           f"{s['rank_by'].lower()}) covers about {100 * s['share_of_state_loss']:.0f}% of Iowa's expected "
           f"{crop_label.lower()} bushels lost to drought per year, on {100 * s['share_of_acres']:.0f}% of its acres "
           f"in the scored counties.")
    if s["n_lower_confidence"]:
        verb = "rests" if s["n_lower_confidence"] == 1 else "rest"
        txt += f" {s['n_lower_confidence']} of them {verb} on fewer than {st.LOW_CONFIDENCE_YEARS} drought years."
    return txt


# ----------------------------------------------------------------------------------
# 4. Rank uncertainty (resample years, keep each year's counties together)
# ----------------------------------------------------------------------------------
N_BOOT_RANK = 2000


def rank_uncertainty(d: pd.DataFrame, crop: str, n_fund: int, n_boot: int = N_BOOT_RANK, seed: int = st.BOOT_SEED) -> pd.DataFrame:
    """Resample the 26 years with replacement (counties in a year share weather, so they move together),
    recompute every county's bushel score, and report a 5th-95th percentile rank range plus the share of
    resamples in which the county falls inside the top n_fund. Counties without a score in a resample count as
    'not in the top'. This captures year-to-year luck, not error in the baseline; treat it as a minimum."""
    sub = d[d[st.COL_CROP] == crop].assign(_d2=lambda x: x["is_d2"].astype(float))
    D = sub.pivot(index=st.COL_FIPS, columns=st.COL_YEAR, values="_d2")
    L = sub.pivot(index=st.COL_FIPS, columns=st.COL_YEAR, values=COL_LOSS_BU).reindex_like(D)
    fips, Dv, Lv = D.index.to_numpy(), D.to_numpy(float), L.to_numpy(float)
    ny = Dv.shape[1]
    rng = np.random.default_rng(seed)
    scores = np.full((len(fips), n_boot), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for b in range(n_boot):
            idx = rng.integers(0, ny, ny)
            Dd, Ld = Dv[:, idx], Lv[:, idx]
            freq = np.nanmean(Dd, axis=1)
            nvalid = (~np.isnan(Ld)).sum(axis=1)
            mean_l = np.where(nvalid >= st.MIN_D2_YEARS_FOR_SCORE, np.nansum(Ld, axis=1) / np.maximum(nvalid, 1), np.nan)
            scores[:, b] = freq * mean_l
        ranks = pd.DataFrame(scores).rank(axis=0, ascending=False, method="min").to_numpy()
        lo, hi = np.nanpercentile(ranks, 5, axis=1), np.nanpercentile(ranks, 95, axis=1)
    p_top = np.nan_to_num(ranks, nan=np.inf) <= n_fund
    return pd.DataFrame({st.COL_FIPS: fips, "rank_lo": lo, "rank_hi": hi, "p_in_funded_set": p_top.mean(axis=1)})


# ----------------------------------------------------------------------------------
# 6. Map with funded counties outlined
# ----------------------------------------------------------------------------------
def make_priority_map(scores: pd.DataFrame, metric_label: str, crop_label: str, n_fund: int,
                      rank_by: str = "Expected bushels lost per year") -> go.Figure:
    """Iowa map of one EXTRA_METRICS measure; the n_fund funded counties are outlined in black.
    `scores` may carry rank_lo / rank_hi / p_in_funded_set from rank_uncertainty() (merged on fips)."""
    col, scale, symmetric = EXTRA_METRICS[metric_label]
    top, summary = funded_counties(scores, n_fund, rank_by)
    hover = {st.COL_FIPS: False, "rank": ":.0f", "bu_lost_per_year": ":,.0f", COL_APEN: ":.1f", "rel_penalty_pct": ":.1f",
             "avg_acres": ":,.0f", "drought_years_used": True, "confidence": True, col: False}
    for extra in ("rank_lo", "rank_hi", "p_in_funded_set"):
        if extra in scores.columns:
            hover[extra] = ":.2f" if extra == "p_in_funded_set" else ":.0f"
    labels = {"rank": "Rank (1 = most bushels lost)", "bu_lost_per_year": "Expected bushels lost / year",
              COL_APEN: "Absolute drought penalty (%)", "rel_penalty_pct": "Relative drought penalty (% vs Iowa)",
              "avg_acres": "Avg harvested acres", "drought_years_used": "Drought years behind the score",
              "confidence": "Confidence", "rank_lo": "Rank, low end of range", "rank_hi": "Rank, high end of range",
              "p_in_funded_set": "Chance in funded set"}
    fig = px.choropleth(scores, geojson=st.iowa_geojson(), locations=st.COL_FIPS, color=col, color_continuous_scale=scale,
                        hover_name=st.COL_COUNTY, hover_data=hover, labels=labels)
    if symmetric and scores[col].notna().any():
        lim = float(np.nanmax(np.abs(scores[col])))
        fig.update_coloraxes(cmin=-lim, cmax=lim)
    fig.add_trace(go.Choropleth(
        geojson=st.iowa_geojson(), locations=top[st.COL_FIPS], z=[1] * len(top),
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
        marker_line_color="black", marker_line_width=2.5, hoverinfo="skip",
        name=f"Funded: top {summary['n_fund']}", showlegend=True))
    n_blank = int(scores[col].isna().sum())
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        title=(f"Historical drought losses, Iowa {crop_label.lower()} (D2+, 2000-2025): {metric_label}"
               f"<br><sup>Outlined: top {summary['n_fund']} by {rank_by.lower()}. Past losses, not a forecast."
               + (f" {n_blank} counties blank (too few drought years)." if n_blank else "") + "</sup>"),
        coloraxis_colorbar_title=metric_label.split(" (")[0], legend=dict(orientation="h", y=-0.02),
        height=500, margin=dict(l=10, r=10, t=70, b=10))
    return fig


# ----------------------------------------------------------------------------------
# 5. Held-out test of the bushel score (train 2000-2015, test 2016-2025)
# ----------------------------------------------------------------------------------
def bushel_heldout_test(ia: pd.DataFrame) -> dict:
    """Score counties on 2000-2015 only, then check them on each 2016-2025 D2+ year with >= MIN_COUNTIES_PER_YEAR
    counties: Spearman against that year's realized bushels lost, and the overlap of the top third by score with
    the top third by realized loss (chance = 1/3). Compared with a baseline that ranks by harvested acres alone,
    because a bushel score is partly just a size ranking. Not covered: placebo years (too few drought-free years
    in the test window, as soil_tool's own notes say)."""
    d = add_bushel_losses(ia, split=True)
    rows, per_year = [], {}
    for crop in st.CROPS.values():
        c = d[d[st.COL_CROP] == crop]
        tr, te = c[c["period"] == "train"], c[c["period"] == "test"]

        def _train(g):
            v = g[g["is_d2"] & g[COL_LOSS_BU].notna()]
            ok = len(v) >= st.MIN_D2_YEARS_FOR_SCORE
            return pd.Series({"bushels": g["is_d2"].mean() * v[COL_LOSS_BU].mean() if ok else np.nan,
                              "abs_penalty": -v[COL_APEN].mean() if ok else np.nan,
                              "acres": g[COL_ACRES].mean()})

        sc = tr.groupby(st.COL_FIPS).apply(_train, include_groups=False)
        t = te[te["is_d2"] & te[COL_LOSS_BU].notna()]
        n = t.groupby(st.COL_YEAR)[st.COL_FIPS].nunique()
        t = t[t[st.COL_YEAR].isin(n[n >= st.MIN_COUNTIES_PER_YEAR].index)].join(sc, on=st.COL_FIPS)
        t = t.dropna(subset=["bushels", "abs_penalty", "acres"])          # same counties for every score
        names = ["bushels", "abs_penalty", "acres"]
        series = {nm: {"rho": {}, "hit": {}} for nm in names}
        for y, g in t.groupby(st.COL_YEAR):
            if len(g) < st.MIN_COUNTIES_PER_YEAR:
                continue
            k = max(1, int(round(st.TOP_SHARE * len(g))))
            actual_top = set(g.nlargest(k, COL_LOSS_BU).index)
            for nm in names:
                series[nm]["rho"][y] = spearmanr(g[nm], g[COL_LOSS_BU]).correlation
                series[nm]["hit"][y] = len(set(g.nlargest(k, nm).index) & actual_top) / k
        per_year[crop] = series
        for nm in names:
            r, h = pd.Series(series[nm]["rho"]), pd.Series(series[nm]["hit"])
            row = {"crop": crop, "score": nm, "test years": len(r)}
            if len(r):
                row["Spearman [95% range] (chance 0)"] = st._fmt(*st._year_bootstrap(r)[:3])
                row["top-third hit rate [95% range] (chance 0.33)"] = st._fmt(*st._year_bootstrap(h)[:3])
                if nm != "acres":
                    dh = h - pd.Series(series["acres"]["hit"])
                    m, lo, hi, _ = st._year_bootstrap(dh)
                    row["hit rate minus acres-only [95% range]"] = st._fmt(m, lo, hi)
                    row["beats acres-only (range above 0)"] = bool(lo > 0)
            rows.append(row)
    return {"summary": pd.DataFrame(rows), "per_year": per_year}
