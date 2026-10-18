# Extra data for the Soil Program Planner (data preparation only)

Pulled by the scripts in `soil_planner/pulls/`. Nothing here changes the drought-penalty scoring; these files
are inputs for later work. `fips` is 5-character text in every file.

## iowa_soil_extra.csv  (Part A: more soil properties)

- **Source.** USDA NRCS Soil Data Access (SDA) tabular service, `https://sdmdataaccess.nrcs.usda.gov/Tabular/SDMTabularService/post.rest`, SSURGO tables
  `legend`, `laoverlap`, `muaoverlap`, `mapunit`, `component`, `chorizon`, `muaggatt`. No key.
- **Date pulled.** 2026-10-17 (raw responses cached in `raw/IA_*.json`; delete them to re-pull).
- **Coverage.** 99 Iowa counties, one row each.
- **Method.** Same county aggregation as `src/build/SSURGO_data_pull.py`: soil survey legends whose symbol starts
  with `IA`, overlapped with counties through `laoverlap` -> `muaoverlap`, each map unit weighted by its acres inside
  the county (`areaovacres`). Within a map unit, components are weighted by `comppct_r`. Each property is averaged
  only over the area where it is recorded (components with the property missing are left out of that average,
  not counted as zero). The county symbol (e.g. `IA153`) becomes FIPS `19153`.
- **Columns and units.**
  - `om_surface_pct`, `clay_surface_pct`, `sand_surface_pct`: representative organic matter, total clay and total
    sand (percent by weight) of the **surface layer**, defined as the component's horizon that starts at 0 cm
    (`chorizon.hzdept_r = 0`; when a component has two such horizons the lowest `chkey` is used).
  - `slope_pct`: representative slope (`component.slope_r`, percent), component- and area-weighted.
  - `drainage_dominant`: the `component.drainagecl` class covering the most component-weighted area in the county;
    `drainage_dominant_share_pct`: its share (percent) of the component area that has a drainage class.
  - `aws_100cm_mm_recomputed`: available water storage, top 100 cm, in mm, recomputed with the exact query of the
    source script (`muaggatt.aws0100wta` x 10) as a validation of the weighting.
  - `surface_horizon_coverage_pct`, `slope_coverage_pct`: share of the county's component area that has a surface
    horizon with organic matter / a slope value (how much of the county each average rests on).
  - `component_acres`: component-weighted acres summed over the county (map-unit overlap acres x comppct / 100).
- **SSURGO release.** These extra properties come from the SSURGO release current on SDA at the pull date; every
  Iowa survey area carries a September 2026 version date (`sacatalog.saverest`), the annual refresh. The master
  dataset's `aws_100cm_mm` (in `data/processed/soil/soil_county.parquet`) was pulled from an earlier release and
  **stays the storage variable used everywhere in the app and the notebooks**; this file supplies only the
  additional properties. `aws_100cm_mm_recomputed` is kept here for the validation only.
- **Validation.** The source script's exact aws query, run on the current release, against `load_soil()` for the
  99 Iowa counties: 94 of 99 within 1 mm, mean absolute difference
  0.27 mm, maximum 4.0 mm (Poweshiek County, 19157). The query is identical, so the
  differences reflect NRCS map revisions between releases, not the weighting. Per-county table:
  `aws_validation.csv` (`aws_100cm_mm_master`, `aws_100cm_mm_sda_2026_09`, `abs_diff_mm`).
- **Queries.** See `Q_AWS`, `Q_SURFACE`, `Q_DRAINAGE` in `soil_planner/pulls/pull_soil_extra.py`.

## iowa_conservation_practices.csv  (Part B: conservation practices, Census of Agriculture)

- **Source.** USDA NASS Quick Stats API (`https://quickstats.nass.usda.gov/api/api_GET`), `source_desc=CENSUS`, `agg_level_desc=COUNTY`, `domain_desc=TOTAL`,
  `state_alpha=IA`. The key is read from the repo-root `.env` at run time and is not stored anywhere.
- **Date pulled.** 2026-10-17 (raw responses cached in `raw/nass_*.json`).
- **Coverage.** Census years 2017, 2022; 99 Iowa counties; 198 county-years.
  The two cropland items are also published for 1997, 2002, 2007, 2012 census years; those years have no
  practice items and are left out of the CSV (they remain in the raw cache). The 2012 Census also collected cover
  crops and tillage, but Quick Stats publishes the 2012 Iowa values at state level only (checked: no county rows under
  any domain), so 2012 is absent.
- **Items** (`short_desc` as confirmed with the parameter-values endpoint; operation counts and acres per operation skipped):
  - `cover_crop_acres` = `PRACTICES, LAND USE, CROPLAND, COVER CROP PLANTED, (EXCL CRP) - ACRES`
  - `no_till_acres` = `PRACTICES, LAND USE, CROPLAND, CONSERVATION TILLAGE, NO-TILL - ACRES`
  - `reduced_till_acres` = `PRACTICES, LAND USE, CROPLAND, CONSERVATION TILLAGE, (EXCL NO-TILL) - ACRES`
  - `conventional_till_acres` = `PRACTICES, LAND USE, CROPLAND, CONVENTIONAL TILLAGE - ACRES`
  - `cropland_acres` = `AG LAND, CROPLAND - ACRES`
  - `harvested_cropland_acres` = `AG LAND, CROPLAND, HARVESTED - ACRES`
- **Units.** All raw columns are acres. Shares are fractions (0-1), ratios are unitless.
- **Suppression.** Any non-numeric `Value` is kept as **missing, never zero**, and the code is preserved in the
  matching `*_code` column. NASS's symbol list (2022 Census of Agriculture, Volume 1, Introduction, "Abbreviations and
  Symbols"): `(D)` "Withheld to avoid disclosing data for individual farms", `(Z)` "Less than half of the unit shown",
  `(NA)` "Not available", `(X)` "Not applicable". Codes seen in this pull: none.
- **Computed columns.**
  - `tilled_total` = `no_till_acres` + `reduced_till_acres` + `conventional_till_acres`, only when all three are
    present; missing otherwise.
  - `no_till_share`, `reduced_till_share`, `conventional_share` = each tillage item / `tilled_total`.
  - `cover_crop_share` = `cover_crop_acres` / `harvested_cropland_acres`.
  - `tilled_to_harvested`, `tilled_to_cropland` = `tilled_total` / harvested cropland and / total cropland (checks).
- **Checks.** Median across counties of `tilled_total` / harvested cropland and / total cropland, per year:

|   year |   tilled_to_harvested median |   tilled_to_harvested min |   tilled_to_harvested max |   tilled_to_harvested count |   tilled_to_cropland median |   tilled_to_cropland min |   tilled_to_cropland max |   tilled_to_cropland count |
|-------:|-----------------------------:|--------------------------:|--------------------------:|----------------------------:|----------------------------:|-------------------------:|-------------------------:|---------------------------:|
|   2017 |                        0.974 |                     0.687 |                     1     |                          99 |                       0.91  |                    0.417 |                    0.971 |                         99 |
|   2022 |                        0.978 |                     0.685 |                     0.997 |                          99 |                       0.897 |                    0.434 |                    0.966 |                         99 |

  Missing county-years per item and year (suppressed or not published):

|   year |   cover_crop_acres |   no_till_acres |   reduced_till_acres |   conventional_till_acres |   cropland_acres |   harvested_cropland_acres |
|-------:|-------------------:|----------------:|---------------------:|--------------------------:|-----------------:|---------------------------:|
|   2017 |                  0 |               0 |                    0 |                         0 |                0 |                          0 |
|   2022 |                  0 |               0 |                    0 |                         0 |                0 |                          0 |

- **Definitions.** Quoted from USDA NASS, *2022 Census of Agriculture, Volume 1, Appendix B: General Explanation and Census of Agriculture Report Form*
(https://www.nass.usda.gov/Publications/AgCensus/2022/Full_Report/Volume_1,_Chapter_1_US/usappxb.pdf; text extracted from the PDF on 2026-10-17; page numbers are the printed "B - n" labels). The Quick Stats `short_desc` names differ slightly from the Appendix B headings; the mapping below is ours.
  - **Land use practices** (B-11): "Includes all agricultural land used for the production of agricultural commodities." The three tillage items and the cover crop item sit under this heading, so their acres are acres of *cropland*, and the Census table heading for the items reads "Cropland on which ... practices were used".
  - **`no_till_acres`** = "No-till practices used" (B-11): "Using no-till or minimum till is a practice used for weed control and helps reduce weed seed germination by not disturbing the soil." (No residue-cover threshold is given for no-till.)
  - **`reduced_till_acres`** = "Conservation or reduced tillage" (B-11 to B-12): "Conserves the soil by reducing erosion and decreasing water pollution. Conservation tillage leaves 30 percent or more of the soil surface covered by crop residue after planting. Reduced tillage leaves between 15 percent and up to 30 percent of the soil surface covered. In 2017, this category was labeled reduced (conservation tillage). This is a wording change only; data are comparable." The Quick Stats name "CONSERVATION TILLAGE, (EXCL NO-TILL)" is this category: conservation or reduced tillage excluding no-till.
  - **`conventional_till_acres`** = "Intensive or conventional tillage" (B-12): "Refers to tillage operations that use standard practices which leaves less than 15 percent of the soil surface covered by crop residue. Intensive tillage often involves multiple operations with implements such as moldboard, disk, or chisel plow. In 2017, this category was labeled as intensive (conventional tillage). This is a wording change only; the data are comparable."
  - **`cover_crop_acres`** = "Cover crop" (B-12): "A crop planted primarily to manage soil fertility, soil quality, water, weeds, pests, diseases, or wildlife. This item does not include CRP acres."
  - **`cropland_acres`** = "Total cropland" (B-18): "This category includes cropland harvested, other pasture and grazing land that could have been used for crops without additional improvements, cropland on which all crops failed or were abandoned, cropland in summer fallow, and cropland idle or used for cover crops or soil improvement but not harvested and not pastured or grazed."
  - **`harvested_cropland_acres`** = "Harvested cropland" (B-9): "This category includes land from which crops were harvested and hay was cut, land used to grow short rotation woody crops, Christmas trees, and land in orchards, groves, vineyards, berries, nurseries, and greenhouses. Land from which two or more crops were harvested was counted only once. Land in tapped maple trees was included in woodland not pastured. The 2022 census definition for harvested cropland is the same as the 2017 definition."
  - **Not confirmed.** Appendix B does not say which cropland acres a respondent counts under the three tillage items (for example whether land in hay or idle cropland is included), nor whether the three categories are meant to be exhaustive and mutually exclusive. We did not find that in NASS text, so we do not assert it; the `tilled_to_harvested` and `tilled_to_cropland` ratios in the CSV are the empirical check. The 2012 Census also collected these practices, but Quick Stats publishes the 2012 values for Iowa at state level only (no county rows), so 2012 is absent from the CSV.
- **Query.** See `ITEMS` and `fetch()` in `soil_planner/pulls/pull_conservation_practices.py`.
