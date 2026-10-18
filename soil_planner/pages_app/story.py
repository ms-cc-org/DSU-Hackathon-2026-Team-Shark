"""How we got here: the project story (STORY_NOTE) followed by the methods note (METHODS_NOTE).
Both texts live only in soil_planner/soil_tool.py. Runs through soil_planner/app.py (st.navigation)."""
import streamlit as st

from soil_planner import soil_tool as tool

st.markdown(tool.STORY_NOTE)
st.divider()
st.markdown(tool.METHODS_NOTE)
