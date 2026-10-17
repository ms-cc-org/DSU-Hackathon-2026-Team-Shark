# Data Dictionary

**Data to Harvest: AI for Agricultural Resilience Hackathon, Delaware State University, October 17–18, 2026.**
Master dataset version 1. Rebuilt October 5, 2026.

---

## What this dataset is

One row is one county, one crop, one year. The dataset covers 4 states (California, Delaware, Iowa, Nebraska), 4 crops (corn grain, soybeans, winter wheat, grain sorghum), and 26 years (2000–2025). It has 17,056 rows and 21 columns.

The question the dataset is sized to answer: given a county, a crop, and a year, what do the weather, drought, soil, and yield records tell you about agricultural risk, and what should a farmer, extension agent, or state agency do about it?

Everything joins on `fips`, the 5-digit county FIPS code. Load it as a string. If you let pandas read it as an integer, California counties lose their leading zero (`06001` becomes `6001`) and every join silently fails.

```python
import pandas as pd

master = pd.read_csv("data/master_dataset.csv", dtype={"fips": str})
# or
master = pd.read_parquet("data/master_dataset.parquet")  # fips is already a string
```

Reading the parquet directly gives `extreme_heat_days`, `max_drought_severity` and `weeks_in_d2_plus` as pandas `Int64`, whose missing values some numpy calls don't see: `np.isnan(master["weeks_in_d2_plus"]).sum()` gives 0, not 150. `load_master()` in `src/data_loader.py` converts them to float.

---

## Why these 4 states

They span the irrigation gradient. Iowa is rainfed. Delaware is rainfed and small enough to reason about as a whole. Nebraska is roughly half irrigated over the Ogallala Aquifer. California is almost entirely irrigated. A team comparing Iowa to Nebraska to California is comparing three kinds of agriculture inside the same columns.

## Why these 4 crops

Corn and soybeans give data density in Iowa and Nebraska. Winter wheat adds a season that crosses the calendar year (planted in fall, harvested the following summer), which forces you to think about temporal alignment. Grain sorghum is grown as a drought-tolerant crop, but in Nebraska the corn-vs-sorghum contrast is confounded by irrigation: most corn is irrigated, most sorghum is not.

**What the crop names actually filter:**

| `crop` value | What it is | What it excludes |
|---|---|---|
| `CORN` | Corn for grain | Corn for silage (reported in tons/acre, not bu/acre) |
| `SOYBEANS` | Soybeans | Nothing (NASS spells it plural — `SOYBEAN` returns zero rows) |
| `WHEAT` | Winter wheat only | Spring wheat, durum |
| `SORGHUM` | Grain sorghum | Sorghum for silage and syrup |

These filters apply to yield and harvested acres. Planted acres cover all uses: corn and sorghum include silage, winter wheat includes acres grazed or cut for hay.

---

## Row universe

Not every county grows every crop. California doesn't grow soybeans at commercial scale. Iowa stopped growing grain sorghum before 2000. Those county-crop pairs produce no rows at all.

For the pairs that do exist, every year from 2000 to 2025 is present. If NASS published a yield, it's there. If NASS listed the crop as planted but reported no grain harvest, the row is there with `yield_per_acre = NaN` and `yield_status = suppressed`. If NASS published no yield for that county-crop-year, the row is there with `yield_status = not_reported`. This means every time series you plot is complete, and every gap is labelled.

**Coverage by state:**

| State | Counties | Rows | Why it matters |
|---|---|---|---|
| California | 37 | 2,158 | Irrigated. Most reported yields are before 2010. |
| Delaware | 3 | 312 | Small, rainfed. Corn reported every year, soybeans almost every year; wheat and sorghum stop early. |
| Iowa | 99 | 5,876 | Rainfed. Best agricultural soil in the US. |
| Nebraska | 91 | 8,710 | Mixed irrigation. Has all 4 crops. Largest coverage. |

**Coverage by crop:**

| Crop | Counties | Rows | Note |
|---|---|---|---|
| Corn | 224 | 5,824 | Most widely reported crop in the dataset. |
| Soybeans | 183 | 4,758 | Not grown in California. |
| Winter wheat | 150 | 3,900 | Sparse in Iowa (28 counties). |
| Grain sorghum | 99 | 2,574 | Mostly Nebraska. No Iowa data post-2000. |

**Counties with a reported yield, by year:**

A row exists for every year, but `yield_per_acre` is filled only where NASS published a county yield: 68% of rows. NASS folds counties with too few reporting farms into a district total, and some crops shrank over time.

| State, crop | Counties | 2000 | 2005 | 2010 | 2015 | 2020 | 2025 |
|---|---|---|---|---|---|---|---|
| California corn | 31 | 24 | 18 | 8 | 7 | 0 | 0 |
| California sorghum | 18 | 0 | 8 | 0 | 0 | 0 | 0 |
| California winter wheat | 34 | 32 | 24 | 17 | 9 | 11 | 6 |
| Delaware corn | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Delaware sorghum | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| Delaware soybeans | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Delaware winter wheat | 3 | 3 | 3 | 0 | 0 | 0 | 0 |
| Iowa corn | 99 | 99 | 99 | 99 | 95 | 95 | 79 |
| Iowa soybeans | 99 | 99 | 99 | 99 | 97 | 86 | 73 |
| Iowa winter wheat | 28 | 6 | 14 | 0 | 0 | 0 | 0 |
| Nebraska corn | 91 | 91 | 90 | 87 | 78 | 83 | 46 |
| Nebraska sorghum | 78 | 56 | 48 | 24 | 9 | 8 | 6 |
| Nebraska soybeans | 81 | 79 | 77 | 73 | 62 | 69 | 36 |
| Nebraska winter wheat | 85 | 64 | 75 | 65 | 48 | 47 | 32 |

The well-covered core is **Iowa and Nebraska corn and soybeans**, plus Nebraska wheat. California, Delaware, sorghum, and Iowa/Delaware wheat are thin, especially after 2010: use them as contrasts and check your sample size before drawing conclusions. Recent years are thinner everywhere.

---

## Fields

### Identity (5 fields, never null)

| Field | Type | Description |
|---|---|---|
| `fips` | String, 5 chars | County FIPS code, starts with zero. `06001`, not `6001`. This is the join key across all datasets. |
| `county_name` | String | County name from the U.S. Drought Monitor county list. Example: `Polk County`. |
| `state_alpha` | String, 2 chars | State abbreviation. One of `CA`, `DE`, `IA`, `NE`. |
| `year` | Integer | Harvest year. 2000 to 2025. For winter wheat, this is the year the crop was harvested, not planted. |
| `crop` | String | One of `CORN`, `SOYBEANS`, `WHEAT`, `SORGHUM`. |

### Yield (5 fields, from USDA NASS)

| Field | Type | Unit | Description |
|---|---|---|---|
| `yield_per_acre` | Float | Bushels per acre | County yield from NASS Quick Stats. NaN when not reported or suppressed. Never zero: NASS lists a yield of 0 when no grain was harvested, and those are stored as NaN (`suppressed`). All 4 crops use the same unit. |
| `yield_status` | String | — | Why the yield is or isn't there. `reported` = NASS published a number. `suppressed` = planted, but no grain harvested (NASS lists a yield of 0 and no harvested acres; 74 rows, 2000–2008). `not_reported` = NASS published no yield for this county-crop-year. Never null. |
| `acres_planted` | Float | Acres | County acres planted. Available when NASS published it: most corn and soybean rows, about half of wheat, a minority of sorghum. |
| `acres_harvested` | Float | Acres | County acres harvested for grain. Planted acres include silage, grazing and hay, so planted − harvested is not abandonment: for California corn the median gap is 44%. Only for soybeans is the gap close to abandonment. |
| `yield_anomaly_pct` | Float | Percent | How far this year's yield deviates from the county's 26-year trend. Positive = above trend, negative = below. Computed as an OLS residual divided by the fitted value, so it removes the secular rise from genetics and technology. NaN when the county-crop pair has fewer than 10 reported yields (trend is too unstable) or when yield itself is NaN. Because the trend is fitted on all 26 years, each county's anomalies average to about zero over 2000–2025. |

**Yield ranges observed in this dataset:**

| Crop | Min | Max | Typical |
|---|---|---|---|
| Corn | 32.5 | 277.1 | 155–215, median about 195 (IA, NE 2016–2025) |
| Soybeans | 15.0 | 75.5 | 50–66, median about 59 (IA, NE 2016–2025) |
| Winter wheat | 8.7 | 120.3 | 33–60, median about 46 (NE) |
| Grain sorghum | 18.0 | 139.6 | 44–108, median about 80 (NE) |

### Weather (5 fields, from NOAA ACIS)

All weather fields are aggregated over the crop's growing-season window (see "Season windows" below). Source is NOAA ACIS grid 1 (interpolated, county-mean, daily). Units are metric: Celsius and millimetres.

| Field | Type | Unit | Description |
|---|---|---|---|
| `precip_mm` | Float | Millimetres | Total precipitation during the growing season. This is the sum of daily county-mean precipitation. If Iowa corn shows about 21 instead of about 530, your data is in inches — it shouldn't be, but check. |
| `precip_anomaly_pct` | Float | Percent | How far this season's precipitation deviates from the 26-year average for this county-crop. `(precip − mean) / mean × 100`. Positive = wetter than normal. The average includes later years; for a strict test on past years, recompute it on your training years. |
| `tavg_c` | Float | °C | Mean daily average temperature over the growing season. Computed as the mean of daily `(tmax + tmin) / 2`. If Iowa corn shows about 68 instead of about 20, the data is in Fahrenheit — it shouldn't be, but check. |
| `extreme_heat_days` | Float (whole numbers) | Days | Count of days in the season where daily max temperature reached or exceeded 35°C (95°F). This is low for winter wheat in Iowa, Nebraska and Delaware because the Sep-to-Jun window rarely hits 35°C. That's a property of the window, not evidence that wheat is heat-tolerant. California wheat is the exception (12 days on average). |
| `gdd` | Float | Degree-days | Growing Degree Days, using crop-specific base and cap temperatures. The formula is: `daily GDD = max(0, (min(tmax, T_cap) + max(tmin, T_base)) / 2 − T_base)`. Seasonal GDD is the sum. |

**GDD parameters by crop:**

| Crop | T_base (°C) | T_cap (°C) |
|---|---|---|
| Corn | 10 | 30 |
| Soybeans | 10 | 30 |
| Winter wheat | 0 | 26 |
| Grain sorghum | 10 | 38 |

### Drought (3 fields, from U.S. Drought Monitor)

All drought fields are aggregated over the crop's growing-season window. Source is the USDM weekly county-level categorical data (D0–D4 categories, each representing the percent of a county's area in that drought severity class).

| Field | Type | Range | Description |
|---|---|---|---|
| `max_drought_severity` | Float (whole numbers) | 0–5 | Worst drought category observed in any week of the season, where more than 1% of the county was affected. 0 = no drought, 1 = D0 (abnormally dry), 2 = D1 (moderate), 3 = D2 (severe), 4 = D3 (extreme), 5 = D4 (exceptional). Note: this scale is offset by 1 from the USDM's own D0–D4 labels. |
| `weeks_in_d2_plus` | Float (whole numbers) | 0–44 | Number of weeks during the season where severe drought or worse (D2 + D3 + D4) covered more than 1% of the county. A quick measure of drought duration. Maximum depends on season length: corn and sorghum ≤ 22, soybeans ≤ 27, winter wheat ≤ 44. |
| `mean_dsci` | Float | 0–500 | Mean weekly Drought Severity and Coverage Index over the season. Computed as `D0×1 + D1×2 + D2×3 + D3×4 + D4×5` using categorical (non-overlapping) percentages. 0 means no drought all season. 500 means the entire county was in D4 every week. |

**Do not confuse the scales.** `max_drought_severity` is 0–5. `mean_dsci` is 0–500. They are not the same thing and neither is a percentage.

The 1% area threshold matters. Without it, a 0.01% sliver of a county in D4 during one week would set `max_drought_severity` to 5, making the field noisy and hard to defend.

### Soil (3 fields, from USDA NRCS SSURGO)

Soil is time-invariant. These 3 values are the same for every year of a county. They join on `fips` alone.

| Field | Type | Unit | Description |
|---|---|---|---|
| `aws_100cm_mm` | Float | Millimetres | Available Water Supply in the top 100 cm of soil, area-weighted across the county's soil map units. Think of it as how much water the soil can hold for plant use. High value = the soil carries the crop further between rains. In irrigated areas (much of Nebraska, nearly all of California) applied water overrides soil storage, so this holds mainly for rainfed land. Iowa averages ~179 mm. California's desert and mountain counties are about 60–70 mm (urban San Francisco is 25). |
| `droughty_pct` | Float | Percent (0–100) | Percent of the county's area on drought-vulnerable soil (defined as ≤ 152 mm of available water storage). Iowa median is 14%. Every California county with soil data is above 50%. This is a threshold view of the same idea as `aws_100cm_mm`, easier to reason about. |
| `nccpi_crop` | Float | 0 to 1 | National Commodity Crop Productivity Index, matched to the crop in the row. 0 = unproductive, 1 = most productive soil in the US for this crop. Iowa corn counties average ~0.74. This is the control variable that lets you separate "bad yield because bad weather" from "bad yield because bad soil." |

**`nccpi_crop` mapping:**

| Crop | NCCPI submodel used | Note |
|---|---|---|
| Corn | NCCPI Corn | |
| Soybeans | NCCPI Soybeans | |
| Wheat | NCCPI Small Grains | |
| Sorghum | NCCPI Corn | No sorghum model exists. Corn is the proxy — same season, similar management. Documented approximation. |

---

## Season windows

Weather and drought fields are aggregated over crop-specific growing seasons, not the calendar year. The window boundaries are fixed across all 4 states.

| Crop | Season start | Season end | Days | Year rule |
|---|---|---|---|---|
| Corn | May 1 | Sep 30 | 153 | Harvest year |
| Soybeans | May 1 | Oct 31 | 184 | Harvest year |
| Winter wheat | Sep 1 | Jun 30 | 303–304 | Sep 1 of year−1 through Jun 30 of harvest year |
| Grain sorghum | Jun 1 | Oct 31 | 153 | Harvest year |

**Winter wheat crosses the calendar year.** The row with `year = 2012` and `crop = WHEAT` aggregates weather from September 1, 2011 through June 30, 2012. If you filter by calendar year alone you'll get the wrong days.

**The windows are fixed and challengeable.** California plants corn from mid-March and winter wheat from mid-October — both earlier than these windows. Delaware double-crops soybeans after wheat, pushing planting into July. These are real limitations, not errors. Teams that want state-specific or year-specific windows can use the daily weather panel (`data/processed/acis/weather_daily.parquet`) to build their own.

---

## Missing data — read this section

NaN is not zero. Do not fill it with zero. Do not drop it without understanding why it's missing.

| What you see | What it means | What to do |
|---|---|---|
| `yield_per_acre` is NaN, `yield_status` = `suppressed` | The crop was planted but no grain was harvested. NASS lists a yield of 0 and no harvested acres. For corn, NASS shows these acres were cut for silage. | Leave as NaN. `acres_planted` shows the crop was grown. |
| `yield_per_acre` is NaN, `yield_status` = `not_reported` | NASS published no estimate for that county-crop-year. The crop may not have been grown, or NASS didn't survey it. | Leave as NaN. The row exists so your time series is complete. |
| No row at all for a county-crop combination | NASS has no record of that crop in that county for the entire 2000–2025 window. | Nothing to do. California soybeans and Iowa sorghum have no rows in any county. |
| `acres_planted` is NaN | NASS published nothing for that county-crop-year, so yield and harvested acres are empty too. Common for sorghum and wheat. | Leave as NaN. |
| Drought fields are NaN, row is `WHEAT` year `2000` | The wheat season starts September 1, 1999. The USDM archive starts January 4, 2000. Only 26 of the ~43 season weeks have drought data. We set all 3 fields to NaN rather than publish a value from 60% of a season. | Exclude wheat year 2000 from drought analysis or note it as incomplete. Weather is complete for this row. |
| Every year of a county-crop pair is `not_reported` or `suppressed` | NASS has acreage for the pair but never published a county yield (17 pairs, 442 rows: 9 in California, 7 Nebraska sorghum, 1 Delaware sorghum). | Exclude from yield analysis. |
| `yield_anomaly_pct` is NaN but `yield_per_acre` is not | The county-crop pair has fewer than 10 reported yields across 2000–2025. The trend is too unstable to detrend meaningfully. | Exclude from anomaly-based analysis. You can still use raw `yield_per_acre`. |

---

## Companion datasets

The master CSV is built from 4 source datasets. The daily and weekly panels are included for teams that want finer resolution. The weather, drought and soil panels and the boundary file cover all 253 counties in the 4 states; the master, `nass_raw` and MODIS have the 230 with NASS data, and the irrigation extension fewer.

| File | What it is | Rows | Join key |
|---|---|---|---|
| `data/processed/acis/weather_daily.parquet` | Daily tmax, tmin, precipitation for every county, 1999–2025 | 2,495,086 | `fips` + `date` |
| `data/processed/drought/drought_weekly.parquet` | Weekly D0–D4 percentages and DSCI for every county, 2000–2025 | 343,321 | `fips` + `map_date` |
| `data/processed/nass/nass_raw.parquet` | NASS yield, harvested acres, planted acres in long format: one row per value, named in `statistic` (`YIELD`, `AREA HARVESTED`, `AREA PLANTED`). State column is `state_abbr` | 35,067 | `fips` + `crop` + `year` + `statistic` |
| `data/processed/soil/soil_county.parquet` | Static soil properties per county: `aws_100cm_mm`, `droughty_pct`, and NCCPI for each crop (`nccpi_corn`, `nccpi_soy`, `nccpi_sg`). Marin County, CA (06041) is all NaN; it has no NASS crops, so it isn't in the master. | 253 | `fips` |
| `data/processed/modis/modis_ndvi_county.parquet` | Annual MODIS NDVI/EVI per county (extension) | 5,980 | `fips` + `year` |
| `data/processed/irrigation/nass_irrigation.parquet` | NASS irrigated share and irrigated/non-irrigated yields (extension) | 3,716 | `fips` + `crop` + `year` |
| `data/counties.geojson` | County boundaries for maps; load with `load_counties()` | 253 | feature `id` = `fips` |

**When to use the panels instead of the master:** if you want to define your own season windows, look at sub-seasonal patterns (was the drought early or late in the season?), compute your own GDD parameters, or examine daily weather extremes. The master aggregates these panels into one row per county-crop-year. The panels give you the daily and weekly resolution to disaggregate.

---

## Extension dataset: MODIS vegetation indices

The master dataset measures agriculture from the ground: yield surveys, weather stations, drought classifications, and soil maps. The MODIS extension adds a view from space — what satellites actually observe about vegetation health across each county.

**Source:** NASA MODIS/Terra Vegetation Indices (MOD13Q1 v061), 250-metre resolution, 16-day composites, extracted via Google Earth Engine. Covers the same 230 counties and 26 years as the master dataset.

**File:** `data/processed/modis/modis_ndvi_county.parquet` (5,980 rows - one row per county per year)

**How to load:**

```python
from src.data_loader import load_modis

modis = load_modis()          # 5,980 rows x 10 columns, fips is already a string
```

There is also a CSV copy, `modis_ndvi_county.csv`. Read it with `dtype={"fips": str}`, or `06001` becomes `6001`.

**How to join with the master:** The extension joins on `fips + year`. Because it has no crop dimension, every master row for a given county-year maps to the same MODIS row. Use a left join:

```python
from src.data_loader import load_master, load_modis

master = load_master()
modis  = load_modis()

modis = modis.drop(columns=["county_name", "state_alpha"])   # already in the master
combined = master.merge(modis, on=["fips", "year"], how="left")
```

### Extension fields (10 fields, zero nulls)

#### Identity (4 fields)

| Field | Type | Description |
|---|---|---|
| `fips` | String, 5 chars | County FIPS code, same as master. Join key. |
| `county_name` | String | Same county name as the master. |
| `state_alpha` | String, 2 chars | State abbreviation. One of `CA`, `DE`, `IA`, `NE`. |
| `year` | Integer | Calendar year, 2000 to 2025. |

#### Vegetation indices (6 fields)

| Field | Type | Range | Description |
|---|---|---|---|
| `ndvi_mean` | Float | 0 to 1 | Mean Normalized Difference Vegetation Index across the county for the calendar year. Computed as the temporal mean of all 16-day composites, then averaged across all 250 m pixels in the county. Higher = greener. Iowa county annual means range 0.32–0.57. California desert counties sit around 0.15. |
| `ndvi_max` | Float | 0 to 1 | Maximum NDVI — the peak greenness value observed in any 16-day composite during the year, averaged across the county's pixels. This captures peak growing-season vegetation regardless of when it occurs. |
| `evi_mean` | Float | 0 to ~0.9 | Mean Enhanced Vegetation Index. EVI corrects for atmospheric effects and soil background better than NDVI in dense-canopy areas. In practice, EVI tracks NDVI closely but with lower saturation in high-biomass regions. |
| `evi_max` | Float | 0 to ~0.9 | Maximum EVI over the year. Same relationship to `evi_mean` as `ndvi_max` to `ndvi_mean`. |
| `ndvi_anomaly_pct` | Float | Percent | How far this year's county NDVI deviates from the county's 26-year mean. `(ndvi_mean − county_mean) / county_mean × 100`. Positive = greener than average. Unlike `yield_anomaly_pct`, it is not detrended: it compares each year to the county's plain average. |
| `peak_ndvi_doy` | Integer | 1 to 366 | Day of year when peak NDVI was observed, averaged across the county's pixels. California counties peak around DOY 145 (late May, irrigated crops). Iowa and Nebraska peak around DOY 205–213 (late July, corn and soybeans at full canopy). A county with an unusually late or early peak may be under stress. |

### What the extension adds

The master dataset tells you what happened to yield — after the season is over. MODIS tells you what the satellite saw while it was happening. This opens a different class of analysis:

- **Explaining yield from greenness.** Does `ndvi_max` explain part of the variation in `yield_anomaly_pct` that weather and drought miss? Because each row covers the full calendar year, including harvest and post-harvest months, it explains yield after the fact but can't forecast it before harvest. A forecast would need composites up to a cutoff date (see `src/build/MODIS_gee_pull.py`).
- **Drought verification.** The USDM drought fields are based on expert classification. NDVI anomaly is a direct physical measurement. Do they agree? When they differ, which one better predicts yield loss?

### How the extension differs from the master dataset

These are design differences, not defects. They exist because satellite data and survey data measure different things.

| Aspect | Master dataset | MODIS extension |
|---|---|---|
| **Observation unit** | County × crop × year | County × year (no crop dimension) |
| **What it measures** | Surveyed yield, weather, drought severity, soil | Satellite-observed vegetation greenness |
| **Temporal resolution** | Seasonal aggregates from daily/weekly sources | Annual aggregates from 16-day composites |
| **Spatial resolution** | County-level (from station/grid data) | County-level (from 250 m satellite pixels) |
| **Land cover** | Crop-specific (corn, soybeans, wheat, sorghum) | All vegetation in the county (crops, forests, grasslands, developed land) |

The most important disparity is the **lack of a crop dimension**. MODIS sees all vegetation in the county, not individual crop fields. A county that is 40% corn, 30% soybeans, and 30% forest will have an NDVI that blends all three. This means:

1. **NDVI anomaly and yield anomaly will not match perfectly.** A drought that destroys corn yield might not move county-wide NDVI much if the county is heavily forested and the forest holds up. This is a real signal, not a flaw — it tells you how much of the county's vegetation is affected.

2. **Joining on `fips + year` duplicates the MODIS row across crops.** When you merge with the master, every crop in a county-year gets the same NDVI value. That's correct — the satellite saw the same county — but keep it in mind when modelling.

3. **The temporal window is the full calendar year, not the crop's growing season.** The master's weather and drought fields use crop-specific season windows (May–Sep for corn, Sep–Jun for wheat). The MODIS extension uses January through December. Teams wanting season-specific NDVI can compute it from the 16-day composites using the GEE pipeline in `src/build/MODIS_gee_pull.py`.

---

## Extension dataset: irrigation (NASS)

The master has no irrigation field. This extension gives the county split NASS published between irrigated and non-irrigated (dryland) acres, mostly for Nebraska.

**File:** `data/processed/irrigation/nass_irrigation.parquet` (3,716 rows, one row per county × crop × year where NASS published the split)

```python
from src.data_loader import load_master, load_irrigation

master = load_master()
irrigation = load_irrigation().drop(columns=["state_alpha"])   # already in the master
combined = master.merge(irrigation, on=["fips", "crop", "year"], how="left")
```

| Field | Type | Unit | Description |
|---|---|---|---|
| `fips`, `crop`, `year` | | | Same as the master. Join key. |
| `state_alpha` | String | | Same as the master. |
| `irrigated_share` | Float | 0 to 1 | Irrigated grain acres harvested ÷ all grain acres harvested (the master's `acres_harvested`). |
| `yield_irrigated` | Float | Bushels per acre | Yield on irrigated acres. |
| `yield_non_irrigated` | Float | Bushels per acre | Yield on non-irrigated acres. |

**Coverage:**

| State, crop | Rows | Years |
|---|---|---|
| Nebraska corn | 1,401 | 2000–2018 |
| Nebraska soybeans | 1,049 | 2000–2018 |
| Nebraska winter wheat | 658 | 2000–2019 |
| Nebraska sorghum | 354 | 2000–2007 |
| California winter wheat | 212 | 2000–2008 |
| Delaware corn | 25 | 2013–2025 |
| Delaware soybeans | 17 | 2015–2025 |

Iowa has none: NASS publishes no irrigated series for Iowa, which is rainfed. NASS stopped publishing the Nebraska split after 2018 (wheat 2019).

**Missing is not zero.** A master row with no match means NASS published no split, not that nothing was irrigated. Inside the file any of the 3 values can be NaN, for example a county with no dryland acres has no `yield_non_irrigated`. Where all three are present, `irrigated_share × yield_irrigated + (1 − irrigated_share) × yield_non_irrigated` matches the master's `yield_per_acre`.

**After 2018.** A county's corn and soybean irrigated share changes little from year to year (typical spread 0.03), so its 2000–2018 average is a reasonable stand-in for later years. Wheat and sorghum shares vary more.

---

## Known limitations

These are real constraints, not defects. They're listed here so you can design around them rather than discover them in your results.

1. **Irrigation is only partly visible.** The master has no irrigation field; the irrigation extension covers mostly Nebraska 2000–2018 and nothing for Iowa. `aws_100cm_mm` measures what the soil can hold, not water applied. In Nebraska this reverses two comparisons: the lowest-storage counties are the most irrigated, and most corn is irrigated while most sorghum is not. USGS irrigation water-use data (not included) is an option for advanced teams.

2. **Season windows are fixed.** They don't shift by state or year. California corn actually starts in March; these windows start in May. The daily panel ships alongside so you can build better windows if you want to.

3. **Sparse coverage is expected.** California corn has 31 counties, not 58. Iowa wheat has 28 counties, not 99. Delaware sorghum has 3 counties. This is not an error — not every county grows every crop. Small samples are real but require care in analysis. Reported yields also thin out over time; see the coverage table under Row universe.

4. **WHEAT means winter wheat only.** Spring wheat, durum, and other classes are excluded. NASS distinguishes them by `class_desc`.

5. **CORN and SORGHUM mean grain only** for yield and harvested acres. Corn for silage is reported in tons per acre, not bushels, and is excluded. Planted acres cover all uses.

6. **SSURGO is static.** Soil properties don't change over 26 years in this dataset. Land-use change, erosion, and soil amendments are not captured.

7. **Vernalization is not modelled.** Winter wheat GDD uses a simple heat sum (T_base = 0°C). Real wheat physiology requires a period of cold to trigger grain development. The GDD field doesn't capture that.

8. **`nccpi_crop` for sorghum uses the corn model.** NCCPI has no sorghum-specific submodel. Corn is used as a proxy because they share similar growing conditions. This is a documented approximation, not a precise match.

9. **`extreme_heat_days` is near zero for wheat outside California.** The September-to-June window rarely reaches 35°C in Iowa, Nebraska and Delaware. The field is correct but uninformative there. Focus on GDD or precipitation anomaly for wheat analysis.

10. **USDM starts January 4, 2000.** Wheat year 2000 is missing the September–December 1999 portion of its drought window. Those 3 drought fields are NaN.

11. **MODIS NDVI is county-wide, not crop-specific.** The satellite sees all vegetation in a county — crops, forests, grasslands, developed land. A county where forests mask crop stress will show a weaker NDVI anomaly than `yield_anomaly_pct` suggests. This is a property of satellite observation, not a data error.

12. **MODIS temporal window is the calendar year.** The master dataset aggregates weather and drought over crop-specific growing seasons. The MODIS extension aggregates NDVI and EVI over January through December.

---

## How the dataset was built

The pipeline is in `src/build/`. Each script is self-contained, caches every API response to `data/raw/`, and writes a processed parquet plus a failures log.

| Script | Source | Output |
|---|---|---|
| `NASS_data_pull.py` | USDA NASS Quick Stats API | `data/processed/nass/nass_raw.parquet` |
| `ACIS_data_pull.py` | NOAA ACIS GridData API | `data/processed/acis/weather_daily.parquet` |
| `USDM_data_pull.py` | U.S. Drought Monitor API | `data/processed/drought/drought_weekly.parquet` |
| `SSURGO_data_pull.py` | NRCS Soil Data Access | `data/processed/soil/soil_county.parquet` |
| `build_master.py` | All 4 parquets above | `data/master_dataset.csv` + `.parquet` |
| `MODIS_gee_pull.py` | Google Earth Engine (extension) | `data/processed/modis/modis_ndvi_county.parquet` |
| `NASS_irrigation_pull.py` | USDA NASS Quick Stats API (extension) | `data/processed/irrigation/nass_irrigation.parquet` |

The master build passes 27 internal validation checks (`build_master.py`) and 27 sanity checks (`validate_sources.py`: known NASS yields, known drought events, known temperature ranges, and known soil geography).

---

## Research questions the dataset can answer

These are what the field set was sized against. They're starting points, not limits.

1. When a county is in D2 drought or worse during its growing season, how far does yield fall below its own trend?
2. In rainfed Iowa, do counties with higher `aws_100cm_mm` (more soil water storage) lose less yield in drought years? (Don't pool Nebraska: its lowest-storage counties are the most heavily irrigated, so they look drought-resistant for reasons the soil fields can't show.)
3. In Nebraska, sorghum's yield falls further below trend than corn's in drought years, even though sorghum is the "drought-tolerant" crop. What could explain that? (Hint: which crop is usually irrigated? Check how many sorghum counties report after 2010.)
4. Is growing-season precipitation a stronger predictor of yield anomaly in rainfed Iowa than in irrigated California?
5. Is there a number of `extreme_heat_days` above which yield anomaly turns sharply negative? Does it differ by crop?
6. Once you control for `nccpi_crop` (soil quality), how much of the yield gap between counties is left for drought to explain?

Question 6 is the most defensible analysis a team can present. It separates what the soil determines from what the weather determines.

---

## Sources

| Source | Access | Documentation |
|---|---|---|
| USDA NASS Quick Stats | REST API, free key | [quickstats.nass.usda.gov/api](https://quickstats.nass.usda.gov/api) |
| NOAA ACIS | REST API, no key needed | [docs.rcc-acis.org](https://docs.rcc-acis.org/acisws/) |
| U.S. Drought Monitor | REST API, no key needed | [droughtmonitor.unl.edu](https://droughtmonitor.unl.edu/) |
| USDA NRCS Soil Data Access | SQL-over-HTTP, no key | [sdmdataaccess.nrcs.usda.gov](https://sdmdataaccess.nrcs.usda.gov/) |
| DSCI definition | — | [NDMC fact sheet](https://droughtmonitor.unl.edu/data/docs/DSCI_fact_sheet.pdf) |
| NASA MODIS MOD13Q1 v061 | Google Earth Engine | [LP DAAC product page](https://lpdaac.usgs.gov/products/mod13q1v061/) |
| Season windows | — | [USDA Usual Planting and Harvesting Dates](https://swat.tamu.edu/media/90113/crops-typicalplanting-harvestingdates-by-states.pdf) |
