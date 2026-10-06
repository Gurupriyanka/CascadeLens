# CascadeLens: cross-layer failure triage

Architecture diagram. Blue boxes are plain Python, which computes the facts. Orange hexagons are AI agents (gpt-4o-mini). Grey boxes are the tools the agents call. Green is the final output.

![CascadeLens: cross-layer failure triage architecture](Architecture_Diagram_CascadeLens.png)

```mermaid
---
title: CascadeLens, cross-layer failure triage
---
flowchart LR
    U["User runs<br>python -m cascadelens.main db_path"] --> CK["main.py<br>check_db_path, setup_logging"]
    CK -.->|"logs every stage"| LOG[/"Run log<br>output/cascadelens.log<br>timestamped steps, tool calls, token totals"/]
    DI[("DiLog table<br>ingestion logs, with attempt")] --> VW[("all_logs view<br>UNION ALL, adds layer:<br>ingestion, curation, semantic")]
    FW[("FwkCurLog table<br>curation and semantic logs,<br>with reference_source_name")] --> VW
    CK --> M1["main.py first check<br>calls get_pipeline_statuses<br>Uses: get_statuses"]
    M1 --> RL["read_logs<br>reads only the all_logs view"]
    RL <--> VW
    RL --> GATE{"Are all pipelines<br>exactly Healthy?"}
    GATE -->|"A. Yes"| HEALTHY["Empty Healthy report<br>no AI call, no analysis"]
    GATE -->|"B. No: Failed, Partially Failed<br>or Succeeded with Issues"| O{{"<b>orchestrator agent</b><br>Actions: delegates to the specialists<br>and writes the final answer"}}

    O -->|"1. calls tool"| T1[["get_pipeline_statuses<br>Purpose: health of each pipeline<br>Uses: get_statuses"]]
    O -->|"2. delegates"| TA{{"<b>triage_agent</b><br>Actions: finds today's failures<br>and how long they recurred"}}
    TA -->|"2a. calls tool"| T2[["get_failure_groups<br>Purpose: failures grouped by signature<br>Uses: analyse"]]
    O -->|"3. delegates, for each failed table<br>one at a time"| LA{{"<b>lineage_agent</b><br>Actions: finds what a failed table affects,<br>splits confirmed and at risk"}}
    LA -->|"3a. calls tool first"| T3[["get_impacted_tables<br>Purpose: tables downstream of a failure<br>Uses: build_downstream, find_impacted"]]
    LA -->|"3b. calls tool second"| T4[["split_impacted_tables<br>Purpose: confirmed vs at risk<br>Uses: split_impacted"]]
    T1 <--> VW
    T2 <--> VW
    T3 <--> VW
    T4 <--> VW

    O -->|"4. final JSON answer"| PARSE["parse_report<br>JSON to Pydantic TriageReport<br>retry once if invalid"]
    PARSE --> CODE["Verify facts after the AI answers<br>code recomputes the facts from the database"]
    CODE <--> VW
    CODE --> FILL["Add warnings, log the result<br>of the fact check (diff_failures)"]
    HEALTHY --> OUT(["FINAL OUTPUT: triage report<br>printed as JSON and saved as<br>output/db_name.md"])
    FILL --> OUT

    classDef ai stroke:#e65100,fill:#fff3e0
    classDef tool stroke:#6b7280,fill:#f3f4f6
    classDef code stroke:#1565c0,fill:#e3f2fd
    classDef data stroke:#38bdf8,fill:#f0f9ff
    classDef final stroke:#2e7d32,stroke-width:3px,fill:#c8e6c9,color:#1b5e20
    classDef logfile stroke:#7b1fa2,fill:#f3e5f5
    class O,TA,LA ai
    class T1,T2,T3,T4 tool
    class CK,M1,RL,HEALTHY,PARSE,CODE,FILL code
    class DI,FW,VW data
    class OUT final
    class LOG logfile
```

## Explanation of the diagram

**Data**
- `DiLog` holds ingestion logs. `FwkCurLog` holds curation and semantic logs.
- The `all_logs` view joins them and adds a `layer` value (ingestion, curation or semantic). The code reads only this view.

**Before any AI (blue boxes)**
- `main.py` checks the database path and sets up logging to `output/cascadelens.log`.
- `get_statuses` reads the logs and works out the health of each pipeline.
- Branch A: if every pipeline is exactly Healthy, the program prints an empty Healthy report. No AI call is made.
- Branch B: if any pipeline is Failed, Partially Failed or Succeeded with Issues, the orchestrator agent starts.

**The AI agents (orange hexagons)**
- Step 1: the orchestrator calls `get_pipeline_statuses`.
- Step 2: it delegates to `triage_agent`, which calls `get_failure_groups` (2a) to find today's failures and how long each has recurred.
- Step 3: for each failed table, one at a time, it delegates to `lineage_agent`, which calls `get_impacted_tables` (3a) and then `split_impacted_tables` (3b). The result is the confirmed impacted tables and the at risk tables.
- Step 4: the orchestrator writes the final JSON answer, including a plain-English root cause for each failure.
- Every agent returns its answer to whoever called it. Each tool runs plain Python and reads the database.

**After the AI answers (blue boxes)**
- `parse_report` turns the JSON into a Pydantic `TriageReport`. If the answer is invalid, it retries once.
- Code verifies the facts: it recomputes them from the database and logs whether the agent's facts match (`diff_failures`). The check only logs. It never changes the agent's answer.
- Code adds the empty-load warnings to the report.

**Output (green)**
- The triage report is printed as JSON and saved as `output/<db name>.md`.

## Where AI is used

- Only the three orange agents use the model. Code decides the facts. The AI chooses which tools to call and writes the root cause wording.