# 2. Store results in SQLite

**Status:** Accepted

## Context

Runs need to be saved so the dashboard and API can browse past results, and so reports can be written across runs.

## Decision

Use SQLite through the standard library `sqlite3` module, with handwritten SQL and parameterized queries.

## Reasons

- No server to install, so anyone can clone the project and run it.
- The two-table schema is simple enough that an ORM would hide more than it helps.
- Aggregate reports (`attraction_report`, `peak_interval`) are plain SQL that is easy to read and review.

## Consequences

- SQLite handles one writer at a time, which is fine for a single-user tool. A shared deployment would move to Postgres, and only `db.py` would change.
- The database path comes from the `QUEUECAST_DB` environment variable, and tests inject a temporary database through FastAPI dependency overrides.
