#!/usr/bin/env python3
"""
View SQLite database contents
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "paperflow.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def show_tables():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


def show_table_schema(table_name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    conn.close()
    return columns


def show_table_data(table_name, limit=10):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
    rows = cursor.fetchall()
    conn.close()
    return rows


def show_count(table_name):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
    result = cursor.fetchone()
    conn.close()
    return result["cnt"] if result else 0


def main():
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print("=" * 60)

    tables = show_tables()
    print(f"\nTables ({len(tables)}): {', '.join(tables)}\n")

    for table in tables:
        print(f"─── {table} ───")

        # Schema
        columns = show_table_schema(table)
        cols = [col["name"] for col in columns]
        print(f"  Columns: {', '.join(cols)}")

        # Count
        count = show_count(table)
        print(f"  Rows: {count}")

        # Sample data
        rows = show_table_data(table, limit=3)
        if rows:
            print(f"  Sample ({len(rows)} rows):")
            for row in rows:
                print(f"    {dict(row)}")
        print()


if __name__ == "__main__":
    main()
