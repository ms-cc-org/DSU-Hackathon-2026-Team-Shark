"""
soil_tool.py - the engine behind the Soil Program Planner notebook and the Streamlit app
(soil_planner/app.py). Both call these functions, so they show the same numbers.

Reusable logic from notebooks 01-04, for Iowa corn and soybeans:
  * loading the Iowa rows with fips kept as text
  * drought codes (max_drought_severity: 3 = D2, 4 = D3, 5 = D4)
  * per-county historical drought statistics
  * one county's report card (summary + year-by-year rows)
  * the map and bar-chart figures
  * the evidence tables: the notebook 03 storage estimate and the notebook 04 held-out
    ranking test, recomputed with the same method and random seed.

Everything here is descriptive or an association across counties. Nothing here is a
measured program effect.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import spearmanr

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.data_loader import load_master, load_counties  # noqa: E402

# ----------------------------------------------------------------------------------
# Column names (verified against data/data_dictionary.md)
# ----------------------------------------------------------------------------------
COL_FIPS = "fips"
COL_COUNTY = "county_name"
COL_YEAR = "year"
COL_STATE = "state_alpha"
COL_CROP = "crop"
COL_YIELD = "yield_per_acre"
COL_YIELD_STATUS = "yield_status"
COL_ANOM = "yield_anomaly_pct"       # trend fitted on all 26 years (in-sample)
COL_SEV = "max_drought_severity"     # 0 none, 1 D0, 2 D1, 3 D2, 4 D3, 5 D4
COL_WEEKS_D2 = "weeks_in_d2_plus"
COL_HEAT = "extreme_heat_days"
COL_DSCI = "mean_dsci"
COL_PRECIP_ANOM = "precip_anomaly_pct"
COL_AWS = "aws_100cm_mm"
COL_DROUGHTY = "droughty_pct"
COL_NCCPI = "nccpi_crop"
COL_LON = "lon"                      # county centroid longitude, from counties.geojson

# ----------------------------------------------------------------------------------
# Drought codes and menus
# ----------------------------------------------------------------------------------
SEV_D2 = 3
SEV_D3 = 4
SEV_LABELS = {0: "none", 1: "D0", 2: "D1", 3: "D2", 4: "D3", 5: "D4"}
DROUGHT_DEFS = {"D2+ (severe or worse)": SEV_D2, "D3+ (extreme or worse)": SEV_D3}
CROPS = {"Corn": "CORN", "Soybeans": "SOYBEANS"}
METRICS = {
    "Drought penalty (2000-2025)": "drought_penalty_pct",
    "Drought frequency (share of reported years in drought)": "drought_share",
    "Drought-year yield loss (mean yield anomaly, %)": "drought_loss_pct",
    "Soil water storage (mm, top 100 cm)": COL_AWS,
}
FOCUS_STATE = "IA"
IOWA_FIPS_PREFIX = "19"


# ----------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------
def load_iowa() -> pd.DataFrame:
    """Iowa corn and soybean rows with a reported yield. fips is 5-character text."""
    df = load_master()
    ia = df[(df[COL_STATE] == FOCUS_STATE) & (df[COL_CROP].isin(CROPS.values())) & df[COL_YIELD].notna()].copy()
    assert ia[COL_FIPS].map(type).eq(str).all() and ia[COL_FIPS].str.len().eq(5).all(), "fips must be 5-char text"
    assert ia[COL_SEV].notna().all(), "unexpected NaN drought severity in Iowa corn/soybeans"
    return ia.reset_index(drop=True)


def iowa_geojson() -> dict:
    """counties.geojson restricted to Iowa features (feature id = fips)."""
    geo = load_counties()
    return {"type": "FeatureCollection",
            "features": [f for f in geo["features"] if str(f["id"]).startswith(IOWA_FIPS_PREFIX)]}


def county_centroid_lon() -> pd.DataFrame:
    """Rough county centroid longitude (mean of polygon vertices), one row per Iowa county."""
    def _lon(feature):
        g = feature["geometry"]
        polys = g["coordinates"] if g["type"] == "Polygon" else [p for mp in g["coordinates"] for p in mp]
        return np.array([pt for ring in polys for pt in ring])[:, 0].mean()
    return pd.DataFrame([(str(f["id"]), _lon(f)) for f in iowa_geojson()["features"]], columns=[COL_FIPS, COL_LON])


# ----------------------------------------------------------------------------------
# Per-county historical drought statistics
# ----------------------------------------------------------------------------------
def county_drought_stats(ia: pd.DataFrame, crop: str, sev_threshold: int) -> pd.DataFrame:
    """One row per Iowa county for one crop and one drought definition.

    drought_years        number of reported years with max_drought_severity >= sev_threshold
    drought_share        drought_years / years_reported
    drought_loss_pct     mean yield_anomaly_pct over the county's drought years (NaN if none)
    normal_year_anom     mean yield_anomaly_pct over the other years, for comparison
    confidence           "lower" when penalty_years_used < LOW_CONFIDENCE_YEARS, "standard" otherwise, "no score" without a score
    penalty_rank         1 = largest penalty among the counties with a score (NaN without a score)
    drought_penalty_pct  DEPLOYMENT drought-penalty score: mean penalty over the county's drought years
                         (at the chosen threshold) that have a valid penalty, using ALL years 2000-2025.
                         NaN if fewer than MIN_D2_YEARS_FOR_SCORE such years. The penalty's "normal"
                         always excludes D2+ years (see compute_penalties).
    penalty_years_used   number of drought years behind drought_penalty_pct
    """
    if COL_PEN not in ia.columns or (ia["period"] != "all").any():
        ia = compute_penalties(ia, split=False)
    sub = ia[ia[COL_CROP] == crop]

    def _one(g):
        d = g[g[COL_SEV] >= sev_threshold]
        dp = d[d[COL_PEN].notna()]
        return pd.Series({
            COL_COUNTY: g[COL_COUNTY].iloc[0],
            "years_reported": g[COL_YEAR].nunique(),
            "drought_years": d[COL_YEAR].nunique(),
            "drought_share": d[COL_YEAR].nunique() / g[COL_YEAR].nunique(),
            "drought_loss_pct": d[COL_ANOM].mean() if len(d) else np.nan,
            "normal_year_anom": g.loc[g[COL_SEV] < sev_threshold, COL_ANOM].mean(),
            "drought_penalty_pct": dp[COL_PEN].mean() if len(dp) >= MIN_D2_YEARS_FOR_SCORE else np.nan,
            "penalty_years_used": len(dp),
            "drought_year_list": ", ".join(str(y) for y in sorted(d[COL_YEAR].unique())),
            COL_AWS: g[COL_AWS].iloc[0],
            COL_DROUGHTY: g[COL_DROUGHTY].iloc[0],
            COL_NCCPI: g[COL_NCCPI].iloc[0],
        })

    out = sub.groupby(COL_FIPS).apply(_one, include_groups=False).reset_index()
    out["confidence"] = confidence_label(out["penalty_years_used"], out["drought_penalty_pct"].notna())
    ranked = out["drought_penalty_pct"].rank(method="first", na_option="keep")       # 1 = largest penalty (most negative)
    out["penalty_rank"] = ranked                                                      # NaN when there is no score
    out["crop"] = crop
    out["drought_definition"] = f"severity >= {sev_threshold} ({SEV_LABELS[sev_threshold]}+)"
    return out


def county_report_card(ia: pd.DataFrame, county: str, crop: str, sev_threshold: int) -> dict:
    """One county's report card. `county` may be a fips code or a county name.

    Returns {"summary": DataFrame (one column), "rows": DataFrame (one row per year)}.
    rows carry, for each drought year, the county's result relative to the state, its normal-year
    baseline (mean of its own non-D2+ years within +/- WINDOW years) and the drought penalty.
    """
    if COL_PEN not in ia.columns or (ia["period"] != "all").any():
        ia = compute_penalties(ia, split=False)
    sub = ia[ia[COL_CROP] == crop]
    if county in set(sub[COL_FIPS]):
        rows = sub[sub[COL_FIPS] == county]
    else:
        rows = sub[sub[COL_COUNTY] == county]
    if rows.empty:
        raise ValueError(f"no Iowa {crop} rows for county {county!r}")
    rows = rows.sort_values(COL_YEAR)
    rows = rows.assign(in_drought=rows[COL_SEV] >= sev_threshold,
                       severity_label=rows[COL_SEV].map(SEV_LABELS))
    rows["drought_penalty"] = rows[COL_PEN].where(rows["in_drought"])
    rows["normal_baseline"] = rows[COL_NORMAL].where(rows["in_drought"])
    stats = county_drought_stats(rows.drop(columns=["in_drought", "severity_label", "drought_penalty", "normal_baseline"]),
                                 crop, sev_threshold).iloc[0]
    pen_txt = ("n/a (fewer than %d drought years with a penalty)" % MIN_D2_YEARS_FOR_SCORE
               if np.isnan(stats["drought_penalty_pct"]) else f"{stats['drought_penalty_pct']:+.1f}%")
    summary = pd.DataFrame({
        "value": {
            "County": stats[COL_COUNTY],
            "FIPS": rows[COL_FIPS].iloc[0],
            "Crop": crop,
            "Drought definition": stats["drought_definition"],
            "Years with a reported yield": int(stats["years_reported"]),
            "Drought years": int(stats["drought_years"]),
            "Share of years in drought": f"{100 * stats['drought_share']:.0f}%",
            "Drought years (list)": stats["drought_year_list"] or "none",
            "Drought penalty score (2000-2025)": pen_txt,
            "Drought years used for the score": int(stats["penalty_years_used"]),
            "Mean yield anomaly in drought years": "n/a" if np.isnan(stats["drought_loss_pct"]) else f"{stats['drought_loss_pct']:+.1f}%",
            "Mean yield anomaly in other years": f"{stats['normal_year_anom']:+.1f}%",
            "Soil water storage, top 100 cm": f"{stats[COL_AWS]:.0f} mm",
            "Share of county on droughty soil": f"{stats[COL_DROUGHTY]:.0f}%",
            "Soil productivity index for this crop (0-1)": f"{stats[COL_NCCPI]:.2f}",
        }
    })
    cols = [COL_YEAR, COL_YIELD, COL_REL_STATE, "normal_baseline", "drought_penalty", COL_ANOM, "severity_label",
            "in_drought", COL_WEEKS_D2, COL_DSCI, COL_PRECIP_ANOM, COL_HEAT]
    return {"summary": summary, "rows": rows[cols].reset_index(drop=True)}


# ----------------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------------
def make_map(stats: pd.DataFrame, metric_col: str, metric_label: str, crop_label: str, def_label: str) -> go.Figure:
    """Iowa choropleth of one metric from county_drought_stats(). Counties with NaN are blank."""
    scale = {"drought_share": "YlOrRd", "drought_loss_pct": "RdYlGn", "drought_penalty_pct": "RdYlGn",
             COL_AWS: "YlGnBu"}.get(metric_col, "Viridis")
    hover = {COL_FIPS: True, "drought_penalty_pct": ":.1f", "penalty_years_used": True, "confidence": True,
             "drought_years": True, "drought_share": ":.2f", "drought_loss_pct": ":.1f", COL_AWS: ":.0f",
             "drought_year_list": True, metric_col: False}
    fig = px.choropleth(stats, geojson=iowa_geojson(), locations=COL_FIPS, color=metric_col,
                        color_continuous_scale=scale, hover_name=COL_COUNTY, hover_data=hover,
                        labels={"drought_years": "drought years", "drought_share": "share of years in drought",
                                "drought_penalty_pct": "drought penalty 2000-2025 (%)",
                                "penalty_years_used": "drought years used for the penalty",
                                "confidence": "confidence in the penalty",
                                "drought_loss_pct": "mean yield anomaly in drought years (%)",
                                COL_AWS: "soil water storage (mm)", "drought_year_list": "drought years (list)"})
    if metric_col in ("drought_loss_pct", "drought_penalty_pct"):
        lim = np.nanmax(np.abs(stats[metric_col])) if stats[metric_col].notna().any() else 1
        fig.update_coloraxes(cmin=-lim, cmax=lim)
    fig.update_geos(fitbounds="locations", visible=False)
    n_blank = int(stats[metric_col].isna().sum())
    if metric_col == "drought_penalty_pct":
        head = "Where drought hits hardest: historical drought penalty"
        blank = f"  ({n_blank} counties blank: fewer than {MIN_D2_YEARS_FOR_SCORE} drought years with a penalty)"
    elif metric_col == COL_AWS:
        head = "Soil water storage (does not change over time)"
        blank = f"  ({n_blank} counties blank: no soil record)"
    else:
        head = "Historical drought exposure"
        blank = f"  ({n_blank} counties blank: no drought years under this definition)"
    fig.update_layout(title=f"{head} - Iowa {crop_label.lower()}, {def_label}: {metric_label}" + (blank if n_blank else ""),
                      coloraxis_colorbar_title=metric_label.split(" (")[0], height=480,
                      margin=dict(l=10, r=10, t=60, b=10))
    return fig


def anomaly_bar(rows: pd.DataFrame, county_name: str, crop_label: str, def_label: str) -> go.Figure:
    """Yield anomaly by year for one county, drought years highlighted."""
    colors = np.where(rows["in_drought"], "#d7301f", "#9ecae1")
    fig = go.Figure(go.Bar(x=rows[COL_YEAR], y=rows[COL_ANOM], marker_color=colors,
                           customdata=np.column_stack([rows[COL_YIELD], rows["severity_label"], rows[COL_WEEKS_D2]]),
                           hovertemplate="%{x}: anomaly %{y:+.1f}%<br>yield %{customdata[0]:.1f} bu/acre"
                                         "<br>worst drought %{customdata[1]}, weeks at D2+ %{customdata[2]}<extra></extra>"))
    fig.add_hline(y=0, line_color="grey", line_dash="dot")
    fig.update_layout(title=f"{county_name} - {crop_label}: yield anomaly by year (red = drought year, {def_label})",
                      xaxis_title="year", yaxis_title="yield anomaly vs county trend (%)", height=380,
                      margin=dict(l=10, r=10, t=50, b=10))
    return fig


# ----------------------------------------------------------------------------------
# Evidence 1: storage estimate in drought years (notebook 03 method, same seed)
# ----------------------------------------------------------------------------------
N_BOOT = 5000
BOOT_SEED = 20261017
CI = (2.5, 97.5)
AWS_UNIT = 10.0
MIN_COUNTIES_PER_YEAR = 15
SPECS = {
    "A: storage only": [],
    "B: + drought weeks, heat": [COL_WEEKS_D2, COL_HEAT],
    "C: + longitude (region)": [COL_WEEKS_D2, COL_HEAT, COL_LON],
    "D: + soil productivity": [COL_WEEKS_D2, COL_HEAT, COL_LON, COL_NCCPI],
}


def _year_bootstrap(values, n_boot=N_BOOT, seed=BOOT_SEED, ci=CI):
    v = np.asarray(pd.Series(values).dropna(), dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    lo, hi = np.percentile(means, ci)
    return v.mean(), lo, hi, len(v)


def _ols_slope(d, controls, ycol):
    X = np.column_stack([np.ones(len(d)), d[[COL_AWS] + list(controls)].to_numpy(float)])
    y = d[ycol].to_numpy(float)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return np.nan
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta[1] * AWS_UNIT


def _fmt(m, lo, hi):
    return f"{m:+.2f} [{lo:+.2f}, {hi:+.2f}]"


def _storage_rows(d, crop, sev_threshold, specs, exclude_year=None, label=None):
    """Per-year slope of yield_anomaly_pct on storage across that year's drought counties (severity >= sev_threshold),
    averaged over years with >= MIN_COUNTIES_PER_YEAR such counties; plus the high-minus-low tertile contrast."""
    sub = d[(d[COL_CROP] == crop) & (d[COL_SEV] >= sev_threshold)]
    if exclude_year is not None:
        sub = sub[sub[COL_YEAR] != exclude_year]
    n = sub.groupby(COL_YEAR)[COL_FIPS].nunique()
    sub = sub[sub[COL_YEAR].isin(n[n >= MIN_COUNTIES_PER_YEAR].index)]
    rows = []
    for spec, controls in specs.items():
        sl = sub.groupby(COL_YEAR).apply(lambda g: _ols_slope(g, controls, COL_ANOM), include_groups=False)
        m, lo, hi, k = _year_bootstrap(sl)
        rows.append({"crop": crop, "definition": label, "specification": spec, "estimate [95% range]": _fmt(m, lo, hi),
                     "units": "pp per +10 mm storage", "drought years": k, "county-years": len(sub),
                     "years positive / negative": f"{int((sl > 0).sum())} / {int((sl < 0).sum())}",
                     "range excludes zero": bool(lo > 0 or hi < 0), "_mean": m, "_lo": lo, "_hi": hi})
    c = sub.groupby(COL_YEAR).apply(
        lambda g: g.loc[g["storage_group"] == "high", COL_ANOM].mean() - g.loc[g["storage_group"] == "low", COL_ANOM].mean()
        if (g["storage_group"] == "high").any() and (g["storage_group"] == "low").any() else np.nan,
        include_groups=False)
    m, lo, hi, k = _year_bootstrap(c)
    contrast_mask = sub["storage_group"].isin(["high", "low"]) & sub[COL_YEAR].isin(c.dropna().index)
    rows.append({"crop": crop, "definition": label, "specification": "high minus low storage third", "estimate [95% range]": _fmt(m, lo, hi),
                 "units": "pp of yield anomaly", "drought years": k, "county-years": int(contrast_mask.sum()),
                 "years positive / negative": f"{int((c > 0).sum())} / {int((c < 0).sum())}",
                 "range excludes zero": bool(lo > 0 or hi < 0), "_mean": m, "_lo": lo, "_hi": hi})
    return rows


def _with_storage_groups(ia):
    d = ia.drop(columns=[COL_LON], errors="ignore").merge(county_centroid_lon(), on=COL_FIPS, how="left")
    aws_by_county = d.groupby(COL_FIPS)[COL_AWS].first()
    grp = pd.qcut(aws_by_county, 3, labels=["low", "middle", "high"]).astype(str).rename("storage_group")
    return d.merge(grp, left_on=COL_FIPS, right_index=True)


def storage_effect_results(ia: pd.DataFrame) -> pd.DataFrame:
    """Notebook 03 main table (D2+): per-year slope of yield_anomaly_pct on storage across that year's D2+ counties,
    averaged over years, 95% range from resampling years. Units: pp of yield anomaly per +10 mm storage.
    Also the high-minus-low tertile contrast (pp). In-sample: yield_anomaly_pct uses all 26 years."""
    d = _with_storage_groups(ia)
    rows = []
    for crop in CROPS.values():
        rows += _storage_rows(d, crop, SEV_D2, SPECS, label="D2+ (main)")
    return pd.DataFrame(rows).drop(columns=["definition"])


SENS_SPEC = {"C: + longitude (region)": SPECS["C: + longitude (region)"]}
SENS_EXCLUDE_YEAR = 2012


def storage_effect_sensitivity(ia: pd.DataFrame) -> pd.DataFrame:
    """Notebook 03 sensitivity: D3+ drought years, specification C and the tertile contrast, with and without 2012."""
    d = _with_storage_groups(ia)
    rows = []
    for crop in CROPS.values():
        rows += _storage_rows(d, crop, SEV_D3, SENS_SPEC, label="D3+")
        rows += _storage_rows(d, crop, SEV_D3, SENS_SPEC, exclude_year=SENS_EXCLUDE_YEAR, label=f"D3+ excl. {SENS_EXCLUDE_YEAR}")
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------
# Evidence 2: held-out ranking test and placebo (notebook 04 method, same seed)
# ----------------------------------------------------------------------------------
TRAIN_YEARS = range(2000, 2016)
TEST_YEARS = range(2016, 2026)
MIN_TRAIN_YEARS_FOR_TREND = 8
MIN_D2_TRAIN_YEARS_FOR_LOSS = 3
TOP_SHARE = 1 / 3
SCORE_DIRECTION = {"drought_freq": +1, "drought_loss": -1, "storage": -1, "combined": +1}


def _strict_anomaly(ia: pd.DataFrame) -> pd.DataFrame:
    """Trend fitted on TRAIN years only, extrapolated to TEST years; relative loss = anomaly - yearly state median."""
    d = ia.drop(columns=[COL_LON], errors="ignore").merge(county_centroid_lon(), on=COL_FIPS, how="left").copy()
    d["split"] = np.where(d[COL_YEAR].isin(TRAIN_YEARS), "train", "test")

    def _fit(g):
        t = g[g["split"] == "train"]
        if len(t) < MIN_TRAIN_YEARS_FOR_TREND:
            return pd.Series({"slope": np.nan, "intercept": np.nan})
        s, i = np.polyfit(t[COL_YEAR].to_numpy(float), t[COL_YIELD].to_numpy(float), 1)
        return pd.Series({"slope": s, "intercept": i})

    tr = d.groupby([COL_CROP, COL_FIPS]).apply(_fit, include_groups=False).reset_index()
    d = d.merge(tr, on=[COL_CROP, COL_FIPS]).dropna(subset=["slope"])
    d["fitted_strict"] = d["intercept"] + d["slope"] * d[COL_YEAR]
    d["anomaly_strict"] = 100 * (d[COL_YIELD] - d["fitted_strict"]) / d["fitted_strict"]
    d["relative_loss"] = d["anomaly_strict"] - d.groupby([COL_CROP, COL_YEAR])["anomaly_strict"].transform("median")
    return d


def _train_scores(d: pd.DataFrame) -> pd.DataFrame:
    train = d[d["split"] == "train"]

    def _one(g):
        dr = g[g[COL_SEV] >= SEV_D2]
        return pd.Series({
            "drought_freq": (g[COL_SEV] >= SEV_D2).mean(),
            "drought_loss": dr["anomaly_strict"].mean() if len(dr) >= MIN_D2_TRAIN_YEARS_FOR_LOSS else np.nan,
            "storage": g[COL_AWS].iloc[0]})

    s = train.groupby([COL_CROP, COL_FIPS]).apply(_one, include_groups=False).reset_index()
    s["combined"] = (s.groupby(COL_CROP)["drought_freq"].rank(pct=True)
                     + s.groupby(COL_CROP)["drought_loss"].transform(lambda x: (-x).rank(pct=True))) / 2
    for name, direction in SCORE_DIRECTION.items():
        s[f"priority_{name}"] = direction * s[name]
    return s


def ranking_test_results(ia: pd.DataFrame) -> dict:
    """Returns {'summary': DataFrame, 'placebo': DataFrame, 'test_years': dict}."""
    d = _strict_anomaly(ia)
    scores = _train_scores(d)
    test = d[d["split"] == "test"]
    summary, placebo, test_years = [], [], {}
    for crop in CROPS.values():
        s = scores[scores[COL_CROP] == crop].set_index(COL_FIPS)
        tc = test[test[COL_CROP] == crop]
        n = tc[tc[COL_SEV] >= SEV_D2].groupby(COL_YEAR)[COL_FIPS].nunique()
        kept = n[n >= MIN_COUNTIES_PER_YEAR]
        zero_years = [y for y in TEST_YEARS if y not in n.index]
        test_years[crop] = {"usable": {int(y): int(k) for y, k in kept.items()}, "no_drought": zero_years}
        t = tc[(tc[COL_SEV] >= SEV_D2) & tc[COL_YEAR].isin(kept.index)]
        for name in SCORE_DIRECTION:
            pcol = f"priority_{name}"
            tt = t.join(s[[pcol]], on=COL_FIPS)
            rho, hit = [], []
            for _, g in tt.groupby(COL_YEAR):
                g = g[[pcol, "relative_loss"]].dropna()
                if len(g) < MIN_COUNTIES_PER_YEAR:
                    continue
                rho.append(spearmanr(g[pcol], -g["relative_loss"]).correlation)
                k = max(1, int(round(TOP_SHARE * len(g))))
                hit.append(len(set(g.nlargest(k, pcol).index) & set(g.nsmallest(k, "relative_loss").index)) / k)
            m1, lo1, hi1, k1 = _year_bootstrap(rho)
            m2, lo2, hi2, _ = _year_bootstrap(hit)
            summary.append({"crop": crop, "score": name,
                            "Spearman [95% range] (chance 0)": _fmt(m1, lo1, hi1),
                            "top-third hit rate [95% range] (chance 0.33)": _fmt(m2, lo2, hi2),
                            "test years": k1,
                            "beats chance (whole range above chance)": bool(lo1 > 0 and lo2 > TOP_SHARE)})
        for y in zero_years:
            g = tc[tc[COL_YEAR] == y].join(s[[f"priority_{n_}" for n_ in SCORE_DIRECTION]], on=COL_FIPS)
            r = {"crop": crop, "year": y, "counties": len(g)}
            for name in SCORE_DIRECTION:
                gg = g[[f"priority_{name}", "relative_loss"]].dropna()
                r[f"Spearman {name}"] = round(spearmanr(gg[f"priority_{name}"], -gg["relative_loss"]).correlation, 2)
            r["storage slope per 10 mm"] = round(_ols_slope(g, [COL_HEAT, COL_LON], "anomaly_strict"), 2)
            placebo.append(r)
    return {"summary": pd.DataFrame(summary), "placebo": pd.DataFrame(placebo), "test_years": test_years}


# ----------------------------------------------------------------------------------
# Drought penalty (notebook 05 method): no trend fitting, cancels persistent county differences
# ----------------------------------------------------------------------------------
WINDOW = 3                       # +/- years around the target year used for the county's "normal"
MIN_NORMAL_YEARS = 2             # minimum non-D2+ years in the window
MIN_D2_YEARS_FOR_SCORE = 3       # minimum D2+ years with a valid penalty, for both the TRAIN score and the DEPLOYMENT score
COL_R = "r"                      # log(yield) - statewide median log(yield) that year, same crop
COL_PEN = "penalty_pct"          # drought penalty (D2+ rows) or placebo (non-D2+ rows), approx percent
COL_NORMAL = "normal_pct"        # the county's normal (mean r of its non-D2+ years in the window), approx percent
COL_REL_STATE = "rel_state_pct"  # 100 * (exp(r) - 1): the county's yield relative to the state median that year
COL_KIND = "kind"                # "drought" or "placebo"
_DERIVED = ["log_yield", COL_R, "period", "is_d2", "n_normal", "normal_log", "x_log", COL_PEN, COL_NORMAL, COL_REL_STATE, COL_KIND]

HEADLINE = """**What we found.** Counties that lost more than their own normal in past droughts tended to lose more in the next ones. We built a drought-penalty score from 2000–2015 and tested it on 2016–2025 droughts it had never seen. Of the counties it ranked in the top third, about 45% (corn) and 49% (soybeans) were among the hardest hit, compared with 33% by chance. The corn ranking held up in every test year; the soybean ranking was less consistent.

**What we did not find.** Soil water storage leans toward smaller losses, but its effect could not be separated from zero, so we don't recommend targeting programs by storage alone.

**How to use this.** The priority list shows where drought has hurt most and is likely to hurt again. Use it as a starting point for site visits and outreach, not as proof that a soil program will reduce losses."""
HEADLINE_CORN_HIT_RATE = 0.45    # figures quoted in HEADLINE; the planner's check cells compare them with the computed values
HEADLINE_SOY_HIT_RATE = 0.49
LOW_CONFIDENCE_YEARS = 6         # a priority-list score built on fewer drought years than this is flagged "lower" confidence
CONFIDENCE_LOWER, CONFIDENCE_STANDARD, CONFIDENCE_NONE = "lower", "standard", "no score"


def confidence_label(drought_years_used, has_score=True):
    """"lower" when a score rests on fewer than LOW_CONFIDENCE_YEARS drought years, "standard" otherwise,
    "no score" where has_score is False. Works element-wise on Series/arrays and on scalars."""
    years = np.asarray(drought_years_used, dtype=float)
    label = np.where(years < LOW_CONFIDENCE_YEARS, CONFIDENCE_LOWER, CONFIDENCE_STANDARD)
    label = np.where(np.asarray(has_score, dtype=bool), label, CONFIDENCE_NONE)
    return label if label.ndim else str(label)


def load_iowa_with_lon() -> pd.DataFrame:
    """load_iowa() plus the county centroid longitude."""
    ia = load_iowa().merge(county_centroid_lon(), on=COL_FIPS, how="left")
    assert ia[COL_LON].notna().all()
    return ia


def _local_penalties(sub: pd.DataFrame, period_col: str = "period") -> pd.DataFrame:
    """One crop. For every county-year: r minus the mean r of the county's OTHER non-D2+ years within
    +/- WINDOW years in the same period. NaN when fewer than MIN_NORMAL_YEARS normal years exist."""
    out = []
    for fips, g in sub.groupby(COL_FIPS):
        g = g.set_index(COL_YEAR).sort_index()
        yrs = g.index.to_numpy()
        for t in yrs:
            same = ((g[period_col] == g.loc[t, period_col]).to_numpy()
                    & (np.abs(yrs - t) <= WINDOW) & (yrs != t) & (~g["is_d2"].to_numpy()))
            normals = g.loc[yrs[same], COL_R]
            ok = len(normals) >= MIN_NORMAL_YEARS
            out.append({COL_FIPS: fips, COL_YEAR: t, "n_normal": len(normals),
                        "normal_log": normals.mean() if ok else np.nan,
                        "x_log": g.loc[t, COL_R] - normals.mean() if ok else np.nan})
    return pd.DataFrame(out)


def compute_penalties(ia: pd.DataFrame, split: bool = True) -> pd.DataFrame:
    """Add r, the drought penalty / placebo and the normal baseline to every Iowa row.

    split=True : normals never cross the TRAIN (2000-2015) / TEST (2016-2025) boundary. Use for the held-out test.
    split=False: one period, all 26 years. Use for the DEPLOYMENT score and the maps.
    Drought rows are D2+ (SEV_D2). Non-D2+ rows get the placebo value instead.
    """
    d = ia.drop(columns=[c for c in _DERIVED if c in ia.columns]).copy()
    assert (d[COL_YIELD] > 0).all()
    d["log_yield"] = np.log(d[COL_YIELD])
    d[COL_R] = d["log_yield"] - d.groupby([COL_CROP, COL_YEAR])["log_yield"].transform("median")
    d["period"] = np.where(d[COL_YEAR].isin(TRAIN_YEARS), "train", "test") if split else "all"
    d["is_d2"] = d[COL_SEV] >= SEV_D2
    pen = pd.concat([_local_penalties(d[d[COL_CROP] == c]).assign(**{COL_CROP: c}) for c in CROPS.values()])
    d = d.merge(pen, on=[COL_CROP, COL_FIPS, COL_YEAR], how="left")
    d[COL_PEN] = 100 * (np.exp(d["x_log"]) - 1)
    d[COL_NORMAL] = 100 * (np.exp(d["normal_log"]) - 1)
    d[COL_REL_STATE] = 100 * (np.exp(d[COL_R]) - 1)
    d[COL_KIND] = np.where(d["is_d2"], "drought", "placebo")
    return d


def deployment_penalty_scores(ia_all: pd.DataFrame, crop: str) -> pd.DataFrame:
    """DEPLOYMENT drought-penalty score, one row per county: mean drought penalty over the county's D2+ years
    with a valid penalty, using ALL years 2000-2025 (compute_penalties(split=False)). NaN with fewer than
    MIN_D2_YEARS_FOR_SCORE such years. This is NOT the TRAIN-only (2000-2015) score used in the held-out test;
    that one is penalty_training_scores()."""
    if COL_PEN not in ia_all.columns or (ia_all["period"] != "all").any():
        ia_all = compute_penalties(ia_all, split=False)
    sub = ia_all[ia_all[COL_CROP] == crop]

    def _one(g):
        d = g[g["is_d2"] & g[COL_PEN].notna()]
        return pd.Series({COL_COUNTY: g[COL_COUNTY].iloc[0],
                          "drought_years_total": int(g["is_d2"].sum()),
                          "drought_years_used": len(d),
                          "penalty_score": d[COL_PEN].mean() if len(d) >= MIN_D2_YEARS_FOR_SCORE else np.nan,
                          COL_AWS: g[COL_AWS].iloc[0]})

    out = sub.groupby(COL_FIPS).apply(_one, include_groups=False).reset_index()
    out["has_score"] = out["penalty_score"].notna()
    out = out.sort_values("penalty_score", na_position="last").reset_index(drop=True)
    out["rank"] = np.where(out["has_score"], np.arange(1, len(out) + 1), np.nan)   # 1 = largest penalty
    out["crop"] = crop
    return out


def priority_list(scores: pd.DataFrame, share: float = TOP_SHARE) -> pd.DataFrame:
    """Top `share` of scored counties by deployment drought penalty (most negative first; order as in
    deployment_penalty_scores). `drought_years_used` is the number of drought years behind each score;
    `confidence` is "lower" when that number is below LOW_CONFIDENCE_YEARS, else "standard"."""
    s = scores[scores["has_score"]]
    k = max(1, int(round(share * len(s))))
    top = s.head(k).reset_index(drop=True).copy()
    top["confidence"] = confidence_label(top["drought_years_used"])
    return top


# ---- Step 2 of notebook 05: storage vs drought penalty, with placebo ----
PEN_SPECS = {"storage only": [], "storage + longitude": [COL_LON]}


def penalty_storage_results(ia_split: pd.DataFrame):
    """Per year with >= MIN_COUNTIES_PER_YEAR rows, slope of the penalty on storage (per +10 mm), averaged over
    years with a year bootstrap; separately for drought rows and placebo rows. Returns (table, per-year slopes)."""
    rows, slopes = [], {}
    for crop in CROPS.values():
        for kind in ["drought", "placebo"]:
            sub = ia_split[(ia_split[COL_CROP] == crop) & (ia_split[COL_KIND] == kind) & ia_split[COL_PEN].notna()]
            n = sub.groupby(COL_YEAR)[COL_FIPS].nunique()
            kept = n[n >= MIN_COUNTIES_PER_YEAR]
            sub = sub[sub[COL_YEAR].isin(kept.index)]
            for spec, ctrl in PEN_SPECS.items():
                sl = sub.groupby(COL_YEAR).apply(lambda g: _ols_slope(g, ctrl, COL_PEN), include_groups=False)
                slopes[(crop, kind, spec)] = pd.DataFrame({"n_counties": kept, "slope_per_10mm": sl})
                m, lo, hi, k = _year_bootstrap(sl)
                rows.append({"crop": crop, "spec": spec, "kind": kind, "estimate [95% range]": _fmt(m, lo, hi),
                             "n_years": k, "county_years": len(sub),
                             "years +/-": f"{int((sl > 0).sum())} / {int((sl < 0).sum())}",
                             "excludes_zero": bool(lo > 0 or hi < 0), "_mean": m, "_lo": lo, "_hi": hi})
    return pd.DataFrame(rows), slopes


# ---- Step 3 of notebook 05: held-out ranking test with placebos ----
PEN_SCORE_DIR = {"penalty_score": -1, "drought_freq": +1, "storage": -1}   # priority = direction * score
REAL_TEST = "real: drought years"
PLACEBO_ZERO = "placebo: zero-drought years"
PLACEBO_ALL = "placebo: non-D2+ counties, all test years"


def penalty_training_scores(ia_split: pd.DataFrame) -> pd.DataFrame:
    """TRAIN-only (2000-2015) scores per county: penalty_score (mean drought penalty over D2+ TRAIN years with a
    valid penalty, needs >= MIN_D2_YEARS_FOR_SCORE), drought_freq, storage; plus priority_* columns (higher = more deserving)."""
    train = ia_split[ia_split["period"] == "train"]

    def _one(g):
        d = g[g["is_d2"] & g[COL_PEN].notna()]
        return pd.Series({"n_d2_train": d[COL_YEAR].nunique(),
                          "penalty_score": d[COL_PEN].mean() if len(d) >= MIN_D2_YEARS_FOR_SCORE else np.nan,
                          "drought_freq": g["is_d2"].mean(),
                          "storage": g[COL_AWS].iloc[0]})

    s = train.groupby([COL_CROP, COL_FIPS]).apply(_one, include_groups=False).reset_index()
    s = s.merge(ia_split[[COL_FIPS, COL_COUNTY]].drop_duplicates(), on=COL_FIPS)
    for name, direction in PEN_SCORE_DIR.items():
        s[f"priority_{name}"] = direction * s[name]
    return s


def _eval_year(d, pcol):
    d = d[[pcol, COL_PEN]].dropna()
    n = len(d)
    if n < MIN_COUNTIES_PER_YEAR:
        return pd.Series({"n": n, "spearman": np.nan, "top_third_hit": np.nan})
    rho = spearmanr(d[pcol], -d[COL_PEN]).correlation          # positive = higher priority goes with bigger loss
    k = max(1, int(round(TOP_SHARE * n)))
    hit = len(set(d.nlargest(k, pcol).index) & set(d.nsmallest(k, COL_PEN).index)) / k
    return pd.Series({"n": n, "spearman": rho, "top_third_hit": hit})


def _run_ranking(sub, scores_crop, crop, label):
    per_year, summ = {}, []
    for name in PEN_SCORE_DIR:
        pcol = f"priority_{name}"
        tt = sub.join(scores_crop[[pcol]], on=COL_FIPS)
        py = tt.groupby(COL_YEAR).apply(lambda d: _eval_year(d, pcol), include_groups=False)
        py = py[py["spearman"].notna()]
        per_year[name] = py
        for metric, chance in [("spearman", 0.0), ("top_third_hit", TOP_SHARE)]:
            m, lo, hi, k = _year_bootstrap(py[metric])
            summ.append({"crop": crop, "test": label, "score": name, "metric": metric,
                         "mean [95% range]": _fmt(m, lo, hi), "n_years": k, "chance": chance,
                         "years_above_chance": int((py[metric] > chance).sum()),
                         "range_above_chance": bool(lo > chance), "_mean": m, "_lo": lo, "_hi": hi})
    return per_year, pd.DataFrame(summ)


def penalty_ranking_results(ia_split: pd.DataFrame) -> dict:
    """Held-out test of the TRAIN scores on TEST drought years, plus two placebos.
    Returns {"scores", "results" {(crop, label): (per_year, summary)}, "summary", "test_years"}."""
    scores = penalty_training_scores(ia_split)
    test = ia_split[ia_split["period"] == "test"]
    results, info = {}, {}
    for crop in CROPS.values():
        sc = scores[scores[COL_CROP] == crop].set_index(COL_FIPS)
        tc = test[(test[COL_CROP] == crop) & test[COL_PEN].notna()]
        n_d2 = tc[tc["is_d2"]].groupby(COL_YEAR)[COL_FIPS].nunique().reindex(list(TEST_YEARS), fill_value=0)
        usable = n_d2[n_d2 >= MIN_COUNTIES_PER_YEAR]
        zero = n_d2[n_d2 == 0].index.tolist()
        info[crop] = {"usable": {int(y): int(n) for y, n in usable.items()}, "zero_drought": [int(y) for y in zero],
                      "other": {int(y): int(n) for y, n in n_d2[(n_d2 > 0) & (n_d2 < MIN_COUNTIES_PER_YEAR)].items()}}
        results[(crop, REAL_TEST)] = _run_ranking(tc[tc["is_d2"]], sc, crop, REAL_TEST)
        results[(crop, PLACEBO_ZERO)] = _run_ranking(tc[(~tc["is_d2"]) & tc[COL_YEAR].isin(zero)], sc, crop, PLACEBO_ZERO)
        results[(crop, PLACEBO_ALL)] = _run_ranking(tc[~tc["is_d2"]], sc, crop, PLACEBO_ALL)
    summary = pd.concat([v[1] for v in results.values()], ignore_index=True)
    return {"scores": scores, "results": results, "summary": summary, "test_years": info}


def ranking_summary_table(summary: pd.DataFrame, crop: str) -> pd.DataFrame:
    """Real test and both placebos side by side for one crop (mean [95% range] per score and metric)."""
    v = summary[summary["crop"] == crop]
    tab = v.pivot(index=["score", "metric"], columns="test", values="mean [95% range]")[[REAL_TEST, PLACEBO_ZERO, PLACEBO_ALL]]
    tab.insert(0, "chance", v.drop_duplicates("metric").set_index("metric")["chance"]
               .reindex(tab.index.get_level_values("metric")).round(2).values)
    ny = v.pivot(index=["score", "metric"], columns="test", values="n_years")
    tab["n_years (real / placebo-0 / placebo-all)"] = (ny[REAL_TEST].astype(str) + " / " + ny[PLACEBO_ZERO].astype(str)
                                                       + " / " + ny[PLACEBO_ALL].astype(str))
    return tab.loc[[(s, m) for s in PEN_SCORE_DIR for m in ["spearman", "top_third_hit"]]]


METHODS_NOTE = """### How we tested this

**Comparing counties fairly.** In Iowa, soil water storage runs high in the west and low in the east, so comparing high- and low-storage counties also compares regions, weather and farming. We added controls one at a time; each one reduced the soybean association, which fell to about a quarter of its raw size after all three. *(Bueno de Mesquita & Fowler, ch. 10; Pearl & Mackenzie, ch. 4)*

**Comparing each county with itself.** The drought penalty compares a county's yield in a drought year with its own nearby normal years, relative to the rest of the state. This cancels anything permanent about a county. Our first test failed because extrapolated yield trends differed by region, which breaks the assumption this kind of comparison relies on. *(Bueno de Mesquita & Fowler, ch. 13; Gelman, Hill & Vehtari, §21.4)*

**Checking the test itself.** We ran each test in years with no drought, where a real drought score should predict nothing. Our first test "predicted" losses there, so we rejected it. The drought-penalty score showed nothing in the non-drought counties of every test year. The stricter check, using only years with no drought anywhere in Iowa, covers just two or three years and is too short to judge.

**Reversion to the mean.** Counties with the worst early drought record did relatively better later even without any real change, which is why raw drought frequency ranked counties in the wrong direction. *(Bueno de Mesquita & Fowler, ch. 8; Gelman, Hill & Vehtari, §6.5)*

**Uncertainty.** Our ranges come from resampling whole years, because counties in the same year share the same weather. A range that includes zero means the data can't rule out "no effect," not that there is none. Of our 26 storage estimates, one range excluded zero; it rested on 5 years and pointed the opposite way from the matching regression, so we don't treat it as a finding. *(Bueno de Mesquita & Fowler, ch. 6–7; Gelman, Hill & Vehtari, §4.5, §5.4)*

**Why some counties are "lower confidence."** Every score mixes real signal with noise, and a score built on only a few drought years carries more noise. Extreme scores built on little data are the most likely to drift back toward average in future droughts, which is why we flag counties whose score rests on fewer than 6 drought years. *(Bueno de Mesquita & Fowler, ch. 8)*

**References.** Bueno de Mesquita, E. & Fowler, A. (2021). *Thinking Clearly with Data.* Princeton University Press, ch. 6–8, 10, 13, 15–17. · Gelman, A., Hill, J. & Vehtari, A. (2020). *Regression and Other Stories.* Cambridge University Press. · Pearl, J. & Mackenzie, D. (2018). *The Book of Why.* Basic Books."""

LIMITS_NOTE = """- **Association, not program effect.** The drought penalty and soil water storage are properties of counties as they are. Comparing counties is not the same as measuring what a conservation practice would do on a given field. Nothing here estimates a program's effect, and the priority list shows where drought has hurt most, not where a program would help most.
- **Few test years, and no statewide drought among them.** The held-out test rests on 5 to 7 drought years (2017–2024), all partial-state events. No 2012-type drought that covered every county is in the test set, and that is the case the office cares most about. The ranges in section 3 are wide for that reason.
- **The score was redesigned once and tested once.** The first ranking test (notebook 04) failed its placebo check. The drought-penalty score was designed to fix that and then tested a single time on the same 2016–2025 years. One pass is encouraging, not proof; a result chosen after one failure deserves more caution than a result that was right the first time.
- **The zero-drought placebo is too thin to judge.** Only three test years (two for soybeans) had no drought anywhere in Iowa. The broader placebo on non-drought counties in every test year is clean, but the strict one cannot confirm or deny anything.
- **Storage could not be separated from zero.** Storage leans toward smaller drought penalties and shows nothing in the placebo, but every range includes zero, Iowa's storage range is narrow (about 154 to 206 mm), and high-storage counties sit in the west while low-storage counties sit in the east, so storage and region are entangled.
- **Irrigation.** The data say Iowa is rainfed only through documentation. There is no irrigation column to confirm it county by county.
- **Yield data thin out after 2022.** Fewer counties report yields in recent years, so recent drought penalties are missing for more counties, especially soybeans.
- **Extra soil and practice data are context only.** The surface-soil properties (September 2026 SSURGO release) and the Census of Agriculture practice shares (2017 and 2022) shown in the county panel were not tested against drought losses and play no part in the ranking or the evidence.
- Our score measures where drought losses have occurred, not where soil programs would reduce them. That is only part of the office's mission (Bueno de Mesquita & Fowler, ch. 16).
- The lessons come from Iowa, 2000–2025. Future droughts, new practices, or other states may not behave the same way.
- A pre-registered replication on Nebraska's rain-fed counties could not be run: irrigation leaves only 13–18 mostly-dryland counties, below our pre-set minimum of 20."""

NEXT_STEPS_NOTE = """**Next steps**
- **Test whether programs work.** Once the office funds programs in some counties, compare how drought penalties change in funded versus unfunded counties, before and after. That is a true difference-in-differences test of program impact (Bueno de Mesquita & Fowler, ch. 13).
- **Use the lever, not just the context.** Compare the change in cover-crop and no-till adoption between the 2017 and 2022 Censuses with the change in each county's drought penalty.
- **Measure drought timing.** The master dataset already includes a seasonal mean drought intensity (`mean_dsci`, 0–500 scale) that could replace the single D2+ threshold; the weekly Drought Monitor maps would add timing within the season, to focus on drought during critical growth months.
- **Limited evidence is not a reason to do nothing.** The storage result was inconclusive, but not acting is also a decision; local evaluation of practices in priority counties is a reasonable response (Bueno de Mesquita & Fowler, ch. 17)."""


# ----------------------------------------------------------------------------------
# Context data for the county panel: DISPLAY ONLY. Nothing here enters a score, a ranking or an evidence table.
# ----------------------------------------------------------------------------------
PRACTICES_NOTE = """**Practices to consider** *(general conservation guidance, not tested in this analysis)*
This county lost more than the rest of Iowa in past droughts. Practices that soil conservation programs commonly support to help soils take in and hold water include cover crops, no-till or reduced tillage, and practices that build soil organic matter over time. Whether they would reduce drought losses here was not tested; evaluate locally with NRCS staff and farmers."""

DATA_NOTE = ("Extra soil properties from the September 2026 SSURGO release (USDA NRCS Soil Data Access); practice shares "
             "from the USDA Census of Agriculture, 2017 and 2022 (county data for 2012 is not published). Shown as context "
             "only; not tested against drought losses.")

SOIL_EXTRA_CSV = _ROOT / "soil_planner/extra_data/iowa_soil_extra.csv"
PRACTICES_CSV = _ROOT / "soil_planner/extra_data/iowa_conservation_practices.csv"
# column -> (label, unit, decimals). aws comes from the master dataset, the others from iowa_soil_extra.csv.
SOIL_CONTEXT_VARS = {
    COL_AWS: ("Soil water storage, top 100 cm", "mm", 0),
    "om_surface_pct": ("Organic matter, surface layer", "%", 1),
    "clay_surface_pct": ("Clay, surface layer", "%", 0),
    "sand_surface_pct": ("Sand, surface layer", "%", 0),
    "slope_pct": ("Slope", "%", 1),
}
PRACTICE_VARS = {
    "cover_crop_share": "Cover crops (share of harvested cropland)",
    "no_till_share": "No-till (share of tilled cropland)",
    "reduced_till_share": "Reduced tillage (share of tilled cropland)",
    "conventional_share": "Conventional tillage (share of tilled cropland)",
}


@lru_cache(maxsize=1)
def load_soil_extra() -> pd.DataFrame:
    """soil_planner/extra_data/iowa_soil_extra.csv, one row per Iowa county, fips as 5-character text."""
    df = pd.read_csv(SOIL_EXTRA_CSV, dtype={COL_FIPS: str})
    assert df[COL_FIPS].str.len().eq(5).all() and not df[COL_FIPS].duplicated().any()
    return df


@lru_cache(maxsize=1)
def load_conservation_practices() -> pd.DataFrame:
    """soil_planner/extra_data/iowa_conservation_practices.csv, one row per county x census year, fips as text."""
    df = pd.read_csv(PRACTICES_CSV, dtype={COL_FIPS: str})
    assert df[COL_FIPS].str.len().eq(5).all()
    df[COL_YEAR] = df[COL_YEAR].astype(int)
    return df


def _percentile(values: pd.Series, x: float) -> float:
    """Share (0-100) of Iowa counties whose value is at or below x."""
    v = values.dropna()
    return float(100 * (v <= x).mean()) if len(v) and not np.isnan(x) else np.nan


def soil_context(ia: pd.DataFrame, fips: str) -> pd.DataFrame:
    """One row per soil variable for one county: value, Iowa county median, percentile among the 99 counties.
    aws_100cm_mm is the master dataset's value (one per county in `ia`); the rest come from load_soil_extra().
    The last row is the dominant drainage class (text) with its share of the county and how many Iowa counties
    share that dominant class."""
    aws = ia.groupby(COL_FIPS)[COL_AWS].first().rename(COL_AWS).reset_index()
    d = load_soil_extra().merge(aws, on=COL_FIPS, how="left")
    row = d[d[COL_FIPS] == fips]
    if row.empty:
        raise ValueError(f"no extra soil data for county {fips!r}")
    row = row.iloc[0]
    out = []
    for col, (label, unit, dec) in SOIL_CONTEXT_VARS.items():
        out.append({"variable": label, "unit": unit, "decimals": dec, "county": float(row[col]),
                    "iowa_median": float(d[col].median()), "percentile": _percentile(d[col], row[col])})
    same = int((d["drainage_dominant"] == row["drainage_dominant"]).sum())
    out.append({"variable": "Dominant drainage class", "unit": "", "decimals": 0,
                "county": f"{row['drainage_dominant']} ({row['drainage_dominant_share_pct']:.0f}% of county)",
                "iowa_median": f"{same} of {len(d)} Iowa counties share this class", "percentile": np.nan})
    return pd.DataFrame(out)


def practices_context(fips: str) -> pd.DataFrame:
    """One row per practice share for one county, with the county value and the Iowa county median in the first and
    last census years available and the county's change between them (percentage points). Shares are fractions."""
    p = load_conservation_practices()
    years = sorted(p[COL_YEAR].unique())
    y0, y1 = years[0], years[-1]
    row = p[p[COL_FIPS] == fips].set_index(COL_YEAR)
    if row.empty:
        raise ValueError(f"no practice data for county {fips!r}")
    out = []
    for col, label in PRACTICE_VARS.items():
        v0 = float(row[col].get(y0, np.nan)); v1 = float(row[col].get(y1, np.nan))
        out.append({"variable": label, "first_year": y0, "last_year": y1,
                    "county_first": v0, "iowa_median_first": float(p.loc[p[COL_YEAR] == y0, col].median()),
                    "county_last": v1, "iowa_median_last": float(p.loc[p[COL_YEAR] == y1, col].median()),
                    "change_pp": 100 * (v1 - v0), "percentile_last": _percentile(p.loc[p[COL_YEAR] == y1, col], v1)})
    return pd.DataFrame(out)


def headline_metrics(summary: pd.DataFrame, crop: str) -> dict:
    """The held-out top-third hit rate of the penalty score for one crop (real test), with its range, the number of
    test years and the chance level. From penalty_ranking_results()["summary"]."""
    r = summary[(summary["crop"] == crop) & (summary["test"] == REAL_TEST) & (summary["score"] == "penalty_score")
                & (summary["metric"] == "top_third_hit")].iloc[0]
    return {"hit_rate": float(r["_mean"]), "lo": float(r["_lo"]), "hi": float(r["_hi"]),
            "n_years": int(r["n_years"]), "chance": float(r["chance"])}


def priority_reasons(ia_all: pd.DataFrame, scores: pd.DataFrame, fips: str, crop: str) -> list[str]:
    """Data-based reasons a county is on the priority list (deployment score, D2+, all years). Empty list if the
    county is not on the list. Every figure comes from deployment_penalty_scores() / county_report_card()."""
    top = priority_list(scores)
    if fips not in set(top[COL_FIPS]):
        return []
    row = top[top[COL_FIPS] == fips].iloc[0]
    scored = scores[scores["has_score"]]
    card = county_report_card(ia_all, fips, crop, SEV_D2)
    worst = card["rows"].dropna(subset=["drought_penalty"]).nsmallest(3, "drought_penalty")
    crop_label = {v: k for k, v in CROPS.items()}[crop].lower()
    reasons = [
        f"Drought penalty {row['penalty_score']:+.1f}%: in its {int(row['drought_years_used'])} drought years with a penalty, "
        f"the county yielded about {abs(row['penalty_score']):.0f}% less, relative to the rest of Iowa, than in its own "
        f"nearby normal years. The median across the {len(scored)} scored {crop_label} counties is {scored['penalty_score'].median():+.1f}%.",
        f"Rank {int(row['rank'])} of {len(scored)} {crop_label} counties by drought penalty; the priority list is the top third ({len(top)} counties).",
        "Largest penalties: " + "; ".join(f"{int(r[COL_YEAR])} ({r['drought_penalty']:+.0f}%)" for _, r in worst.iterrows()) + ".",
        f"Confidence '{row['confidence']}': {int(row['drought_years_used'])} drought years behind the score"
        + (f", fewer than {LOW_CONFIDENCE_YEARS}; verify with local information." if row["confidence"] == CONFIDENCE_LOWER else "."),
    ]
    return reasons

DATA_CREDITS = """**Data credits.** Credit the sources when presenting results from this data (wording from the hackathon README):
- **USDA NASS Quick Stats** (county yields; Census of Agriculture conservation practices): This product uses the NASS API but is not endorsed or certified by NASS.
- **NOAA ACIS** (weather): Weather data from the Applied Climate Information System (ACIS), NOAA Regional Climate Centers.
- **U.S. Drought Monitor** (drought): The U.S. Drought Monitor is jointly produced by the National Drought Mitigation Center at the University of Nebraska-Lincoln, the United States Department of Agriculture, and the National Oceanic and Atmospheric Administration.
- **USDA NRCS SSURGO / Soil Data Access** (soil): Soil Survey Staff, Natural Resources Conservation Service, United States Department of Agriculture. Soil Survey Geographic (SSURGO) Database, via Soil Data Access.
- **Data to Harvest hackathon master dataset** (Delaware State University, October 2026): the county x crop x year table that combines the sources above."""
