"""
Part B, step 1: list the Quick Stats short_desc items available for Iowa counties in the Census of Agriculture
that mention cover crops, tillage or cropland. Discovery only; nothing is pulled.

Run from the repo root:  python soil_planner/pulls/nass_discover_items.py
"""
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nass_key import ROOT, load_key, redact  # noqa: E402

URL = "https://quickstats.nass.usda.gov/api/get_param_values/"
OUT = ROOT / "soil_planner/extra_data/nass_census_item_candidates.csv"
KEYWORDS = ["COVER CROP", "NO-TILL", "NO TILL", "TILLAGE", "CROPLAND"]

key = load_key()
params = {"key": key, "param": "short_desc", "source_desc": "CENSUS", "state_alpha": "IA", "agg_level_desc": "COUNTY"}
try:
    resp = requests.get(URL, params=params, timeout=300)
except Exception as e:  # never let the URL (which carries the key) reach the output
    raise SystemExit(f"request failed: {redact(e, key)}")
if resp.status_code != 200:
    raise SystemExit(f"HTTP {resp.status_code}: {redact(resp.text[:300], key)}")
values = resp.json().get("short_desc", [])
print(f"short_desc values for CENSUS / IA / COUNTY: {len(values)}")

rows = [{"short_desc": v, "keyword": next(k for k in KEYWORDS if k in v.upper())}
        for v in values if any(k in v.upper() for k in KEYWORDS)]
df = pd.DataFrame(rows).sort_values(["keyword", "short_desc"]).reset_index(drop=True)
df.to_csv(OUT, index=False)
print(f"{len(df)} candidates mention {KEYWORDS}; saved to {OUT.relative_to(ROOT)}\n")
pd.set_option("display.max_colwidth", 200); pd.set_option("display.width", 250)
for kw, g in df.groupby("keyword"):
    print(f"--- {kw} ({len(g)}) ---")
    for v in g["short_desc"]:
        print("  ", v)
