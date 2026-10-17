import json
import time
from pathlib import Path

import pandas as pd
import requests

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

API_URL = "https://data.rcc-acis.org/GridData"

# State abbreviation → 2-digit FIPS prefix (for filtering border counties)
STATES = {
    "CA": "06",
    "NE": "31",
    "IA": "19",
    "DE": "10",
}

# 1999 needed for wheat year 2000 (season starts Sep 1 1999).
# ACIS grid 1 covers 1950-present so 1999 is available.
YEAR_START = 1999
YEAR_END = 2025

PAYLOAD_ELEMS = [
    {"name": "pcpn", "interval": "dly", "units": "mm", "area_reduce": "county_mean"},
    {"name": "maxt", "interval": "dly", "units": "degreeC", "area_reduce": "county_mean"},
    {"name": "mint", "interval": "dly", "units": "degreeC", "area_reduce": "county_mean"},
]

raw_dir = ROOT / "data/raw/acis"
raw_dir.mkdir(parents=True, exist_ok=True)

# Download
all_frames = []
failures = []

for state_alpha, state_fips in STATES.items():
    for year in range(YEAR_START, YEAR_END + 1):
        raw_file = raw_dir / f"{state_alpha}_{year}.json"

        # Use cached raw file if it exists (never re-fetch)
        if raw_file.exists() and raw_file.stat().st_size > 0:
            with open(raw_file) as f:
                raw = json.load(f)
            n_days = len(raw.get("data", []))
            print(f"  Cached: {state_alpha} {year} ({n_days} days)")
        else:
            payload = {
                "state": state_alpha.lower(),
                "grid": 1,
                "sdate": f"{year}-01-01",
                "edate": f"{year}-12-31",
                "elems": PAYLOAD_ELEMS,
            }

            response = None
            for attempt in range(1, 4):
                try:
                    response = requests.post(
                        API_URL, json=payload, timeout=180,
                    )
                    break
                except requests.exceptions.Timeout:
                    print(f"  Timeout attempt {attempt}/3 — {state_alpha} {year}")
                    if attempt < 3:
                        time.sleep(10 * attempt)
                    else:
                        failures.append({
                            "state": state_alpha,
                            "year": year,
                            "status": "TIMEOUT",
                            "error": "timed out after 3 attempts",
                        })

            if response is None:
                time.sleep(2)
                continue

            if response.status_code != 200:
                failures.append({
                    "state": state_alpha,
                    "year": year,
                    "status": response.status_code,
                    "error": response.text[:200],
                })
                print(f"  FAILED {state_alpha} {year}: HTTP {response.status_code}")
                time.sleep(2)
                continue

            raw = response.json()
            # Archive raw response immediately
            with open(raw_file, "w") as f:
                json.dump(raw, f)
            n_days = len(raw.get("data", []))
            print(f"  {state_alpha} {year}: {n_days} days")
            time.sleep(1)

        # Parse: each day is [date_str, {fips: pcpn}, {fips: maxt}, {fips: mint}]
        rows = []
        for day_entry in raw.get("data", []):
            date_str = day_entry[0]
            pcpn_dict = day_entry[1]
            maxt_dict = day_entry[2]
            mint_dict = day_entry[3]

            for fips_raw in pcpn_dict:
                fips = fips_raw.zfill(5)
                # Filter to only this state's counties
                if not fips.startswith(state_fips):
                    continue
                rows.append((
                    date_str,
                    fips,
                    pcpn_dict[fips_raw],
                    maxt_dict.get(fips_raw),
                    mint_dict.get(fips_raw),
                ))

        if rows:
            chunk = pd.DataFrame(
                rows, columns=["date", "fips", "pcpn_mm", "tmax_c", "tmin_c"],
            )
            chunk["state_alpha"] = state_alpha
            all_frames.append(chunk)

print(f"\nParsed {len(all_frames)} state-year chunks")

# Combine
df = pd.concat(all_frames, ignore_index=True)
df["date"] = pd.to_datetime(df["date"])
print(f"Combined: {len(df):,} rows")

# Validation
print(f"\n{'=' * 50}")
print("DAILY PANEL SUMMARY")
print(f"{'=' * 50}")
print(f"Rows:        {len(df):,}")
print(f"Counties:    {df['fips'].nunique()}")
print(f"States:      {sorted(df['state_alpha'].unique())}")
print(f"Date range:  {df['date'].min().date()} – {df['date'].max().date()}")
print(f"FIPS 5-char: {(df['fips'].str.len() == 5).all()}")

print(f"\nNull pcpn:   {df['pcpn_mm'].isna().sum()}")
print(f"Null tmax:   {df['tmax_c'].isna().sum()}")
print(f"Null tmin:   {df['tmin_c'].isna().sum()}")

# Plausibility ranges (V11 prep)
print(f"\ntmax range:  [{df['tmax_c'].min():.1f}, {df['tmax_c'].max():.1f}] °C")
print(f"tmin range:  [{df['tmin_c'].min():.1f}, {df['tmin_c'].max():.1f}] °C")
print(f"pcpn range:  [{df['pcpn_mm'].min():.3f}, {df['pcpn_mm'].max():.1f}] mm")
print(f"pcpn < 0:    {(df['pcpn_mm'] < 0).sum()}")

# tavg sanity check
tavg = (df["tmax_c"] + df["tmin_c"]) / 2
print(f"tavg range:  [{tavg.min():.1f}, {tavg.max():.1f}] °C  (spec: -20 to 40)")
out_of_range = (tavg < -20) | (tavg > 40)
if out_of_range.any():
    print(f"  WARNING: {out_of_range.sum()} days with tavg outside [-20, 40]")

print(f"\nCounties per state:")
for st in sorted(df["state_alpha"].unique()):
    n = df.loc[df["state_alpha"] == st, "fips"].nunique()
    print(f"  {st}: {n}")

# Days per county — check coverage consistency
days_per_county = df.groupby("fips").size()
print(f"\nDays per county: min={days_per_county.min()}, "
      f"max={days_per_county.max()}, median={days_per_county.median():.0f}")

# Save
panel = (
    df[["fips", "date", "state_alpha", "pcpn_mm", "tmax_c", "tmin_c"]]
    .sort_values(["fips", "date"])
    .reset_index(drop=True)
)
out_path = ROOT / "data/processed/acis/weather_daily.parquet"
out_path.parent.mkdir(parents=True, exist_ok=True)
panel.to_parquet(out_path, index=False)
print(f"\nSaved {len(panel):,} rows -> {out_path}")

if failures:
    fail_path = ROOT / "data/processed/acis/acis_failures.json"
    with open(fail_path, "w") as f:
        json.dump(failures, f, indent=2)
    print(f"Logged {len(failures)} failures -> {fail_path}")
    for fail in failures:
        print(f"  FAILED: {fail['state']} {fail['year']} (HTTP {fail['status']})")
else:
    print("No failures.")
