import json
import sys

from smolagents import OpenAIModel, ToolCallingAgent

from cascadelens.analysis import analyse, build_failures, build_warnings
from cascadelens.reader import read_logs
from cascadelens.report import TriageReport
from cascadelens.tools import (
    get_failure_groups,
    get_impacted_tables,
    get_pipeline_statuses,
    split_impacted_tables,
)


def triage_single(db_path: str) -> TriageReport:
    """Baseline: one agent with all four tools, plus the same early exit and validation."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    analysis, records = analyse(db_path), read_logs(db_path)
    warnings = build_warnings(analysis, records, build_failures(analysis, records))
    broken = any(s in ("Failed", "Partially Failed") for s in statuses.values())
    if not broken:
        status = "Unhealthy" if warnings else "Healthy"
        return TriageReport(database=db_path, overall_status=status, warnings=warnings)

    example = {
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
        "Check the pipeline statuses, find today's failures, and for each failed table "
        "find the confirmed and at risk tables. "
        "If a failed table is downstream of another failed table, it is a consequence, "
        "not its own failure. "
        "For root_cause, write one plain sentence based on the example error. "
        "Leave warnings as an empty list. "
        "Call final_answer alone, after you have seen all tool results. "
        "Put one flat JSON object in the single 'answer' argument of final_answer, "
        "with the real values you found. Do not add a description or properties wrapper. "
        f"Shape: {json.dumps(example)}"
    )
    agent = ToolCallingAgent(
        tools=[get_pipeline_statuses, get_failure_groups, get_impacted_tables, split_impacted_tables],
        model=OpenAIModel(model_id="gpt-4o-mini"),
    )
    raw = agent.run(task)
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(text)
    report = TriageReport.model_validate(data)
    report.warnings = warnings
    return report


if __name__ == "__main__":
    print(triage_single(sys.argv[1]).model_dump_json(indent=2))