"""Comprehensive tests for Query Completeness Stage, Intent Resolution, and Stateful Multi-turn Clarification."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

os.environ["STT_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from main import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as directory:
        db_path = os.path.join(directory, "test_completeness.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = "sqlite:///" + db_path
        app = create_app()
        with TestClient(app) as test_client:
            conn = app.state.query_service.database.connection
            conn.executescript("""
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    total REAL,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    status TEXT,
                    salary INTEGER,
                    joined_date TEXT
                );

                INSERT INTO customers VALUES (1, 'Alice', 'active', '2025-01-01', '2025-01-02'), (2, 'Bob', 'inactive', '2025-01-03', '2025-01-04');
                INSERT INTO orders VALUES (101, 1, 150.0, '2025-02-01', '2025-02-01'), (102, 1, 250.0, '2025-02-05', '2025-02-06');
                INSERT INTO employees VALUES (1, 'Charlie', 'active', 60000, '2025-03-01');
            """)
            conn.commit()
            yield test_client


# 1. Exact Screenshot Scenario: Multi-turn clarification for "Can you delete the last row"
def test_exact_screenshot_scenario_multiturn(client):
    # Step 1: User asks ambiguous query without table or ordering definition
    res1 = client.post("/api/query", json={"message": "Can you delete the last row"})
    data1 = res1.json()
    assert data1["status"] == "CLARIFICATION_REQUIRED"
    assert data1["field"] == "table"
    assert "table" in data1["question"].lower()
    assert "orders" in data1["options"]
    assert "customers" in data1["options"]
    req_id1 = data1["request_id"]

    # Step 2: User responds specifying table "orders"
    res2 = client.post("/api/query/clarify", json={"request_id": req_id1, "selection": "orders"})
    data2 = res2.json()
    assert data2["status"] == "CLARIFICATION_REQUIRED"
    assert data2["field"] == "ordering_definition"
    assert "last" in data2["question"].lower()
    req_id2 = data2["request_id"]

    # Step 3: User specifies ordering definition "Most recently created"
    res3 = client.post("/api/query/clarify", json={"request_id": req_id2, "selection": "Most recently created"})
    data3 = res3.json()
    assert data3["status"] == "CONFIRMATION_REQUIRED"
    assert data3["operation"] == "DELETE"
    assert "DELETE FROM orders" in data3["sql"]
    assert "ORDER BY created_at DESC" in data3["sql"]


# 2. "Delete the last row from orders" -> clarify ordering definition
def test_delete_last_row_with_table_specified(client):
    res1 = client.post("/api/query", json={"message": "Delete the last row from orders"})
    data1 = res1.json()
    assert data1["status"] == "CLARIFICATION_REQUIRED"
    assert data1["field"] == "ordering_definition"

    req_id = data1["request_id"]
    res2 = client.post("/api/query/clarify", json={"request_id": req_id, "selection": "Highest order ID"})
    data2 = res2.json()
    assert data2["status"] == "CONFIRMATION_REQUIRED"
    assert "DELETE FROM orders" in data2["sql"]


# 3. Explicit complete request requires NO clarification
def test_complete_request_no_clarification(client):
    res = client.post("/api/query", json={"message": "Delete the most recently created order from orders"})
    data = res.json()
    assert data["status"] == "CONFIRMATION_REQUIRED"
    assert data["operation"] == "DELETE"
    assert "DELETE FROM orders" in data["sql"]


# 4. Ambiguous SELECT queries trigger metric clarification
def test_ambiguous_select_queries(client):
    res1 = client.post("/api/query", json={"message": "Show me the best customers"})
    assert res1.json()["status"] == "CLARIFICATION_REQUIRED"
    assert res1.json()["field"] == "metric"

    res2 = client.post("/api/query", json={"message": "Show sales"})
    assert res2.json()["status"] == "CLARIFICATION_REQUIRED"
    assert res2.json()["field"] in ("metric", "table")


# 5. Explicit Conversation Context Usage
def test_conversation_context_explicit_table(client):
    c_id = "conv_explicit_context_1"
    # Turn 1: Show orders
    res1 = client.post("/api/query", json={"message": "Show me orders", "conversation_id": c_id})
    assert res1.json()["status"] == "SUCCESS"

    # Turn 2: Delete the last one -> table is resolved to orders, but "last" requires ordering clarification
    res2 = client.post("/api/query", json={"message": "Delete the last one", "conversation_id": c_id})
    data2 = res2.json()
    assert data2["status"] == "CLARIFICATION_REQUIRED"
    assert data2["field"] == "ordering_definition"

    # Clarify
    req_id = data2["request_id"]
    res3 = client.post("/api/query/clarify", json={"request_id": req_id, "selection": "Most recently created"})
    data3 = res3.json()
    assert data3["status"] == "CONFIRMATION_REQUIRED"
    assert "orders" in data3["sql"].lower()


# 6. Adversarial Vague Queries test suite
@pytest.mark.parametrize("query", [
    "Delete the best customer",
    "Delete the latest customer",
    "Remove the first employee",
    "Delete the oldest row",
    "Show the biggest customers",
    "Delete that",
    "Remove those",
    "Delete the last one",
])
def test_adversarial_vague_queries(client, query):
    res = client.post("/api/query", json={"message": query})
    data = res.json()
    # Must NOT generate un-clarified SQL or show CONFIRMATION_REQUIRED directly!
    assert data["status"] in ("CLARIFICATION_REQUIRED", "FAILED")
    assert data["status"] != "CONFIRMATION_REQUIRED"
