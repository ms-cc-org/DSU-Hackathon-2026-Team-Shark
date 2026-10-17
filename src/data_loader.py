from pathlib import Path
import pandas as pd
import json

_ROOT = Path(__file__).resolve().parents[1]

def load_master():
    # The 21-field county × crop × year dataset
    df = pd.read_parquet(_ROOT / "data/master_dataset.parquet")
    # Plain floats (NaN for missing) behave the same in pandas, numpy and scikit-learn
    int_cols = ["extreme_heat_days", "max_drought_severity", "weeks_in_d2_plus"]
    df[int_cols] = df[int_cols].astype("float64")
    return df

def load_daily_weather():
    # Daily tmax, tmin, precipitation — 1999-2025, all counties
    return pd.read_parquet(_ROOT / "data/processed/acis/weather_daily.parquet")

def load_weekly_drought():
    # Weekly D0-D4 percentages and DSCI — 2000-2025, all counties
    return pd.read_parquet(_ROOT / "data/processed/drought/drought_weekly.parquet")

def load_nass_raw():
    # NASS yield, harvested acres, planted acres in long format
    return pd.read_parquet(_ROOT / "data/processed/nass/nass_raw.parquet")

def load_soil():
    # Static soil properties — one row per county
    return pd.read_parquet(_ROOT / "data/processed/soil/soil_county.parquet")

def load_modis():
    return pd.read_parquet(_ROOT / "data/processed/modis/modis_ndvi_county.parquet")

def load_irrigation():
    # NASS irrigated share and irrigated/non-irrigated yields per county x crop x year (extension)
    return pd.read_parquet(_ROOT / "data/processed/irrigation/nass_irrigation.parquet")

def load_counties():
    with open(_ROOT / "data/counties.geojson") as f:
        return json.load(f)