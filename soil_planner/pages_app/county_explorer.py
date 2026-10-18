"""County explorer: the map at full width on top, then the county information in three cards below it.

Top to bottom: the map metric selectbox, the choropleth (counties to fund outlined, click to select), its caption;
then a header row with the County selectbox and the county's name, crop and definition; then three cards (drought
score, soil context, current practices); then, for priority counties, the reasons box, and the year-by-year expander.
Runs through soil_planner/app.py (st.navigation), which sets the shared crop and drought-definition controls.
The selected county is kept in st.session_state (key app_common.KEY_COUNTY) and survives page switches."""
import numpy as np
import streamlit as st

from soil_planner import app_common as ac
from soil_planner import soil_tool as tool

crop_label, crop, def_label, sev = ac.selection()
top = ac.priority(crop)
first = top.iloc[0]
stats = ac.county_stats(crop, sev)
idx = ac.county_index()
names = idx[tool.COL_COUNTY].tolist()
name_to_fips = dict(zip(idx[tool.COL_COUNTY], idx[tool.COL_FIPS]))
fips_to_name = dict(zip(idx[tool.COL_FIPS], idx[tool.COL_COUNTY]))
priority_fips = set(top[tool.COL_FIPS])                       # the tested top third: badge and reasons in the panel
fund = ac.top_n(crop, ac.n_fund(crop))                          # counties to fund (slider on This winter's plan): outlines
fund_fips = set(fund[tool.COL_FIPS])

# ----------------------------------------------------------------------------------
# 1. Map, full width
# ----------------------------------------------------------------------------------
metric_label = st.selectbox("Map metric", list(tool.METRICS), key=ac.KEY_METRIC, persist_state="session")
metric_col = tool.METRICS[metric_label]
n_blank = int(stats[metric_col].isna().sum())
clicked = None
if n_blank == len(stats):
    st.info(f"No {crop_label.lower()} county has a value for \"{metric_label}\" under {def_label}. "
            f"Try the other drought definition or another metric.")
else:
    fig = tool.make_map(stats, metric_col, metric_label, crop_label, def_label)
    is_funded = stats[tool.COL_FIPS].isin(fund_fips).to_numpy()            # same row order as the trace
    fig.update_traces(marker_line_width=np.where(is_funded, 2.2, 0.5),
                      marker_line_color=np.where(is_funded, "#222222", "white"))
    fig.update_layout(height=560, title_font_size=15)
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                            key=f"map_{crop}_{sev}_{metric_col}")
    clicked = ac.clicked_fips(event, stats)
    blank_txt = (f"Blank counties have no score for this setting ({n_blank} here)." if n_blank
                 else "Blank counties would have no score for this setting; every county has one here.")
    st.caption(f"{ac.MAP_CAPTIONS[metric_col]} {blank_txt} The top {len(fund)} counties to fund (slider on "
               "This winter's plan) have a dark outline. Click a county to open it below.")

# ----------------------------------------------------------------------------------
# 2. Selected county: reset to the top-ranked county when the crop changes, follow map clicks, else keep the selection.
#    Runs after the map and before the County selectbox: a click cannot change a widget already rendered this run.
# ----------------------------------------------------------------------------------
default_county = first[tool.COL_COUNTY]
if st.session_state.get(ac.KEY_COUNTY_CROP) != crop:
    st.session_state[ac.KEY_COUNTY_CROP] = crop
    st.session_state[ac.KEY_COUNTY] = default_county
    st.session_state[ac.KEY_LAST_CLICK] = None
if clicked and clicked in fips_to_name and clicked != st.session_state.get(ac.KEY_LAST_CLICK):
    st.session_state[ac.KEY_LAST_CLICK] = clicked
    st.session_state[ac.KEY_COUNTY] = fips_to_name[clicked]
if st.session_state.get(ac.KEY_COUNTY) not in name_to_fips:
    st.session_state[ac.KEY_COUNTY] = default_county

# ----------------------------------------------------------------------------------
# 3. Header row: County selectbox and the county's name
# ----------------------------------------------------------------------------------
st.divider()
h_left, h_right = st.columns([1, 2], vertical_alignment="bottom")
with h_left:
    county = st.selectbox("County", names, key=ac.KEY_COUNTY, persist_state="session")
fips = name_to_fips[county]
row = stats[stats[tool.COL_FIPS] == fips]
on_list = fips in priority_fips
with h_right:
    st.markdown(f"### {county}")
    st.markdown(f"{crop_label}, {def_label}" + (" · **priority county**" if on_list else ""))
if row.empty:
    st.info(f"No Iowa {crop_label.lower()} yields are reported for {county}.")
    st.stop()
row = row.iloc[0]
has_score = not np.isnan(row["drought_penalty_pct"])
n_scored = int(stats["drought_penalty_pct"].notna().sum())

# ----------------------------------------------------------------------------------
# 4. Three cards: drought score, soil context, current practices
# ----------------------------------------------------------------------------------
c_score, c_soil, c_prac = st.columns([1, 1.15, 1.15], gap="medium")

with c_score, st.container(border=True):
    st.markdown("**Drought score**")
    m1, m2 = st.columns(2)
    m1.metric("Drought penalty", f"{row['drought_penalty_pct']:+.1f}%" if has_score else "no score",
              help=f"Mean drought penalty over the county's drought years ({def_label}) with a penalty, all years "
                   f"{ac.ALL_YEARS}. Negative = loses more than its own normal in drought.")
    m2.metric("Rank in Iowa", f"{int(row['penalty_rank'])} of {n_scored}" if has_score else "—",
              help="1 = largest penalty among the counties with a score, for this crop and drought definition.")
    m3, m4 = st.columns(2)
    m3.metric("Drought years used", int(row["penalty_years_used"]),
              help=f"Drought years with a usable penalty; {int(row['drought_years'])} drought years in all under {def_label}.")
    m4.metric("Confidence", row["confidence"],
              help=f"'{tool.CONFIDENCE_LOWER}' when fewer than {tool.LOW_CONFIDENCE_YEARS} drought years are behind the score.")
    if not has_score:
        st.info(f"{county} has only {int(row['penalty_years_used'])} drought year(s) with a penalty under {def_label}; "
                f"a score needs at least {tool.MIN_D2_YEARS_FOR_SCORE}. Switch to the other drought definition to see a score.")
    st.caption(f"Drought years ({def_label}): {row['drought_year_list'] or 'none'}.")

with c_soil, st.container(border=True):
    st.markdown("**Soil context**")
    try:
        st.dataframe(ac.fmt_soil(ac.soil_context(fips)), hide_index=True, width="stretch",
                     column_config={"percentile": st.column_config.TextColumn(
                         "percentile", help="Share of Iowa counties at or below this county's value (0-100).")})
    except FileNotFoundError:
        st.info("Extra soil properties file not found (soil_planner/extra_data/iowa_soil_extra.csv).")
    st.caption("Context only; soil properties play no part in the ranking.")

with c_prac, st.container(border=True):
    st.markdown("**Current practices**")
    try:
        prac = ac.fmt_practices(ac.practices_context(fips))
        latest = prac.columns[3]
        compact = prac[["practice", latest, f"Iowa median {latest}", prac.columns[-1]]].copy()
        compact["practice"] = compact["practice"].str.replace(r" \(.*\)", "", regex=True)
        st.dataframe(compact, hide_index=True, width="stretch")
    except FileNotFoundError:
        st.info("Practice shares file not found (soil_planner/extra_data/iowa_conservation_practices.csv).")
    st.caption("Share of cropland in the latest Census of Agriculture, with the change since the previous one. "
               + tool.DATA_NOTE)

# ----------------------------------------------------------------------------------
# 5. Reasons (priority counties) and the year-by-year expander, full width
# ----------------------------------------------------------------------------------
if on_list:
    with st.container(border=True):
        st.markdown("**Why this county is on the priority list**")
        for r in ac.reasons(fips, crop):
            st.markdown(f"- {r}")
        st.markdown(tool.PRACTICES_NOTE)

with st.expander(f"Year-by-year: {county}, {crop_label}"):
    card = ac.report_card(fips, crop, sev)
    st.plotly_chart(tool.anomaly_bar(card["rows"], county, crop_label, def_label), width="stretch")
    rows = card["rows"].rename(columns=ac.ROW_COLUMNS).round(1)
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_config={"year": st.column_config.NumberColumn(format="%d")})
