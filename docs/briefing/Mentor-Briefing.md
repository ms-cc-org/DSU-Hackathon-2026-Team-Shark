Everything in the student briefing applies to mentors as well. 

**Mentors are not tech support.** Mentors help students think clearly; they don't write the team's code. If a team is stuck on one bug for more than 20 minutes, move them to a simpler approach so they have something to present. If stuck technically, point them to the starter notebook or data dictionary, if stuck conceptually, ask questions.

**Failure modes:** 

* **Problem definition.** If students are brainstorming after hour 3, push them to commit to an idea. “Pick an idea you can finish in time, not the coolest one. Who is the user and what decision do they make?”.  
* **Explore first, build second.** Watch for teams building an app layout or a model before they've looked at what's in the data and what's missing.  
* **Thin data, big claims.** If a team is drawing conclusions from 10 counties, one year or one crop, ask: “How many rows do you have for that filter? Run a cross-tab.”  
* **Last minute.** One valuable thing: “Stop adding features. Make what you have work, practice your presentation”. 

**What judges reward:** The two criteria at 20% each are *problem relevance* and *use of data*. Not a fancy model or technical complexity. A team who clearly names their user, asks specific questions and backs claims with evidence, not just charts of the data, will outscore a team with an unexplained random forest.

**Checkpoints:**

* **Saturday afternoon:** Does the team have a user, a decision, and data to support their approach?   
* **Saturday evening:** Is data loaded and is something working? A chart, filtered table or a prototype tab. If not, help them unblock. If they’re blocked on scope, help them cut it down.  
* **Sunday morning:** Can the team demonstrate input → analysis → recommendation? If not, help them cut to the one path that works.

**Data pitfalls to catch:**

* fips read as a number: joins return zero rows with no error.  
* Analysing rows whose yield\_status isn't "reported".  
* Winter wheat's year is the harvest year; its season starts the previous September.  
* Using master season totals, acres\_harvested, or the all-years yield\_anomaly\_pct / precip\_anomaly\_pct for an August 1 decision (leakage).  
* np.isnan on the Int64 columns from pd.read\_parquet misses missing values; use load\_master().  
* Conclusions from thin groups (California, Delaware, sorghum, wheat outside Nebraska): run a cross-tab first.

