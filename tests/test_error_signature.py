from cascadelens.error_signature import make_signature


def test_empty_message_gives_empty_signature():
    assert make_signature(None) == ""
    assert make_signature("") == ""
    assert make_signature("   ") == ""


def test_guid_is_replaced():
    raw = (
        "ErrorCode=SqlFailedToConnect: Login failed for user 'svc_adf_crm'. "
        "Password expired. Activity ID: 3f2a9c1e-7b4d-4e2a-9c1f-0a1b2c3d4e5f"
    )
    expected = (
        "errorcode=sqlfailedtoconnect: login failed for user 'svc_adf_crm'. "
        "password expired. activity id: <guid>"
    )
    assert make_signature(raw) == expected

def test_only_first_line_is_kept():
    raw = (
        "TimeoutException: request to sales_api/orders timed out.\n"
        "\tat org.apache.spark.Foo.run(Foo.scala:54)\n"
        "\tat org.apache.spark.Bar.run(Bar.scala:12)"
    )
    assert make_signature(raw) == "timeoutexception: request to sales_api/orders timed out."

def test_wrapper_prefix_is_removed():
    raw1 = (
        "Operation on target Ingest_sales_ingestion failed: "
        "HttpStatus 429: Too Many Requests from sales_api."
    )
    raw2 = (
        "Operation on target Ingest_customer_ingestion failed: "
        "HttpStatus 429: Too Many Requests from sales_api."
    )
    expected = "httpstatus 429: too many requests from sales_api."

    assert make_signature(raw1) == expected
    assert make_signature(raw2) == expected

def test_each_wrapper_prefix_style_is_removed():
    expected = "httpstatus 429: too many requests from sales_api."

    activity_style = "Activity Copy_orders failed: HttpStatus 429: Too Many Requests from sales_api."
    stacked = (
        "Operation on target Ingest_sales_ingestion failed: "
        "Activity Copy_orders failed: HttpStatus 429: Too Many Requests from sales_api."
    )

    assert make_signature(activity_style) == expected
    assert make_signature(stacked) == expected

def test_timestamp_is_replaced():
    plain = "Request timed out. Started at 2026-09-30 02:25:13"
    iso = "Request timed out. Started at 2026-10-01T02:26:58.123Z"
    expected = "request timed out. started at <timestamp>"

    assert make_signature(plain) == expected
    assert make_signature(iso) == expected

def test_timestamp_and_numbers_are_replaced():
    raw1 = (
        "TimeoutException: request to sales_api/orders timed out after 120s. "
        "Started at 2026-09-30 02:25:13"
    )
    raw2 = (
        "Operation on target nb_customer_ingestion failed: "
        "Databricks job run 884213 failed with state FAILED."
    )
    assert make_signature(raw1) == (
        "timeoutexception: request to sales_api/orders timed out after <num>s. "
        "started at <timestamp>"
    )
    assert make_signature(raw2) == "databricks job run <num> failed with state failed."


def test_http_status_code_is_kept():
    too_many = make_signature("HttpStatus 429: Too Many Requests from sales_api.")
    unavailable = make_signature("HttpStatus 503: Service Unavailable from sales_api.")

    assert "429" in too_many
    assert too_many != unavailable

def test_compact_date_in_file_name_is_replaced():
    day1 = make_signature("inventory_20260930.csv does not exist")
    day2 = make_signature("inventory_20261001.csv does not exist")

    assert day1 == "inventory_<date>.csv does not exist"
    assert day1 == day2


def test_eight_digit_number_that_is_not_a_date_becomes_num():
    raw = "Databricks job run 88421300 failed"
    assert make_signature(raw) == "databricks job run <num> failed"

def test_non_empty_column_list_is_replaced():
    a = make_signature("AnalysisException: cannot resolve 'order_id' given input columns [customer_id, name, city].")
    b = make_signature("AnalysisException: cannot resolve 'order_id' given input columns [col_1, col_2].")

    assert a == "analysisexception: cannot resolve 'order_id' given input columns [<list>]."
    assert a == b


def test_empty_column_list_is_kept():
    raw = "AnalysisException: cannot resolve 'order_id' given input columns []."
    assert make_signature(raw) == "analysisexception: cannot resolve 'order_id' given input columns []."

def test_repeated_spaces_are_collapsed():
    a = make_signature("Request  timed   out\tafter 120s")
    b = make_signature("Request timed out after 120s")

    assert a == "request timed out after <num>s"
    assert a == b