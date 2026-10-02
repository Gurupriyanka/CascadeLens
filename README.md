# CascadeLens

AI-assisted triage of data pipeline failures across the ingestion, curation, and semantic layers. CascadeLens groups related failures, traces cascades through table lineage, and produces one status per pipeline plus prioritized incidents with suggested fixes.

All sample data in this repo is synthetic.

## Problem

TODO: 3 to 5 sentences. Hundreds of raw log rows, many downstream failures caused by one upstream problem, engineers chasing symptoms.

## Use cases

1. Shared root cause: many failures across pipelines that trace to one upstream issue.
2. Cross-layer cascade: an ingestion failure that breaks curation and then the semantic layer.
3. Recurring failure: the same error repeating across days, which needs a permanent fix, not another retry.

## Architecture

TODO: add the architecture diagram (docs/architecture.png) and the route diagram (docs/routes.png).

Where AI is used: TODO (Analyst agent with tools, Reporter agent). Where Python is used: TODO (noise filter, grouping, lineage graph, status rules).

## Setup

GitHub Codespaces: open the repo in a codespace and add `OPENAI_API_KEY` as a Codespaces secret.

Local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=your-key-here
```

## Run

```bash
python generate_sample_data.py
python main.py --db data/scenario_1_cascade.db --date YYYY-MM-DD
```

Outputs are written to `output/`: a Markdown report, a JSON result, and a run log.

## Sample scenarios

| File | Situation | Expected result |
|---|---|---|
| scenario_0_healthy.db | Nothing failed | TODO |
| scenario_1_cascade.db | Ingestion failure cascades to curation and semantic | TODO |
| scenario_2_noisy.db | Recurring error plus known noise and skipped runs | TODO |
| scenario_3_ambiguous.db | Vague, unclassifiable errors | TODO |

## Testing approach

TODO: expected vs actual table, number of runs per scenario, what "good output" means.

## Prompt design

TODO: system role, structured output schema, "say unknown instead of guessing" rule, evidence requirement, one before/after prompt iteration.

## Reflection

TODO: what worked, what to improve.

## Future enhancements

- "Not run" detection using an expected-pipelines list
- Live SQL reader against the log tables instead of `.db` files
- Draft tickets pushed to Jira after human approval
- Slow-run trend detection across days
- Chat and results-table writers for production use

## Code size

Core solution: TODO lines. Sample data generator: TODO lines.

## AI usage

See [AI_USAGE.md](AI_USAGE.md).

## Architecture
orchestrator_agent
   tools: get_pipeline_statuses
   managed agents: triage_agent, lineage_agent

   triage_agent
      tools: get_failure_groups

   lineage_agent
      tools: get_impacted_tables, split_impacted_tables
