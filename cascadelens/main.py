import json
import sys

from cascadelens.agents import build_orchestrator
from cascadelens.report import TriageReport
from cascadelens.tools import get_pipeline_statuses


def triage(db_path: str) -> TriageReport:
    """Check the statuses first. Stop early when everything is Healthy."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    if all(status == "Healthy" for status in statuses.values()):
        return TriageReport(database=db_path, overall_status="Healthy", root_cause="None")

    example_schema =  {
        "database": db_path,
        "overall_status": "Unhealthy",
        "root_cause": "<one sentence>",
        "failed_table": "<table name>",
        "recurrence_days": 0,
        "confirmed_impacted": ["<table name>"],
        "at_risk": ["<table name>"],
    }
    task = (
        f"Investigate the database at {db_path}. "
        "First check the pipeline statuses. "
        "Then ask triage_agent for the failed table, the error and the recurrence days. "
        "Then ask lineage_agent for the confirmed and at risk tables, "
        "giving it the database path and the failed table. "
        "Call final_answer alone, after you have seen all results. "
        "Put one flat JSON object in the single 'answer' argument of final_answer, with exactly "
        "these keys and the real values you found. Do not add a description or properties wrapper. "
        f"Shape: {json.dumps(example_schema)}"
    )
    raw = build_orchestrator().run(task)
    # The model may return a dict, or text wrapped in a markdown code fence.
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(text)
    return TriageReport.model_validate(data)


def main() -> None:
    print(triage(sys.argv[1]).model_dump_json(indent=2))


if __name__ == "__main__":
    main()