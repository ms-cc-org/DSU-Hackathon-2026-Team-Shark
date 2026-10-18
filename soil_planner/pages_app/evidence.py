"""How we know it works: the evidence scorecard, the proof chart, the held-out and placebo tables, earlier attempts.
Runs through soil_planner/app.py (st.navigation), which sets the shared crop and drought-definition controls."""
import pandas as pd
import streamlit as st

from soil_planner import app_common as ac
from soil_planner import soil_tool as tool

crop_label, crop, _, _ = ac.selection()
top = ac.priority(crop)
with st.spinner("Running the held-out test (first load only)…"):
    rk = ac.ranking_evidence()
hm = tool.headline_metrics(rk["summary"], crop)

st.header("How we know it works")

# ----------------------------------------------------------------------------------
# 1. Scorecard and 2. proof chart
# ----------------------------------------------------------------------------------
# Row 1 is computed from penalty_ranking_results (headline_metrics / placebo_clean). The storage and organic-matter rows
# are fixed text summarising notebooks 03 and 05 (storage: every drought-year range included zero) and notebook 07
# (organic matter: pre-registered decision rule gave "no clear effect" for both crops). The Nebraska row summarises
# notebook 06 (pre-registered feasibility gate: 13-18 dryland counties, below the pre-set minimum of 20).
scorecard = pd.DataFrame([
    ["Drought-penalty ranking on unseen years",
     f"Beats chance ({crop_label} hit rate {hm['hit_rate']:.0%} vs {hm['chance']:.0%}, {hm['n_years']} test years)"],
    ["Placebo check (drought-free counties)", "Clean" if ac.placebo_clean(rk["summary"], crop) else "Not clean (see Evidence details)"],
    ["Soil water storage", "No clear effect"],
    ["Organic matter (pre-registered)", "No clear effect"],
    ["Nebraska replication (pre-registered)", "Not testable: too few rain-fed counties"],
], columns=["What we tested", "Result"])
sc_col, chart_col = st.columns([2, 3])
with sc_col:
    st.subheader("What we tested")
    st.table(scorecard.set_index("What we tested"))
with chart_col:
    st.plotly_chart(ac.proof_chart(rk["summary"], crop), width="stretch")

# ----------------------------------------------------------------------------------
# 3. Held-out and placebo tables
# ----------------------------------------------------------------------------------
st.divider()
st.subheader(f"Does the drought-penalty score hold up on years it never saw? ({ac.TRAIN_LABEL} → {ac.TEST_LABEL})")
prose, _ = st.columns([2, 1])
prose.markdown(
    f"Three scores were built from {ac.TRAIN_LABEL} only: the drought-penalty score, drought frequency and soil "
    f"water storage. Each was then asked to rank counties in the {ac.TEST_LABEL} drought years. **Spearman** is the "
    "rank correlation between the score and the actual drought penalty that year, signed so positive means the "
    "score got the order right (chance 0). **Top-third hit rate** is the share of the highest-priority third of "
    "counties that really were in the worst-losing third (chance about 0.33). Ranges come from resampling test "
    "years. The two placebo columns repeat the test where it should find nothing: in years with no drought "
    "anywhere in Iowa, and on the non-drought counties of every test year.")
for c_label, c in tool.CROPS.items():
    info = rk["test_years"][c]
    st.markdown(f"**{c_label}** — test years with at least {tool.MIN_COUNTIES_PER_YEAR} drought counties: "
                + ", ".join(f"{y} ({n})" for y, n in info["usable"].items())
                + f". Years with no drought county (used for the first placebo): "
                + (", ".join(map(str, info["zero_drought"])) or "none") + ".")
    st.dataframe(tool.ranking_summary_table(rk["summary"], c).reset_index(), hide_index=True, width="stretch")
real = rk["summary"][rk["summary"]["test"] == tool.REAL_TEST]
beats = real[real["range_above_chance"]]
st.markdown("**Computed verdict.** Score / metric combinations whose whole range sits above chance on held-out "
            "drought years: " + ("; ".join(f"{r.crop.lower()} {r.score} ({r.metric})" for r in beats.itertuples())
                                  if len(beats) else "none") + ".")

st.subheader("Does soil water storage go with smaller drought penalties?")
prose, _ = st.columns([2, 1])
prose.markdown(
    f"For each year with at least {tool.MIN_COUNTIES_PER_YEAR} drought counties, the slope of the drought penalty "
    f"on storage across those counties, in percentage points per extra {tool.AWS_UNIT:.0f} mm of storage, "
    "averaged over years with a range from resampling years. Positive would mean more storage, smaller penalty. "
    "The placebo columns run the same regression on non-drought county-years, where a real buffering effect "
    "should not appear.")
with st.spinner("Estimating the storage effect (first load only)…"):
    step2 = ac.storage_evidence()
step2_view = (step2.drop(columns=["_mean", "_lo", "_hi"])
              .pivot(index=["crop", "spec"], columns="kind",
                     values=["estimate [95% range]", "n_years", "county_years", "years +/-", "excludes_zero"])
              .swaplevel(axis=1).sort_index(axis=1, level=0, sort_remaining=False)[["drought", "placebo"]])
st.dataframe(ac.flat_columns(step2_view), hide_index=True, width="stretch")
n_dr = int((step2["kind"] == "drought").sum())
n_excl = int(((step2["kind"] == "drought") & step2["excludes_zero"]).sum())
n_excl_pl = int(((step2["kind"] == "placebo") & step2["excludes_zero"]).sum())
st.markdown(f"**Computed verdict.** {n_excl} of {n_dr} drought-year storage estimates have a range that excludes "
            f"zero; placebo estimates excluding zero: {n_excl_pl}.")

# ----------------------------------------------------------------------------------
# 4. Earlier attempts, collapsed
# ----------------------------------------------------------------------------------
with st.expander("Earlier attempts and why we moved on", expanded=False):
    prose, _ = st.columns([2, 1])
    prose.markdown(
        "The first storage estimate (notebook 03) used the dataset's own yield anomaly, a trend fitted on all "
        "years and therefore in-sample, and found no clear effect. The first held-out ranking test (notebook 04) "
        f"built scores on a {ac.TRAIN_LABEL} trend and failed: no score beat chance, and the scores \"predicted\" "
        "losses even in years with no drought, because the trend extrapolated unevenly across the state and "
        "counties with a bad early record did better later regardless of weather. The drought-penalty score "
        "above was designed to fix that and was then tested once.")
    with st.spinner("Recomputing the earlier estimates (first load only)…"):
        storage03 = ac.earlier_storage_evidence()
        rank04 = ac.earlier_ranking_evidence()
    st.markdown(f"**Notebook 03: in-sample storage estimate (pp of yield anomaly per +{tool.AWS_UNIT:.0f} mm, "
                "drought years)**")
    st.dataframe(storage03[["crop", "specification", "estimate [95% range]", "drought years", "range excludes zero"]],
                 hide_index=True, width="stretch")
    st.markdown("**Notebook 04: held-out test of trend-based scores (none beat chance)**")
    st.dataframe(rank04["summary"], hide_index=True, width="stretch")
    st.markdown("**Notebook 04: its failed placebo, years with no drought county.** A score that works should "
                "show nothing here.")
    st.dataframe(rank04["placebo"], hide_index=True, width="stretch")
