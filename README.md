# CascadeLens

Cross-layer failure triage for data pipeline logs (ingestion, curation and semantic layers, stored in SQLite). Plain Python computes the facts: pipeline statuses, today's failures, recurrence and the tables downstream of each failure. AI agents (OpenAI gpt-4o-mini through smolagents) choose which tools to call and write the root cause in plain English. After the agents answer, the code recomputes the facts and logs whether they match.

All sample data is synthetic.

## Setup

Python 3.10 or newer (tested on 3.14).

```bash
pip install -e ".[dev]"
export OPENAI_API_KEY=your-key-here
```

In GitHub Codespaces, add OPENAI_API_KEY as a Codespaces secret instead of exporting it. There is no .env file.
If OPENAI_API_KEY is not set the tool stops with a Missing credentials error; the healthy database works without a key.

## Run

```bash
python -m cascadelens.main cascadelens/scripts/data/clean_cascade.db
```

The report is printed as JSON and saved as `output/<database name>.md`. The run log is `output/cascadelens.log`.

Sample databases are in `cascadelens/scripts/data/`: all_healthy.db, clean_cascade.db, noisy_recurring.db and ambiguous.db. Their run date is 2026-10-01. The expected results are in `cascadelens/scripts/data/expected_answers.md`.

Cost: all_healthy.db makes no AI call and costs nothing. The other three databases start the agents and used roughly 15,000 to 36,000 input tokens per run in my tests.

Baseline, for testing and comparison only (one agent with all four tools):

```bash
python -m cascadelens.try_real cascadelens/scripts/data/ambiguous.db
```

## Tests

```bash
python -m pytest tests -q
```

The tests cover the plain Python parts and do not call the AI.

## Notes

- Log timestamps are UTC. The Codespace clock is also UTC.

## Code size

Core code (cascadelens/*.py without try_real.py): 540 lines. try_real.py: 83 lines. Sample data generator: 325 lines. Counted without blank lines, comment lines and docstrings.

## Documentation

- [docs/report.md](docs/report.md): problem, approach, prompt design, code map, testing and reflection
- [docs/architecture.md](docs/architecture.md): architecture diagram (PNG and Mermaid)
- [docs/AIUsage.md](docs/AIUsage.md): AI usage log and prompt iterations