# Master Dataset Specification

# 1\. Dataset definition

| Property | Value |
| :---- | :---- |
| Row | One county, one crop, one year |
| Primary key | (fips, crop, year) |
| States | CA, NE, IA, DE (253 counties in the panels; 230 in the master, those with NASS data) |
| Years | 2000 to 2025 |
| Crops | CORN, SOYBEANS, WHEAT, SORGHUM |
| Row universe | All 26 years for every county-crop pair with at least 1 NASS record for any of the 3 statistics (yield, acres planted, acres harvested) in 2000 to 2025 |
| Expected rows | Roughly 17,000. The dataset is sparse: about 65% of the 26,312 theoretical county-crop-year combinations exist (253 counties x 4 crops x 26 years), because many county-crop pairs have no NASS observations. Teams should design for a sparse matrix |
| Student output | data/master\_dataset.csv, data/master\_dataset.parquet |
| Backbone | County list from the U.S. Drought Monitor county statistics (253 counties) |

# 2\. Crop filters

The crop column carries 4 short values, and each one is a filtered slice of NASS. The filters are the contract; without them the query returns several rows per key.

| crop | commodity\_desc | Extra filter | short\_desc (yield) |
| :---- | :---- | :---- | :---- |
| CORN | CORN | util\_practice\_desc=GRAIN | CORN, GRAIN \- YIELD, MEASURED IN BU / ACRE |
| SOYBEANS | SOYBEANS | none | SOYBEANS \- YIELD, MEASURED IN BU / ACRE |
| WHEAT | WHEAT | class\_desc=WINTER | WHEAT, WINTER \- YIELD, MEASURED IN BU / ACRE |
| SORGHUM | SORGHUM | util\_practice\_desc=GRAIN | SORGHUM, GRAIN \- YIELD, MEASURED IN BU / ACRE |

Applied to every request regardless of crop:

* agg\_level\_desc \= COUNTY  
* source\_desc \= SURVEY  
* reference\_period\_desc \= YEAR  
* domain\_desc \= TOTAL  
* prodn\_practice\_desc \= ALL PRODUCTION PRACTICES

Each does specific work. SURVEY excludes Census of Agriculture records (source CENSUS, published for 2002, 2007, 2012, 2017, 2022), which would duplicate survey rows; survey records for those years are kept. YEAR excludes mid-season forecast records. TOTAL excludes farm-type domain splits. ALL PRODUCTION PRACTICES is redundant once short\_desc is pinned, since irrigated series carry their own short description, and it stays as a cheap safety net.  
Statistics collected: YIELD, AREA HARVESTED, AREA PLANTED. That's 4 crops × 4 states × 3 statistics \= 48 requests.

# 3\. Season windows

| Crop | Start | End | Days | Year the window belongs to |
| :---- | :---- | :---- | :---- | :---- |
| CORN | May 1 | Sep 30 | 153 | Harvest year |
| SOYBEANS | May 1 | Oct 31 | 184 | Harvest year |
| WHEAT | Sep 1 | Jun 30 | 303 (304 when the harvest year is a leap year) | **Sep 1 of year−1 through Jun 30 of the harvest year** |
| SORGHUM | Jun 1 | Oct 31 | 153 | Harvest year |

Implementation Tip: For a WHEAT row with year Y, the window is 1 Sep (Y-1) to 30 Jun (Y). Build it as an explicit date pair per row. A filter such as month \>= 9 or month \<= 6 inside a single calendar year returns the wrong days.

**GDD parameters:**

GDD is growing degree days, a running total of heat available to the crop

| Crop | T\_base | T\_cap | Source |
| :---- | :---- | :---- | :---- |
| CORN | 10 °C (50 °F) | 30 °C (86 °F) | The "86/50" modified GDD system, NDSU NDAWN corn GDD model |
| SOYBEANS | 10 °C (50 °F) | 30 °C (86 °F) | NDSU NDAWN soybean GDD model |
| WHEAT | 0 °C (32 °F) | 26 °C (78.8 °F) | USA National Phenology Network winter wheat development forecast |
| SORGHUM | 10 °C (50 °F) | 38 °C (100 °F) | Grain sorghum base 50 °F, upper cutoff 100 °F, extension standard |

The °C values are conversions of the published °F thresholds (sorghum's 37.8 °C is rounded to 38 in `build_master.py`). The formula in section 4.3 is the modified GDD method those thresholds belong to: Tmin floored at T\_base, Tmax capped at T\_cap.

Extreme heat threshold: 35 °C on Tmax, uniform across crops. This is a design choice, not a defined standard. If teams want a crop specific threshold they can rebuild the field from a daily panel.

# 4\. Field specifications

21 fields.

## 4.1 Identity (5)

| Field | Type | Source | Rule |
| :---- | :---- | :---- | :---- |
| fips | String, exactly 5 chars | USDM county FIPS | Not nullable. Zero-padded. 06001, not 6001\. |
| county\_name | String | USDM county name | Not nullable. |
| state\_alpha | String, 2 chars | USDM state | Not nullable. One of CA, NE, IA, DE. |
| year | Integer | NASS year | Not nullable. 2000 to 2025\. Harvest year. |
| crop | String | Derived (section 2\) | Not nullable. One of the 4 values. |

## 4.2 Yield, from NASS (5)

| Field | Derived? | Calculation | Missing-data rule |
| :---- | :---- | :---- | :---- |
| yield\_per\_acre | No | NASS Value where statisticcat\_desc \= YIELD. Strip commas, coerce non-numeric to NaN. The unit is bushels per acre (bu/acre) for all 4 crops. | NaN when NASS did not publish. Never imputed, never zero-filled. |
| yield\_status | Yes | reported when a numeric value came back. suppressed when NASS returned a yield of 0 (planted, no grain harvest; 74 rows, 2000–2008). not\_reported when the county-crop-year has no NASS record but the pair exists elsewhere in the window. | Not nullable. |
| acres\_planted | No | NASS Value where statisticcat\_desc \= AREA PLANTED. | NaN when absent. |
| acres\_harvested | No | NASS Value where statisticcat\_desc \= AREA HARVESTED. | NaN when absent. |
| yield\_anomaly\_pct | Yes | OLS (ordinary least squares) linear trend fitted per (fips, crop) over all non-null yields in 2000 to 2025\. (actual − fitted) / fitted × 100\. | NaN when fewer than 10 non-null yields exist for that pair, when yield\_per\_acre is NaN, or when the fitted value falls below 1.0 bu/acre |

## 4.3 Weather, from NOAA ACIS (5)

**Request contract.** GridData, grid \= 1 (NRCC Interpolated, the Northeast Regional Climate Center's national grid, US-wide, 1950 to present), one JSON POST per state per calendar year, 1999 through 2025\. That's 4 states x 27 years \= 108 requests

* Grid codes and the area reduction options are documented in ACIS Web Services V2 references.

Four things about this request are load-bearing:

* units must be present. ACIS defaults to degreeF and inch. Omit it and every value is wrong by a conversion while still looking plausible.  
* grid is required. Use grid 1\.  
* area\_reduce is what produces county values. GridData has no county key, and loc takes a lon/lat point rather than a FIPS code. There is no county\_sum, so seasonal precipitation is a daily county\_mean summed across days.  
* Output is JSON. GridData does not offer CSV.

Grid 1 has almost no gaps: 30 county-days of missing temperature in 5 coastal California counties, which season aggregates skip. Coverage is asserted rather than tolerated: every county-crop-year must have a day count equal to its window length.  
tavg\_c is computed as the mean of daily (tmax \+ tmin) / 2 rather than requesting the avgt element, so all temperature fields share one definition and the pipeline doesn't depend on avgt being served on grid 1\.

| Field | Calculation |
| :---- | :---- |
| precip\_mm | Sum of daily county-mean precipitation across the window |
| precip\_anomaly\_pct | (precip\_mm − mean) / mean × 100, where mean is the avg precip\_mm for that (fips, crop) over 2000 to 2025\. NaN when fewer than 5 non-null years exist. |
| tavg\_c | Mean across the window of daily (tmax \+ tmin) / 2 |
| extreme\_heat\_days | Count of days in the window where tmax \>= 35 °C |
| gdd | Sum across the window of max(0, (min(tmax, T\_cap) \+ max(tmin, T\_base)) / 2 − T\_base) |

extreme\_heat\_days will be near zero for WHEAT rows outside California (California wheat averages 12 days), because the September-to-June window rarely reaches 35 °C. That is a property of the window, not evidence that wheat is heat-tolerant, and the data dictionary says so.

## 4.4 Drought, from U.S. Drought Monitor (3)

**Source.** USDM REST API, `CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent` with `statisticsType=2` (**categorical**, not cumulative), one JSON request per state per year. The JSON keys are lowercase: fips, mapDate, none, d0, d1, d2, d3, d4, each a percentage of county area.  
D0 abnormally dry, D1 moderate drought, D2 severe, D3 extreme, D4 exceptional  
DSCI is the Drought Severity and Coverage Index: one number from 0 to 500 combining how much of a county is in drought with how severe it is. Weights of 1 through 5 on the categorical D0 to D4 area percentages, per the National Drought Mitigation Center DSCI fact sheet.  
A week belongs to a season when its MapDate falls inside the window, inclusive.  
Categorical is required. Under the cumulative form, D0 includes D1 through D4, which makes D2 \+ D3 \+ D4 a triple count and makes the DSCI weights produce values above 500\.  
**Coverage.** The USDM archive begins 4 Jan 2000\.

| Field | Calculation | Missing-data rule |
| :---- | :---- | :---- |
| max\_drought\_severity | Highest category with more than 1% of county area in any week of the season. The 1% is a design choice: at 0%, a sliver of D4 anywhere in the county would set the field to 5\. Teams can rebuild it with another threshold from the weekly panel. 0 \= none, 1 \= D0, 2 \= D1, 3 \= D2, 4 \= D3, 5 \= D4. | 0 when all season weeks are clear. NaN when no USDM weeks fall in the window, and for every WHEAT year 2000 row (its season starts before the USDM archive). |
| weeks\_in\_d2\_plus | Count of weeks where D2 \+ D3 \+ D4 \> 1% of county area | Same as max\_drought\_severity |
| mean\_dsci | Mean across season weeks of D0×1 \+ D1×2 \+ D2×3 \+ D3×4 \+ D4×5. Range 0 to 500\. | Same as max\_drought\_severity |

## 4.5 Soil, from NRCS SSURGO (3)

**Access:** Soil Data Access (SDA) API, https://sdmdataaccess.nrcs.usda.gov/Tabular/SDMTabularService/post.rest. SQL over the legend, laoverlap, muaoverlap, mapunit, muaggatt, component, and cointerp tables. The gSSURGO valu1 table is not in Soil Data Access, so its values are rebuilt from these.

| Field | Source | Calculation |
| :---- | :---- | :---- |
| aws\_100cm\_mm | muaggatt.aws0100wta × 10 (cm to mm) | Area-weighted mean across the county's map units. Millimetres of plant-available water in the top 100 cm. |
| droughty\_pct | derived: muaggatt.aws0100wta ≤ 15.2 cm | Percent of county area on map units with 152 mm or less of available water in the top 100 cm, the same threshold as the gSSURGO droughty flag. |
| nccpi\_crop | cointerp NCCPI Corn, Soybeans, Small Grains submodels, component-weighted | Area-weighted mean of the crop-matched NCCPI, 0 to 1\. |

NCCPI is the National Commodity Crop Productivity Index, 0 to 1\. nccpi\_crop mapping by crop:

| crop | NCCPI submodel | Note |
| :---- | :---- | :---- |
| CORN | Corn | \- |
| SOYBEANS | Soybeans | \- |
| WHEAT | Small Grains | \- |
| SORGHUM | Corn | Proxy. Documented proxy; teams should be aware that NCCPI-Sorghum models do not exist. |

Soil is time-invariant, so these 3 values repeat across all 26 years of a county. Soil is also the only field group that joins on fips alone.  
Only Marin County, CA (06041) has NaN soil values in the soil panel. It has no NASS crop records, so the master has no soil NaNs.

# 5\. Missing-data summary

One table, because this is what students get wrong.

| What you see | What it means |
| :---- | :---- |
| yield\_per\_acre NaN, yield\_status \= suppressed | NASS listed planted acres, a yield of 0 and no harvested acres: no grain harvest. For corn, NASS's silage series shows these acres were cut for silage. |
| yield\_per\_acre NaN, yield\_status \= not\_reported | NASS published no estimate for that county-crop-year. |
| No row at all for a county-crop | That crop has no NASS county record in this state across 2000 to 2025\. California soybeans is a known case. |
| Rows exist but yield\_per\_acre is always NaN.  | NASS publishes acreage without a county yield estimate. |
| Drought fields NaN on a WHEAT year 2000 row | The season starts Sep 1999 and the USDM archive starts Jan 2000\. |
| Soil fields NaN | Does not occur in the master. In the soil panel, Marin County (06041) is NaN. |

None of these is a zero. None should be imputed.

# 6\. Validation checks

These are the spec's check numbers. The last column gives the label `build_master.py` prints, which uses its own numbering.

| \# | Check | Pass condition | build\_master.py |
| :---- | :---- | :---- | :---- |
| V1 | Row count | Row count matches the filtered universe (all county-crop pairs with at least 1 NASS observation) multiplied by 26\. Do not assert against the theoretical 26,312 total. | V1 (only checks 10k–25k) |
| V2 | Uniqueness | Zero duplicate fips, crop, year, asserted **before** any dedupe so a fan-out fails loudly | V2 |
| V3 | FIPS validity | Every fips is in the 253-county backbone. | V3 |
| V4 | FIPS type | fips is a string of length 5 in both the CSV and the parquet | V4 |
| V5 | Year span per group | For each (crop, state\_alpha), report min and max year. Flag any group not spanning 2000 to 2025\. | V5 note (printed, not a pass/fail check) |
| V6 | Crop and state values | crop in the 4 values, state\_alpha in the 4 states, no others | V6 |
| V7 | Yield positivity | Every non-null yield\_per\_acre is greater than 0 | V7 |
| V8 | Yield unit | Every NASS yield record carries unit\_desc \= "BU / ACRE" | not implemented |
| V9 | Weather coverage | Every row's contributing day count equals its window length, computed from that row's start and end dates rather than a fixed constant. WHEAT is 303 days, or 304 in leap harvest years (2000, 2004, 2008, 2012, 2016, 2020, 2024\) | V10 day count |
| V10 | Join accounting | Row count before and after every join is logged; every dropped row is recorded with a reason | not implemented (row counts asserted) |
| V11 | Soil time-invariance | Within each county, aws\_100cm\_mm has zero variance across years | V16 |
| V12 | Soil coverage | Null rate for aws\_100cm\_mm reported per state; flag any state above 10%, as a reporting trigger not a strong filter. These flags will be reported in data dictionary. | not implemented |
| V13 | State reconciliation | Acreage-weighted county yields per (crop, state, year) land within 10% of the published NASS state yield. | not implemented |
| V14 | Drought ranges | max\_drought\_severity in {0,1,2,3,4,5}. mean\_dsci in \[0, 500\]. weeks\_in\_d2\_plus \<= weeks in the window. | V12, V14 |
| V15 | Weather plausibility  | precip\_mm \>= 0\. gdd \>= 0\. tavg\_c in \[-20, 40\] (observed 2.9 to 30.8). Per crop GDD upper bounds should be derived rather than assumptions: window days x (T\_cap \- T\_base). This will give corn 3060, soybeans 3680, winter wheat 7878, sorghum 4253 | V11 |
| V16 | Acreage consistency | acres\_harvested \<= acres\_planted wherever both are non-null | V9 |
| V17 | Known gaps present | Zero non-null SOYBEANS yields in CA. Zero non-null SORGHUM yields in IA. Both cross-referenced to the per-source failure logs in data/processed/ (e.g. nass\_failures.json). | V18 (CA soybeans only) |
| V18 | yield\_status | yield\_status \= reported implies yield\_per\_acre is non-null, and suppressed or not\_reported implies it is null | not implemented |

# 7\. Known limitations, for the data dictionary

* **Irrigation is not a field in the master.** The irrigation extension (`data/processed/irrigation/nass_irrigation.parquet`) covers mostly Nebraska 2000–2018. In the master, no field records which counties or acres are irrigated, and aws\_100cm\_mm measures what the soil can hold, not water applied. In Nebraska this reverses two comparisons: the lowest-storage counties are the most irrigated, and most corn is irrigated while most sorghum is not. USGS irrigation water-use data is available as an advanced extension.  
* **Season windows are fixed per crop.** Actual planting and harvest shift by year and by state. California in particular plants corn from mid-March and winter wheat from mid-October, both earlier than the fixed windows. The daily weather panel ships so teams can build their own.  
* **Sparse coverage is expected.** Not every county grows every crop every year. California corn, Delaware sorghum, and Iowa winter wheat are thin by nature, not by error.  
* **WHEAT is winter wheat only. CORN and SORGHUM are grain only** for yield and harvested acres, excluding silage, which NASS reports in tons per acre. Planted acres cover all uses (silage, and grazing or hay for wheat), so planted − harvested is not abandonment.  
* **SSURGO is static.** Land use change, erosion, and amendments over 26 years are not captured.  
* **Vernalization is not modelled.** Winter wheat GDD uses a simple heat sum and ignores the cold requirement for grain development.  
* **nccpi\_crop for sorghum is a corn proxy.** NCCPI publishes no sorghum model.