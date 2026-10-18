# Soil Program Planner — Team Shark (Data to Harvest Hackathon, DSU 2026)

A decision tool for a **Soil Conservation Office**. Each winter, before the next season's program sign-ups, the office has to decide **which Iowa counties get priority for soil-program outreach and funding to cut drought losses**. The planner ranks the 99 Iowa counties by how much more they lost in past droughts than in their own normal years, shows the evidence that this ranking predicts losses in droughts it had never seen, flags counties whose score rests on few drought years, and shows each county's soil and current conservation practices as context. It covers corn and soybeans separately, 2000–2025, rain-fed Iowa only.

## Main result

- **The drought-penalty ranking beats chance on unseen droughts.** Built on 2000–2015 and tested on the 2016–2025 drought years, about 45% (corn) and 49% (soybeans) of the counties it ranked in the top third were among the hardest hit, against 33% by chance: roughly 15 to 16 of every 33 flagged counties, against 11 by chance. The corn ranking held up in every test year; the soybean ranking was less consistent.
- **Soil water storage shows no clear effect.** It leans toward smaller losses, but every estimate's range includes zero, and Iowa's storage range is narrow and entangled with region, so we don't recommend targeting programs by storage alone.
- **Organic matter shows no clear effect** under a pre-registered decision rule (notebook 07).
- **A Nebraska replication was not testable.** Irrigation leaves only 13–18 mostly rain-fed counties, below our pre-set minimum of 20, so the pre-registered plan stopped at its feasibility gate (notebook 06).

## Quick start

Needs **Python 3.11 to 3.13**. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run soil_planner/app.py
```

Run the app from the repository root, as above. The first load takes a few seconds while the drought penalties and the held-out test are computed; after that every setting change is instant.

Live app: (link to be added)

The report version, `notebooks/Soil_Program_Planner.ipynb`, calls the same functions as the app, so both show the same numbers. To re-run it without opening it: `jupyter nbconvert --to notebook --execute --inplace notebooks/Soil_Program_Planner.ipynb`.

## App pages

The crop and drought definition chosen at the top apply to every page.

**Plan**
- **This winter's plan.** The recommendation for the counties to fund, the standard-confidence county list, three insight cards and the priority list with a CSV download.
- **County explorer.** A county map with a metric selector and the funded counties outlined; click a county for its penalty, rank, confidence, soil context, current practices, reasons and year-by-year chart.

**Evidence**
- **How we know it works.** The scorecard, the held-out proof chart, the held-out and placebo tables, and the earlier attempts we moved on from.
- **How we got here.** The project story and the methods note.

**Reference**
- **Limits and next steps.** What the evidence can and cannot say, and what to test once programs are funded.
- **About and data sources.** The data behind the tool and the credits.

The "Counties we can fund this winter" slider on the plan page defaults to 33, the top third, which is the cutoff that was tested. Other cutoffs use the same ranking but were not tested separately.

## Repository map

- `soil_planner/` — the planner.
  - `soil_planner/app.py` — Streamlit entrypoint: shared controls and navigation.
  - `soil_planner/soil_tool.py` — the engine: drought penalty, ranking, held-out test, placebo checks, and every note the app and the notebook display.
  - `soil_planner/app_common.py` — cached calls, labels and helpers shared by the pages.
  - `soil_planner/pages_app/` — the six pages.
  - `soil_planner/extra_data/` — extra soil properties and conservation-practice shares shown as context only (see `soil_planner/extra_data/README.md`).
  - `soil_planner/pulls/` — the scripts that pulled the extra data from USDA NRCS Soil Data Access and USDA NASS.
- `notebooks/` — the analysis, in order:
  - `notebooks/01_coverage_checks.ipynb` — how complete yield reporting and drought exposure are by state and crop; settles on Iowa corn and soybeans.
  - `notebooks/02_storage_groups.ipynb` — defines low, middle and high soil-water-storage groups and checks whether they are fair to compare (region, drought exposure, heat).
  - `notebooks/03_storage_effect.ipynb` — in-sample estimate of whether more storage goes with smaller drought-year losses; no clear effect.
  - `notebooks/04_priority_ranking_test.ipynb` — first held-out ranking test, built on a 2000–2015 trend; it failed its placebo check and was abandoned.
  - `notebooks/05_drought_penalty.ipynb` — the drought-penalty score, its held-out test on 2016–2025 and its placebo checks; the method the app uses.
  - `notebooks/06_nebraska_replication.ipynb` — pre-registered replication on Nebraska's rain-fed counties; stopped at the feasibility gate.
  - `notebooks/07_soil_and_practices.ipynb` — pre-registered test of organic matter, other soil properties and conservation-practice shares against the drought penalty; no clear effect.
  - `notebooks/Soil_Program_Planner.ipynb` — the report version of the app, same functions and numbers.
- `soil_priority_extras.py` — a teammate's exploratory bushel-weighted analysis (expected bushels lost per county). The app shows one descriptive line from it; it is not used for the ranking.
- `data/` and `src/` — the master dataset and loaders provided by the organizers, unchanged.
- `docs/` — the organizers' briefing material and the original hackathon README.

## Method in brief

Every comparison is made within a year, so counties are only ever compared with other counties under the same season's weather. A county's drought penalty is how far its drought-year yield fell below its own nearby normal years, after removing that year's statewide drop, so anything permanent about a county cancels out. The score was built on 2000–2015 only and tested on the 2016–2025 drought years it had never seen, with resampled years giving the ranges. The same test was run where it should find nothing, in the non-drought counties of every test year, and the score showed nothing there; our first, trend-based attempt failed that placebo check and was discarded. The Nebraska replication and the soil-and-practices test were pre-registered: their plans were committed before any result existed (commits `2bc1c15` and `dd6722b`), and the results are reported whatever they turned out to be.

## Limits

- **Association, not program effect.** The ranking shows where drought has hurt most, not where a soil program would help most. Nothing here estimates what a program would do.
- **Few test years, no statewide drought among them.** The held-out test rests on 5 to 7 drought years, all partial-state events; no 2012-scale drought is in the test set, and the ranges are wide for that reason.
- **Scoped to rain-fed Iowa, 2000–2025.** Future droughts, new practices or other states may not behave the same way, and the Nebraska replication could not be run.

## Reproducing the analysis

The notebooks `notebooks/01_coverage_checks.ipynb` to `notebooks/07_soil_and_practices.ipynb` run in order. From the repository root, for each one:

```bash
jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/05_drought_penalty.ipynb
```

They write no files; each notebook's results are the tables and verdicts inside it.

- `notebooks/05_drought_penalty.ipynb` produces the drought penalty for every county-year, its held-out ranking test (scores from 2000–2015, tested on the 2016–2025 drought years) with the placebo checks, and the storage estimate with ranges.
- `notebooks/06_nebraska_replication.ipynb` (pre-registered) produces the feasibility gate for Nebraska's rain-fed counties and, for any crop that passes it, the same replication; both crops stopped at the gate.
- `notebooks/07_soil_and_practices.ipynb` (pre-registered) produces the primary test of surface organic matter against the drought penalty, the exploratory soil-property and conservation-practice tests, and the verdict under the rules fixed in advance.

`notebooks/Soil_Program_Planner.ipynb` is the report version of the app: it calls the same functions in `soil_planner/soil_tool.py` and shows the same numbers.

## Troubleshooting

- Run every command from the repository root. From anywhere else, Python cannot find the `src` or `soil_planner` packages and stops with `No module named 'src'` or `No module named 'soil_planner'`.
- Use Python 3.11 to 3.13. An older Python fails at `pip install` (the pinned numpy needs 3.11 or newer); delete `.venv` and create it again with a newer Python.

## Extra data

The app uses the files already in `soil_planner/extra_data/` (see `soil_planner/extra_data/README.md` for their sources, dates and methods). Re-pulling them with the scripts in `soil_planner/pulls/` is optional. The conservation-practices pull needs a free [NASS Quick Stats key](https://quickstats.nass.usda.gov/api) in a `.env` file at the repository root (`NASS_API_KEY=your_key_here`), which `.gitignore` excludes; the soil pull needs no key. Never commit keys.


## Acknowledgments

Built at the Data to Harvest: AI for Agricultural Resilience Hackathon (Delaware State University, Oct 17-18, 2026), organized by MS-CC with support from the National Science Foundation (Grant #2234326).

## Data sources and credits

**Data credits.** Credit the sources when presenting results from this data (wording from the hackathon README):
- **USDA NASS Quick Stats** (county yields; Census of Agriculture conservation practices): This product uses the NASS API but is not endorsed or certified by NASS.
- **NOAA ACIS** (weather): Weather data from the Applied Climate Information System (ACIS), NOAA Regional Climate Centers.
- **U.S. Drought Monitor** (drought): The U.S. Drought Monitor is jointly produced by the National Drought Mitigation Center at the University of Nebraska-Lincoln, the United States Department of Agriculture, and the National Oceanic and Atmospheric Administration.
- **USDA NRCS SSURGO / Soil Data Access** (soil): Soil Survey Staff, Natural Resources Conservation Service, United States Department of Agriculture. Soil Survey Geographic (SSURGO) Database, via Soil Data Access.
- **Data to Harvest hackathon master dataset** (Delaware State University, October 2026): the county x crop x year table that combines the sources above.

From the original hackathon README, for the other sources in the repository:
- **MODIS:** Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061. NASA EOSDIS Land Processes DAAC. https://doi.org/10.5067/MODIS/MOD13Q1.061
- **County boundaries** (`data/counties.geojson`): U.S. Census Bureau county boundaries, from the [plotly/datasets](https://github.com/plotly/datasets) county GeoJSON.

The code and documentation in this repo are under the [MIT License](LICENSE).

## Team

| Name | GitHub |
| --- | --- |
| Lorenzo | [RenzoRamirez26](https://github.com/RenzoRamirez26) |
| Maria Gomez Jacome | [cjgomez14](https://github.com/cjgomez14) |
| Orlando Hernandez | [Orlando-Hernandez](https://github.com/Orlando-Hernandez) |
| Alba Benedito | [albabc2020-hub](https://github.com/albabc2020-hub) |
| Nitya Shah | [Nitya485-nyb](https://github.com/Nitya485-nyb) |

Original hackathon instructions: [docs/HACKATHON_README.md](docs/HACKATHON_README.md)
