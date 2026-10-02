import json
import sys

from cascadelens.agents import build_orchestrator
from cascadelens.tools import get_pipeline_statuses


def triage(db_path: str) -> str:
    """Check the statuses first. Stop early when everything is Healthy."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    if all(status == "Healthy" for status in statuses.values()):
        return "All pipelines are Healthy. No failures, no impact."

    task = (
        f"Investigate the database at {db_path}. "
        "First check the pipeline statuses. "
        "Then ask triage_agent for the failed table and the error. "
        "Then ask lineage_agent for the confirmed and at risk tables, "
        "giving it the database path and the failed table. "
        "Call final_answer alone, after you have seen all results."
    )
    return str(build_orchestrator().run(task))


def main() -> None:
    print(triage(sys.argv[1]))


if __name__ == "__main__":
    main()