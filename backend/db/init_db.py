import os
import sys
from pathlib import Path

# Add backend directory to sys.path to import Settings and Database
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from db.connection import Database

def init_database():
    settings = Settings()
    db = Database(settings.database_url)
    db.connect()
    conn = db.connection
    cursor = db.cursor()

    if db.is_postgres:
        print(f"Initializing PostgreSQL database at: {settings.database_url}")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                location VARCHAR(255)
            );

            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                department_id INT REFERENCES departments(id),
                role VARCHAR(255) NOT NULL,
                salary NUMERIC NOT NULL,
                joined_date DATE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                created_at DATE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                customer_id INT NOT NULL REFERENCES customers(id),
                total NUMERIC NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'completed',
                order_date DATE NOT NULL
            );
        """)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM customers;")
        row = cursor.fetchone()
        count = row['count'] if isinstance(row, dict) else row[0]

        if count == 0:
            cursor.execute("""
                INSERT INTO departments (name, location) VALUES
                ('Engineering', 'New York'),
                ('Sales', 'San Francisco'),
                ('Marketing', 'Chicago');

                INSERT INTO employees (name, department_id, role, salary, joined_date, status) VALUES
                ('Alice Smith', 1, 'Senior Developer', 120000, '2024-01-15', 'active'),
                ('Bob Jones', 1, 'Developer', 90000, '2024-03-01', 'active'),
                ('Charlie Brown', 2, 'Sales Manager', 110000, '2023-06-10', 'active'),
                ('Diana Prince', 2, 'Sales Representative', 75000, '2024-05-20', 'active'),
                ('Edward Elric', 3, 'Marketing Lead', 95000, '2023-11-01', 'inactive');

                INSERT INTO customers (name, email, status, created_at) VALUES
                ('Acme Corp', 'contact@acme.com', 'active', '2024-01-10'),
                ('Stark Industries', 'info@stark.com', 'active', '2024-02-14'),
                ('Wayne Enterprises', 'bruce@wayne.com', 'active', '2024-03-22'),
                ('Cyberdyne Systems', 'support@cyberdyne.com', 'inactive', '2023-09-05');

                INSERT INTO orders (customer_id, total, status, order_date) VALUES
                (1, 1500.50, 'completed', '2024-06-01'),
                (1, 3200.00, 'completed', '2024-07-15'),
                (2, 8500.00, 'completed', '2024-08-20'),
                (3, 450.75, 'completed', '2024-09-02'),
                (4, 120.00, 'cancelled', '2023-10-12');
            """)
            conn.commit()
    else:
        print(f"Initializing SQLite database at: {db.sqlite_path}")
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT
            );

            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                department_id INTEGER,
                role TEXT NOT NULL,
                salary REAL NOT NULL,
                joined_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY (department_id) REFERENCES departments(id)
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                order_date TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)

        cursor.execute("SELECT COUNT(*) FROM customers;")
        if cursor.fetchone()[0] == 0:
            cursor.executescript("""
                INSERT INTO departments (name, location) VALUES
                ('Engineering', 'New York'),
                ('Sales', 'San Francisco'),
                ('Marketing', 'Chicago');

                INSERT INTO employees (name, department_id, role, salary, joined_date, status) VALUES
                ('Alice Smith', 1, 'Senior Developer', 120000, '2024-01-15', 'active'),
                ('Bob Jones', 1, 'Developer', 90000, '2024-03-01', 'active'),
                ('Charlie Brown', 2, 'Sales Manager', 110000, '2023-06-10', 'active'),
                ('Diana Prince', 2, 'Sales Representative', 75000, '2024-05-20', 'active'),
                ('Edward Elric', 3, 'Marketing Lead', 95000, '2023-11-01', 'inactive');

                INSERT INTO customers (name, email, status, created_at) VALUES
                ('Acme Corp', 'contact@acme.com', 'active', '2024-01-10'),
                ('Stark Industries', 'info@stark.com', 'active', '2024-02-14'),
                ('Wayne Enterprises', 'bruce@wayne.com', 'active', '2024-03-22'),
                ('Cyberdyne Systems', 'support@cyberdyne.com', 'inactive', '2023-09-05');

                INSERT INTO orders (customer_id, total, status, order_date) VALUES
                (1, 1500.50, 'completed', '2024-06-01'),
                (1, 3200.00, 'completed', '2024-07-15'),
                (2, 8500.00, 'completed', '2024-08-20'),
                (3, 450.75, 'completed', '2024-09-02'),
                (4, 120.00, 'cancelled', '2023-10-12');
            """)
            conn.commit()

    db.close()
    print("Database initialization complete.")

if __name__ == "__main__":
    init_database()
