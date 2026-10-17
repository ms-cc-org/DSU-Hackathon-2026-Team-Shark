"""
SSURGO soil data pipeline.

Downloads county-level soil properties from NRCS Soil Data Access for
CA, NE, IA, DE, and produces data/processed/soil_county.parquet.

Source: Soil Data Access tabular service (SDA)
  https://sdmdataaccess.nrcs.usda.gov/Tabular/SDMTabularService/post.rest

Tables used: legend, laoverlap, muaoverlap, mapunit, muaggatt, component, cointerp.
County aggregation goes through the overlap tables (laoverlap → muaoverlap)
because soil survey areas don't map 1:1 to counties.

Note: the spec references `valu1` (gSSURGO value-added table) which is NOT
available in SDA. Equivalent values come from:
  - aws0_100  → muaggatt.aws0100wta (in cm, ×10 for mm)
  - droughty  → derived as muaggatt.aws0100wta ≤ 15.2 cm (= 152 mm threshold)
  - nccpi3*   → cointerp with crop-specific rulenames, component-weighted
"""

import json
import time
from pathlib import Path

import pandas as pd
import requests

# Repo root, so the script works from any directory
ROOT = Path(__file__).resolve().parents[2]

SDA_URL = "https://sdmdataaccess.nrcs.usda.gov/Tabular/SDMTabularService/post.rest"

# State abbreviation → 2-digit FIPS prefix
STATES = {
    "CA": "06",
    "NE": "31",
    "IA": "19",
    "DE": "10",
}

NCCPI_RULES = {
    "nccpi_corn": "NCCPI - NCCPI Corn Submodel (I)",
    "nccpi_soy": "NCCPI - NCCPI Soybeans Submodel (I)",
    "nccpi_sg": "NCCPI - NCCPI Small Grains Submodel (II)",
}

raw_dir = ROOT / "data/raw/ssurgo"
raw_dir.mkdir(parents=True, exist_ok=True)


def sda_query(sql, timeout=300):
    """Execute a SQL query against SDA and return parsed JSON."""
    resp = requests.post(
        SDA_URL,
        json={"query": sql, "format": "JSON+COLUMNNAME+METADATA"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"SDA HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "Table" not in data:
        return pd.DataFrame()
    rows = data["Table"]
    # rows[0] = column names, rows[1] = metadata, rows[2:] = data
    if len(rows) <= 2:
        return pd.DataFrame()
    return pd.DataFrame(rows[2:], columns=rows[0])


def county_sym_to_fips(sym, state_fips_prefix):
    """Convert SDA county symbol (e.g. 'DE001') to 5-digit FIPS ('10001')."""
    county_code = sym[2:]  # strip 2-char state abbreviation
    return state_fips_prefix + county_code


# ── Query 1: AWS + droughty from muaggatt ────────────────────────────

def build_aws_query(state_abbr):
    return f"""
SELECT
    lao.areasymbol AS county_sym,
    SUM(CAST(mao.areaovacres AS FLOAT) * ma.aws0100wta * 10)
        / NULLIF(SUM(CASE WHEN ma.aws0100wta IS NOT NULL
                     THEN CAST(mao.areaovacres AS FLOAT) ELSE 0 END), 0)
        AS aws_100cm_mm,
    SUM(CASE WHEN ma.aws0100wta <= 15.2
             THEN CAST(mao.areaovacres AS FLOAT) ELSE 0 END) * 100.0
        / NULLIF(SUM(CAST(mao.areaovacres AS FLOAT)), 0)
        AS droughty_pct
FROM legend l
    INNER JOIN laoverlap lao ON l.lkey = lao.lkey
    INNER JOIN muaoverlap mao ON lao.lareaovkey = mao.lareaovkey
    INNER JOIN muaggatt ma ON CAST(mao.mukey AS VARCHAR) = CAST(ma.mukey AS VARCHAR)
WHERE lao.areatypename = 'County or Parish'
    AND l.areasymbol LIKE '{state_abbr}%'
GROUP BY lao.areasymbol
ORDER BY lao.areasymbol
"""


# ── Query 2: NCCPI from cointerp (component-weighted, area-weighted) ─

def build_nccpi_query(state_abbr, rule_name, col_alias):
    return f"""
SELECT
    lao.areasymbol AS county_sym,
    SUM(CAST(mao.areaovacres AS FLOAT) * c.comppct_r * CAST(ci.interphr AS FLOAT))
        / NULLIF(SUM(CAST(mao.areaovacres AS FLOAT) * c.comppct_r), 0)
        AS {col_alias}
FROM legend l
    INNER JOIN laoverlap lao ON l.lkey = lao.lkey
    INNER JOIN muaoverlap mao ON lao.lareaovkey = mao.lareaovkey
    INNER JOIN mapunit mu ON mao.mukey = mu.mukey
    INNER JOIN component c ON mu.mukey = c.mukey
    INNER JOIN cointerp ci ON c.cokey = ci.cokey
WHERE lao.areatypename = 'County or Parish'
    AND l.areasymbol LIKE '{state_abbr}%'
    AND ci.rulename = '{rule_name}'
    AND ci.interphr IS NOT NULL
    AND c.comppct_r > 0
GROUP BY lao.areasymbol
ORDER BY lao.areasymbol
"""


# ── Execute ──────────────────────────────────────────────────────────

all_rows = []
failures = []

for state_abbr, state_fips in STATES.items():
    print(f"\n{'=' * 40}")
    print(f"  {state_abbr} (FIPS prefix {state_fips})")
    print(f"{'=' * 40}")

    # AWS + droughty
    raw_file = raw_dir / f"{state_abbr}_aws.json"
    try:
        if raw_file.exists() and raw_file.stat().st_size > 10:
            aws_df = pd.read_json(raw_file)
            print(f"  AWS: cached ({len(aws_df)} counties)")
        else:
            print(f"  AWS: querying...")
            aws_df = sda_query(build_aws_query(state_abbr), timeout=300)
            aws_df.to_json(raw_file, orient="records")
            print(f"  AWS: {len(aws_df)} counties")
    except Exception as e:
        print(f"  AWS FAILED: {e}")
        failures.append({"state": state_abbr, "query": "aws", "error": str(e)[:200]})
        aws_df = pd.DataFrame()

    time.sleep(2)

    # NCCPI — one query per crop submodel
    nccpi_frames = []
    for col_alias, rule_name in NCCPI_RULES.items():
        raw_file = raw_dir / f"{state_abbr}_{col_alias}.json"
        try:
            if raw_file.exists() and raw_file.stat().st_size > 10:
                ndf = pd.read_json(raw_file)
                print(f"  {col_alias}: cached ({len(ndf)} counties)")
            else:
                print(f"  {col_alias}: querying...")
                ndf = sda_query(
                    build_nccpi_query(state_abbr, rule_name, col_alias),
                    timeout=600,
                )
                ndf.to_json(raw_file, orient="records")
                print(f"  {col_alias}: {len(ndf)} counties")
        except Exception as e:
            print(f"  {col_alias} FAILED: {e}")
            failures.append({
                "state": state_abbr, "query": col_alias, "error": str(e)[:200],
            })
            ndf = pd.DataFrame()
        nccpi_frames.append(ndf)
        time.sleep(2)

    # Merge aws + nccpi for this state
    if aws_df.empty:
        continue

    merged = aws_df.copy()
    for ndf in nccpi_frames:
        if not ndf.empty:
            merged = merged.merge(ndf, on="county_sym", how="left")

    # Drop cross-border counties (e.g. NV/OR entries from CA survey areas)
    merged = merged[merged["county_sym"].str.startswith(state_abbr)].copy()

    # Convert county_sym → FIPS
    merged["fips"] = merged["county_sym"].apply(
        lambda s: county_sym_to_fips(s, state_fips)
    )
    merged["state_alpha"] = state_abbr
    all_rows.append(merged)

# ── Combine ──────────────────────────────────────────────────────────

df = pd.concat(all_rows, ignore_index=True)

# Coerce numeric columns
for col in ["aws_100cm_mm", "droughty_pct", "nccpi_corn", "nccpi_soy", "nccpi_sg"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ── Validation ───────────────────────────────────────────────────────

print(f"\n{'=' * 50}")
print("SOIL COUNTY SUMMARY")
print(f"{'=' * 50}")
print(f"Counties:       {len(df)}")
print(f"States:         {sorted(df['state_alpha'].unique())}")
print(f"FIPS 5-char:    {(df['fips'].str.len() == 5).all()}")
print(f"\nCounties per state:")
for st in sorted(df["state_alpha"].unique()):
    n = len(df[df["state_alpha"] == st])
    print(f"  {st}: {n}")

print(f"\naws_100cm_mm:  [{df['aws_100cm_mm'].min():.1f}, {df['aws_100cm_mm'].max():.1f}] mm"
      f"  (null: {df['aws_100cm_mm'].isna().sum()})")
print(f"droughty_pct:  [{df['droughty_pct'].min():.1f}, {df['droughty_pct'].max():.1f}] %"
      f"  (null: {df['droughty_pct'].isna().sum()})")
for col in ["nccpi_corn", "nccpi_soy", "nccpi_sg"]:
    if col in df.columns:
        print(f"{col:15s}: [{df[col].min():.3f}, {df[col].max():.3f}]"
              f"  (null: {df[col].isna().sum()})")

# V16 prep: soil is time-invariant — one row per county is correct
print(f"\nDuplicate FIPS: {df['fips'].duplicated().sum()}")

# ── Save ─────────────────────────────────────────────────────────────

panel = (
    df[["fips", "state_alpha", "aws_100cm_mm", "droughty_pct",
        "nccpi_corn", "nccpi_soy", "nccpi_sg"]]
    .sort_values("fips")
    .reset_index(drop=True)
)

out_path = ROOT / "data/processed/soil/soil_county.parquet"
out_path.parent.mkdir(parents=True, exist_ok=True)
panel.to_parquet(out_path, index=False)
print(f"\nSaved {len(panel)} rows -> {out_path}")

if failures:
    fail_path = ROOT / "data/processed/soil/ssurgo_failures.json"
    with open(fail_path, "w") as f:
        json.dump(failures, f, indent=2)
    print(f"Logged {len(failures)} failures -> {fail_path}")
    for fail in failures:
        print(f"  FAILED: {fail['state']} {fail['query']}: {fail['error'][:80]}")
else:
    print("No failures.")
