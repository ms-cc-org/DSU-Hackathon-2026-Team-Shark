"""
Part A: extra SSURGO soil properties for the 99 Iowa counties, from NRCS Soil Data Access (no key).

Same request pattern, overlap-table county aggregation and FIPS handling as src/build/SSURGO_data_pull.py:
county area comes from laoverlap -> muaoverlap (areaovacres), components are weighted by comppct_r, and the
county symbol (e.g. IA153) is turned into a 5-character FIPS text ('19' + '153').

Outputs (soil_planner/extra_data/):
  iowa_soil_extra.csv      one row per county
  raw/IA_*.json            the raw SDA responses (cache; delete to re-pull)
  README.md                source, queries, date pulled, units, method, validation result

Run from the repo root:  python soil_planner/pulls/pull_soil_extra.py
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.data_loader import load_master, load_soil  # noqa: E402

SDA_URL = "https://sdmdataaccess.nrcs.usda.gov/Tabular/SDMTabularService/post.rest"
STATE, FIPS_PREFIX = "IA", "19"
OUT_DIR = ROOT / "soil_planner/extra_data"
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "iowa_soil_extra.csv"
README = OUT_DIR / "README.md"
AWS_CLOSE_MM = 1.0            # "within 1 mm" count reported in the README
AWS_STOP_MM = 10.0            # stop only for differences this large; smaller ones are expected from the newer SSURGO release
AWS_VALIDATION_CSV = OUT_DIR / "aws_validation.csv"


def sda_query(sql, timeout=600):
    """Execute a SQL query against SDA and return a DataFrame (same as src/build/SSURGO_data_pull.py)."""
    resp = requests.post(SDA_URL, json={"query": sql, "format": "JSON+COLUMNNAME+METADATA"}, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"SDA HTTP {resp.status_code}: {resp.text[:1500]}")
    data = resp.json()
    if "Table" not in data or len(data["Table"]) <= 2:
        return pd.DataFrame()
    rows = data["Table"]
    return pd.DataFrame(rows[2:], columns=rows[0])


def cached_query(name, sql, timeout=600):
    raw_file = RAW_DIR / f"{STATE}_{name}.json"
    if raw_file.exists() and raw_file.stat().st_size > 10:
        print(f"  {name}: cached")
        return pd.read_json(raw_file, dtype=False)
    print(f"  {name}: querying SDA...", end=" ", flush=True)
    t0 = time.time()
    df = sda_query(sql, timeout=timeout)
    df.to_json(raw_file, orient="records")
    print(f"{len(df)} rows in {time.time() - t0:.0f}s")
    time.sleep(2)
    return df


def county_sym_to_fips(sym):
    return FIPS_PREFIX + sym[2:]


# The same overlap joins as the source script: survey legend -> county overlap -> map-unit overlap acres.
JOINS = f"""
FROM legend l
    INNER JOIN laoverlap lao ON l.lkey = lao.lkey
    INNER JOIN muaoverlap mao ON lao.lareaovkey = mao.lareaovkey
"""
WHERE = f"""
WHERE lao.areatypename = 'County or Parish'
    AND l.areasymbol LIKE '{STATE}%'
"""

# Query 1: aws_100cm_mm exactly as in src/build/SSURGO_data_pull.py (validation of the weighting)
Q_AWS = f"""
SELECT
    lao.areasymbol AS county_sym,
    SUM(CAST(mao.areaovacres AS FLOAT) * ma.aws0100wta * 10)
        / NULLIF(SUM(CASE WHEN ma.aws0100wta IS NOT NULL
                     THEN CAST(mao.areaovacres AS FLOAT) ELSE 0 END), 0)
        AS aws_100cm_mm
{JOINS}
    INNER JOIN muaggatt ma ON CAST(mao.mukey AS VARCHAR) = CAST(ma.mukey AS VARCHAR)
{WHERE}
GROUP BY lao.areasymbol
ORDER BY lao.areasymbol
"""

# Query 2: surface-layer texture / organic matter and component slope, area x component-percent weighted.
# Surface layer = the component's horizon starting at 0 cm (one per component; ties broken by the lowest chkey).
Q_SURFACE = f"""
SELECT
    lao.areasymbol AS county_sym,
    SUM(CASE WHEN h.om_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r * h.om_r END)
        / NULLIF(SUM(CASE WHEN h.om_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END), 0)
        AS om_surface_pct,
    SUM(CASE WHEN h.claytotal_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r * h.claytotal_r END)
        / NULLIF(SUM(CASE WHEN h.claytotal_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END), 0)
        AS clay_surface_pct,
    SUM(CASE WHEN h.sandtotal_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r * h.sandtotal_r END)
        / NULLIF(SUM(CASE WHEN h.sandtotal_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END), 0)
        AS sand_surface_pct,
    SUM(CASE WHEN c.slope_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r * c.slope_r END)
        / NULLIF(SUM(CASE WHEN c.slope_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END), 0)
        AS slope_pct,
    SUM(CAST(mao.areaovacres AS FLOAT) * c.comppct_r) / 100.0 AS component_acres,
    SUM(CASE WHEN h.om_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END) / 100.0 AS acres_with_om,
    SUM(CASE WHEN c.slope_r IS NOT NULL THEN CAST(mao.areaovacres AS FLOAT) * c.comppct_r END) / 100.0 AS acres_with_slope
{JOINS}
    INNER JOIN mapunit mu ON mao.mukey = mu.mukey
    INNER JOIN component c ON mu.mukey = c.mukey
    LEFT JOIN (SELECT cokey, MIN(chkey) AS chkey FROM chorizon WHERE hzdept_r = 0 GROUP BY cokey) tophz
        ON tophz.cokey = c.cokey
    LEFT JOIN chorizon h ON h.chkey = tophz.chkey
{WHERE}
    AND c.comppct_r > 0
GROUP BY lao.areasymbol
ORDER BY lao.areasymbol
"""

# Query 3: area x component-percent by drainage class, for the dominant class and its share
Q_DRAINAGE = f"""
SELECT
    lao.areasymbol AS county_sym,
    c.drainagecl,
    SUM(CAST(mao.areaovacres AS FLOAT) * c.comppct_r) / 100.0 AS acres
{JOINS}
    INNER JOIN mapunit mu ON mao.mukey = mu.mukey
    INNER JOIN component c ON mu.mukey = c.mukey
{WHERE}
    AND c.comppct_r > 0
    AND c.drainagecl IS NOT NULL
GROUP BY lao.areasymbol, c.drainagecl
ORDER BY lao.areasymbol, c.drainagecl
"""

print(f"Iowa SSURGO extra pull, {dt.date.today()}")
aws = cached_query("aws_validation", Q_AWS)
surf = cached_query("surface_slope", Q_SURFACE)
drain = cached_query("drainage", Q_DRAINAGE)

for df in (aws, surf, drain):
    df.drop(df[~df["county_sym"].astype(str).str.startswith(STATE)].index, inplace=True)   # cross-border counties
    df["fips"] = df["county_sym"].astype(str).map(county_sym_to_fips)
for col in ["aws_100cm_mm"]:
    aws[col] = pd.to_numeric(aws[col], errors="coerce")
for col in ["om_surface_pct", "clay_surface_pct", "sand_surface_pct", "slope_pct", "component_acres", "acres_with_om", "acres_with_slope"]:
    surf[col] = pd.to_numeric(surf[col], errors="coerce")
drain["acres"] = pd.to_numeric(drain["acres"], errors="coerce")

# ---- validation: recomputed aws_100cm_mm vs load_soil() ----
ref = load_soil()
ref = ref[ref["fips"].str.startswith(FIPS_PREFIX)][["fips", "aws_100cm_mm"]].rename(columns={"aws_100cm_mm": "aws_ref"})
val = ref.merge(aws[["fips", "aws_100cm_mm"]], on="fips", how="outer", indicator=True)
val["diff_mm"] = (val["aws_100cm_mm"] - val["aws_ref"]).abs()
max_diff = float(val["diff_mm"].max())
print(f"\nValidation: {len(ref)} Iowa counties in load_soil(), {len(aws)} from SDA, matched {int((val['_merge'] == 'both').sum())}")
n_close = int((val["diff_mm"] <= AWS_CLOSE_MM).sum())
worst = val.sort_values("diff_mm", ascending=False).iloc[0]
names_all = load_master()[["fips", "county_name"]].drop_duplicates("fips")
worst_name = names_all.set_index("fips")["county_name"].get(worst["fips"], worst["fips"])
print(f"aws_100cm_mm: {n_close} of {len(val)} counties within {AWS_CLOSE_MM:.0f} mm; mean |difference| = {val['diff_mm'].mean():.2f} mm; "
      f"max = {max_diff:.2f} mm ({worst_name}, {worst['fips']}); counties differing by > 0.01 mm: {int((val['diff_mm'] > 0.01).sum())}")
if (val["_merge"] != "both").any() or max_diff > AWS_STOP_MM:
    print(val[val["diff_mm"] > AWS_CLOSE_MM].to_string())
    raise SystemExit(f"STOP: aws_100cm_mm differs from load_soil() by more than {AWS_STOP_MM} mm or counties are missing")
aws_val = (val.merge(names_all, on="fips", how="left")
           .rename(columns={"aws_ref": "aws_100cm_mm_master", "aws_100cm_mm": "aws_100cm_mm_sda_2026_09", "diff_mm": "abs_diff_mm"})
           [["fips", "county_name", "aws_100cm_mm_master", "aws_100cm_mm_sda_2026_09", "abs_diff_mm"]]
           .sort_values("abs_diff_mm", ascending=False).reset_index(drop=True))
aws_val.to_csv(AWS_VALIDATION_CSV, index=False, float_format="%.4f")
print(f"per-county differences -> {AWS_VALIDATION_CSV.relative_to(ROOT)}")

# ---- drainage: dominant class and its share ----
tot = drain.groupby("fips")["acres"].sum().rename("drainage_acres")
dom = (drain.sort_values(["fips", "acres"], ascending=[True, False]).drop_duplicates("fips")
       .rename(columns={"drainagecl": "drainage_dominant", "acres": "dom_acres"})[["fips", "drainage_dominant", "dom_acres"]]
       .merge(tot, on="fips"))
dom["drainage_dominant_share_pct"] = 100 * dom["dom_acres"] / dom["drainage_acres"]

# ---- assemble ----
names = (load_master()[["fips", "county_name"]].drop_duplicates("fips"))
out = (surf[["fips", "county_sym", "om_surface_pct", "clay_surface_pct", "sand_surface_pct", "slope_pct",
             "component_acres", "acres_with_om", "acres_with_slope"]]
       .merge(dom[["fips", "drainage_dominant", "drainage_dominant_share_pct", "drainage_acres"]], on="fips", how="left")
       .merge(aws[["fips", "aws_100cm_mm"]].rename(columns={"aws_100cm_mm": "aws_100cm_mm_recomputed"}), on="fips", how="left")
       .merge(names, on="fips", how="left")
       .sort_values("fips").reset_index(drop=True))
out["surface_horizon_coverage_pct"] = 100 * out["acres_with_om"] / out["component_acres"]
out["slope_coverage_pct"] = 100 * out["acres_with_slope"] / out["component_acres"]
out = out[["fips", "county_name", "county_sym", "om_surface_pct", "clay_surface_pct", "sand_surface_pct", "slope_pct",
           "drainage_dominant", "drainage_dominant_share_pct", "aws_100cm_mm_recomputed",
           "surface_horizon_coverage_pct", "slope_coverage_pct", "component_acres"]]
assert out["fips"].map(type).eq(str).all() and out["fips"].str.len().eq(5).all() and not out["fips"].duplicated().any()
out.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(out)} counties -> {OUT_CSV.relative_to(ROOT)}")

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 20)
print("\ndescribe():")
print(out.drop(columns=["component_acres"]).describe().round(2).T.to_string())
print("\nmissing per column:"); print(out.isna().sum().to_string())
print("\ndominant drainage class counts:"); print(out["drainage_dominant"].value_counts().to_string())
print("\nall drainage classes present (acres, statewide):")
print(drain.groupby("drainagecl")["acres"].sum().sort_values(ascending=False).round(0).to_string())

# ---- README (Part A section; Part B is appended by its own script) ----
readme = f"""# Extra data for the Soil Program Planner (data preparation only)

Pulled by the scripts in `soil_planner/pulls/`. Nothing here changes the drought-penalty scoring; these files
are inputs for later work. `fips` is 5-character text in every file.

## iowa_soil_extra.csv  (Part A: more soil properties)

- **Source.** USDA NRCS Soil Data Access (SDA) tabular service, `{SDA_URL}`, SSURGO tables
  `legend`, `laoverlap`, `muaoverlap`, `mapunit`, `component`, `chorizon`, `muaggatt`. No key.
- **Date pulled.** {dt.date.today().isoformat()} (raw responses cached in `raw/IA_*.json`; delete them to re-pull).
- **Coverage.** {len(out)} Iowa counties, one row each.
- **Method.** Same county aggregation as `src/build/SSURGO_data_pull.py`: soil survey legends whose symbol starts
  with `IA`, overlapped with counties through `laoverlap` -> `muaoverlap`, each map unit weighted by its acres inside
  the county (`areaovacres`). Within a map unit, components are weighted by `comppct_r`. Each property is averaged
  only over the area where it is recorded (components with the property missing are left out of that average,
  not counted as zero). The county symbol (e.g. `IA153`) becomes FIPS `19153`.
- **Columns and units.**
  - `om_surface_pct`, `clay_surface_pct`, `sand_surface_pct`: representative organic matter, total clay and total
    sand (percent by weight) of the **surface layer**, defined as the component's horizon that starts at 0 cm
    (`chorizon.hzdept_r = 0`; when a component has two such horizons the lowest `chkey` is used).
  - `slope_pct`: representative slope (`component.slope_r`, percent), component- and area-weighted.
  - `drainage_dominant`: the `component.drainagecl` class covering the most component-weighted area in the county;
    `drainage_dominant_share_pct`: its share (percent) of the component area that has a drainage class.
  - `aws_100cm_mm_recomputed`: available water storage, top 100 cm, in mm, recomputed with the exact query of the
    source script (`muaggatt.aws0100wta` x 10) as a validation of the weighting.
  - `surface_horizon_coverage_pct`, `slope_coverage_pct`: share of the county's component area that has a surface
    horizon with organic matter / a slope value (how much of the county each average rests on).
  - `component_acres`: component-weighted acres summed over the county (map-unit overlap acres x comppct / 100).
- **SSURGO release.** These extra properties come from the SSURGO release current on SDA at the pull date; every
  Iowa survey area carries a September 2026 version date (`sacatalog.saverest`), the annual refresh. The master
  dataset's `aws_100cm_mm` (in `data/processed/soil/soil_county.parquet`) was pulled from an earlier release and
  **stays the storage variable used everywhere in the app and the notebooks**; this file supplies only the
  additional properties. `aws_100cm_mm_recomputed` is kept here for the validation only.
- **Validation.** The source script's exact aws query, run on the current release, against `load_soil()` for the
  {len(ref)} Iowa counties: {n_close} of {len(val)} within {AWS_CLOSE_MM:.0f} mm, mean absolute difference
  {val['diff_mm'].mean():.2f} mm, maximum {max_diff:.1f} mm ({worst_name}, {worst['fips']}). The query is identical, so the
  differences reflect NRCS map revisions between releases, not the weighting. Per-county table:
  `aws_validation.csv` (`aws_100cm_mm_master`, `aws_100cm_mm_sda_2026_09`, `abs_diff_mm`).
- **Queries.** See `Q_AWS`, `Q_SURFACE`, `Q_DRAINAGE` in `soil_planner/pulls/pull_soil_extra.py`.
"""
README.write_text(readme)
print(f"README written -> {README.relative_to(ROOT)}")
