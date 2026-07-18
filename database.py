"""
Local development database (SQLite).

This mirrors schema.sql (the PostgreSQL production schema) closely enough
that moving to Postgres later is a matter of swapping the connection layer,
not redesigning the data model. See README.md for the Postgres migration
notes.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "agrovision.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'farmer' CHECK(role IN ('farmer','agronomist','admin')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS farms (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    location        TEXT,
    size_ha         REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id         INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    variety         TEXT,
    area_ha         REAL,
    planting_date   TEXT,
    status          TEXT NOT NULL DEFAULT 'growing',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS harvests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    crop_id         INTEGER NOT NULL REFERENCES crops(id) ON DELETE CASCADE,
    harvest_date    TEXT NOT NULL,
    quantity_kg     REAL NOT NULL,
    quality_grade   TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS farm_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id         INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK(type IN ('expense','income')),
    category        TEXT NOT NULL,
    amount          REAL NOT NULL,
    record_date     TEXT NOT NULL,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]
