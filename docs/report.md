# CascadeLens report

## 1. Problem definition

When a data platform fails overnight, an engineer has to open ingestion, curation and semantic logs separately and work out which failure came first and what it broke. CascadeLens reads the three layers from one SQLite view, finds today's real failures, and lists the tables they affect. It does not guess at facts. Plain Python computes them, and AI agents choose the tools and write the root cause in plain English.

### Use case 1: a clean cascade (clean_cascade.db)

The CRM ingestion fails because a login password expired. Nothing downstream errors, but customer_curation and customer_dal wrote 0 rows. The tool should report one failure at customer_ingestion, list those two tables as confirmed impacted, and list sales_curation and sales_dal as at risk. Inventory must not appear.

### Use case 2: noise and a recurring defect (noisy_recurring.db)

sales_ingestion failed twice and then succeeded on a retry, which is noise. Separately, customer_dal fails every day with the same error. The tool should report one failure (customer_dal) with its recurrence, and not count the recovered retries.

### Use case 3: two failures in one run (ambiguous.db)

Sales has a failed curation script and an empty ingestion load, so the real cause is unclear. Inventory has a separate failure. The tool should report two independent failures, list sales_dal as impacted, and show the empty sales_ingestion load as a warning. It does not decide the Sales cause for the engineer.


## 2. Approach summary

The design rule is "code decides, AI explains". Plain Python reads the logs, works out the pipeline statuses, groups the errors, counts recurrence and follows the lineage between tables. The AI never computes these facts. It chooses which tool to call and writes the root cause sentence.

The flow, in order:

1. main.py checks that the database file exists and starts logging to output/cascadelens.log.
2. It reads the pipeline statuses first. If every pipeline is exactly Healthy, it returns an empty Healthy report and makes no AI call.
3. Otherwise an orchestrator agent runs. It calls get_pipeline_statuses, asks triage_agent for today's failures, and asks lineage_agent, one failed table at a time, for the confirmed and at risk tables.
4. The orchestrator returns one JSON answer. The code validates it with a Pydantic TriageReport and retries once if it is invalid.
5. Only after the agents answer, the code recomputes the facts itself, adds the empty-load warnings, and logs whether the agent's facts match (diff_failures). This check only logs. It never changes the agent's answer.
6. The report is printed as JSON and saved as output/<database name>.md.

The model is OpenAI gpt-4o-mini, used through the smolagents framework. The full diagram is in docs/architecture.md. Prompts and how they changed are in docs/AIUsage.md, section 5.


## 3. Prompt design

The orchestrator gets one task text, built in main.py. Each part of it exists because of a problem I saw in a real run. The full change history is in docs/AIUsage.md, section 5.

| Part of the prompt | Example wording | Why it is there |
|---|---|---|
| A filled example of the answer | A JSON object with database, overall_status, failures and warnings, using placeholder values | The model copies the shape it sees. A bare JSON schema made it copy the schema wrapper into its answer |
| Where to put the answer | "Put one flat JSON object in the single 'answer' argument of final_answer. Do not add a description or properties wrapper." | Once the model spread the keys into final_answer instead of using answer |
| One failure per failed table | "Each failed table is one failure." "Call lineage_agent for one failed table at a time." | ambiguous.db has two failed tables, and one combined failure could not hold both |
| Consequences are not failures | "If a failed table appears in the impacted tables of another failed table, it is a consequence, so do not list it as its own failure." | Stops a downstream table being counted twice |
| Plain root cause | "Write one plain sentence based on the example error. Do not use the signature text." | The model repeated the raw error signature. This is only partly fixed, see the reflection |
| Warnings left empty | "Leave warnings as an empty list." | Model-written warnings were unreliable, so code now builds them |

Two choices go beyond the wording:

- Narrow agents. The orchestrator, triage_agent and lineage_agent each have only their own tools, with a short description of what each agent and tool does. This gave fewer wrong and repeated tool calls than one agent with four tools.
- Verification in code. The prompt cannot guarantee correct facts, so the code retries once on invalid output and compares the answer to its own recomputation with diff_failures.

One lesson from testing: adding "one at a time" to the task text did not stop parallel tool calls. Reading the smolagents source showed that max_tool_threads=1 does.


## 4. Code map

Everything is in the cascadelens folder unless stated.

| File | What it does |
|---|---|
| main.py | Entry point. Checks the database path, sets up logging, runs the status check, starts the orchestrator, validates the answer, runs the code check and saves the report |
| agents.py | Builds the orchestrator, triage_agent and lineage_agent. Holds CountingModel, which adds up tokens inside the model because each agent resets its own counters |
| tools.py | Four smolagents tools that wrap plain Python: get_pipeline_statuses, get_failure_groups, get_impacted_tables, split_impacted_tables |
| analysis.py | Plain Python entry points: analyse, get_statuses, build_failures (the code answer key) and build_warnings |
| reader.py | Reads the all_logs view from the SQLite database into LogRecord objects. It reads nothing else |
| models.py | The LogRecord dataclass, one row of the unified log |
| pipeline_status.py | Picks the latest attempt of each unit, applies the status rule (Healthy, Succeeded with Issues, Partially Failed, Failed) and finds empty loads |
| noise_filter.py | Removes failed attempts that a later attempt recovered, so retries are not counted as failures |
| error_signature.py | Turns an error message into a signature (GUIDs, timestamps and numbers removed) so the same error groups together, and counts recurrence over 7 days |
| lineage.py | Builds the table dependency graph, finds every table below a failed table, splits confirmed from at risk, and groups related failures |
| report.py | The Pydantic report shape, the markdown renderer and diff_failures, which lists facts the agent got wrong |
| try_real.py | The baseline: one agent with all four tools, with the same early exit and the same checks |
| scripts/generate_sample_data.py | Creates the four sample databases and the expected_answers.md answer key |

The tests folder has six files:

- test_analysis: the four sample databases end to end, build_failures, build_warnings, plus check_db_path and parse_report from main.py and diff_failures from report.py
- test_error_signature, test_lineage, test_models, test_noise_filter and test_pipeline_status: one file each for the module of the same name

Not covered by unit tests: agents.py, tools.py, try_real.py and render_markdown. The agent behaviour is checked by real runs and by diff_failures.


## 5. Testing

### Unit tests

`python -m pytest tests -q` ran 46 tests with all passing at the last run. They cover the plain Python parts (status rule, error signatures, noise filter, lineage, build_failures, build_warnings, parse_report and diff_failures). They do not call the AI.

### Sample inputs and manual verification

I ran the tool on three sample databases (run date 2026-10-01) and compared each report by hand with the independent answer key, cascadelens/scripts/data/expected_answers.md.

| Input | What good output looks like | What the tool produced | Result |
|---|---|---|---|
| clean_cascade.db | One failure at customer_ingestion. Confirmed: customer_curation, customer_dal. At risk: sales_curation, sales_dal. No Inventory table | The same facts. The log said all facts match, using 15,674 input tokens. The root cause was a plain sentence about an expired password | Facts match |
| noisy_recurring.db | One failure at customer_dal, recurrence 6 of 7 days. The recovered sales_ingestion retries not counted | One failure at customer_dal, recurrence 6. The log said all facts match, using 15,411 input tokens | Facts match |
| ambiguous.db | Two independent failures: sales_curation (with sales_dal impacted) and inventory_dal. A warning that sales_ingestion loaded 0 rows | The same two failures, sales_dal confirmed impacted, and the sales_ingestion warning | Facts match in this run |

A fourth database, all_healthy.db, must produce an empty Healthy report with no AI call. The log of a real run shows "All pipelines Healthy, skipping the agents" and no agent steps, for both main.py and try_real.py. A unit test checks that analyse finds no failures and that every status is Healthy, but it does not check the early exit itself.

What good output means: the failed tables, the confirmed and at risk tables, the recurrence and the warnings equal what the code computes. The root cause sentence is wording, so I read it for sense but do not score it.

### Repeated runs on ambiguous.db

Because the model is not fully consistent, I ran ambiguous.db 10 times with the multi-agent version and 10 times with the single agent baseline (output/experiment_multi.txt and output/experiment_single.txt). A run counts as fully correct when diff_failures is empty.

| Version | Fully correct runs | Mean input tokens |
|---|---|---|
| Multi-agent (orchestrator and two specialists) | 7 of 10 | 24,557 (range 19,966 to 36,042) |
| Single agent with all four tools | 4 of 10 | 9,878 (range 9,794 to 9,902) |

Multi-agent errors: two runs wrote display names instead of table names, and two runs dropped inventory_dal. Single agent errors: five runs listed sales_dal as confirmed under inventory_dal instead of sales_curation, one dropped inventory_dal, and one also dropped sales_curation.

I chose the multi-agent version for accuracy, at about 2.5 times the tokens. Limits: one database and 10 runs per side. My explanation, that the single agent holds both failures in one context, is a guess I did not verify. The choice must be tested on a larger dataset before it is final. I accept the intermittent errors and document them. The code does not override the agent.

### A note on time

Log timestamps are UTC. The run date 2026-10-01 is the latest date in each database.


## 6. Reflection

### What worked

- Splitting the work into "code decides, AI explains". Plain Python computes the facts, so a wrong agent answer can be detected and measured with diff_failures.
- Checking the agent against the code, not trusting it. The answer key in expected_answers.md is independent of the agents.
- Stopping early when every pipeline is Healthy. A healthy database costs no tokens.
- Building one small piece at a time, and running pytest and a real run after each piece.
- Counting tokens inside the model (CountingModel). Each agent resets its own counters on every run, so the step lines cannot be summed. My first token tables were wrong for this reason, and I discarded them.

### Why an agent at all, if code computes everything

The code owns the facts. The agent reads the error text, writes a plain English root cause, and routes the tool calls, which matters more as the tool set grows. I measured it against a non-agent baseline (try_real.py, a single agent) and against the code as the answer key.

### Where AI was wrong, and how I found out

- Its first early-exit rule missed "Succeeded with Issues". I corrected it.
- Adding "one at a time" to the prompt did not stop parallel tool calls. Reading the smolagents source showed that max_tool_threads=1 does.
- The first answer key described confidence levels, competing hypotheses and routing that the tool never built. I found this by comparing the key with a real report, and I changed the key to match the tool.

### Known limits

- Root cause wording is not enforced. clean_cascade gave a plain sentence, but noisy_recurring repeated the raw error text.
- The agents are intermittent. On ambiguous.db the multi-agent version was fully correct in 7 of 10 runs. The comparison used one database and 10 runs per side.
- The orchestrator sometimes calls lineage_agent twice for one failed table, and reads the statuses a second time itself. This is cheap redundancy.
- A database whose only issue is a recovered retry now starts the agents. That is the cost of the Healthy-only rule.
- I did not retest the unhealthy path of try_real.py after my last edit. The retry-once branch was never exercised in a real run.
- Each tool recomputes analyse(). The early exit is duplicated in main.py and try_real.py. I skipped per-agent log labels.
- Two failures with a shared cause but no lineage path are reported as independent. Recurrence is counted by error signature, not by table.
- The core code is slightly above 500 lines, because I removed dead code instead of compressing working code.
- The tool reports facts only. It gives no confidence level, no competing hypotheses and no escalation to a human. For Sales in ambiguous.db it names sales_curation and warns about the empty load, but does not weigh the two causes.

### What I would improve

1. Compute a confidence level in code (for example, low when an ingestion table loaded 0 rows and its curation table also failed), and add it to the report.
2. Test on a larger dataset before the final choice between multi-agent and single agent.
3. Enforce the root cause wording, and run the retry branch on purpose.
4. Add per-agent log labels, and remove the duplicated early-exit logic.

### A note on time

Log timestamps are UTC. My own clock is Vancouver, UTC-7.