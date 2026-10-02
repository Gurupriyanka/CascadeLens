import json
import sys

from cascadelens.agents import TOKENS, build_orchestrator
from cascadelens.tools import get_pipeline_statuses
from pathlib import Path
from cascadelens.report import TriageReport, diff_failures, render_markdown
from cascadelens.analysis import analyse, build_failures, build_warnings
from cascadelens.reader import read_logs
from pydantic import ValidationError
import logging
log = logging.getLogger("cascadelens")
log.setLevel(logging.INFO)

def check_db_path(db_path: str) -> None:
    """Stop with a clear message if the database file does not exist."""
    if not Path(db_path).is_file():
        sys.exit(f"Error: database file not found: {db_path}")

def setup_logging() -> None:
    """Log to the terminal and to output/cascadelens.log."""
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(out_dir / "cascadelens.log")],
    )


def parse_report(raw) -> TriageReport:
    """Turn the agent's answer into a validated report. Raises on bad JSON or a wrong shape."""
    # The model may return a dict, or text wrapped in a markdown code fence.
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(text)
    return TriageReport.model_validate(data)

def triage(db_path: str) -> TriageReport:
    """Check the statuses first. Stop early when every pipeline is Healthy."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    log.info("Pipeline statuses: %s", statuses)
    broken = any(s != "Healthy" for s in statuses.values())
    if not broken:
        log.info("All pipelines Healthy, skipping the agents")
        return TriageReport(database=db_path, overall_status="Healthy")

    example_schema = {
        "database": db_path,
        "overall_status": "Unhealthy",
        "failures": [
            {
                "failed_table": "<table name>",
                "root_cause": "<one sentence>",
                "recurrence_days": 0,
                "confirmed_impacted": ["<table name>"],
                "at_risk": ["<table name>"],
            }
        ],
        "warnings": [],
    }
    task = (
        f"Investigate the database at {db_path}. "
        "First check the pipeline statuses. "
        "Then ask triage_agent for today's failures. "
        "Each failed table is one failure. "
        "Call lineage_agent for one failed table at a time, and wait for its answer before calling it for the next failed table. "
        "For each failed table, ask lineage_agent separately for the confirmed and at risk tables, "
        "giving it the database path and that one failed table. "
        "If a failed table appears in the impacted tables of another failed table, "
        "it is a consequence, so do not list it as its own failure. "
        "For root_cause, write one plain sentence based on the example error. "
        "Do not use the signature text. Leave warnings as an empty list. "
        "Call final_answer alone, after you have seen all results. "
        "Put one flat JSON object in the single 'answer' argument of final_answer, "
        "with the real values you found. Do not add a description or properties wrapper. "
        f"Shape: {json.dumps(example_schema)}"
    )

    # Retry once if the model returns bad JSON or the wrong shape.
    # A new orchestrator is built per attempt so no memory carries over.
    report = None
    for attempt in (1, 2):
        log.info("Pipelines not all Healthy, starting the orchestrator agent (attempt %d)", attempt)
        raw = build_orchestrator().run(task)
        log.info("Agent finished, validating the answer")
        try:
            report = parse_report(raw)
            break
        except (json.JSONDecodeError, ValidationError) as err:
            log.warning("Invalid model output on attempt %d: %s", attempt, err)
    if report is None:
        raise RuntimeError("The agent did not return a valid report after 2 attempts")

    # The code computes its answer key only now, after the agents have answered.
    analysis, records = analyse(db_path), read_logs(db_path)
    expected = build_failures(analysis, records)
    report.warnings = build_warnings(analysis, records, expected)
    log.info("Code found %d warning(s)", len(report.warnings))
    log.info("Report valid with %d failure(s)", len(report.failures))
    log.info("Check against code: %s", diff_failures(expected, report.failures) or "all facts match")
    log.info("Total tokens used: input %d, output %d", TOKENS["input"], TOKENS["output"])
    return report


def main() -> None:
    setup_logging()
    db_path = sys.argv[1]
    check_db_path(db_path)
    log.info("Starting triage for %s", db_path)
    try:
        report = triage(db_path)
    except Exception as err:
        log.exception("Triage failed")  # writes the full traceback to the log file
        sys.exit(f"Error: triage failed: {err}")
    print(report.model_dump_json(indent=2))

    # Save the markdown report as output/<database name>.md
    out_file = Path("output") / f"{Path(db_path).stem}.md"
    out_file.write_text(render_markdown(report))
    print(f"Report saved to {out_file}")
    log.info("Report saved to %s", out_file)


if __name__ == "__main__":
    main()