"""Limits and next steps: LIMITS_NOTE then NEXT_STEPS_NOTE, both from soil_planner/soil_tool.py, in a narrower
prose column. Runs through soil_planner/app.py (st.navigation)."""
import streamlit as st

from soil_planner import soil_tool as tool

st.header("Limits and next steps")
prose, _ = st.columns([2, 1])
with prose:
    st.subheader("Limits")
    st.markdown(tool.LIMITS_NOTE)
    st.divider()
    st.markdown(tool.NEXT_STEPS_NOTE)
