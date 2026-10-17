"""
NASS irrigation extension.

Pulls county irrigated harvested acres plus irrigated and non-irrigated yields
from NASS Quick Stats (SURVEY) and produces
data/processed/irrigation/nass_irrigation.parquet.

One row per county x crop x year where NASS published at least one of these.
Coverage is mostly Nebraska (corn and soybeans 2000-2018, winter wheat to 2019,
sorghum to 2007), plus California winter wheat to 2008 and Delaware corn and
soybeans from 2013. Iowa has no irrigated series.

Run after NASS_data_pull.py: irrigated_share divides by the total grain acres
harvested in data/processed/nass/nass_raw.parquet. Does not change the master.
"""

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")
API_KEY = os.environ["NASS_API_KEY"]

URL = "https://quickstats.nass.usda.gov/api/api_GET"

STATES = ["CA", "NE", "IA", "DE"]

# Irrigated series carry their own short_desc, so prodn_practice_desc is not set.
SERIES = {
    "CORN": {
        "irrigated_acres": "CORN, GRAIN, IRRIGATED - ACRES HARVESTED",
        "yield_irrigated": "CORN, GRAIN, IRRIGATED - YIELD, MEASURED IN BU / ACRE",
        "yield_non_irrigated": "CORN, GRAIN, NON-IRRIGATED - YIELD, MEASURED IN BU / ACRE",
    },
    "SOYBEANS": {
        "irrigated_acres": "SOYBEANS, IRRIGATED - ACRES HARVESTED",
        "yield_irrigated": "SOYBEANS, IRRIGATED - YIELD, MEASURED IN BU / ACRE",
        "yield_non_irrigated": "SOYBEANS, NON-IRRIGATED - YIELD, MEASURED IN BU / ACRE",
    },
    "WHEAT": {
        "irrigated_acres": "WHEAT, WINTER, IRRIGATED - ACRES HARVESTED",
        "yield_irrigated": "WHEAT, WINTER, IRRIGATED - YIELD, MEASURED IN BU / ACRE",
        "yield_non_irrigated": "WHEAT, WINTER, NON-IRRIGATED - YIELD, MEASURED IN BU / ACRE",
    },
    "SORGHUM": {
        "irrigated_acres": "SORGHUM, GRAIN, IRRIGATED - ACRES HARVESTED",
        "yield_irrigated": "SORGHUM, GRAIN, IRRIGATED - YIELD, MEASURED IN BU / ACRE",
        "yield_non_irrigated": "SORGHUM, GRAIN, NON-IRRIGATED - YIELD, MEASURED IN BU / ACRE",
    },
}

raw_dir = ROOT / "data/raw/nass_irrigation"
raw_dir.mkdir(parents=True, exist_ok=True)
out_dir = ROOT / "data/processed/irrigation"
out_dir.mkdir(parents=True, exist_ok=True)

frames = []
failures = []

for crop, series in SERIES.items():
    for state in STATES:
        for field, short_desc in series.items():
            params = {
                "key": API_KEY,
                "short_desc": short_desc,
                "source_desc": "SURVEY",
                "reference_period_desc": "YEAR",
                "domain_desc": "TOTAL",
                "agg_level_desc": "COUNTY",
                "state_alpha": state,
                "year__GE": 2000,
                "year__LE": 2025,
                "format": "JSON",
            }

            response = None
            for attempt in range(1, 4):
                try:
                    response = requests.get(URL, params=params, timeout=120)
                    break
                except requests.exceptions.Timeout:
                    print(f"  Timeout on attempt {attempt}/3 — {crop} {field} {state}")
                    time.sleep(5 * attempt)

            if response is None:
                failures.append({"crop": crop, "field": field, "state_alpha": state,
                                 "status": "TIMEOUT", "error": "timed out after 3 attempts"})
                continue

            # NASS answers HTTP 400 when a series has no records for that state
            if response.status_code != 200:
                failures.append({"crop": crop, "field": field, "state_alpha": state,
                                 "status": response.status_code, "error": response.text[:200]})
                time.sleep(1)
                continue

            with open(raw_dir / f"{crop}_{state}_{field}.json", "w") as f:
                f.write(response.text)

            data = pd.DataFrame(response.json().get("data", []))
            if data.empty:
                failures.append({"crop": crop, "field": field, "state_alpha": state,
                                 "status": 200, "error": "empty data array"})
            else:
                data["crop"] = crop
                data["field"] = field
                frames.append(data)
            print(f"  {crop:8s} {state} {field:20s} {len(data):5d} rows")
            time.sleep(1)

df = pd.concat(frames, ignore_index=True)

# Drop OTHER (COMBINED) COUNTIES (county_code 998): not a real county
df = df[(df["county_code"] != "998") & (df["county_ansi"] != "")].copy()

df["fips"] = df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)
df["year"] = df["year"].astype(int)
df["value"] = pd.to_numeric(df["Value"].str.replace(",", "", regex=False), errors="coerce")

# Same rule as the master: a yield of 0 is not an observation
zero_yield = df["field"].str.startswith("yield") & (df["value"] <= 0)
df.loc[zero_yield, "value"] = float("nan")
print(f"\nNulled {zero_yield.sum()} yields <= 0")

dups = df.duplicated(["fips", "crop", "year", "field"]).sum()
print("Duplicate (fips, crop, year, field) rows:", dups)
assert dups == 0, "Duplicate NASS irrigation records"

wide = (
    df.pivot_table(index=["fips", "crop", "year"], columns="field",
                   values="value", aggfunc="first")
    .reset_index()
)
wide.columns.name = None
for col in SERIES["CORN"]:
    if col not in wide:
        wide[col] = float("nan")

# Share of grain acres harvested that were irrigated, against the master's acres
nass = pd.read_parquet(ROOT / "data/processed/nass/nass_raw.parquet")
total = (
    nass[nass["statistic"] == "AREA HARVESTED"][["fips", "crop", "year", "value"]]
    .rename(columns={"value": "acres_harvested"})
)
wide = wide.merge(total, on=["fips", "crop", "year"], how="left")
wide["irrigated_share"] = (wide["irrigated_acres"] / wide["acres_harvested"]).round(3)

wide["state_alpha"] = wide["fips"].str[:2].map({"06": "CA", "10": "DE", "19": "IA", "31": "NE"})
out = wide[["fips", "state_alpha", "crop", "year",
            "irrigated_share", "yield_irrigated", "yield_non_irrigated"]]
out = out.dropna(subset=["irrigated_share", "yield_irrigated", "yield_non_irrigated"], how="all")
out = out.sort_values(["fips", "crop", "year"]).reset_index(drop=True)

# Checks
print()
print("Rows:", len(out))
print("irrigated_share in [0, 1]:", out["irrigated_share"].dropna().between(0, 1).all())
print("Share without total acres:", (wide["irrigated_acres"].notna() & wide["acres_harvested"].isna()).sum())
print(out.groupby(["state_alpha", "crop"])["year"].agg(["count", "min", "max"]).to_string())

# Acre-weighted irrigated + non-irrigated yield should match the published total yield
total_yield = (
    nass[nass["statistic"] == "YIELD"][["fips", "crop", "year", "value"]]
    .rename(columns={"value": "yield_total"})
)
chk = out.merge(total_yield, on=["fips", "crop", "year"]).dropna()
blend = chk["irrigated_share"] * chk["yield_irrigated"] + (1 - chk["irrigated_share"]) * chk["yield_non_irrigated"]
gap = (blend - chk["yield_total"]).abs() / chk["yield_total"]
print(f"Blended vs total yield: {len(chk)} rows, median gap {gap.median():.1%}, "
      f"{(gap > 0.05).mean():.1%} over 5%")

out.to_parquet(out_dir / "nass_irrigation.parquet", index=False)
print(f"\nSaved {len(out):,} rows --> {out_dir / 'nass_irrigation.parquet'}")

with open(out_dir / "irrigation_failures.json", "w") as f:
    json.dump(failures, f, indent=2)
print(f"Logged {len(failures)} empty or failed series --> {out_dir / 'irrigation_failures.json'}")
