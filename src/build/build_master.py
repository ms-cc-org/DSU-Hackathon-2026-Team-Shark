"""
Build the master dataset.

Joins the 4 source parquets (NASS, ACIS, USDM, SSURGO) into the 21-field
county × crop × year master dataset.

Run:    python src/build/build_master.py
Inputs: data/processed/{nass,acis,drought,soil}/*.parquet
Output: data/master_dataset.csv  +  data/master_dataset.parquet
"""

import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]

SRC = {
    "nass":    ROOT / "data/processed/nass/nass_raw.parquet",
    "acis":    ROOT / "data/processed/acis/weather_daily.parquet",
    "drought": ROOT / "data/processed/drought/drought_weekly.parquet",
    "soil":    ROOT / "data/processed/soil/soil_county.parquet",
}

OUT_CSV     = ROOT / "data/master_dataset.csv"
OUT_PARQUET = ROOT / "data/master_dataset.parquet"
BUILD_LOG   = ROOT / "data/processed/master_build_log.json"

# ── Constants ─────────────────────────────────────────────────────────

YEARS = list(range(2000, 2026))

#                  start_mo  end_mo  cross_year
SEASON = {
    "CORN":       (5,        9,      False),
    "SOYBEANS":   (5,        10,     False),
    "WHEAT":      (9,        6,      True),
    "SORGHUM":    (6,        10,     False),
}

GDD_PARAMS = {             # (T_base °C, T_cap °C)
    "CORN":     (10, 30),
    "SOYBEANS": (10, 30),
    "WHEAT":    (0,  26),
    "SORGHUM":  (10, 38),
}

EXTREME_HEAT_C = 35        # tmax threshold, all crops

NCCPI_COL = {              # soil column → master nccpi_crop
    "CORN":     "nccpi_corn",
    "SOYBEANS": "nccpi_soy",
    "WHEAT":    "nccpi_sg",
    "SORGHUM":  "nccpi_corn",   # documented proxy
}

MASTER_COLUMNS = [
    # Identity (5)
    "fips", "county_name", "state_alpha", "year", "crop",
    # Yield (5)
    "yield_per_acre", "yield_status", "acres_planted", "acres_harvested",
    "yield_anomaly_pct",
    # Weather (5)
    "precip_mm", "precip_anomaly_pct", "tavg_c", "extreme_heat_days", "gdd",
    # Drought (3)
    "max_drought_severity", "weeks_in_d2_plus", "mean_dsci",
    # Soil (3)
    "aws_100cm_mm", "droughty_pct", "nccpi_crop",
]

build_log = {}

# ── Validation helpers ────────────────────────────────────────────────

_checks = []


def check(tag, passed, detail=""):
    _checks.append((tag, "PASS" if passed else "FAIL", detail))
    mark = "  [OK]" if passed else "  [!!]"
    print(f"{mark} {tag}")
    if detail:
        print(f"       {detail}")


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── Season helpers ────────────────────────────────────────────────────

def in_season(month_series, crop):
    """Boolean mask: is this month inside the crop's season window?"""
    s, e, cross = SEASON[crop]
    if cross:
        return (month_series >= s) | (month_series <= e)
    return (month_series >= s) & (month_series <= e)


def assign_harvest_year(cal_year, month, crop):
    """Vectorised harvest-year from calendar year + month arrays."""
    s, _, cross = SEASON[crop]
    if cross:
        return np.where(month >= s, cal_year + 1, cal_year)
    return cal_year


def expected_days(crop, yr):
    """Exact day count for a crop-year season window."""
    if crop == "CORN":     return 153
    if crop == "SOYBEANS": return 184
    if crop == "SORGHUM":  return 153
    # WHEAT: Sep 1 (Y-1) to Jun 30 (Y) — includes Feb of harvest year
    return 303 + (1 if calendar.isleap(yr) else 0)


# ── Yield anomaly ─────────────────────────────────────────────────────

def compute_yield_anomaly(g):
    """Per (fips, crop) group: OLS detrend → anomaly %.

    NaN when fewer than 10 non-null yields or fitted value < 1.0.
    """
    y_vals = g["yield_per_acre"]
    valid = y_vals.notna()
    n = valid.sum()
    result = np.full(len(g), np.nan)

    if n < 10:
        return pd.Series(result, index=g.index)

    coeffs = np.polyfit(
        g.loc[valid, "year"].values.astype(float),
        y_vals[valid].values, 1,
    )
    fitted = np.polyval(coeffs, g["year"].values.astype(float))

    ok = valid.values & (fitted >= 1.0)
    result[ok] = (y_vals.values[ok] - fitted[ok]) / fitted[ok] * 100
    return pd.Series(result, index=g.index)


# ══════════════════════════════════════════════════════════════════════
print("Building master dataset …\n")

# ── 1. Load sources ──────────────────────────────────────────────────

section("1 · Load source parquets")

nass = pd.read_parquet(SRC["nass"])
acis = pd.read_parquet(SRC["acis"])
usdm = pd.read_parquet(SRC["drought"])
soil = pd.read_parquet(SRC["soil"])

for name, df in [("NASS", nass), ("ACIS", acis), ("USDM", usdm), ("SSURGO", soil)]:
    print(f"  {name:8s} {len(df):>10,} rows")


# ── 2. County backbone ───────────────────────────────────────────────
# Derived from USDM (all 253 counties with fips, county_name, state_alpha).
# See docs/dataset_specification.md section 1 (Backbone).

section("2 · County backbone (from USDM)")

backbone = (
    usdm[["fips", "county_name", "state_alpha"]]
    .drop_duplicates()
    .sort_values("fips")
    .reset_index(drop=True)
)

n_counties = len(backbone)
check("Backbone county count", n_counties == 253, f"{n_counties}")

# Cross-validate FIPS across sources
acis_fips = set(acis["fips"].unique())
soil_fips = set(soil["fips"].unique())
bk_fips   = set(backbone["fips"])
check("ACIS FIPS = backbone",  acis_fips == bk_fips)
check("SSURGO FIPS ⊆ backbone", soil_fips.issubset(bk_fips))

build_log["counties"] = n_counties


# ── 3. Row universe ──────────────────────────────────────────────────
# Every (fips, crop) with ≥ 1 NASS observation → expand to all 26 years.

section("3 · Row universe")

nass_pairs = nass[["fips", "crop"]].drop_duplicates()
universe = nass_pairs.merge(pd.DataFrame({"year": YEARS}), how="cross")
universe = universe.merge(backbone, on="fips", how="left")
assert universe["county_name"].notna().all(), "Backbone join left orphan FIPS"

n_pairs = len(nass_pairs)
n_rows = len(universe)
print(f"  {n_pairs} (fips, crop) pairs × {len(YEARS)} years = {n_rows:,} rows")
build_log["pairs"] = n_pairs
build_log["universe_rows"] = n_rows


# ── 4. NASS yield, acres, yield_status ────────────────────────────────

section("4 · NASS fields")

# ── yield ──
nass_yield = (
    nass[nass["statistic"] == "YIELD"]
    [["fips", "crop", "year", "value"]]
    .rename(columns={"value": "yield_per_acre"})
)
check("V2 NASS yield no dups",
      nass_yield.duplicated(["fips", "crop", "year"]).sum() == 0)

n_pre = len(universe)
universe = universe.merge(
    nass_yield, on=["fips", "crop", "year"], how="left", indicator=True,
)

# yield_status: reported / suppressed / not_reported
universe["yield_status"] = np.where(
    universe["_merge"] == "left_only", "not_reported",
    np.where(universe["yield_per_acre"].notna(), "reported", "suppressed"),
)
universe.drop(columns="_merge", inplace=True)
assert len(universe) == n_pre, "Yield merge changed row count"

# ── harvested acres ──
nass_harv = (
    nass[nass["statistic"] == "AREA HARVESTED"]
    [["fips", "crop", "year", "value"]]
    .rename(columns={"value": "acres_harvested"})
)
universe = universe.merge(nass_harv, on=["fips", "crop", "year"], how="left")
assert len(universe) == n_pre, "Harvested-acres merge changed row count"

# ── planted acres ──
nass_plant = (
    nass[nass["statistic"] == "AREA PLANTED"]
    [["fips", "crop", "year", "value"]]
    .rename(columns={"value": "acres_planted"})
)
universe = universe.merge(nass_plant, on=["fips", "crop", "year"], how="left")
assert len(universe) == n_pre, "Planted-acres merge changed row count"

sc = universe["yield_status"].value_counts().to_dict()
print(f"  yield_status: {sc}")
build_log["yield_status"] = sc


# ── 5. Yield anomaly ─────────────────────────────────────────────────

section("5 · Yield anomaly (OLS detrend)")

universe["yield_anomaly_pct"] = (
    universe.groupby(["fips", "crop"], group_keys=False)
    .apply(compute_yield_anomaly)
)

n_anom = int(universe["yield_anomaly_pct"].notna().sum())
n_reported = int((universe["yield_status"] == "reported").sum())
print(f"  {n_anom} anomaly values from {n_reported} reported yields")
build_log["yield_anomaly_count"] = n_anom


# ── 6. Weather aggregation ───────────────────────────────────────────
# For each crop: filter daily panel to season months, assign harvest year,
# compute precip, tavg, GDD, extreme heat days per (fips, year).

section("6 · Seasonal weather (ACIS)")

acis_mo = acis["date"].dt.month
acis_yr = acis["date"].dt.year

wx_parts = []
for crop in SEASON:
    mask = in_season(acis_mo, crop)
    cd = acis[mask].copy()
    cd["year"] = assign_harvest_year(
        acis_yr[mask].values, acis_mo[mask].values, crop,
    )
    cd = cd[(cd["year"] >= 2000) & (cd["year"] <= 2025)]

    # daily derived columns
    cd["tavg"]  = (cd["tmax_c"] + cd["tmin_c"]) / 2
    tb, tc      = GDD_PARAMS[crop]
    cd["gdd_d"] = np.maximum(
        0,
        (np.minimum(cd["tmax_c"], tc) + np.maximum(cd["tmin_c"], tb)) / 2 - tb,
    )
    cd["extr"] = (cd["tmax_c"] >= EXTREME_HEAT_C).astype(int)

    agg = (
        cd.groupby(["fips", "year"])
        .agg(
            precip_mm=("pcpn_mm", "sum"),
            tavg_c=("tavg", "mean"),
            extreme_heat_days=("extr", "sum"),
            gdd=("gdd_d", "sum"),
            _days=("date", "count"),
        )
        .reset_index()
    )
    agg["crop"] = crop

    # V10 day-count check
    if crop == "WHEAT":
        exp_days = agg["year"].map(
            lambda y: 303 + (1 if calendar.isleap(y) else 0)
        )
    else:
        exp_days = expected_days(crop, 2000)  # constant for non-wheat
    bad = (agg["_days"] != exp_days).sum()
    check(f"V10 {crop} day count", bad == 0,
          f"{bad} mismatches" if bad else "")

    agg.drop(columns="_days", inplace=True)
    wx_parts.append(agg)

weather = pd.concat(wx_parts, ignore_index=True)

# precip anomaly: (precip - mean) / mean × 100 per (fips, crop)
mu = weather.groupby(["fips", "crop"])["precip_mm"].transform("mean")
n_yr = weather.groupby(["fips", "crop"])["precip_mm"].transform("count")
weather["precip_anomaly_pct"] = np.where(
    (n_yr >= 5) & (mu > 0),
    (weather["precip_mm"] - mu) / mu * 100,
    np.nan,
)

print(f"  {len(weather):,} seasonal weather rows")

# merge onto universe
n_pre = len(universe)
universe = universe.merge(
    weather[["fips", "crop", "year", "precip_mm", "precip_anomaly_pct",
             "tavg_c", "extreme_heat_days", "gdd"]],
    on=["fips", "crop", "year"], how="left",
)
assert len(universe) == n_pre, "Weather merge changed row count"
wx_null = int(universe["precip_mm"].isna().sum())
print(f"  {wx_null} universe rows without weather")
build_log["weather_null_rows"] = wx_null


# ── 7. Drought aggregation ───────────────────────────────────────────
# For each crop: filter weekly panel to season months, assign harvest year,
# compute max severity, weeks in D2+, mean DSCI per (fips, year).

section("7 · Seasonal drought (USDM)")

usdm_mo = usdm["map_date"].dt.month
usdm_yr = usdm["map_date"].dt.year

dr_parts = []
for crop in SEASON:
    mask = in_season(usdm_mo, crop)
    cw = usdm[mask].copy()
    cw["year"] = assign_harvest_year(
        usdm_yr[mask].values, usdm_mo[mask].values, crop,
    )
    cw = cw[(cw["year"] >= 2000) & (cw["year"] <= 2025)]

    # weekly severity — ascending overwrites so highest category wins
    cw["sev"] = 0
    for i, col in enumerate(["D0", "D1", "D2", "D3", "D4"], 1):
        cw.loc[cw[col] > 1, "sev"] = i

    cw["d2p"] = (
        (cw["D2"] + cw["D3"] + cw["D4"]) > 1
    ).astype(int)

    agg = (
        cw.groupby(["fips", "year"])
        .agg(
            max_drought_severity=("sev", "max"),
            weeks_in_d2_plus=("d2p", "sum"),
            mean_dsci=("dsci", "mean"),
        )
        .reset_index()
    )
    agg["crop"] = crop
    dr_parts.append(agg)

drought = pd.concat(dr_parts, ignore_index=True)

# Wheat year 2000 → NaN (USDM starts Jan 2000, missing Sep-Dec 1999)
w00 = (drought["crop"] == "WHEAT") & (drought["year"] == 2000)
drought.loc[w00, ["max_drought_severity", "weeks_in_d2_plus", "mean_dsci"]] = np.nan
print(f"  Wheat year 2000: {w00.sum()} rows → drought NaN")

print(f"  {len(drought):,} seasonal drought rows")

# merge onto universe
n_pre = len(universe)
universe = universe.merge(
    drought[["fips", "crop", "year",
             "max_drought_severity", "weeks_in_d2_plus", "mean_dsci"]],
    on=["fips", "crop", "year"], how="left",
)
assert len(universe) == n_pre, "Drought merge changed row count"


# ── 8. Soil fields ───────────────────────────────────────────────────

section("8 · Soil (SSURGO)")

n_pre = len(universe)
universe = universe.merge(
    soil[["fips", "aws_100cm_mm", "droughty_pct",
          "nccpi_corn", "nccpi_soy", "nccpi_sg"]],
    on="fips", how="left",
)
assert len(universe) == n_pre, "Soil merge changed row count"

# map nccpi_crop based on the crop column
universe["nccpi_crop"] = np.nan
for crop, col in NCCPI_COL.items():
    m = universe["crop"] == crop
    universe.loc[m, "nccpi_crop"] = universe.loc[m, col]
universe.drop(columns=["nccpi_corn", "nccpi_soy", "nccpi_sg"], inplace=True)

print(f"  nccpi_crop nulls: {universe['nccpi_crop'].isna().sum()}")


# ── 9. Final assembly ────────────────────────────────────────────────

section("9 · Final assembly")

master = universe[MASTER_COLUMNS].copy()
master.sort_values(["state_alpha", "fips", "crop", "year"], inplace=True)
master.reset_index(drop=True, inplace=True)

# Round computed fields to reasonable precision
master["yield_anomaly_pct"]  = master["yield_anomaly_pct"].round(2)
master["precip_mm"]          = master["precip_mm"].round(1)
master["precip_anomaly_pct"] = master["precip_anomaly_pct"].round(2)
master["tavg_c"]             = master["tavg_c"].round(2)
master["gdd"]                = master["gdd"].round(0)
master["mean_dsci"]          = master["mean_dsci"].round(1)
master["nccpi_crop"]         = master["nccpi_crop"].round(4)

# Nullable integer columns (integer-valued but can be NaN)
for col in ["extreme_heat_days", "max_drought_severity", "weeks_in_d2_plus"]:
    master[col] = master[col].astype("Int64")

print(f"  {len(master):,} rows × {len(master.columns)} columns")
build_log["final_rows"] = len(master)
build_log["final_columns"] = len(master.columns)


# ── 10. Validation ───────────────────────────────────────────────────

section("10 · Validation")

# V1 — row count
check("V1 row count in [10k, 25k]",
      10_000 <= len(master) <= 25_000,
      f"{len(master):,}")

# V2 — uniqueness
dups = master.duplicated(["fips", "crop", "year"]).sum()
check("V2 unique (fips, crop, year)", dups == 0, f"{dups} dups")

# V3 — FIPS validity
check("V3 all FIPS in backbone",
      set(master["fips"]).issubset(bk_fips))

# V4 — FIPS type
check("V4 FIPS is str len 5",
      master["fips"].dtype == object and (master["fips"].str.len() == 5).all())

# V5 — year span per (crop, state)
v5_notes = []
for crop in master["crop"].unique():
    for st in master["state_alpha"].unique():
        g = master[(master["crop"] == crop) & (master["state_alpha"] == st)]
        if len(g) > 0 and (g["year"].min() != 2000 or g["year"].max() != 2025):
            v5_notes.append(f"{st} {crop} {g['year'].min()}-{g['year'].max()}")
if v5_notes:
    for note in v5_notes:
        print(f"       V5 note: {note}")

# V6 — value domains
check("V6 crop values",
      set(master["crop"].unique()) <= {"CORN", "SOYBEANS", "WHEAT", "SORGHUM"})
check("V6 state values",
      set(master["state_alpha"].unique()) <= {"CA", "NE", "IA", "DE"})

# V7 — yield positivity
nn_yield = master["yield_per_acre"].dropna()
check("V7 non-null yields > 0", (nn_yield > 0).all(),
      f"min = {nn_yield.min():.2f}" if len(nn_yield) else "")

# V9 — acreage consistency
both = master.dropna(subset=["acres_harvested", "acres_planted"])
if len(both):
    bad_acres = (both["acres_harvested"] > both["acres_planted"]).sum()
    check("V9 harvested ≤ planted", bad_acres == 0,
          f"{bad_acres}/{len(both)} violations")

# V11 — weather plausibility
wx_rows = master.dropna(subset=["tavg_c"])
check("V11 tavg_c in [-20, 40]",
      (wx_rows["tavg_c"] >= -20).all() and (wx_rows["tavg_c"] <= 40).all(),
      f"[{wx_rows['tavg_c'].min():.1f}, {wx_rows['tavg_c'].max():.1f}]")
check("V11 precip_mm ≥ 0",
      (master["precip_mm"].dropna() >= 0).all())
check("V11 gdd ≥ 0",
      (master["gdd"].dropna() >= 0).all())

# V12 — drought ranges
ds = master["max_drought_severity"].dropna()
check("V12 severity in {0..5}",
      ds.isin([0, 1, 2, 3, 4, 5]).all(),
      f"unique = {sorted(ds.unique())}")
dsci_vals = master["mean_dsci"].dropna()
check("V12 DSCI in [0, 500]",
      (dsci_vals >= 0).all() and (dsci_vals <= 500).all(),
      f"[{dsci_vals.min():.1f}, {dsci_vals.max():.1f}]")

# V14 — no duplicate weekly maps, and weeks_in_d2_plus never exceeds the maps in that crop-season
SEASON_WEEKS = {"CORN": ((5, 1), (9, 30), 0), "SOYBEANS": ((5, 1), (10, 31), 0),
                "SORGHUM": ((6, 1), (10, 31), 0), "WHEAT": ((9, 1), (6, 30), -1)}
map_dates = pd.Series(sorted(usdm["map_date"].unique()))
n_weeks = pd.DataFrame(
    [(c, y, int(map_dates.between(pd.Timestamp(y + off, sm, sd), pd.Timestamp(y, em, ed)).sum()))
     for c, ((sm, sd), (em, ed), off) in SEASON_WEEKS.items() for y in range(2000, 2026)],
    columns=["crop", "year", "n_weeks"])
too_many = master.merge(n_weeks, on=["crop", "year"]).query("weeks_in_d2_plus > n_weeks")
check("V14 no duplicate USDM weeks", usdm.duplicated(["fips", "map_date"]).sum() == 0)
check("V14 weeks_in_d2_plus ≤ weeks in season", len(too_many) == 0, f"{len(too_many)} rows")

# V13 — wheat cross-year
wheat_2000 = master[(master["crop"] == "WHEAT") & (master["year"] == 2000)]
if len(wheat_2000):
    check("V13 wheat 2000 has weather",
          wheat_2000["precip_mm"].notna().any())
    check("V13 wheat 2000 drought NaN",
          wheat_2000["max_drought_severity"].isna().all())

# V16 — soil time-invariance
soil_var = master.groupby("fips")["aws_100cm_mm"].nunique()
check("V16 soil time-invariant", (soil_var <= 1).all())

# V18 — known gaps
ca_soy = master[(master["state_alpha"] == "CA") & (master["crop"] == "SOYBEANS")]
check("V18 zero CA soybeans rows", len(ca_soy) == 0, f"{len(ca_soy)} rows")

# ── summary ──

section("Summary")

passed = sum(1 for _, s, _ in _checks if s == "PASS")
failed = sum(1 for _, s, _ in _checks if s == "FAIL")
print(f"\n  {passed}/{len(_checks)} passed, {failed} failed")

if failed:
    print("\n  FAILURES:")
    for tag, status, detail in _checks:
        if status == "FAIL":
            print(f"    [!!] {tag}  {detail}")

build_log["validation"] = {
    "passed": passed, "failed": failed, "total": len(_checks),
}


# ── 11. Export ────────────────────────────────────────────────────────

section("11 · Export")

master.to_csv(OUT_CSV, index=False)
print(f"  {OUT_CSV.relative_to(ROOT)}")

master.to_parquet(OUT_PARQUET, index=False)
print(f"  {OUT_PARQUET.relative_to(ROOT)}")

build_log["timestamp"] = pd.Timestamp.now().isoformat()
with open(BUILD_LOG, "w") as f:
    json.dump(build_log, f, indent=2, default=str)
print(f"  {BUILD_LOG.relative_to(ROOT)}")

print(f"\nDone. {len(master):,} rows × {len(master.columns)} columns.\n")
