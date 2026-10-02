from datetime import date

from cascadelens.analysis import analyse, build_failures, build_warnings, get_statuses
from cascadelens.lineage import find_impacted
from cascadelens.lineage import find_impacted, split_impacted
from cascadelens.reader import read_logs

import json

import pytest
from pydantic import ValidationError

from cascadelens.main import check_db_path, parse_report


def test_noisy_recurring_end_to_end():
    result = analyse("cascadelens/scripts/data/noisy_recurring.db")

    assert result.today == date(2026, 10, 1)
    statuses = get_statuses("cascadelens/scripts/data/noisy_recurring.db")
    assert statuses["PL_04_Cur_Execute_Scripts"] == "Partially Failed"

    # sales retries are noise, so only the customer_dal defect remains today
    assert len(result.failure_groups) == 1
    (group,) = result.failure_groups.values()
    assert group[0].unit_name == "customer_dal"

    # raw recurrence still sees the recovering 429 and the 6 day defect
    assert sorted(result.recurrence.values()) == [1, 2, 6]

def test_clean_cascade_impact_stays_inside_the_customer_and_sales_chains():
    result = analyse("cascadelens/scripts/data/clean_cascade.db")

    statuses = get_statuses("cascadelens/scripts/data/clean_cascade.db")
    assert statuses["PL_01_Ingest_Crm"] == "Failed"
    assert statuses["PL_03_Ingest_Inventory"] == "Healthy"

    (group,) = result.failure_groups.values()
    assert group[0].unit_name == "Ingest_customer_ingestion"

    impacted = find_impacted(result.downstream, "customer_ingestion")
    assert impacted == {"customer_curation", "customer_dal", "sales_curation", "sales_dal"}
    assert not any("inventory" in table for table in impacted)

def test_all_healthy_has_no_failures_and_no_issues():
    result = analyse("cascadelens/scripts/data/all_healthy.db")

    assert result.failure_groups == {}
    assert set(get_statuses("cascadelens/scripts/data/all_healthy.db").values()) == {"Healthy"}


def test_ambiguous_has_two_failures_and_a_flagged_empty_load():
    result = analyse("cascadelens/scripts/data/ambiguous.db")

    failed_units = {
        r.unit_name for group in result.failure_groups.values() for r in group
    }
    assert failed_units == {"sales_curation", "inventory_dal"}
    statuses = get_statuses("cascadelens/scripts/data/ambiguous.db")
    assert statuses["PL_02_Ingest_Sales"] == "Succeeded with Issues"
    assert statuses["PL_04_Cur_Execute_Scripts"] == "Partially Failed"

def test_clean_cascade_splits_confirmed_from_at_risk():
    path = "cascadelens/scripts/data/clean_cascade.db"
    result = analyse(path)
    impacted = find_impacted(result.downstream, "customer_ingestion")

    confirmed, at_risk = split_impacted(read_logs(path), impacted, result.today)

    assert confirmed == {"customer_curation", "customer_dal"}
    assert at_risk == {"sales_curation", "sales_dal"}

def test_build_failures_for_each_database():
    def run(name):
        path = f"cascadelens/scripts/data/{name}.db"
        return build_failures(analyse(path), read_logs(path))

    assert run("all_healthy") == []

    (cascade,) = run("clean_cascade")
    assert cascade.failed_table == "customer_ingestion"
    assert cascade.confirmed_impacted == ["customer_curation", "customer_dal"]
    assert cascade.at_risk == ["sales_curation", "sales_dal"]

    (noisy,) = run("noisy_recurring")
    assert noisy.failed_table == "customer_dal"
    assert noisy.recurrence_days == 6

    inventory, sales = run("ambiguous")
    assert inventory.failed_table == "inventory_dal"
    assert sales.failed_table == "sales_curation"
    assert sales.confirmed_impacted == ["sales_dal"]


def test_build_warnings_links_the_empty_load_to_its_downstream_tables():
    path = "cascadelens/scripts/data/ambiguous.db"
    analysis, records = analyse(path), read_logs(path)
    failures = build_failures(analysis, records)

    (warning,) = build_warnings(analysis, records, failures)
    assert warning.empty_table == "sales_ingestion"
    assert warning.at_risk == ["sales_curation", "sales_dal"]

def test_check_db_path_exits_with_a_clear_message():
    # sys.exit("text") raises SystemExit, so pytest.raises can catch it
    with pytest.raises(SystemExit) as err:
        check_db_path("nothere.db")
    assert "database file not found" in str(err.value)


def test_parse_report_rejects_bad_output_and_accepts_a_fenced_answer():
    # text that is not JSON at all
    with pytest.raises(json.JSONDecodeError):
        parse_report("not json")

    # valid JSON, but a string where a list is expected
    with pytest.raises(ValidationError):
        parse_report({"database": "x.db", "overall_status": "Healthy", "failures": "oops"})

    # models often wrap the answer in a markdown fence, which parse_report strips
    fenced = '```json\n{"database": "x.db", "overall_status": "Healthy"}\n```'
    assert parse_report(fenced).overall_status == "Healthy"


from cascadelens.report import diff_failures

def test_diff_failures_finds_wrong_facts():
    path = "cascadelens/scripts/data/ambiguous.db"
    expected = build_failures(analyse(path), read_logs(path))

    # identical lists have no problems
    assert diff_failures(expected, expected) == []

    # drop one failure and change a recurrence: two problems
    wrong = [expected[0].model_copy(update={"recurrence_days": 99})]
    assert len(diff_failures(expected, wrong)) == 2