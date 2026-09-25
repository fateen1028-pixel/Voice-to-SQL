"""
Comprehensive test suite verifying that the Voice-to-SQL application is 100% dynamic,
schema-grounded, and operates across entirely different database schemas (Schema A and Schema B)
without requiring any application source-code changes.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from main import create_app


def create_schema_a(conn):
    """Schema A: Education domain (students, courses, enrollments)."""
    conn.executescript("""
        CREATE TABLE students (
            student_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            major TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            enrolled_at TEXT NOT NULL
        );

        CREATE TABLE courses (
            course_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            credits INTEGER NOT NULL,
            category TEXT NOT NULL
        );

        CREATE TABLE enrollments (
            enrollment_id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            grade REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            enrolled_date TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(student_id),
            FOREIGN KEY(course_id) REFERENCES courses(course_id)
        );

        INSERT INTO students VALUES
            (1, 'Alice Walker', 'alice@school.edu', 'Computer Science', 'active', '2024-09-01'),
            (2, 'Bob Builder', 'bob@school.edu', 'Mathematics', 'active', '2024-09-01'),
            (3, 'Charlie Chaplin', 'charlie@school.edu', 'Physics', 'inactive', '2023-09-01');

        INSERT INTO courses VALUES
            (101, 'Intro to Computer Science', 4, 'CS'),
            (102, 'Calculus I', 3, 'Math'),
            (103, 'Quantum Physics', 4, 'Physics');

        INSERT INTO enrollments VALUES
            (1, 1, 101, 3.8, 'active', '2024-09-05'),
            (2, 1, 102, 3.5, 'active', '2024-09-05'),
            (3, 2, 102, 4.0, 'active', '2024-09-05'),
            (4, 3, 103, 2.5, 'inactive', '2023-09-05');
    """)
    conn.commit()


def create_schema_b(conn):
    """Schema B: Corporate / Operations domain (projects, teams, tasks)."""
    conn.executescript("""
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_name TEXT NOT NULL,
            region TEXT NOT NULL
        );

        CREATE TABLE projects (
            project_id INTEGER PRIMARY KEY,
            project_name TEXT NOT NULL,
            team_id INTEGER NOT NULL,
            budget REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_date TEXT NOT NULL,
            FOREIGN KEY(team_id) REFERENCES teams(team_id)
        );

        CREATE TABLE tasks (
            task_id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            task_title TEXT NOT NULL,
            hours_estimated REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(project_id)
        );

        INSERT INTO teams VALUES
            (1, 'Alpha Team', 'North America'),
            (2, 'Beta Team', 'Europe');

        INSERT INTO projects VALUES
            (10, 'Apollo Upgrade', 1, 50000.0, 'active', '2025-01-10'),
            (20, 'Zeus Migration', 2, 75000.0, 'active', '2025-02-15'),
            (30, 'Hermes Redesign', 1, 20000.0, 'inactive', '2024-06-01');

        INSERT INTO tasks VALUES
            (100, 10, 'Backend API Hardening', 40.0, 'active', '2025-01-12'),
            (200, 20, 'Cloud Infrastructure Setup', 60.0, 'pending', '2025-02-18');
    """)
    conn.commit()


def test_schema_a_education_domain():
    """Verify application pipeline dynamically adapts to Education Schema A."""
    with tempfile.TemporaryDirectory() as directory:
        db_path = os.path.join(directory, "schema_a.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = "sqlite:///" + db_path
        app = create_app()

        with TestClient(app) as client:
            conn = app.state.query_service.database.connection
            create_schema_a(conn)
            app.state.query_service.schema.refresh()

            # 1. Dynamic Schema API Discovery
            schema_res = client.get("/api/schema").json()
            assert "tables" in schema_res
            assert "students" in schema_res["tables"]
            assert "courses" in schema_res["tables"]
            assert "enrollments" in schema_res["tables"]
            assert "employees" not in schema_res["tables"]

            # 2. Dynamic Text Query on Schema A
            q_res = client.post("/api/query", json={"message": "Show all students"}).json()
            assert q_res["status"] == "SUCCESS"
            assert q_res["operation"] == "SELECT"
            assert q_res["table"] == "students"
            assert len(q_res["rows"]) == 3
            assert "full_name" in q_res["columns"]
            assert "major" in q_res["columns"]

            # 3. Dynamic Clarification grounded in Schema A
            clar_res = client.post("/api/query", json={"message": "Show me the best students"}).json()
            assert clar_res["status"] == "CLARIFICATION_REQUIRED"
            assert clar_res["field"] == "metric"
            assert any("grade" in opt.lower() or "enrollments" in opt.lower() or "students" in opt.lower() for opt in clar_res["options"])

            # 4. Dynamic Mutation & Confirmation on Schema A
            mut_prep = client.post("/api/query", json={"message": "Delete inactive enrollments"}).json()
            assert mut_prep["status"] == "CONFIRMATION_REQUIRED"
            assert mut_prep["operation"] == "DELETE"
            assert "DELETE FROM enrollments" in mut_prep["sql"]
            token = mut_prep["confirmation_token"]

            mut_confirm = client.post("/api/query/confirm", json={"confirmation_token": token}).json()
            assert mut_confirm["status"] == "SUCCESS"
            assert mut_confirm["row_count"] == 1


def test_schema_b_corporate_domain():
    """Verify application pipeline dynamically adapts to Corporate Schema B with ZERO code changes."""
    with tempfile.TemporaryDirectory() as directory:
        db_path = os.path.join(directory, "schema_b.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = "sqlite:///" + db_path
        app = create_app()

        with TestClient(app) as client:
            conn = app.state.query_service.database.connection
            create_schema_b(conn)
            app.state.query_service.schema.refresh()

            # 1. Dynamic Schema API Discovery
            schema_res = client.get("/api/schema").json()
            assert "tables" in schema_res
            assert "teams" in schema_res["tables"]
            assert "projects" in schema_res["tables"]
            assert "tasks" in schema_res["tables"]
            assert "students" not in schema_res["tables"]

            # 2. Dynamic Text Query on Schema B
            q_res = client.post("/api/query", json={"message": "Show all projects"}).json()
            assert q_res["status"] == "SUCCESS"
            assert q_res["operation"] == "SELECT"
            assert q_res["table"] == "projects"
            assert len(q_res["rows"]) == 3
            assert "project_name" in q_res["columns"]
            assert "budget" in q_res["columns"]

            # 3. Dynamic Visualization Recommendation on Schema B (numeric + category)
            viz_res = client.post("/api/query", json={"message": "Show top 10 projects by budget"}).json()
            assert viz_res["status"] == "SUCCESS", f"Failed with viz_res: {viz_res}"
            assert viz_res["visualization"] is not None

            assert viz_res["visualization"]["type"] in ("bar", "pie", "kpi", "line")


            # 4. Dynamic Clarification grounded in Schema B
            clar_res = client.post("/api/query", json={"message": "Show me the best projects"}).json()
            assert clar_res["status"] == "CLARIFICATION_REQUIRED"
            assert clar_res["field"] == "metric"
            assert any("budget" in opt.lower() or "projects" in opt.lower() for opt in clar_res["options"])

            # 5. Dynamic Mutation & Confirmation on Schema B
            mut_prep = client.post("/api/query", json={"message": "Delete pending tasks"}).json()
            assert mut_prep["status"] == "CONFIRMATION_REQUIRED"
            assert mut_prep["operation"] == "DELETE"
            assert "DELETE FROM tasks" in mut_prep["sql"]
            token = mut_prep["confirmation_token"]

            mut_confirm = client.post("/api/query/confirm", json={"confirmation_token": token}).json()
            assert mut_confirm["status"] == "SUCCESS"
            assert mut_confirm["row_count"] == 1

