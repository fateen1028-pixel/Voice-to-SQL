"""Comprehensive regression and operation resolution test suite."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture
def test_client():
    with tempfile.TemporaryDirectory() as directory:
        db_path = os.path.join(directory, "test_regression.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = "sqlite:///" + db_path
        os.environ["STT_PROVIDER"] = "mock"
        os.environ["LLM_PROVIDER"] = "mock"
        app = create_app()
        with TestClient(app) as client:
            conn = app.state.query_service.database.connection
            conn.executescript("""
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    role TEXT,
                    salary INTEGER,
                    status TEXT
                );
                INSERT INTO employees VALUES (1, 'Alice', 'Engineer', 90000, 'active');
                INSERT INTO employees VALUES (2, 'Bob', 'Manager', 110000, 'active');
            """)
            conn.commit()
            yield client


# 1. Screenshot Regression Test (Michael Jackson INSERT)
def test_regression_michael_jackson_insert(test_client):
    msg = "Can you add employee Michael Jackson for the role of dancer with a salary of 100,000 to the employee table?"
    res = test_client.post("/api/query", json={"message": msg})
    data = res.json()

    assert data["status"] == "CONFIRMATION_REQUIRED"
    assert data["operation"] == "INSERT"
    assert "INSERT INTO employees" in data["sql"]
    assert "Michael Jackson" in data["sql"]
    assert "dancer" in data["sql"]
    assert "100000" in data["sql"]

    # Pre-confirmation DB check (zero mutation)
    conn = test_client.app.state.query_service.database.connection
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM employees")
    assert cur.fetchone()[0] == 2

    # Execute confirmation
    token = data["confirmation_token"]
    confirm_res = test_client.post("/api/query/confirm", json={"confirmation_token": token})
    confirm_data = confirm_res.json()

    assert confirm_data["status"] == "SUCCESS"
    assert confirm_data["row_count"] == 1

    # Post-confirmation DB check
    cur.execute("SELECT name, role, salary FROM employees WHERE name = 'Michael Jackson'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "Michael Jackson"
    assert row[1] == "dancer"
    assert row[2] == 100000


# 2. Test All Four Operations (SELECT, INSERT, UPDATE, DELETE)
def test_operation_select(test_client):
    res = test_client.post("/api/query", json={"message": "Show all employees"})
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["operation"] == "SELECT"
    assert len(data["rows"]) == 2


def test_operation_insert(test_client):
    res = test_client.post("/api/query", json={"message": "Add employee Charlie with role Analyst and salary 80000"})
    data = res.json()
    assert data["status"] == "CONFIRMATION_REQUIRED"
    assert data["operation"] == "INSERT"
    assert "Charlie" in data["sql"]


def test_operation_update(test_client):
    res = test_client.post("/api/query", json={"message": "Update employees set status to inactive where id = 1"})
    data = res.json()
    assert data["status"] == "CONFIRMATION_REQUIRED"
    assert data["operation"] == "UPDATE"
    assert "UPDATE employees" in data["sql"]


def test_operation_delete(test_client):
    res = test_client.post("/api/query", json={"message": "Delete employee where id = 2"})
    data = res.json()
    assert data["status"] == "CONFIRMATION_REQUIRED"
    assert data["operation"] == "DELETE"
    assert "DELETE FROM employees" in data["sql"]


# 3. Ambiguous Operation Test (No SELECT-by-default)
def test_ambiguous_operation_clarification(test_client):
    res = test_client.post("/api/query", json={"message": "What can you do with employees?"})
    data = res.json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert data["field"] == "operation"
    assert "View data" in data["options"]
    assert "Add data" in data["options"]


# 4. Duplicate Confirmation Token Rejection Test
def test_duplicate_confirmation_rejection(test_client):
    res = test_client.post("/api/query", json={"message": "Add employee David with role Designer and salary 75000"})
    data = res.json()
    token = data["confirmation_token"]

    # First confirm -> SUCCESS
    c1 = test_client.post("/api/query/confirm", json={"confirmation_token": token})
    assert c1.json()["status"] == "SUCCESS"

    # Second confirm -> REJECTED
    c2 = test_client.post("/api/query/confirm", json={"confirmation_token": token})
    assert c2.json()["status"] in ("INVALID_CONFIRMATION", "SECURITY_VIOLATION", "FAILED")


# 5. Intent vs SQL Mismatch Protection Test
def test_intent_sql_mismatch_rejection():
    from unittest.mock import MagicMock
    from config.settings import Settings
    from services.query_service import QueryService
    from model.query_models import StructuredIntent

    qs = QueryService(MagicMock(), Settings())
    intent = StructuredIntent(operation="INSERT", table="employees")
    bad_sql = "SELECT * FROM employees"

    mismatch = qs._verify_intent_sql_consistency(intent, bad_sql, {"employees": {}})
    assert mismatch is not None
    assert "INSERT" in mismatch
