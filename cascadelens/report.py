from pydantic import BaseModel, Field

class Failure(BaseModel):
    """One independent failure: its own table, cause and victims."""

    failed_table: str = Field(description="Table where this failure started")
    root_cause: str = Field(description="One sentence naming the cause")
    recurrence_days: int = Field(default=0, description="Days this error occurred in the last 7")
    confirmed_impacted: list[str] = Field(default_factory=list)
    at_risk: list[str] = Field(default_factory=list)

class EmptyLoad(BaseModel):
    """An empty load: a table that ran but wrote 0 rows, and what sits below it."""

    pipeline: str = Field(description="Pipeline that ran the empty load")
    empty_table: str = Field(description="Table that wrote 0 rows although it normally writes rows")
    at_risk: list[str] = Field(default_factory=list, description="Tables downstream of the empty table")

class TriageReport(BaseModel):
    """The fixed shape of the final answer, whatever wording the agents use."""

    database: str = Field(description="Path of the analysed database")
    overall_status: str = Field(description="Healthy, or Unhealthy when any pipeline is not Healthy")
    failures: list[Failure] = Field(default_factory=list, description="One entry per independent failure")
    warnings: list[EmptyLoad] = Field(default_factory=list, description="Empty loads found by code")

# What it does: it reads the fields of a TriageReport and builds the text line by line. The if parts leave out a section when it is empty, so a healthy report is short and has no failed table or empty lists. It only formats data we already validated, so no AI is involved.
def render_markdown(report: TriageReport) -> str:
    """Turn a validated report into a short markdown document."""
    lines = [
        "# CascadeLens triage report",
        "",
        f"- **Database:** {report.database}",
        f"- **Overall status:** {report.overall_status}",
    ]
    for number, failure in enumerate(report.failures, start=1):
        lines += [
            "",
            f"## Failure {number}: {failure.failed_table}",
            "",
            f"- **Root cause:** {failure.root_cause}",
            f"- **Recurrence:** {failure.recurrence_days} of the last 7 days",
        ]
        if failure.confirmed_impacted:
            lines += ["", "**Confirmed impacted**", ""]
            lines += [f"- {table}" for table in failure.confirmed_impacted]
        if failure.at_risk:
            lines += ["", "**At risk**", ""]
            lines += [f"- {table}" for table in failure.at_risk]
    if report.warnings:
        lines += ["", "## Warnings", ""]
        for w in report.warnings:
            lines.append(f"- {w.pipeline}: {w.empty_table} loaded 0 rows, at risk: {', '.join(w.at_risk) or 'none'}")
    return "\n".join(lines) + "\n"

def diff_failures(expected: list[Failure], actual: list[Failure]) -> list[str]:
    """List every fact the agent got wrong. An empty list means fully correct.

    Compares only facts that code can compute. root_cause is wording, so it is skipped.
    """
    want = {f.failed_table: f for f in expected}
    got = {f.failed_table: f for f in actual}
    problems = []
    if len(got) != len(actual):
        problems.append("duplicate failure entries")
    for table in sorted(want.keys() - got.keys()):
        problems.append(f"missing failure: {table}")
    for table in sorted(got.keys() - want.keys()):
        problems.append(f"unexpected failure: {table}")
    for table in sorted(want.keys() & got.keys()):
        w, g = want[table], got[table]
        if w.recurrence_days != g.recurrence_days:
            problems.append(f"{table}: recurrence {g.recurrence_days}, expected {w.recurrence_days}")
        if sorted(w.confirmed_impacted) != sorted(g.confirmed_impacted):
            problems.append(f"{table}: confirmed {g.confirmed_impacted}, expected {w.confirmed_impacted}")
        if sorted(w.at_risk) != sorted(g.at_risk):
            problems.append(f"{table}: at risk {g.at_risk}, expected {w.at_risk}")
    return problems