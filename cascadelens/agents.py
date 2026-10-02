from smolagents import OpenAIModel, ToolCallingAgent

from cascadelens.tools import (
    get_failure_groups,
    get_impacted_tables,
    split_impacted_tables,
    get_pipeline_statuses,
)


def build_triage_agent() -> ToolCallingAgent:
    """Specialist: finds today's failures and how long they have been recurring."""
    return ToolCallingAgent(
        tools=[get_failure_groups],
        model=OpenAIModel(model_id="gpt-4o-mini"),
        name="triage_agent",
        description=(
            "Finds today's failures in a log database. Reports the failed table, "
            "the error, and how many days it has recurred. Give it the database path."
        ),
    )

def build_lineage_agent() -> ToolCallingAgent:
    """Specialist: finds what a failed table affects, then splits it into confirmed and at risk."""
    return ToolCallingAgent(
        tools=[get_impacted_tables, split_impacted_tables],
        model=OpenAIModel(model_id="gpt-4o-mini"),
        name="lineage_agent",
        description=(
            "Works out the impact of a failed table. Give it the database path and the "
            "failed table name. Returns the confirmed impacted tables and the at risk tables."
        ),
    )

def build_orchestrator() -> ToolCallingAgent:
    """Boss agent: reads the pipeline statuses, then delegates to the specialists."""
    return ToolCallingAgent(
        tools=[get_pipeline_statuses],
        model=OpenAIModel(model_id="gpt-4o-mini"),
        managed_agents=[build_triage_agent(), build_lineage_agent()],
        name="orchestrator",
        description="Coordinates the failure investigation.",
    )