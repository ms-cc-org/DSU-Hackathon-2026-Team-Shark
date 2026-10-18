"""This winter's plan: the recommendation, the main insights and the priority list.
Runs through soil_planner/app.py (st.navigation), which sets the shared crop and drought-definition controls."""
import streamlit as st

from soil_planner import app_common as ac
from soil_planner import soil_tool as tool

crop_label, crop, _, _ = ac.selection()

# ----------------------------------------------------------------------------------
# Shared computations for the selected crop
# ----------------------------------------------------------------------------------
dep = ac.deployment_scores(crop)
top = ac.priority(crop)
with st.spinner("Running the held-out test (first load only)…"):
    rk = ac.ranking_evidence()
hm = tool.headline_metrics(rk["summary"], crop)
std = top[top["confidence"] == tool.CONFIDENCE_STANDARD]
low = top[top["confidence"] == tool.CONFIDENCE_LOWER]
n_std, n_low = len(std), len(low)
first = top.iloc[0]

# ----------------------------------------------------------------------------------
# 1. Recommendation
# ----------------------------------------------------------------------------------
st.success(
    f"**Recommendation for this winter's sign-ups ({crop_label}):** Start outreach in the **{n_std} priority counties "
    f"with standard confidence**. Verify the **{n_low} lower-confidence counties** with local staff before committing "
    f"funds. Pair any program with a before-and-after comparison of funded and unfunded counties, so next year you'll "
    f"know whether it worked.")
st.markdown(f"**Standard-confidence priority counties, in ranking order:** "
            + ", ".join(n.replace(" County", "") for n in std[tool.COL_COUNTY]) + ".")

# ----------------------------------------------------------------------------------
# 2. Insight cards
# ----------------------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
with k1.container(border=True):
    st.markdown("**Where drought hits hardest**")
    st.markdown(f"The {len(top)} counties in the top third by drought penalty are flagged for {crop_label.lower()}; "
                f"{first[tool.COL_COUNTY]} ranks first with a penalty of {first['penalty_score']:+.1f}%, "
                f"built on {int(first['drought_years_used'])} drought years.")
with k2.container(border=True):
    st.markdown("**How sure we are**")
    st.markdown(f"{ac.hit_rate_caption(hm, len(top))}, in {hm['n_years']} held-out test years ({ac.TEST_LABEL}). "
                f"Range from resampling years: {hm['lo']:.0%} to {hm['hi']:.0%}.")
with k3.container(border=True):
    st.markdown("**What doesn't drive it**")
    st.markdown("Soil water storage and organic matter didn't clearly separate counties in drought, so don't target "
                "programs by soil type alone.")

# ----------------------------------------------------------------------------------
# 3. Priority list
# ----------------------------------------------------------------------------------
no_score = dep.loc[~dep["has_score"], tool.COL_COUNTY].tolist()
st.markdown(f"**Priority list — {crop_label}: top {len(top)} of {int(dep['has_score'].sum())} scored counties** "
            f"(no score for {len(no_score)}: {', '.join(no_score) if no_score else 'none'})")
st.caption(f"Counties in the top third by drought penalty, all years {ac.ALL_YEARS}, {ac.D2_LABEL}, largest penalty first. "
           f"This list does not change with the drought definition selected above.")
view = (top[list(ac.PRIORITY_COLUMNS)].rename(columns=ac.PRIORITY_COLUMNS)
        .round({"drought penalty (%)": 1, "soil water storage (mm)": 0}).astype({"rank": int}))
st.dataframe(view, hide_index=True, width="stretch", height=min(38 + 35 * len(view), 450),
             column_config={"drought penalty (%)": st.column_config.NumberColumn(format="%+.1f"),
                            "soil water storage (mm)": st.column_config.NumberColumn(format="%.0f"),
                            "FIPS": st.column_config.TextColumn()})
st.markdown("Scores built on few drought years are less reliable; verify these counties with local information. "
            f"*({n_low} of {len(top)} {crop_label.lower()} counties above are marked '{tool.CONFIDENCE_LOWER}': "
            f"fewer than {tool.LOW_CONFIDENCE_YEARS} drought years behind the score.)*")
st.download_button("Download the priority list (CSV)", data=view.to_csv(index=False).encode("utf-8"),
                   file_name=f"priority_list_{crop.lower()}_{ac.FIRST_YEAR}_{ac.LAST_YEAR}.csv", mime="text/csv")

# ----------------------------------------------------------------------------------
# 4. Where to go next
# ----------------------------------------------------------------------------------
st.divider()
l1, l2 = st.columns(2)
with l1:
    st.page_link(ac.PAGE_EXPLORER, label="County explorer: map and county details", icon=":material/map:")
with l2:
    st.page_link(ac.PAGE_EVIDENCE, label="How we know it works: the held-out test", icon=":material/fact_check:")
