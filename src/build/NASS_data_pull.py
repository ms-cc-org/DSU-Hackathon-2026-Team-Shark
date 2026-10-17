import json
import os
from pathlib import Path

import pandas as pd
import requests
import time
from dotenv import load_dotenv

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")
API_KEY = os.environ["NASS_API_KEY"]

URL = "https://quickstats.nass.usda.gov/api/api_GET"

STATES = ["CA", "NE", "IA", "DE"]

# Two requests per crop x state: one for yield, one for acres harvested.
# Passing short_desc directly prevents HTTP 413 (NASS 50k-record limit) that
# occurs when querying all statistics for high-density states like NE and IA.
# reference_period_desc=YEAR keeps only the final annual value (not mid-season
# forecasts). domain_desc=TOTAL keeps aggregate data only (not farm-type splits).
CROP_QUERIES = {
    "CORN": {
        "commodity_desc": "CORN",
        "yield_short_desc": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
        "acres_short_desc": "CORN, GRAIN - ACRES HARVESTED",
        "planted_short_desc": "CORN - ACRES PLANTED",
        # NASS stores corn grain under both util_practice "GRAIN" and
        # "ALL UTILIZATION PRACTICES". Pin to "GRAIN" to avoid duplicates.
        "extra_params": {"util_practice_desc": "GRAIN"},
    },
    "SOYBEANS": {
        "commodity_desc": "SOYBEANS",
        "yield_short_desc": "SOYBEANS - YIELD, MEASURED IN BU / ACRE",
        "acres_short_desc": "SOYBEANS - ACRES HARVESTED",
        "planted_short_desc": "SOYBEANS - ACRES PLANTED",
        "extra_params": {},
    },
    "WHEAT": {
        "commodity_desc": "WHEAT",
        "yield_short_desc": "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE",
        "acres_short_desc": "WHEAT, WINTER - ACRES HARVESTED",
        # NASS stores winter wheat under both class "WINTER" and "ALL CLASSES"
        # when it is the only wheat class in a county. Pin to "WINTER".
        "planted_short_desc": "WHEAT, WINTER - ACRES PLANTED",
        "extra_params": {"class_desc": "WINTER"},
    },
    "SORGHUM": {
        "commodity_desc": "SORGHUM",
        "yield_short_desc": "SORGHUM, GRAIN - YIELD, MEASURED IN BU / ACRE",
        "acres_short_desc": "SORGHUM, GRAIN - ACRES HARVESTED",
        # Same util_practice split as corn grain.
        "planted_short_desc": "SORGHUM - ACRES PLANTED",
        "extra_params": {"util_practice_desc": "GRAIN"},
    },
}


all_frames = []
raw_dir = ROOT / "data/raw/nass"
raw_dir.mkdir(parents=True, exist_ok=True)
failures = []

for crop, query in CROP_QUERIES.items():
    for state in STATES:
        for stat_label, short_desc in [
            ("yield", query["yield_short_desc"]),
            ("acres", query["acres_short_desc"]),
            ("planted", query["planted_short_desc"]),
        ]:
            # Planted acres are reported at the commodity level (not
            # grain-specific), so util_practice_desc and class_desc
            # filters that work for yield/harvested make planted
            # queries return HTTP 400.  Drop them for planted.
            extra = query["extra_params"] if stat_label != "planted" else {}

            params = {
                "key": API_KEY,
                "commodity_desc": query["commodity_desc"],
                "short_desc": short_desc,
                "reference_period_desc": "YEAR",
                "domain_desc": "TOTAL",
                "prodn_practice_desc": "ALL PRODUCTION PRACTICES",
                "source_desc": "SURVEY",
                **extra,
                "state_alpha": state,
                "agg_level_desc": "COUNTY",
                "format": "JSON",
            }

            max_attempts = 3
            response = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = requests.get(URL, params=params, timeout=60)
                    break
                except requests.exceptions.Timeout:
                    print(f"  Timeout on attempt {attempt}/3 — {crop} {stat_label} {state}")
                    if attempt < max_attempts:
                        time.sleep(5 * attempt)
                    else:
                        failures.append({
                            "crop": crop,
                            "stat": stat_label,
                            "state_alpha": state,
                            "status": "TIMEOUT",
                            "error": "timed out after 3 attempts",
                        })

            if response is None:
                time.sleep(1)
                continue

            # Archive raw response immediately
            raw_filename = raw_dir / f"{crop}_{state}_{stat_label}.json"
            if response.status_code == 200:
                with open(raw_filename, "w") as f:
                    f.write(response.text)

            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    frame = pd.DataFrame(data)
                    frame["crop"] = crop
                    all_frames.append(frame)
                else:
                    failures.append({
                        "crop": crop,
                        "stat": stat_label,
                        "state_alpha": state,
                        "status": 200,
                        "error": "empty data array",
                    })
            else:
                failures.append({
                    "crop": crop,
                    "stat": stat_label,
                    "state_alpha": state,
                    "status": response.status_code,
                    "error": response.text[:200],
                })

            time.sleep(1)

# Filter to analysis window
df = pd.concat(all_frames, ignore_index=True)
df["year"] = pd.to_numeric(df["year"], errors="coerce")

# Post-filter zero-row check (I-06): snapshot counts before year filter
_pre_counts = df.groupby(["crop", "state_alpha", "statisticcat_desc"]).size()
df = df[df["year"].between(2000, 2025)].copy()

# Log any (crop, state, stat) that had rows before but zero after year filter
_post_counts = df.groupby(["crop", "state_alpha", "statisticcat_desc"]).size()
for (crop_key, state_key, stat_key), pre_n in _pre_counts.items():
    post_n = _post_counts.get((crop_key, state_key, stat_key), 0)
    if post_n == 0:
        failures.append({
            "crop": crop_key,
            "stat": stat_key,
            "state_alpha": state_key,
            "status": "FILTERED_TO_ZERO",
            "error": f"{pre_n} rows returned but 0 survived year filter 2000-2025",
        })
        print(f"WARNING: {crop_key} {stat_key} {state_key} — {pre_n} rows filtered to zero")

_before_dedup = len(df)
drop_mask = (
    (df["crop"].isin(["CORN", "SORGHUM"])
     & (df["util_practice_desc"] == "ALL UTILIZATION PRACTICES")
     & (df["statisticcat_desc"] != "AREA PLANTED"))
    | (df["crop"].eq("WHEAT") & (df["class_desc"] == "ALL CLASSES")
     & (df["statisticcat_desc"] != "AREA PLANTED"))
)                                                                                                                                                                                                      
df = df[~drop_mask].copy()
print(f"Dedup: dropped {_before_dedup - len(df)} ALL-aggregate rows, {len(df)} remain") 

# Remove county_code=998 (OTHER COMBINED COUNTIES) — not a real county (I-22)
# NASS uses this code to publish aggregated data for counties it doesn't publish individually,
# returning multiple conflicting rows per year that cause all 884 duplicates.                                                                                                                        
_before_998 = len(df)
df = df[df["county_code"] != "998"].copy()
print(f"Removed {_before_998 - len(df)} county_code=998 rows (OTHER COMBINED COUNTIES)")

print("Total records:", len(df))
print("Year range:", df["year"].min(), "–", df["year"].max())
print("Failed queries:", len(failures))
print()
print(df.groupby(["crop", "statisticcat_desc", "state_alpha"]).size().to_string())

# Duplicate diagnosis — runs on raw data before source_desc is dropped
_dup_mask = df.duplicated(
    subset=["state_fips_code", "county_code", "year", "crop", "statisticcat_desc"],
    keep=False,
)
if _dup_mask.sum() > 0:
    _dups = df[_dup_mask]
    print("\nDuplicate diagnosis (fields that vary within duplicate groups):")
    for col in ["source_desc", "prodn_practice_desc", "util_practice_desc",
                "class_desc", "freq_desc", "domaincat_desc"]:
        if col in _dups.columns:
            counts = _dups[col].value_counts()
            if len(counts) > 1:
                print(f"  *** {col} VARIES: {counts.to_dict()}")
            else:
                print(f"  {col} uniform: {counts.to_dict()}")

# Rename columns
columns = [
    "state_name",
    "state_alpha",
    "state_fips_code",
    "county_name",
    "county_code",
    "year",
    "crop",
    "short_desc",
    "statisticcat_desc",
    "unit_desc",
    "Value",
]

df = df[columns].copy()
df = df.rename(columns={
    "state_name" : "state",
    "state_alpha" : "state_abbr",
    "state_fips_code" : "state_fips",
    "county_name" : "county",
    "county_code" : "county_fips",
    "short_desc" : "description",
    "statisticcat_desc" : "statistic",
    "unit_desc" : "unit",
    "Value" : "value_raw",
})

# Numeric conversion
df["value"] = pd.to_numeric(
    df["value_raw"].str.replace(",", "", regex=False),
    errors="coerce",
)

# Null yield <= 0 (I-05): NASS lists a yield of 0 when a planted crop had no grain harvest
# Set to NaN so V7 ("every non-null yield > 0") can pass and downstream code treats them as missing, not as real zero-yield observations
_zero_yield_mask = (df["statistic"] == "YIELD") & df["value"].notna() & (df["value"] <= 0)
_zero_count = _zero_yield_mask.sum()
df.loc[_zero_yield_mask, "value"] = float("nan")
print(f"Nulled {_zero_count} yield rows with value <= 0 (planted, no grain harvest)")

print()
print("Missing numeric values:", df["value"].isna().sum())
print("Non-numeric value_raw samples:",
      df.loc[df["value"].isna(), "value_raw"].unique()[:10])

# GEOID construction
df["state_fips"]  = df["state_fips"].astype("string").str.zfill(2)
df["county_fips"] = df["county_fips"].astype("string").str.zfill(3)
df["fips"]        = df["state_fips"] + df["county_fips"]

print()
print("FIPS all 5 chars:", (df["fips"].str.len() == 5).all())
print("States present:", sorted(df["state_abbr"].unique()))
print("Crops present: ", sorted(df["crop"].unique()))
print("Units present: ", df["unit"].unique())

# Validation checks

duplicates = df.duplicated(subset=["fips", "year", "crop", "statistic"])
print()
print("Duplicate (fips, year, crop, statistic) rows:", duplicates.sum())

yield_rows = df[df["statistic"] == "YIELD"]
bad_yields = yield_rows[yield_rows["value"].notna() & (yield_rows["value"] <= 0)]
print("Yield value <= 0:", len(bad_yields))
if len(bad_yields) > 0:
    print(bad_yields[["fips", "year", "crop", "state_abbr", "value"]].to_string(index=False))

# Dataset save

out_dir = ROOT / "data/processed/nass"
out_dir.mkdir(parents=True, exist_ok=True)

df.to_parquet(out_dir / "nass_raw.parquet", index=False)
print()
print(f"Saved {len(df):,} rows --> {out_dir / 'nass_raw.parquet'}")

if failures:
    with open(out_dir / "nass_failures.json", "w") as f:
        json.dump(failures, f, indent=2)
    print(f"Logged {len(failures)} failures --> {out_dir / 'nass_failures.json'}")
    for fail in failures:
        print(f"FAILED: {fail['crop']} ({fail['stat']}) / {fail['state_alpha']} "
              f"(HTTP {fail['status']}): {fail['error'][:80]}")
