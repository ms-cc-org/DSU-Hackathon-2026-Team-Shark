"""
Part B: conservation practices for Iowa counties from the Census of Agriculture (NASS Quick Stats, needs a key).

Same request pattern as src/build/NASS_data_pull.py: one api_GET request per short_desc with
source_desc=CENSUS, state_alpha=IA, agg_level_desc=COUNTY, domain_desc=TOTAL; raw responses archived; values parsed
with pd.to_numeric after removing thousands separators; county_code 998 (OTHER COMBINED COUNTIES) dropped;
fips = state_fips_code (2) + county_code (3), kept as 5-character text.

Suppression codes such as "(D)" and "(Z)" are kept as missing (never zero) and counted; the code is preserved in the
matching *_code column.

Outputs (soil_planner/extra_data/):
  iowa_conservation_practices.csv   county x census year, raw acres + computed shares
  raw/nass_*.json                   raw Quick Stats responses (cache; delete to re-pull; they hold no key)
  README.md                         Part B section appended

Run from the repo root:  python soil_planner/pulls/pull_conservation_practices.py
"""
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nass_key import ROOT, load_key, redact  # noqa: E402

URL = "https://quickstats.nass.usda.gov/api/api_GET"
OUT_DIR = ROOT / "soil_planner/extra_data"
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "iowa_conservation_practices.csv"
README = OUT_DIR / "README.md"
STATE, FIPS_PREFIX = "IA", "19"

ITEMS = {   # column name -> Quick Stats short_desc (confirmed from the parameter-values endpoint, see nass_discover_items.py)
    "cover_crop_acres":        "PRACTICES, LAND USE, CROPLAND, COVER CROP PLANTED, (EXCL CRP) - ACRES",
    "no_till_acres":           "PRACTICES, LAND USE, CROPLAND, CONSERVATION TILLAGE, NO-TILL - ACRES",
    "reduced_till_acres":      "PRACTICES, LAND USE, CROPLAND, CONSERVATION TILLAGE, (EXCL NO-TILL) - ACRES",
    "conventional_till_acres": "PRACTICES, LAND USE, CROPLAND, CONVENTIONAL TILLAGE - ACRES",
    "cropland_acres":          "AG LAND, CROPLAND - ACRES",
    "harvested_cropland_acres": "AG LAND, CROPLAND, HARVESTED - ACRES",
}
PRACTICE_ITEMS = ["cover_crop_acres", "no_till_acres", "reduced_till_acres", "conventional_till_acres"]
TILL_ITEMS = ["no_till_acres", "reduced_till_acres", "conventional_till_acres"]

# Definitions: filled in from NASS's Census of Agriculture Appendix B (General Explanation) where confirmed.
# Where a definition could not be confirmed the README says so instead of guessing.
DEFINITIONS_FILE = Path(__file__).resolve().parent / "nass_item_definitions.md"

key = load_key()


def slug(col):
    return re.sub(r"[^a-z0-9]+", "_", col.lower()).strip("_")


def fetch(col, short_desc):
    raw_file = RAW_DIR / f"nass_{slug(col)}.json"
    if raw_file.exists() and raw_file.stat().st_size > 10:
        print(f"  {col}: cached")
        return json.loads(raw_file.read_text()).get("data", [])
    params = {"key": key, "source_desc": "CENSUS", "short_desc": short_desc, "state_alpha": STATE,
              "agg_level_desc": "COUNTY", "domain_desc": "TOTAL", "format": "JSON"}
    for attempt in range(1, 4):
        try:
            resp = requests.get(URL, params=params, timeout=120)
            break
        except requests.exceptions.RequestException as e:
            print(f"  {col}: attempt {attempt} failed: {redact(e, key)[:120]}")
            if attempt == 3:
                raise SystemExit("giving up")
            time.sleep(5 * attempt)
    if resp.status_code != 200:
        raise SystemExit(f"  {col}: HTTP {resp.status_code}: {redact(resp.text[:300], key)}")
    body = resp.json()
    raw_file.write_text(json.dumps(body))      # the body carries no key
    data = body.get("data", [])
    print(f"  {col}: {len(data)} rows")
    time.sleep(1)
    return data


print(f"Iowa Census of Agriculture conservation practices, {dt.date.today()}")
frames = []
for col, sd in ITEMS.items():
    rows = fetch(col, sd)
    f = pd.DataFrame(rows)
    f["item"] = col
    frames.append(f)
raw = pd.concat(frames, ignore_index=True)

# sanity on the filters (same checks the source script relies on)
print("\nsource_desc:", raw["source_desc"].unique().tolist(), "| domain_desc:", raw["domain_desc"].unique().tolist(),
      "| reference_period_desc:", raw["reference_period_desc"].unique().tolist(), "| unit_desc:", raw["unit_desc"].unique().tolist())
n998 = int((raw["county_code"] == "998").sum())
raw = raw[raw["county_code"] != "998"].copy()
print(f"dropped {n998} county_code=998 (OTHER COMBINED COUNTIES) rows")
raw["year"] = pd.to_numeric(raw["year"], errors="coerce").astype(int)
raw["fips"] = raw["state_fips_code"].astype(str).str.zfill(2) + raw["county_code"].astype(str).str.zfill(3)
assert raw["fips"].str.len().eq(5).all() and raw["fips"].str.startswith(FIPS_PREFIX).all()
raw["value_raw"] = raw["Value"].astype(str).str.strip()
raw["value"] = pd.to_numeric(raw["value_raw"].str.replace(",", "", regex=False), errors="coerce")
raw["code"] = raw["value_raw"].where(raw["value"].isna(), None)       # "(D)", "(Z)", ... kept as missing, never zero
dups = raw.duplicated(subset=["fips", "year", "item"], keep=False)
assert not dups.any(), raw[dups][["fips", "year", "item", "short_desc", "value_raw"]].to_string()

print("\nrows and years per item:")
print(raw.groupby("item").agg(rows=("fips", "size"), counties=("fips", "nunique"),
                              years=("year", lambda s: ", ".join(map(str, sorted(s.unique())))),
                              suppressed=("code", lambda s: s.notna().sum())).reindex(list(ITEMS)).to_string())
print("\nsuppression codes seen:")
print(raw.loc[raw["code"].notna()].groupby(["item", "code"]).size().to_string())

# keep the census years in which the practice items are published (the cropland items go back further)
practice_years = sorted(raw.loc[raw["item"].isin(PRACTICE_ITEMS), "year"].unique())
other_years = sorted(set(raw["year"].unique()) - set(practice_years))
print(f"\ncensus years with practice items: {practice_years}; cropland-only years left out of the CSV: {other_years}")
raw = raw[raw["year"].isin(practice_years)]

# wide: one row per county x year
val = raw.pivot(index=["fips", "year"], columns="item", values="value").reindex(columns=list(ITEMS))
code = raw.pivot(index=["fips", "year"], columns="item", values="code").reindex(columns=list(ITEMS)).add_suffix("_code")
names = raw.groupby("fips")["county_name"].first().str.title().str.replace(r"\bO\s?Brien\b", "O'Brien", regex=True) + " County"
wide = val.join(code).reset_index()
wide.insert(1, "county_name", wide["fips"].map(names))

# derived: missing stays missing, never zero
all_till = wide[TILL_ITEMS].notna().all(axis=1)
wide["tilled_total"] = wide[TILL_ITEMS].sum(axis=1).where(all_till)
wide["no_till_share"] = wide["no_till_acres"] / wide["tilled_total"]
wide["reduced_till_share"] = wide["reduced_till_acres"] / wide["tilled_total"]
wide["conventional_share"] = wide["conventional_till_acres"] / wide["tilled_total"]
wide["cover_crop_share"] = wide["cover_crop_acres"] / wide["harvested_cropland_acres"]
wide["tilled_to_harvested"] = wide["tilled_total"] / wide["harvested_cropland_acres"]
wide["tilled_to_cropland"] = wide["tilled_total"] / wide["cropland_acres"]
wide = wide.sort_values(["year", "fips"]).reset_index(drop=True)
assert wide["fips"].map(type).eq(str).all()
wide.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(wide)} county-years -> {OUT_CSV.relative_to(ROOT)}")

pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print("\ncounties per year with a value, per item:")
print(wide.groupby("year")[list(ITEMS) + ["tilled_total", "cover_crop_share"]].count().to_string())
print("\nmissing (suppressed or not published) county-years per item and year:")
print(wide.groupby("year")[list(ITEMS)].apply(lambda g: g.isna().sum()).to_string())
print("\nmedian ratio across counties, per year: tilled_total / harvested cropland and / total cropland")
ratios = wide.groupby("year")[["tilled_to_harvested", "tilled_to_cropland"]].agg(["median", "min", "max", "count"]).round(3)
ratios.columns = [f"{a} {b}" for a, b in ratios.columns]
print(ratios.to_string())
print("\ndescribe():")
print(wide.drop(columns=["fips", "county_name", "year"] + [c + "_code" for c in ITEMS]).describe().round(3).T.to_string())

# ---- README: Part B section (replace an earlier Part B section if present) ----
defs = DEFINITIONS_FILE.read_text() if DEFINITIONS_FILE.exists() else "- Definitions not yet looked up.\n"
sup = raw.loc[raw["code"].notna()].groupby(["item", "code"]).size()
sup_txt = "; ".join(f"{i}: {c} x{n}" for (i, c), n in sup.items()) or "none"
miss = wide.groupby("year")[list(ITEMS)].apply(lambda g: g.isna().sum())
section = f"""
## iowa_conservation_practices.csv  (Part B: conservation practices, Census of Agriculture)

- **Source.** USDA NASS Quick Stats API (`{URL}`), `source_desc=CENSUS`, `agg_level_desc=COUNTY`, `domain_desc=TOTAL`,
  `state_alpha=IA`. The key is read from the repo-root `.env` at run time and is not stored anywhere.
- **Date pulled.** {dt.date.today().isoformat()} (raw responses cached in `raw/nass_*.json`).
- **Coverage.** Census years {", ".join(map(str, practice_years))}; {wide['fips'].nunique()} Iowa counties; {len(wide)} county-years.
  The two cropland items are also published for {", ".join(map(str, other_years)) or "no other"} census years; those years have no
  practice items and are left out of the CSV (they remain in the raw cache). The 2012 Census also collected cover
  crops and tillage, but Quick Stats publishes the 2012 Iowa values at state level only (checked: no county rows under
  any domain), so 2012 is absent.
- **Items** (`short_desc` as confirmed with the parameter-values endpoint; operation counts and acres per operation skipped):
""" + "\n".join(f"  - `{c}` = `{sd}`" for c, sd in ITEMS.items()) + f"""
- **Units.** All raw columns are acres. Shares are fractions (0-1), ratios are unitless.
- **Suppression.** Any non-numeric `Value` is kept as **missing, never zero**, and the code is preserved in the
  matching `*_code` column. NASS's symbol list (2022 Census of Agriculture, Volume 1, Introduction, "Abbreviations and
  Symbols"): `(D)` "Withheld to avoid disclosing data for individual farms", `(Z)` "Less than half of the unit shown",
  `(NA)` "Not available", `(X)` "Not applicable". Codes seen in this pull: {sup_txt}.
- **Computed columns.**
  - `tilled_total` = `no_till_acres` + `reduced_till_acres` + `conventional_till_acres`, only when all three are
    present; missing otherwise.
  - `no_till_share`, `reduced_till_share`, `conventional_share` = each tillage item / `tilled_total`.
  - `cover_crop_share` = `cover_crop_acres` / `harvested_cropland_acres`.
  - `tilled_to_harvested`, `tilled_to_cropland` = `tilled_total` / harvested cropland and / total cropland (checks).
- **Checks.** Median across counties of `tilled_total` / harvested cropland and / total cropland, per year:

{ratios.to_markdown()}

  Missing county-years per item and year (suppressed or not published):

{miss.to_markdown()}

- **Definitions.** {defs.strip()}
- **Query.** See `ITEMS` and `fetch()` in `soil_planner/pulls/pull_conservation_practices.py`.
"""
text = README.read_text() if README.exists() else "# Extra data for the Soil Program Planner\n"
marker = "\n## iowa_conservation_practices.csv"
if marker in text:
    text = text[:text.index(marker)]
README.write_text(text.rstrip("\n") + "\n" + section)
print(f"README Part B section written -> {README.relative_to(ROOT)}")
