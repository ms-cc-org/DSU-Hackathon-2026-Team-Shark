import pandas as pd
import numpy as np
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
NOTE = "NOTE"

results = []


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((name, status, detail))
    mark = "[OK]" if passed else "[!!]"
    print(f"{mark} {name}")
    if detail:
        print(f"{detail}")


def section(title):
    print(f"{title}")


# Load data
_ROOT = Path(__file__).resolve().parents[2]

nass = pd.read_parquet(_ROOT / "data/processed/nass/nass_raw.parquet")
usdm = pd.read_parquet(_ROOT / "data/processed/drought/drought_weekly.parquet")
acis = pd.read_parquet(_ROOT / "data/processed/acis/weather_daily.parquet")
soil = pd.read_parquet(_ROOT / "data/processed/soil/soil_county.parquet")


#
section("NASS: Do yield numbers fall within expected ranges?")
# Sanity check: county yields, weighted by harvested acres, should land in historically typical ranges.
# These are plausibility checks against well-known production benchmarks — not direct comparisons to
# published state-level estimates (which are a separate, independent NASS product). If our county data has
# the wrong crop filter, wrong units, or duplicate rows, the weighted mean will fall outside these ranges.

yield_df = nass[nass["statistic"] == "YIELD"][["fips", "year", "crop", "state_abbr", "value"]].copy()
yield_df = yield_df.rename(columns={"value": "yield_val"})
harvested_df = nass[nass["statistic"] == "AREA HARVESTED"][["fips", "year", "crop", "value"]].copy()
harvested_df = harvested_df.rename(columns={"value": "acres_harv"})

merged = yield_df.merge(harvested_df, on=["fips", "year", "crop"], how="inner")
merged = merged.dropna(subset=["yield_val", "acres_harv"])
merged = merged[merged["acres_harv"] > 0]

# Compute acreage-weighted state yields
state_yields = (
    merged.groupby(["state_abbr", "crop", "year"])
    .apply(lambda g: np.average(g["yield_val"], weights=g["acres_harv"]), include_groups=False)
    .reset_index(name="weighted_yield")
)

# Plausibility ranges based on typical NASS state yields:
# Iowa corn ~180 bu/acre (recent years), Nebraska corn ~175-185,
# Iowa soybeans ~50-55, Nebraska soybeans ~50-55
# These are wide bands — if we're outside them, something is wrong with the data.

spot_checks = [
    ("IA", "CORN", 2020, 170, 210, "Iowa corn 2020 should be ~178-195"),
    ("NE", "CORN", 2020, 170, 210, "Nebraska corn 2020 should be ~178-195"),
    ("IA", "SOYBEANS", 2020, 45,  60,  "Iowa soybeans 2020 should be ~50-55"),
]

for st, crop, yr, lo, hi, reason in spot_checks:
    row = state_yields[
        (state_yields["state_abbr"] == st)
        & (state_yields["crop"] == crop)
        & (state_yields["year"] == yr)
    ]
    if len(row) == 0:
        check(f"NASS {st} {crop} {yr}", False, "no data")
        continue
    val = row["weighted_yield"].iloc[0]
    check(
        f"NASS {st} {crop} {yr}: {val:.1f} bu/acre in [{lo}, {hi}]",
        lo <= val <= hi,
        reason,
    )

for st in ["IA", "NE"]:
    for crop in ["CORN", "SOYBEANS"]:
        y11 = state_yields[
            (state_yields["state_abbr"] == st)
            & (state_yields["crop"] == crop)
            & (state_yields["year"] == 2011)
        ]
        y12 = state_yields[
            (state_yields["state_abbr"] == st)
            & (state_yields["crop"] == crop)
            & (state_yields["year"] == 2012)
        ]
        if len(y11) > 0 and len(y12) > 0:
            drop = y11["weighted_yield"].iloc[0] - y12["weighted_yield"].iloc[0]
            check(
                f"NASS {st} {crop}: 2012 yield < 2011 (drought signal)",
                drop > 0,
                f"2011={y11['weighted_yield'].iloc[0]:.1f}, 2012={y12['weighted_yield'].iloc[0]:.1f}, drop={drop:.1f}",
            )
        else:
            check(f"NASS {st} {crop}: 2012 yield < 2011 (drought signal)", False, "no data for 2011 or 2012")


# 2012 Drought check
section("USDM: Do known droughts show up?")

usdm["year"] = usdm["map_date"].dt.year
usdm["month"] = usdm["map_date"].dt.month

# 2012 drought: Iowa, July-August, should show widespread D2+
ia_2012_summer = usdm[
    (usdm["state_alpha"] == "IA")
    & (usdm["year"] == 2012)
    & (usdm["month"].isin([7, 8]))
]
ia_d2_plus = (ia_2012_summer["D2"] + ia_2012_summer["D3"] + ia_2012_summer["D4"]).mean()
check(
    f"USDM Iowa summer 2012: mean D2+ area = {ia_d2_plus:.1f}%",
    ia_d2_plus > 20,
    "2012 Midwest drought should show substantial D2+ coverage in IA Jul-Aug",
)

# Nebraska same period
ne_2012_summer = usdm[
    (usdm["state_alpha"] == "NE")
    & (usdm["year"] == 2012)
    & (usdm["month"].isin([7, 8]))
]
ne_d2_plus = (ne_2012_summer["D2"] + ne_2012_summer["D3"] + ne_2012_summer["D4"]).mean()
check(
    f"USDM Nebraska summer 2012: mean D2+ area = {ne_d2_plus:.1f}%",
    ne_d2_plus > 20,
    "2012 Midwest drought should show substantial D2+ coverage in NE Jul-Aug",
)

# California 2014-2015 drought
ca_2015 = usdm[
    (usdm["state_alpha"] == "CA")
    & (usdm["year"] == 2015)
]
ca_d3_plus = (ca_2015["D3"] + ca_2015["D4"]).mean()
check(
    f"USDM California 2015: mean D3+ area = {ca_d3_plus:.1f}%",
    ca_d3_plus > 30,
    "California 2015 was extreme drought — should show widespread D3/D4",
)

# Conversely: 2019 was not a major drought year in Iowa
ia_2019 = usdm[
    (usdm["state_alpha"] == "IA")
    & (usdm["year"] == 2019)
    & (usdm["month"].isin([6, 7, 8]))
]
ia_2019_d2 = (ia_2019["D2"] + ia_2019["D3"] + ia_2019["D4"]).mean()
check(
    f"USDM Iowa summer 2019: mean D2+ area = {ia_2019_d2:.1f}% (no major drought)",
    ia_2019_d2 < 15,
    "2019 was not a major drought year in Iowa — D2+ should be low",
)

# DSCI check: 2012 IA DSCI should be much higher than 2019
ia_dsci_2012 = usdm[
    (usdm["state_alpha"] == "IA") & (usdm["year"] == 2012)
    & (usdm["month"].isin([6, 7, 8]))
]["dsci"].mean()
ia_dsci_2019 = usdm[
    (usdm["state_alpha"] == "IA") & (usdm["year"] == 2019)
    & (usdm["month"].isin([6, 7, 8]))
]["dsci"].mean()
check(
    f"USDM Iowa DSCI: 2012 ({ia_dsci_2012:.0f}) >> 2019 ({ia_dsci_2019:.0f})",
    ia_dsci_2012 > ia_dsci_2019 * 3,
    "2012 drought DSCI should be far higher than a non-drought year",
)


# Unit check for temp and rain precipitation
section("ACIS: Are temperatures and precipitation in the right units?")

acis["year"] = acis["date"].dt.year
acis["month"] = acis["date"].dt.month

ia_daily = acis[acis["state_alpha"] == "IA"]
ia_tavg = ((ia_daily["tmax_c"] + ia_daily["tmin_c"]) / 2).mean()
check(
    f"ACIS Iowa mean daily tavg = {ia_tavg:.1f}°C",
    5 < ia_tavg < 15,
    "Iowa mean ~9°C. If ~48, data is in Fahrenheit.",
)

# Iowa annual precipitation — sum daily means across a year, per county, then average
ia_2020 = acis[(acis["state_alpha"] == "IA") & (acis["year"] == 2020)]
ia_annual_precip = ia_2020.groupby("fips")["pcpn_mm"].sum().mean()
check(
    f"ACIS Iowa 2020 mean annual precip = {ia_annual_precip:.0f} mm",
    600 < ia_annual_precip < 1200,
    "Iowa annual precip ~850-950mm. If ~34, data is in inches.",
)

# Nebraska January — should be cold (mean < 0°C)
ne_jan = acis[(acis["state_alpha"] == "NE") & (acis["month"] == 1)]
ne_jan_tavg = ((ne_jan["tmax_c"] + ne_jan["tmin_c"]) / 2).mean()
check(
    f"ACIS Nebraska January mean tavg = {ne_jan_tavg:.1f}°C",
    -15 < ne_jan_tavg < 2,
    "Nebraska January should be cold. If ~25-30, data is Fahrenheit.",
)

# California summer highs — Central Valley regularly hits 35-40°C
ca_summer = acis[
    (acis["state_alpha"] == "CA")
    & (acis["month"].isin([7, 8]))
]
ca_tmax_mean = ca_summer["tmax_c"].mean()
check(
    f"ACIS California Jul-Aug mean tmax = {ca_tmax_mean:.1f}°C",
    25 < ca_tmax_mean < 42,
    "CA summer highs should average ~30-35°C across all counties.",
)

# Extreme heat: California should have many days ≥ 35°C, Delaware almost none in winter
ca_extreme = (ca_summer["tmax_c"] >= 35).mean() * 100
check(
    f"ACIS California Jul-Aug days ≥ 35°C: {ca_extreme:.1f}% of county-days",
    ca_extreme > 10,
    "Central Valley counties regularly exceed 35°C in summer.",
)

de_winter = acis[
    (acis["state_alpha"] == "DE") & (acis["month"].isin([12, 1, 2]))
]
de_winter_extreme = (de_winter["tmax_c"] >= 35).sum()
check(
    f"ACIS Delaware winter days ≥ 35°C: {de_winter_extreme}",
    de_winter_extreme == 0,
    "Delaware should never hit 35°C in winter.",
)


# IOWA has great agricultural friendly soil, California soil varies, Delaware is plain, and Nebraska has sandy soil
section("SSURGO: Do soil patterns match known geography?")

ia_soil = soil[soil["state_alpha"] == "IA"]
ne_soil = soil[soil["state_alpha"] == "NE"]
ca_soil = soil[soil["state_alpha"] == "CA"]

# Iowa should have highest median NCCPI corn
ia_nccpi = ia_soil["nccpi_corn"].median()
ne_nccpi = ne_soil["nccpi_corn"].median()
ca_nccpi = ca_soil["nccpi_corn"].median()

check(
    f"SSURGO Iowa median nccpi_corn ({ia_nccpi:.3f}) > Nebraska ({ne_nccpi:.3f})",
    ia_nccpi > ne_nccpi,
    "Iowa has the most productive corn soil in the US.",
)
check(
    f"SSURGO Iowa median nccpi_corn ({ia_nccpi:.3f}) > California ({ca_nccpi:.3f})",
    ia_nccpi > ca_nccpi,
    "Iowa should outrank CA for rainfed corn productivity.",
)

# Iowa should have high AWS (deep prairie soils)
ia_aws = ia_soil["aws_100cm_mm"].median()
check(
    f"SSURGO Iowa median AWS = {ia_aws:.0f} mm",
    ia_aws > 160,
    "Iowa prairie soils should hold 170-210mm of water per metre.",
)

# California should have high droughty_pct in many counties
ca_droughty_high = (ca_soil["droughty_pct"] > 50).sum()
check(
    f"SSURGO CA counties with >50% droughty soil: {ca_droughty_high} of 58",
    ca_droughty_high > 15,
    "Many CA counties have low water-holding soil (desert, mountains).",
)

# Iowa should have very low droughty_pct
ia_droughty_median = ia_soil["droughty_pct"].median()
check(
    f"SSURGO Iowa median droughty_pct = {ia_droughty_median:.1f}%",
    ia_droughty_median < 30,
    "Iowa's deep loam soils should not be drought-vulnerable.",
)

# NCCPI soybeans: Iowa should lead
ia_soy = ia_soil["nccpi_soy"].median()
ne_soy = ne_soil["nccpi_soy"].median()
check(
    f"SSURGO Iowa median nccpi_soy ({ia_soy:.3f}) > Nebraska ({ne_soy:.3f})",
    ia_soy > ne_soy,
    "Iowa soybean soil productivity should exceed Nebraska.",
)


# The drought check above should be in USDM, ACIS and NASS in terms of high severity, low prcp and low yields.
section("CROSS-SOURCE: Do the sources tell a consistent story?")

# Iowa 2012 vs 2014 precipitation (growing season May-Sep)
ia_acis = acis[acis["state_alpha"] == "IA"]
for yr, label in [(2012, "drought"), (2014, "normal")]:
    season = ia_acis[
        (ia_acis["year"] == yr)
        & (ia_acis["month"].isin([5, 6, 7, 8, 9]))
    ]
    precip = season.groupby("fips")["pcpn_mm"].sum().mean()
    print(f"  Iowa {yr} ({label}) May-Sep precip: {precip:.0f} mm")

ia_precip_2012 = ia_acis[
    (ia_acis["year"] == 2012) & (ia_acis["month"].isin([5, 6, 7, 8, 9]))
].groupby("fips")["pcpn_mm"].sum().mean()
ia_precip_2014 = ia_acis[
    (ia_acis["year"] == 2014) & (ia_acis["month"].isin([5, 6, 7, 8, 9]))
].groupby("fips")["pcpn_mm"].sum().mean()

check(
    f"CROSS Iowa 2012 precip ({ia_precip_2012:.0f}mm) < 2014 ({ia_precip_2014:.0f}mm)",
    ia_precip_2012 < ia_precip_2014,
    "2012 drought should show lower growing-season precipitation.",
)

# Iowa 2012 vs 2014 drought (USDM, Jul-Aug, same window as the 2012 check above)
ia_2014_summer = usdm[
    (usdm["state_alpha"] == "IA")
    & (usdm["year"] == 2014)
    & (usdm["month"].isin([7, 8]))
]
ia_d2_plus_2014 = (ia_2014_summer["D2"] + ia_2014_summer["D3"] + ia_2014_summer["D4"]).mean()
check(
    f"CROSS Iowa Jul-Aug D2+: 2012 ({ia_d2_plus:.1f}%) > 2014 ({ia_d2_plus_2014:.1f}%)",
    ia_d2_plus > ia_d2_plus_2014,
    "2012 drought should show more D2+ area than 2014.",
)


# Combine: 2012 had less rain, more drought, and lower yields
def ia_corn_yield(yr):
    row = state_yields[
        (state_yields["state_abbr"] == "IA")
        & (state_yields["crop"] == "CORN")
        & (state_yields["year"] == yr)
    ]
    return row["weighted_yield"].iloc[0] if len(row) > 0 else np.nan

ia_yield_2012 = ia_corn_yield(2012)
ia_yield_2014 = ia_corn_yield(2014)

check(
    f"CROSS Iowa corn: 2012 yield ({ia_yield_2012:.0f}) < 2014 yield ({ia_yield_2014:.0f})",
    ia_yield_2012 < ia_yield_2014,
    "Less rain + more drought --> lower yield. A missing year shows as nan and fails.",
)

print(f"\n  2012 Iowa story: precip {ia_precip_2012:.0f}mm, "
      f"D2+ {ia_d2_plus:.0f}%, corn {ia_yield_2012:.0f} bu/acre")
print(f"  2014 Iowa story: precip {ia_precip_2014:.0f}mm, "
      f"D2+ {ia_d2_plus_2014:.0f}%, corn {ia_yield_2014:.0f} bu/acre")
cross_failed = sum(1 for n, st, _ in results if n.startswith("CROSS") and st == FAIL)
if cross_failed == 0:
    print(f"  --> All 3 sources tell the same story.")
else:
    print(f"  --> {cross_failed} cross-source check(s) failed; the sources disagree.")



section("SUMMARY")
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
total = len(results)

print(f"\n  {passed}/{total} checks passed, {failed} failed")
if failed > 0:
    print("\n FAILURES:")
    for name, status, detail in results:
        if status == FAIL:
            print(f" [!!] {name}")
            if detail:
                print(f" {detail}")
else:
    print("  All sanity checks passed.")
