import json
import sys

from smolagents import OpenAIModel, ToolCallingAgent

from cascadelens.tools import (
    get_failure_groups,
    get_impacted_tables,
    get_pipeline_statuses,
    split_impacted_tables,
)


def triage(db_path: str) -> str:
    """Check the statuses first. Stop early when everything is Healthy."""
    statuses = json.loads(get_pipeline_statuses(db_path))
    if all(status == "Healthy" for status in statuses.values()):
        return "All pipelines are Healthy. No failures, no impact."

    agent = ToolCallingAgent(
        tools=[
            get_pipeline_statuses,
            get_failure_groups,
            get_impacted_tables,
            split_impacted_tables,
        ],
        model=OpenAIModel(model_id="gpt-4o-mini"),
    )
    task = (
        f"Use the database at {db_path}. "
        "Find the root cause of today's failure and which tables are confirmed impacted or at risk. "
        "Call the analysis tools first and read their results. "
        "Call final_answer alone, in a separate step, only after you have seen all tool results."
    )
    return str(agent.run(task))


def main() -> None:
    print(triage(sys.argv[1]))


if __name__ == "__main__":
    main()