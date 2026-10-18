"""About this tool and data sources: the About text and DATA_CREDITS (from soil_planner/soil_tool.py).
Runs through soil_planner/app.py (st.navigation)."""
import streamlit as st

from soil_planner import app_common as ac
from soil_planner import soil_tool as tool

ia = ac.load_data()
n_counties = ia[tool.COL_FIPS].nunique()
data_years = f"{int(ia[tool.COL_YEAR].min())}–{int(ia[tool.COL_YEAR].max())}"

st.markdown(
    f"**Data.** USDA NASS county yields, U.S. Drought Monitor weekly maps, NOAA ACIS weather and NRCS SSURGO soil, "
    f"combined in the Data to Harvest hackathon master dataset: {n_counties} Iowa counties, {data_years}, corn and "
    f"soybeans, rainfed. **Context data** in the county panel: extra surface-soil properties from the September 2026 "
    f"SSURGO release (USDA NRCS Soil Data Access) and conservation-practice shares from the USDA Census of "
    f"Agriculture, 2017 and 2022. These are shown for context only and enter no score or test.\n\n"
    f"**Ranking.** The priority list and the default map use the drought penalty computed on all years {ac.ALL_YEARS}, "
    f"with the {ac.D2_LABEL.split(' ')[0]} definition.\n\n"
    f"**Test.** The evidence section shows the held-out test that validated the method: scores built on {ac.TRAIN_LABEL} "
    f"only, checked on the {ac.TEST_LABEL} drought years they had never seen.\n\n"
    f"`notebooks/Soil_Program_Planner.ipynb` shows the same analysis as a report."
)
st.markdown(tool.DATA_CREDITS)
