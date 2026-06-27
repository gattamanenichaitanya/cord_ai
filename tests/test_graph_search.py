import pytest
from graph_db.build_index import build_index
from graph_db.search import search_graph

@pytest.fixture(scope="session", autouse=True)
def initialize_graph_index():
    print("\n[Pytest Fixture] Building ChromaDB graph index...")
    build_index()

def print_top_results_on_failure(results, query):
    print(f"\n[DEBUG] Search results for query '{query}':")
    for idx, r in enumerate(results[:3], 1):
        print(f"  {idx}. ID: {r['metadata']['entry_id']} (Type: {r['metadata']['type']}, Distance: {r['distance']:.4f})")

def test_finds_last_interaction_date():
    query = "last interaction date with customer"
    results = search_graph(query, n_results=5)
    if not results or results[0]["metadata"]["entry_id"] != "notes_last_contacted":
        print_top_results_on_failure(results, query)
    assert results and results[0]["metadata"]["entry_id"] == "notes_last_contacted"

def test_finds_create_custom_property_operation():
    query = "create a custom field on contact"
    results = search_graph(query, n_results=5)
    if not results or results[0]["metadata"]["entry_id"] != "hubspot.create_custom_property":
        print_top_results_on_failure(results, query)
    assert results and results[0]["metadata"]["entry_id"] == "hubspot.create_custom_property"

def test_finds_workflow_capability():
    query = "automate when properties change"
    results = search_graph(query, n_results=3)
    entry_ids = [r["metadata"]["entry_id"] for r in results]
    if "workflow" not in entry_ids and "create_workflow" not in entry_ids:
        print_top_results_on_failure(results, query)
    assert "workflow" in entry_ids or "create_workflow" in entry_ids

def test_filter_type_works():
    query = "data not being populated reliably"
    results = search_graph(query, n_results=5, filter_type="gotcha")
    expected_id = "notes_last_contacted_requires_logged_activity"
    if not results or results[0]["metadata"]["entry_id"] != expected_id:
        print_top_results_on_failure(results, query)
    assert results and results[0]["metadata"]["entry_id"] == expected_id

def test_finds_re_enrollment_gotcha():
    query = "manual changes being overwritten by automation"
    results = search_graph(query, n_results=5, filter_type="gotcha")
    expected_id = "workflow_re_enrollment_overwrites_manual_changes"
    if not results or results[0]["metadata"]["entry_id"] != expected_id:
        print_top_results_on_failure(results, query)
    assert results and results[0]["metadata"]["entry_id"] == expected_id
