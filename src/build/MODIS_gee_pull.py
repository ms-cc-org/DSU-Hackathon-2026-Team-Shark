import os
import time
from pathlib import Path

import ee
import pandas as pd
from dotenv import load_dotenv

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

# Earth Engine needs a Google Cloud project ID: set EE_PROJECT in .env
load_dotenv(ROOT / ".env")
ee.Initialize(project=os.environ["EE_PROJECT"])

STATE_FIPS_TO_ALPHA = {"06": "CA", "10": "DE", "19": "IA", "31": "NE"}
SCALE_FACTOR = 0.0001  # NDVI/EVI are stored as int * 10000

RAW_DIR = ROOT / "data/raw/modis"
PROCESSED_DIR = ROOT / "data/processed/modis"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Load target counties from master dataset
master = pd.read_parquet(ROOT / "data/master_dataset.parquet")
target_fips = sorted(master["fips"].unique().tolist())
fips_to_state = (master.drop_duplicates("fips").set_index("fips")["state_alpha"].to_dict())
fips_to_county = (master.drop_duplicates("fips").set_index("fips")["county_name"].to_dict())

print(f"Target: {len(target_fips)} counties, 4 states, 2000-2025")

# GEE setup

# MODIS 16-day vegetation indices
modis = ee.ImageCollection("MODIS/061/MOD13Q1")


counties = ee.FeatureCollection("TIGER/2018/Counties").filter(ee.Filter.inList("GEOID", target_fips))

n_counties = counties.size().getInfo()
print(f"GEE counties loaded: {n_counties}")
if n_counties != len(target_fips):
    print(f"WARNING: expected {len(target_fips)}, got {n_counties}")

# Extract annual stats per county

KEEP_PROPS = ["GEOID", "ndvi_mean", "evi_mean", "ndvi_max", "evi_max", "peak_ndvi_doy",]


def strip_geometry(feature):
    # Drop polygon geometry to speed up getInfo() transfer.
    return ee.Feature(None, feature.toDictionary(KEEP_PROPS))


all_records = []
t0 = time.time()

for year in range(2000, 2026):
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"

    year_col = modis.filterDate(year_start, year_end).select(["NDVI", "EVI", "DayOfYear"])

    # Pixel-wise temporal mean
    mean_img = year_col.select(["NDVI", "EVI"]).mean()

    # Pixel-wise temporal max
    max_img = year_col.select(["NDVI", "EVI"]).max()

    # Peak greenness timing: for each pixel, DOY of the composite with highest NDVI
    peak_doy = year_col.qualityMosaic("NDVI").select("DayOfYear")

    # Stack into one image
    combined = (
        mean_img.rename(["ndvi_mean", "evi_mean"])
        .addBands(max_img.rename(["ndvi_max", "evi_max"]))
        .addBands(peak_doy.rename(["peak_ndvi_doy"]))
    )

    # Spatial mean per county polygon
    stats = combined.reduceRegions(
        collection=counties,
        reducer=ee.Reducer.mean(),
        scale=250,
    )

    # Strip geometry for faster transfer
    stats = stats.map(strip_geometry)

    # Retrieve results (retry on timeout)
    for attempt in range(1, 4):
        try:
            result = stats.getInfo()
            break
        except Exception as exc:
            if attempt < 3:
                print(f"  {year}: attempt {attempt} failed ({exc}), retrying...")
                time.sleep(5 * attempt)
            else:
                print(f"  {year}: FAILED after 3 attempts — {exc}")
                result = {"features": []}

    for feat in result.get("features", []):
        props = feat.get("properties", {})
        fips = props.get("GEOID", "")

        ndvi_mean = props.get("ndvi_mean")
        ndvi_max = props.get("ndvi_max")
        evi_mean = props.get("evi_mean")
        evi_max = props.get("evi_max")
        peak_doy_val = props.get("peak_ndvi_doy")

        all_records.append({
            "fips": fips,
            "year": year,
            "ndvi_mean": round(ndvi_mean * SCALE_FACTOR, 4) if ndvi_mean else None,
            "ndvi_max": round(ndvi_max * SCALE_FACTOR, 4) if ndvi_max else None,
            "evi_mean": round(evi_mean * SCALE_FACTOR, 4) if evi_mean else None,
            "evi_max": round(evi_max * SCALE_FACTOR, 4) if evi_max else None,
            "peak_ndvi_doy": int(round(peak_doy_val)) if peak_doy_val else None,
        })

    elapsed = time.time() - t0
    print(f"  {year}: {len(result.get('features', []))} counties  ({elapsed:.0f}s)")

# Build extension dataset
ext = pd.DataFrame(all_records)
print(f"\nRaw records: {len(ext):,}")

# Add county name and state
ext["county_name"] = ext["fips"].map(fips_to_county)
ext["state_alpha"] = ext["fips"].map(fips_to_state)

# NDVI anomaly: percent deviation from county's 26-year mean
county_means = ext.groupby("fips")["ndvi_mean"].transform("mean")
ext["ndvi_anomaly_pct"] = (
    (ext["ndvi_mean"] - county_means) / county_means * 100
).round(2)

# Final column order and sort
ext = ext[
    [
        "fips", "county_name", "state_alpha", "year",
        "ndvi_mean", "ndvi_max", "evi_mean", "evi_max",
        "ndvi_anomaly_pct", "peak_ndvi_doy",
    ]
].sort_values(["fips", "year"]).reset_index(drop=True)

# Save
ext.to_parquet(PROCESSED_DIR / "modis_ndvi_county.parquet", index=False)
ext.to_csv(PROCESSED_DIR / "modis_ndvi_county.csv", index=False)

elapsed_total = time.time() - t0

print(f"\n{'='*50}")
print("MODIS EXTENSION DATASET")
print(f"{'='*50}")
print(f"Rows: {len(ext):,}")
print(f"Counties: {ext['fips'].nunique()}")
print(f"Years: {ext['year'].min()}-{ext['year'].max()}")
print(f"States: {sorted(ext['state_alpha'].unique())}")
print(f"NDVI mean: [{ext['ndvi_mean'].min():.4f}, {ext['ndvi_mean'].max():.4f}]")
print(f"NDVI max: [{ext['ndvi_max'].min():.4f}, {ext['ndvi_max'].max():.4f}]")
print(f"EVI mean: [{ext['evi_mean'].min():.4f}, {ext['evi_mean'].max():.4f}]")
print(f"EVI max: [{ext['evi_max'].min():.4f}, {ext['evi_max'].max():.4f}]")
print(f"Peak DOY: [{ext['peak_ndvi_doy'].min()}, {ext['peak_ndvi_doy'].max()}]")
print(f"Time: {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
print(f"\nSaved to:")
print(f" {PROCESSED_DIR / 'modis_ndvi_county.parquet'}")
print(f" {PROCESSED_DIR / 'modis_ndvi_county.csv'}")
