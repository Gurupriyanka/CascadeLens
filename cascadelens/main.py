import json
import sys

from cascadelens.agents import build_orchestrator
from cascadelens.tools import get_pipeline_statuses
from pathlib import Path
from cascadelens.report import TriageReport, render_markdown
from cascadelens.analysis import analyse, build_failures, build_warnings
from cascadelens.reader import read_logs

def triage(db_path: str) -> TriageReport:
    """Check the statuses first. Stop early when everything is Healthy."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    analysis, records = analyse(db_path), read_logs(db_path)
    warnings = build_warnings(analysis, records, build_failures(analysis, records))
    broken = any(s in ("Failed", "Partially Failed") for s in statuses.values())
    if not broken:
        status = "Unhealthy" if warnings else "Healthy"
        return TriageReport(database=db_path, overall_status=status, warnings=warnings)

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
    raw = build_orchestrator().run(task)
    # The model may return a dict, or text wrapped in a markdown code fence.
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(text)
    report = TriageReport.model_validate(data)
    report.warnings = warnings
    return report


def main() -> None:
    db_path = sys.argv[1]
    report = triage(db_path)
    print(report.model_dump_json(indent=2))

    # Save the markdown report as output/<database name>.md
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{Path(db_path).stem}.md"
    out_file.write_text(render_markdown(report))
    print(f"Report saved to {out_file}")


if __name__ == "__main__":
    main()