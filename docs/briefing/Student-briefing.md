1. **The Situation:**  
   Droughts, heat waves and odd weather make farming hard to plan. Every season, real people decide what to do about it: crop insurers, extension agents, state drought programs, grain buyers. Your team picks **one of them**, uses 26 years of county farm data to help them make **one decision**, and builds a tool that shows it.

2. **What are you looking at**  
   A dataset of farming in 4 US states (California, Iowa, Nebraska, Delaware) over 26 years (2000-2025). **One row \= one county, one crop, one year**. Each row has yield (how much the crop produced), weather (rain, temperature, heat), drought severity and soil quality; all joined together so you can ask questions such as “*when drought hits, which counties lose the most yield and why?*”

3. **What you need to know before touching anything:**   
* **FIPS codes are *text*, not numbers.** The county ID 06001 (Alameda County, California) will silently become 6001 if you let pandas read it as an integer. Every join you write will return zero rows and you won’t get an error or warning. The parquet file and *load\_master()* helper handle this for you. If you use *read\_csv*, you must pass dtype={"fips": str}  
* **Analyze reported yields only.**  Filter to *yield\_status \== "reported"*; only 68% of rows have a reported yield. *not\_reported* means NASS published no data for that county and year; *suppressed* means the crop was planted, but no grain was harvested.  
* **Row counts are lopsided.** IA has 99 corn counties and DE has three. Iowa and Nebraska corn and soybeans are well covered. California, Delaware and sorghum are thin. Count rows before you compare.  
* **Weather and drought cover each crop’s growing season, not the calendar year.** Corn is May-September, Winter wheat is previous year’s Sept \- June. This is already in the master dataset, but you need to know it to interpret numbers.  
* **The data dictionary is not optional.** The *data dictionary* explains every field, NaN reason, limitation. Read it before you start. 

4. **Pick your task**  
   A good task fits in a sentence:  
   **\[User\]** needs to decide **\[decision\]** by **\[when\]**. Our tool shows them **\[evidence\]**.  
     
   Pick a direction below, combine a couple or bring your own. Then check the coverage table in the data dictionary to make sure your states and crops have enough rows. Each direction’s starting step and next steps are in the repo README. 

| Direction | Who decides | Their decision | Success looks like |
| ----- | ----- | ----- | ----- |
| **Crop Loss Early Warning** | Crop insurance office | Which counties to inspect first, on Aug 1 | Flags more real losses than "all counties in severe drought" (or shows why it can't) |
| **Drought Assistance Targeting** | State drought program | Which counties get help first, and the trigger | A county report card; a 2000–2015 ranking that beats chance on 2016–2025 |
| **Heat-Stress Advisory** | Extension crop specialist | When to warn corn and soybean growers | A heat rule that beats "days at 35 °C or hotter" on unseen years |
| **Soil and Crop Resilience Planning** | Soil conservation office | Where soil programs cut drought losses most | A priority map and a soil-effect estimate with a range ("no clear effect" counts) |
| **Grain Supply Outlook** | Iowa ethanol plant | Whether to buy corn from outside its area | A production estimate with a range that beats the trend |
| **Frost-Safe Planting Calendar** | Extension agronomist | Earliest safe planting date per county | A date built on 2000–2018 with frost after it in no more than 1 in 10 years of 2019–2025 |
| **Drought Category Reality Check** | State drought task force | Should D3 mean the same in Iowa and Nebraska? | A drought level → yield loss table from 2000–2012 that predicts 2013–2025 within about 4 points (Iowa and Nebraska corn and beans) |
| **AgriAdvisor** (optional, on top of another) | County extension agent | How to answer a farmer's question | Right answers on hand-checked questions; says "the data can't answer that" when it can't |

5. **How to get there**  
* **Start simple.** Do your direction’s starting step first. It is your baseline: the simple answer your tool has to beat.  
* **Test on years you didn’t use.** Build on earlier years and test on later ones. For example, build on 2000-2018, test on 2019-2025. That is how you show it would have worked in a real season.  
* **Go further only if it helps your user.** Use the daily weather, weekly drought data, a model or a map.  
* **Build the tool for your user.** They should get the answer without reading your code.  
* **Tell the story.** Who is the user, what should they decide, what evidence did you use and how do you know it works?  
  An honest result is a good one. If your result only ties a simple baseline or the effect is unclear, explain why. Judges reward that over an unexplained win.  
    
6. **How to start:**  
   You need python 3.11 or newer. Install before the event, not on event wifi:  
     
   *git clone https\://github.com/ms-cc-org/YOUR-TEAM-REPO.git*  
   *cd YOUR-TEAM-REPO*  
   *python3 \-m venv .venv               (if windows: py \-m venv .venv)*  
   *source .venv/bin/activate           (if windows: .venv\\Scripts\\Activate.ps1)*  
   *python \-m pip install \-r requirements.txt*

   Then pick one entry point, depending on comfort level:

* **Starter notebook (most teams start here):** jupyter lab, open notebooks/starter\_notebook.ipynb. It walks through the 2012 Iowa drought, then offers a few questions (soil buffering, corn vs sorghum, rainfed vs irrigated) or bring your own idea.   
* **Streamlit app** to build an interactive tool: streamlit run app.py. The overview tab works and shows the pattern (filter → aggregate → chart). The other tabs (Weather & Yield, Drought Analysis, Soil & Risk) are empty tabs for you to fill.  
* **Detailed data,** for advanced teams: daily weather (2.5M rows), weekly drought (343k rows) and soil per county. Build your own season windows, drought timing or heat during pollination.  
* **Extensions:** *Optional*: satellite greenness (MODIS NDVI/EVI) by county and year, and irrigated share by county, crop and year (mostly Nebraska 2000-2018)

7. **What the data cannot do:**  
* **Irrigation is only partly covered.** The master has no irrigation column, and the extension is mostly Nebraska 2000-2018. So it can't fully explain why California gets high yields on little rain.  
* **Satellite greenness sees the whole county,** forests and towns included, and gives one value per calendar year. It can explain a yield after the fact, not forecast it before harvest.  
* **It's county averages only.** Nothing is at field level, and nothing comes after 2025\.


8. **Deliverables**  
     
   **Minimum deliverable.** Every team must finish: one named user and decision; one piece of evidence checked on years not used to build it (or an honest statement of why it can't be); a tool the user can use; a 5-minute pitch with a live demo.   
   **Your repo is public.** Never commit API keys or passwords. Keep them in a .env file.  
   **AI use is allowed.** Your README must include an AI disclosure section: tools used, what for, which parts, and how you verified the output. You must be able to explain and change any part of your code during judging.

| When | What you show | Done when |
| ----- | ----- | ----- |
| **Checkpoint 1** Saturday afternoon | Your user, their decision, your proposed solution, and the data you'll use | A mentor can repeat your task back to you |
| **Checkpoint 2** Saturday evening | Data loads and a first version runs | You can show one real result on screen |
| **Final**  Sunday, before pitches | **1\. A working tool:** Streamlit app, notebook or Python app **2\. A GitHub repo:** your code plus short instructions to run it **3\. A pitch and live demo:** about 5 minutes, then 3 minutes of judges' questions | Your user can use the tool without reading your code; someone else can run the repo from its instructions |

**Your pitch must answer four questions:** Who is your user? What do they decide? What evidence did you use? How do you know it works?

**Deadline:** Sunday October 18, 12:00 PM (noon) ET. One submission per team, via the submission form with the full 40-character commit SHA.

* Judges reward a tool that clearly helps its user, not technical complexity for its own sake.

**Judging Rubric:**

| Criterion | Weight | Key Expectation |
| ----- | :---: | ----- |
| C1. Problem Definition & Relevance | 20% | Solve a specific, realistic agricultural decision for a clear and specific stakeholder. |
| C2. Technical Implementation | 10% | Clean, organized code that runs and accounts for data edge cases. |
| C3. Use of Data & Evidence | 20% | Extract insights from data; handle missing values and support claims. |
| C4. Usability & Working Prototype | 15% | Functional, complete tool/notebook running reliably with clear setup instructions. |
| C5. Innovation | 10% | Fresh framing, analytical thinking, or novel insights beyond simple walkthroughs. |
| C6. Demonstration & Presentation | 15% | Clear narrative arc (problem to solution) delivered within the 8-minute limit. |
| C7. Collaboration & Teamwork | 10% | Shared ownership and meaningful participation from all team members. |

 