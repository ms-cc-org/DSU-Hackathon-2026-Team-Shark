# Data to Harvest: AI for Agricultural Resilience Hackathon at Delaware State University

# Draft Concept and Challenge Structure

**October 17–18, 2026  |  24-hour interdisciplinary student hackathon  |  Target: up to 50 students**

## 1\. Event Concept

The hackathon will bring together students from computer science, agriculture, data science, business, MIS, and related disciplines to solve a shared agricultural challenge using data, AI, and software development. Teams of approximately 3–5 students will have 24 hours to define a problem, analyze relevant data, build a working prototype, and present their solution to a panel of judges.

The event should be organized around one coherent real-world problem rather than a collection of unrelated prompts. A shared challenge gives the hackathon a clear identity while still allowing teams to choose different users, datasets, methods, and technical approaches.

## 2\. Recommended Theme

**Data to Harvest: AI for Agricultural Resilience Hackathon**  
Agricultural producers and researchers increasingly make decisions under uncertainty about rainfall, drought, temperature, soil conditions, water availability, crop performance, and changing land conditions. The challenge asks students to use environmental and agricultural data to build a tool that helps an agricultural stakeholder understand risk and make a better-informed decision.

## 3\. Core Challenge Statement

A farming community is facing increasing variability in rainfall, temperature, drought, water availability, and growing conditions. Your team has been asked to develop a digital tool that helps farmers, researchers, extension professionals, or other agricultural stakeholders understand these conditions and make better decisions.  
All teams would work from the same broad scenario and a curated starter data package. Teams would decide which specific problem to address, who their intended user is, and what kind of application or decision-support tool to build.

## 4\. Possible Challenge Directions

Seven directions the data supports, each with a user and a decision. The README gives what success looks like and where to start for each.

* **Crop Loss Early Warning:** a crop insurance office decides, by August 1, which Iowa and Nebraska counties to send loss inspectors to first.
* **Drought Assistance Targeting:** a state drought program decides which counties get help first and what drought rule triggers it.
* **Heat-Stress Advisory:** an extension crop specialist decides when to warn corn and soybean growers that heat is hurting their crop.
* **Soil and Crop Resilience Planning:** a soil conservation office decides where long-term soil programs would cut drought losses the most.
* **Grain Supply Outlook:** an Iowa ethanol plant decides whether to buy extra corn from outside its local area this year.
* **Frost-Safe Planting Calendar:** an extension agronomist decides the earliest date to recommend planting frost-sensitive crops in each county.
* **Drought Category Reality Check:** a state drought task force decides whether a drought category should trigger the same response in Iowa as in Nebraska.
* **AgriAdvisor (optional):** an evidence-grounded assistant built on top of another direction. It must show the data behind each answer, and teams need their own AI model access.

## 5\. Shared Data Package

[Technical Implementation Plan](technical_implementation_plan.md)

| Dataset | What We Provide | Example Variables | Source | How Teams Might Use It |
| ----- | ----- | ----- | ----- | ----- |
| **Weather & Climate** | County-level weather conditions summarized by growing season | Precipitation, precipitation anomaly, average temperature, extreme heat days, growing degree days (daily max/min temperature and precipitation in the daily panel) | NOAA | Identify heat and water stress; explore relationships between weather and crop outcomes |
| **Drought** | County-level drought exposure and severity | Weeks in severe drought (D2+), maximum drought severity, mean Drought Severity and Coverage Index (DSCI) | U.S. Drought Monitor | Build drought-risk indicators, compare drought exposure with crop yield, identify high-risk areas |
| **Soil Characteristics** | Simplified agricultural soil characteristics by county | Available water storage, share of drought-vulnerable soil, crop productivity index (NCCPI) | USDA NRCS | Evaluate how soil conditions affect vulnerability to drought or crop stress |
| **Crop & Yield** | Agricultural production and crop outcomes by county and year | Crop type, acres planted/harvested, yield per acre, yield anomaly | USDA NASS | Analyze crop performance, predict yield, or identify unusually good/bad growing seasons |
| **Geographic Data** | Simplified county boundary file for mapping | County, state, FIPS code, geographic boundary | Census / USDA | Create risk maps, dashboards, and other geospatial applications |
| **Satellite Vegetation (Optional)** | Vegetation-condition measures for advanced teams | Annual NDVI/EVI mean and max, NDVI anomaly, peak-greenness date | NASA / satellite data | Detect vegetation stress and test whether satellite observations explain yield differences (calendar-year values, so not a pre-harvest forecast) |
| **Irrigation (Optional)** | Irrigated share of harvested acres and irrigated vs. dryland yields, mostly Nebraska 2000–2018 | Irrigated share, irrigated yield, non-irrigated yield | USDA NASS | Separate irrigation from soil and drought effects |
| **Master Hackathon Dataset** | Beginner-friendly file combining the core datasets | County, year, crop, precipitation, extreme heat days, drought severity, soil water capacity, yield, yield anomaly | Derived from above sources | Begin analysis immediately without having to join multiple datasets |

**Supporting materials:** The package will also include a data dictionary, source documentation, starter notebook, county boundary file, and example code for loading, visualizing, and mapping the data. Starter materials will demonstrate how to work with the datasets without providing a solution to the challenge.

**Possible applications:** Drought-risk dashboards, crop-yield prediction, agricultural resilience indices, geographic risk maps, crop-stress early-warning systems, or evidence-grounded AI agricultural assistants.

**Common framework:** **Environmental Exposure → Agricultural Vulnerability → Crop Impact → Decision Support**

### 6\. Required Team Deliverables

Every team should produce the same core set of deliverables so that judging is consistent across different technical approaches.

* A working application or prototype that addresses the selected agricultural problem  
* A GitHub repository containing the code, documentation, and instructions needed to understand or run the project  
* A short final presentation and live demonstration  
* A clear explanation of the intended user, the problem being solved, the data/evidence used, and why the solution is useful


### 7\. Technical Expectations

The event should support students with different levels of experience. Teams should be judged on the quality of the solution, not simply on the complexity of the technology used.

| Level | Example expectation |
| :---- | :---- |
| Minimum viable submission | Load and use provided data, perform meaningful analysis, visualize results, and provide an interactive interface or useful decision output.  |
| Competitive submission | Add prediction, machine learning, geospatial analysis, external data integration, or another technically substantive capability.  |
| Advanced submission | Add AI assistance, model evaluation or explainability, real-time APIs, sophisticated geospatial analysis, optimization, or another original capability. |

A Streamlit, Gradio, or similar lightweight application would be an appropriate target. A well-developed interactive Jupyter notebook could be accepted for less experienced teams, but the primary goal should be a usable prototype rather than a notebook containing analysis alone.

### 8\. Team Formation

Teams should contain approximately 3–5 students, with no more than five members. Students who already have established teams may register together. Students registering individually can be matched by organizers, with an effort to create interdisciplinary teams that combine technical and domain expertise.

Registration should collect major/discipline, year of study, relevant technical experience, and whether the student already has a team. With a cap of 50 students, the event would likely have approximately 10–12 teams.

### 9\. Proposed Judging Rubric

| Criterion | Weight |
| :---- | :---- |
| Problem relevance and understanding | 20% |
| Technical implementation | 15% |
| Use of data and evidence | 15% |
| Usability and working prototype | 25% |
| Innovation | 15% |
| Presentation and demonstration | 10% |
| Total | 100% |

Judges should be instructed that technical complexity alone does not determine the strongest project. A simpler, well-executed application that clearly solves an agricultural problem should be competitive with a more complex AI or ML solution.

### 10\. Proposed 24-Hour Structure

| Time | Activity | Notes  |
| :---- | :---- | :---- |
| Saturday morning | Registration, welcome, challenge reveal, dataset overview, team formation, and brief technical orientation. | Registration opens at 8:00am  Hackathon begins at 9:00am  |
| Late morning–afternoon | Problem definition and initial build. |  |
| Saturday afternoon | Mentor checkpoint \#1: teams identify their user, problem, proposed solution, and data. |  |
| Saturday evening | Mentor checkpoint \#2: teams demonstrate that data is loaded and a basic analysis or prototype is functioning. |  |
| Overnight | Build, test, and refine. |  |
| Sunday morning | Final development, testing, code stabilization, and presentation preparation. |  |
| Sunday late morning / midday | Approximately 5-minute team pitches and demonstrations followed by 3 minutes of judge Q\&A. |  |
| Sunday | Judging, awards, and closing. | Conclude at 2pm  |

### 11\. Mentoring and Staffing

For approximately 50 students, the event should ideally have at least 5–6 available mentors covering complementary areas such as agriculture/domain expertise, Python and data science, application development, geospatial analysis, and AI/ML. Mentors can rotate rather than remain on duty continuously, but coverage should be planned across the full event.

### 12\. Alternative Theme Options

AI for Agriculture: From Data to Decisions  
A broader AI-forward theme in which teams choose an agricultural problem and use supplied datasets to build an AI- or data-driven application.  
Resilient Farms Challenge: Climate, Land & Water  
A more environmental and geospatial framing focused on drought, water availability, land use, crop conditions, and environmental risk.

### 13\. Recommended Next Steps

1. Confirm the primary hackathon theme and challenge statement with the host institution.  
2. Identify 3–5 authoritative datasets and prepare a cleaned, documented starter data package.  
3. Decide whether an interactive notebook may qualify as a final prototype or whether all teams must produce an application.  
4. Finalize the judging rubric and recruit judges with both technical and agriculture/domain perspectives.  
5. Recruit additional mentors and create an overnight staffing plan.  
6. Define the registration questions needed for team formation and experience-level planning.  
7. Prepare a starter GitHub repository or resource page with data descriptions, example loading code, rules, submission requirements, and judging criteria.

