from cascadelens.lineage import build_downstream, find_impacted
from cascadelens.models import LogRecord


def script(layer, target, source, reference=None):
    return LogRecord(
        layer=layer,
        log_id=1,
        source_name=source,
        reference_source_name=reference,
        target_delta_table=target,
    )


def test_downstream_follows_source_and_reference_links():
    records = [
        LogRecord(layer="ingestion", log_id=1, source_name="sales_api/orders", target_delta_table="sales_ingestion"),
        script("curation", "customer_curation", "customer_ingestion"),
        script("curation", "sales_curation", "sales_ingestion", reference="customer_curation"),
        script("semantic", "sales_dal", "sales_curation"),
    ]

    downstream = build_downstream(records)

    assert downstream["customer_ingestion"] == {"customer_curation"}
    assert downstream["customer_curation"] == {"sales_curation"}
    assert downstream["sales_ingestion"] == {"sales_curation"}
    assert downstream["sales_curation"] == {"sales_dal"}
    assert "sales_api/orders" not in downstream

def test_impact_follows_the_chain_and_the_reference_link_but_not_other_chains():
    downstream = {
        "customer_ingestion": {"customer_curation"},
        "customer_curation": {"customer_dal", "sales_curation"},
        "sales_curation": {"sales_dal"},
        "inventory_ingestion": {"inventory_curation"},
    }

    assert find_impacted(downstream, "customer_ingestion") == {
        "customer_curation",
        "customer_dal",
        "sales_curation",
        "sales_dal",
    }
    assert find_impacted(downstream, "sales_dal") == set()