# AI usage log

How AI tools were used to build CascadeLens.

## Tools used

- Claude (problem scoping, design review, code review, prompt drafting, diagram and documentation drafting)
- OpenAI gpt-4o-mini through the smolagents framework (runtime: orchestrator, triage_agent and lineage_agent)

## 1. Problem definition

| # | My prompt (reconstructed, paraphrased) | What Claude did | What I decided |
|---|---|---|---|
| 1 | "I have to build a hands-on AI project. Compare Smart Backlog Assistant, a PR review tool and ingestion failure triage for me." | Compared the three ideas on fit, effort and how well AI is used | Chose ingestion failure triage because it fits my data engineering background |
| 2 | "Which logs and layers should the tool read, and how do I tell that one failure caused another?" | Suggested three layers (ingestion, curation, semantic) and lineage matching on source and target table names | Kept the three layers and the lineage rule, using SQLite logs with a unified all_logs view |
| 3 | "What should the output show, and what are realistic use cases?" | Proposed a per-pipeline status board, root cause with impacted tables, and recurrence | Kept the status board, failures with confirmed and at risk tables, and a recurrence count |

## 2. Solution design

- Used Claude to review the architecture: Python for deterministic facts, LLM agents for judgment and writing.
- Output design reduced from many outputs to one report, saved as a markdown file (output/<database name>.md). It shows the overall status and, when something failed, the failures with their impacted tables and any empty-load warnings. The pipeline statuses are logged and available through the get_pipeline_statuses tool.
- Agent design went from one agent with many tools to an orchestrator and two specialists (triage_agent and lineage_agent), each with only its own tools.

## 3. Implementation

Claude helped me build the code one small piece at a time: the plain Python analysis, the smolagents tool wrappers, the three agents, the Pydantic report, error handling and logging. After each piece I ran pytest and a real run, and I checked the agents' answers against the plain Python result.

### Decisions made from AI proposals
| AI proposed | What I decided | Why |
|---|---|---|
| Skip the agents only when no pipeline is Failed or Partially Failed | I required Succeeded with Issues to count as well | A recovered retry or an empty load still needs a look. This also made the early exit simpler, because it needs no analysis |
| Run the full analysis before the status check | I asked for the status check first, and the heavy analysis only after the agents answer | The first step should read only what it needs, and the agents should get facts through their tools |
| Keep one analyse() that returns everything | I asked to split it so statuses are computed alone (get_statuses) | The first check should not run signatures, recurrence and lineage. Claude checked the callers and tests with grep before the change |
| Let code override wrong agent facts | I chose to accept the intermittent multi-agent errors and document them. No code override | The experiment should show what the agents really do. The check only logs |
| Pick multi-agent or single agent from a few runs | I ran 10 runs of each and reported the mixed result. I will test on a larger dataset before a final choice | 7 of 10 correct for multi-agent against 4 of 10 for the single agent, at about 2.5 times the tokens. Small sample, one database |
| Earlier token tables summed from the step lines | I discarded them as wrong and counted tokens inside the model (CountingModel) | The step lines show a running total, and each agent resets its counters on every run |
| "One at a time" in the task text to stop parallel calls | I found by reading the smolagents source that max_tool_threads=1 stops it | The wording alone did not work |
| Keep unused code | I removed the unused enums and fake_model.py, and did not compress working code | Less code to explain. The core is slightly above 500 lines for this reason |
| Per-agent labels in the log lines | I skipped them to keep things simple, and listed them under what I would improve | Identified as areas of improvement |


## 4. Prompt iterations (sample development prompts)

| # | Area | My prompt (short) | What Claude did | What I changed or verified |
|---|---|---|---|---|
| 1 | Code | "can we split the analyse to two? one part just finds the statuses and is called first, the other is called by the tools" | Searched the code and tests with grep for every use of statuses, asked to see the test file, then gave four small steps: add get_statuses, switch the tool, switch the tests, remove the field | I ran pytest after every step (46 passed each time) and a real run on all_healthy.db |
| 2 | Code | "Failed, Partially Failed should also include Succeeded with Issues" | Its first early-exit rule missed this case. It changed the rule to "skip the agents only if every pipeline is exactly Healthy", which also removed the analysis from the early exit | My correction. Cost: a database with only a recovered retry now starts the agents |
| 3 | Code | "make the edit in main.py first" (run the status check first, analysis only after the agents) | Moved analyse, build_failures and build_warnings to after the agent answer, so they act as a check on the agents | Ran noisy_recurring.db: "Check against code: all facts match", and the token total (15,411) equals the sum of the three agents' last step lines |
| 4 | Code | "can you update the triage function in main.py and try_real.py" | Gave the full triage() for main.py, and for try_real.py asked me to paste the file rather than write it from memory | I pasted the file. Both versions now use the same early exit and the same order, so the single agent baseline stays comparable |
| 5 | Architecture diagram | "I will give you all files so that you can design the diagram correctly" | Drew a first Mermaid diagram from the pasted code, then revised it over many rounds | I corrected it from the real database (DiLog, FwkCurLog and the all_logs view), asked for numbered steps and one-way agent arrows, and replaced confusing wording with "Verify facts after the AI answers" |

## 5. Prompt refining

How I improved the runtime prompts for the orchestrator, triage_agent and lineage_agent (the prompts that gpt-4o-mini receives). Each row is one change, tied to a problem I saw in a real run. The prompts I wrote to Claude during development are in section 4.

| # | Agent | Problem I saw in a run | Prompt before (short) | Prompt after (short) | Result |
|---|---|---|---|---|---|
| 1 | Single agent, then split into orchestrator, triage_agent, lineage_agent | One agent with 4 tools made wrong and repeated tool calls | One agent, vague tool docstrings | Tighter docstrings that say when to call the tool and what it returns; three agents, each with only its own tools | Fewer wrong and repeated calls |
| 2 | Orchestrator | The model copied the JSON schema wrapper into its answer, and once spread the keys into `final_answer` instead of using `answer` | A JSON schema in the task text | A filled example, "Do not add a description or properties wrapper", "single 'answer' argument of final_answer" | One flat JSON object that validates with `TriageReport` |
| 3 | Orchestrator | `ambiguous.db` has two failed tables, and the one-failure shape could not hold both, or a downstream table was reported as its own failure | One `failed_table`, `root_cause` and `at_risk` at top level | A `failures` list, "Each failed table is one failure", "one failed table at a time", "if a failed table appears in the impacted tables of another failed table, it is a consequence" | Independent failures are listed separately and cascaded ones are not double counted |
| 4 | Orchestrator | `root_cause` repeated the raw signature text, and model-written warnings were unreliable | Free choice of wording, model asked to fill warnings | "One plain sentence based on the example error. Do not use the signature text. Leave warnings as an empty list." | Readable root causes, and warnings now come from code (`build_warnings`) |
| 5 | Orchestrator | Occasional invalid JSON or a wrong shape from the model, and no way to know whether the facts were right | A single run, answer trusted as is | Retry once with a fresh orchestrator, then compare the report to the code answer key with `diff_failures` and log the result | Bad output is caught, and every run logs whether the facts match the plain Python baseline |

### What I learned about prompting

- A filled example works better than a schema, because the model copies the shape it sees.
- Narrow agents, tight docstrings and explicit rules for edge cases (several failures, consequences) mattered more than longer instructions.
- Facts the code can compute (warnings, the answer key) should not be left to the model. Use the model for wording and routing, and use code to verify.
