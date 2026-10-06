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

## Run

```bash
python -m cascadelens.main cascadelens/scripts/data/clean_cascade.db
```

The report is printed as JSON and saved as `output/<database name>.md`. The run log is `output/cascadelens.log`.

Sample databases are in `cascadelens/scripts/data/`: all_healthy.db, clean_cascade.db, noisy_recurring.db and ambiguous.db. Their run date is 2026-10-01. The expected results are in `cascadelens/scripts/data/expected_answers.md`.

Cost: all_healthy.db makes no AI call and costs nothing. The other three databases start the agents and used roughly 15,000 to 36,000 input tokens per run in my tests.

Baseline (one agent with all four tools, for comparison):

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
- The tool reports facts only. It gives no confidence level and does not escalate to a human. See the reflection in docs/report.md.

## Code size

Core code (cascadelens/*.py without try_real.py): 579 lines. try_real.py: 84 lines. Sample data generator: 357 lines. Counted without blank lines and lines that start with #. Docstring lines are included.

## Documentation

- [docs/report.md](docs/report.md): problem, approach, prompt design, code map, testing and reflection
- [docs/architecture.md](docs/architecture.md): architecture diagram (PNG and Mermaid)
- [docs/AIUsage.md](docs/AIUsage.md): AI usage log and prompt iterations