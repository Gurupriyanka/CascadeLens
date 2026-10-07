"""The three smolagents agents: an orchestrator and two specialists.

Each agent gets only its own tools. Python computes the facts inside the tools,
and the agents choose which tool to call and write the root cause wording.
"""
from smolagents import OpenAIModel, ToolCallingAgent

from cascadelens.tools import (
    get_failure_groups,
    get_impacted_tables,
    get_pipeline_statuses,
    split_impacted_tables,
)

# Running total of tokens across every model call, for all agents in one run.
# It is never reset, so it is correct for one run per process, as main.py does.
TOKENS = {"input": 0, "output": 0}


class CountingModel(OpenAIModel):
    """OpenAIModel that adds up token usage on every call.

    Each agent resets its own counters on every run, so counting inside the
    model is the only way to get one total across the orchestrator and both
    sub-agents.
    """

    def generate(self, *args, **kwargs):
        message = super().generate(*args, **kwargs)
        # token_usage can be missing, so only count when the API reported it
        if message.token_usage is not None:
            TOKENS["input"] += message.token_usage.input_tokens
            TOKENS["output"] += message.token_usage.output_tokens
        return message


# All three agents use the same small model, so any difference in a run comes
# from the prompt and the tool set, not from the model.
def build_triage_agent() -> ToolCallingAgent:
    """Specialist: finds today's failures and how long they have been recurring."""
    return ToolCallingAgent(
        tools=[get_failure_groups],
        model=CountingModel(model_id="gpt-4o-mini"),
        name="triage_agent",
        # The description is what the orchestrator reads when it decides to call this agent
        description=(
            "Finds today's failures in a log database. Reports the failed table, "
            "the error, and how many days it has recurred. Give it the database path."
        ),
    )


def build_lineage_agent() -> ToolCallingAgent:
    """Specialist: finds what a failed table affects, then splits it into confirmed and at risk."""
    return ToolCallingAgent(
        tools=[get_impacted_tables, split_impacted_tables],
        model=CountingModel(model_id="gpt-4o-mini"),
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
        model=CountingModel(model_id="gpt-4o-mini"),
        managed_agents=[build_triage_agent(), build_lineage_agent()],
        # One tool call at a time. Asking for this in the prompt did not stop
        # parallel calls, this setting does.
        max_tool_threads=1,
        name="orchestrator",
        description="Coordinates the failure investigation.",
    )
