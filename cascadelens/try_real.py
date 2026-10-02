from smolagents import OpenAIModel, ToolCallingAgent
from cascadelens.tools import (
    get_failure_groups,
    get_impacted_tables,
    get_pipeline_statuses,
    split_impacted_tables,
)

# Model name is a placeholder: use any model your OpenAI account can call.
model = OpenAIModel(model_id="gpt-4o-mini")

agent = ToolCallingAgent(
    tools=[
        get_pipeline_statuses,
        get_failure_groups,
        get_impacted_tables,
        split_impacted_tables,
    ],
    model=model,
)

task = (
    "Use the database at cascadelens/scripts/data/all_healthy.db. "
    "Find the root cause of today's failure and which tables are confirmed impacted or at risk. "
    "Call the analysis tools first and read their results. "
    "Call final_answer alone, in a separate step, only after you have seen all tool results."
)
print(agent.run(task))