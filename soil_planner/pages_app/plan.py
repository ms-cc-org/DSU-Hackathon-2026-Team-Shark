"""This winter's plan: the counties-to-fund slider, the recommendation, the main insights and the priority list.
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
first = top.iloc[0]

st.header("This winter's plan")

# ----------------------------------------------------------------------------------
# 1. Counties to fund (slider) and the recommendation
# ----------------------------------------------------------------------------------
# The slider picks the top N of our deployment ranking (same order as the priority list). Only the recommendation
# counts, the county lists, the CSV and the map outlines follow N; the evidence (tested on the top third) does not.
n = st.slider("Counties we can fund this winter", min_value=5, max_value=60, value=len(top), step=1,
              key=ac.KEY_N_FUND, persist_state="session")
st.caption(f"Accuracy was tested for the top {len(top)} counties (the top third); other cutoffs use the same ranking "
           "but were not tested separately.")
fund = ac.top_n(crop, n)
std = fund[fund["confidence"] == tool.CONFIDENCE_STANDARD]
low = fund[fund["confidence"] == tool.CONFIDENCE_LOWER]
n_std, n_low = len(std), len(low)

# Colour vocabulary: green box = act now; the lower-confidence names are orange = verify first.
low_names = ", ".join(c.replace(" County", "") for c in low[tool.COL_COUNTY])
st.success(
    f"**Recommendation for this winter's sign-ups ({crop_label}):** Start outreach in the **{n_std} counties with "
    f"standard confidence among the top {len(fund)}**. Verify the **{n_low} lower-confidence counties**"
    + (f" (:orange[{low_names}])" if n_low else "")
    + " with local staff before committing funds. Pair any program with a before-and-after comparison of funded and "
    "unfunded counties.")
shares = ac.bushel_shares(crop, tuple(fund[tool.COL_FIPS]))
if shares is not None:
    st.caption(f"These {len(fund)} counties account for about {shares[0]:.0%} of Iowa's expected {crop_label.lower()} "
               f"bushels lost to drought per year, on {shares[1]:.0%} of its harvested acres (historical, descriptive).")
st.markdown(f"**Standard-confidence counties among the top {len(fund)}, in ranking order:** "
            + ", ".join(c.replace(" County", "") for c in std[tool.COL_COUNTY]) + ".")

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
st.subheader(f"Priority list — {crop_label}: top {len(fund)} of {int(dep['has_score'].sum())} scored counties")
st.markdown(f"No score for {len(no_score)}: {', '.join(no_score) if no_score else 'none'}.")
st.caption(f"The top {len(fund)} counties by drought penalty, all years {ac.ALL_YEARS}, {ac.D2_LABEL}, largest penalty first. "
           f"This list does not change with the drought definition selected above.")
view = (fund[list(ac.PRIORITY_COLUMNS)].rename(columns=ac.PRIORITY_COLUMNS)
        .round({"drought penalty (%)": 1, "soil water storage (mm)": 0}).astype({"rank": int}))
st.dataframe(view, hide_index=True, width="stretch", height=min(38 + 35 * len(view), 450),
             column_config={"drought penalty (%)": st.column_config.NumberColumn(format="%+.1f"),
                            "soil water storage (mm)": st.column_config.NumberColumn(format="%.0f"),
                            "FIPS": st.column_config.TextColumn()})
st.markdown("Scores built on few drought years are less reliable; verify these counties with local information. "
            f"*({n_low} of {len(fund)} {crop_label.lower()} counties above are marked '{tool.CONFIDENCE_LOWER}': "
            f"fewer than {tool.LOW_CONFIDENCE_YEARS} drought years behind the score.)*")
st.download_button("Download the priority list (CSV)", data=view.to_csv(index=False).encode("utf-8"),
                   file_name=f"priority_list_{crop.lower()}_top{len(fund)}_{ac.FIRST_YEAR}_{ac.LAST_YEAR}.csv", mime="text/csv")

# ----------------------------------------------------------------------------------
# 4. Where to go next
# ----------------------------------------------------------------------------------
st.divider()
l1, l2 = st.columns(2)
with l1:
    st.page_link(ac.PAGE_EXPLORER, label="County explorer: map and county details", icon=":material/map:")
with l2:
    st.page_link(ac.PAGE_EVIDENCE, label="How we know it works: the held-out test", icon=":material/fact_check:")
