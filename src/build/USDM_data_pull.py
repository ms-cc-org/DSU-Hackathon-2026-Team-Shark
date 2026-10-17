import json
import time
from pathlib import Path

import pandas as pd
import requests

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

API_URL = (
    "https://usdmdataservices.unl.edu/api/CountyStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)

STATES = ["CA", "NE", "IA", "DE"]
YEAR_START = 2000
YEAR_END = 2025

raw_dir = ROOT / "data/raw/usdm"
raw_dir.mkdir(parents=True, exist_ok=True)

# Download 
all_frames = []
failures = []

for state in STATES:
    for year in range(YEAR_START, YEAR_END + 1):
        raw_file = raw_dir / f"{state}_{year}.json"

        # Use cached raw file if it exists (never re-fetch)
        if raw_file.exists() and raw_file.stat().st_size > 0:
            with open(raw_file) as f:
                data = json.load(f)
            if data:
                all_frames.append(pd.DataFrame(data))
            print(f"  Cached: {state} {year} ({len(data)} rows)")
            continue

        # USDM archive starts 2000-01-04
        start = f"1/4/{year}" if year == 2000 else f"1/1/{year}"
        end = f"12/31/{year}"

        params = {
            "aoi": state,
            "startdate": start,
            "enddate": end,
            "statisticsType": 2,
        }

        response = None
        headers = {"Accept": "application/json"}
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    API_URL, params=params, headers=headers, timeout=120,
                )
                break
            except requests.exceptions.Timeout:
                print(f"  Timeout attempt {attempt}/3 — {state} {year}")
                if attempt < 3:
                    time.sleep(5 * attempt)
                else:
                    failures.append({
                        "state": state,
                        "year": year,
                        "status": "TIMEOUT",
                        "error": "timed out after 3 attempts",
                    })

        if response is None:
            time.sleep(1)
            continue

        if response.status_code == 200:
            data = response.json()
            # Archive raw response immediately
            with open(raw_file, "w") as f:
                json.dump(data, f)
            if data:
                all_frames.append(pd.DataFrame(data))
                print(f"  {state} {year}: {len(data)} rows")
            else:
                print(f"  {state} {year}: empty response")
                failures.append({
                    "state": state,
                    "year": year,
                    "status": 200,
                    "error": "empty data array",
                })
        else:
            failures.append({
                "state": state,
                "year": year,
                "status": response.status_code,
                "error": response.text[:200],
            })
            print(f"  FAILED {state} {year}: HTTP {response.status_code}")

        time.sleep(0.5)

print(f"\nDownloaded/loaded {len(all_frames)} chunks")

# Combine
df = pd.concat(all_frames, ignore_index=True)
print(f"Combined: {len(df):,} rows")

# Clean 
# JSON response uses lowercase keys: fips, mapDate, county, state,
# none, d0-d4, validStart, validEnd, statisticFormatID.
# fips is already a string ("10001"), mapDate is ISO datetime string.

# FIPS: ensure 5-char zero-padded string
df["fips"] = df["fips"].astype(str).str.zfill(5)

# Parse mapDate (ISO string --> datetime)
df["map_date"] = pd.to_datetime(df["mapDate"])
df = df.drop_duplicates(subset=["fips", "map_date"])

# Verify all rows are categorical (statisticFormatID == 2)
non_cat = (df["statisticFormatID"] != 2).sum()
if non_cat > 0:
    print(f"WARNING: {non_cat} non-categorical rows found, dropping")
    df = df[df["statisticFormatID"] == 2].copy()
else:
    print("statisticFormatID: all categorical (2)")

# Verify none + d0 + d1 + d2 + d3 + d4 ≈ 100%
pct_total = df["none"] + df["d0"] + df["d1"] + df["d2"] + df["d3"] + df["d4"]
bad_sums = (pct_total - 100).abs() > 0.5
if bad_sums.any():
    print(f"WARNING: {bad_sums.sum()} rows with percentage sums deviating >0.5% from 100")
    print(df.loc[bad_sums, ["fips", "map_date", "none", "d0", "d1", "d2", "d3", "d4"]].head())
else:
    print("Percentage sums: all within 0.5% of 100%")

# Pre-compute weekly DSCI: D0×1 + D1×2 + D2×3 + D3×4 + D4×5 (range 0–500)
df["dsci"] = df["d0"] * 1 + df["d1"] * 2 + df["d2"] * 3 + df["d3"] * 4 + df["d4"] * 5

# Building weekly panel

panel = (
    df[["fips", "map_date", "county", "state",
        "none", "d0", "d1", "d2", "d3", "d4", "dsci"]]
    .rename(columns={
        "county": "county_name",
        "state": "state_alpha",
        "none": "none_pct",
        "d0": "D0",
        "d1": "D1",
        "d2": "D2",
        "d3": "D3",
        "d4": "D4",
    })
    .sort_values(["fips", "map_date"])
    .reset_index(drop=True)
)

# Validation

print(f"WEEKLY PANEL SUMMARY")
print(f"Rows: {len(panel):,}")
print(f"Counties: {panel['fips'].nunique()}")
print(f"States: {sorted(panel['state_alpha'].unique())}")
print(f"Date range: {panel['map_date'].min().date()} – {panel['map_date'].max().date()}")
print(f"FIPS 5-char: {(panel['fips'].str.len() == 5).all()}")
print(f"DSCI range: {panel['dsci'].min():.1f} – {panel['dsci'].max():.1f}")
print(f"D0-D4 all >= 0: {(panel[['D0','D1','D2','D3','D4']].min().min() >= 0)}")
print(f"D0-D4 all <= 100: {(panel[['D0','D1','D2','D3','D4']].max().max() <= 100)}")

print(f"\nCounties per state:")
for st in sorted(panel["state_alpha"].unique()):
    n = panel.loc[panel["state_alpha"] == st, "fips"].nunique()
    print(f"  {st}: {n}")

# Weeks per county — check coverage consistency
weeks_per_county = panel.groupby("fips").size()
print(f"\nWeeks per county: min={weeks_per_county.min()}, "
      f"max={weeks_per_county.max()}, median={weeks_per_county.median():.0f}")

# Save
out_path = ROOT / "data/processed/drought/drought_weekly.parquet"
out_path.parent.mkdir(parents=True, exist_ok=True)
panel.to_parquet(out_path, index=False)
print(f"\nSaved {len(panel):,} rows --> {out_path}")

if failures:
    fail_path = ROOT / "data/processed/drought/usdm_failures.json"
    with open(fail_path, "w") as f:
        json.dump(failures, f, indent=2)
    print(f"Logged {len(failures)} failures --> {fail_path}")
    for fail in failures:
        print(f"  FAILED: {fail['state']} {fail['year']} "
              f"(HTTP {fail['status']}): {fail['error'][:80]}")
else:
    print("No failures.")
