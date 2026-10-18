"""
Soil Program Planner - multipage Streamlit app for the Soil Conservation Office.

This file is the entrypoint: page config, title and decision line, the shared controls (crop, drought definition)
and the navigation. The pages live in soil_planner/pages_app/ (not soil_planner/pages/, so Streamlit's legacy
page auto-discovery stays off); shared cached calls and helpers are in soil_planner/app_common.py.

Run from the repository root:
    python -m streamlit run soil_planner/app.py

Every number shown in the app comes from soil_planner/soil_tool.py, the same functions the notebook
notebooks/Soil_Program_Planner.ipynb calls, so the app and the notebook show the same figures.
Nothing is typed in. The extra soil and practice data in the county panel are display only:
they enter no score, ranking or evidence table.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from soil_planner import app_common as ac  # noqa: E402
from soil_planner import soil_tool as tool  # noqa: E402

st.set_page_config(page_title="Soil Program Planner — Iowa", layout="wide", initial_sidebar_state="collapsed")

# ----------------------------------------------------------------------------------
# Header and shared controls (every page responds to these)
# ----------------------------------------------------------------------------------
with st.spinner("Loading the Iowa data and computing drought penalties…"):
    ia = ac.load_data()
n_counties = ia[tool.COL_FIPS].nunique()
data_years = f"{int(ia[tool.COL_YEAR].min())}–{int(ia[tool.COL_YEAR].max())}"

st.title("Soil Program Planner — Iowa corn and soybeans")
st.markdown("For the Soil Conservation Office: each winter, before the next season's program sign-ups, decide which "
            "counties get priority for soil-program outreach and funding to cut drought losses. "
            f"Data: {n_counties} Iowa counties, {data_years}.")
st.caption("The crop and drought definition chosen here apply to every page. Method, evidence, limits and data "
           "sources are in the menu above.")

c1, c2, _ = st.columns([1, 1.4, 2])
c1.radio("Crop", list(tool.CROPS), horizontal=True, key=ac.KEY_CROP)
c2.radio("Drought definition", list(tool.DROUGHT_DEFS), horizontal=True, key=ac.KEY_DEF)

# ----------------------------------------------------------------------------------
# Navigation (Streamlit 1.65: st.Page, sections, position="top")
# ----------------------------------------------------------------------------------
pages = {
    "Plan": [
        st.Page(ac.PAGE_PLAN, title="This winter's plan", default=True),
        st.Page(ac.PAGE_EXPLORER, title="County explorer"),
    ],
    "Evidence": [
        st.Page(ac.PAGE_EVIDENCE, title="How we know it works"),
        st.Page(ac.PAGE_STORY, title="How we got here"),
    ],
    "Reference": [
        st.Page(ac.PAGE_LIMITS, title="Limits and next steps"),
        st.Page(ac.PAGE_ABOUT, title="About and data sources"),
    ],
}
pg = st.navigation(pages, position="top")
pg.run()
