from pydantic import BaseModel, Field


class TriageReport(BaseModel):
    """The fixed shape of the final answer, whatever wording the agents use."""

    database: str = Field(description="Path of the analysed database")
    overall_status: str = Field(description="Healthy, or Unhealthy when any pipeline is not Healthy")
    root_cause: str = Field(description="One sentence naming the cause, or 'None' when healthy")
    failed_table: str | None = Field(default=None, description="Table where the failure started")
    recurrence_days: int = Field(default=0, description="Days this error occurred in the last 7")
    confirmed_impacted: list[str] = Field(default_factory=list)
    at_risk: list[str] = Field(default_factory=list)