"""SQLite persistence for simulation runs. Standard library only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from queuecast.metrics import IntervalMetric, Summary

SCHEMA = """
CREATE TABLE IF NOT EXISTS simulation_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    attraction_id         TEXT    NOT NULL,
    seed                  INTEGER NOT NULL,
    priority_share        REAL    NOT NULL,
    crowd_multiplier      REAL    NOT NULL,
    created_at            TEXT    NOT NULL,
    guests_served         INTEGER NOT NULL,
    standby_avg_wait_min  REAL    NOT NULL,
    standby_p90_wait_min  REAL    NOT NULL,
    standby_max_wait_min  REAL    NOT NULL,
    priority_avg_wait_min REAL    NOT NULL,
    throughput_per_hour   REAL    NOT NULL,
    utilization           REAL    NOT NULL,
    breakdowns            INTEGER NOT NULL,
    downtime_min          REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS interval_metrics (
    run_id                INTEGER NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    bucket_start_min      INTEGER NOT NULL,
    arrivals              INTEGER NOT NULL,
    standby_avg_wait_min  REAL,
    priority_avg_wait_min REAL,
    PRIMARY KEY (run_id, bucket_start_min)
);

CREATE INDEX IF NOT EXISTS idx_runs_attraction ON simulation_runs(attraction_id);
"""


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_run(
        self,
        attraction_id: str,
        seed: int,
        priority_share: float,
        crowd_multiplier: float,
        summary: Summary,
        intervals: list[IntervalMetric],
    ) -> int:
        s = summary
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO simulation_runs (
                    attraction_id, seed, priority_share, crowd_multiplier, created_at,
                    guests_served, standby_avg_wait_min, standby_p90_wait_min,
                    standby_max_wait_min, priority_avg_wait_min, throughput_per_hour,
                    utilization, breakdowns, downtime_min
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attraction_id, seed, priority_share, crowd_multiplier,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    s.guests_served, s.standby_avg_wait_min, s.standby_p90_wait_min,
                    s.standby_max_wait_min, s.priority_avg_wait_min, s.throughput_per_hour,
                    s.utilization, s.breakdowns, s.downtime_min,
                ),
            )
            run_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO interval_metrics VALUES (?, ?, ?, ?, ?)",
                [
                    (run_id, m.bucket_start_min, m.arrivals,
                     m.standby_avg_wait_min, m.priority_avg_wait_min)
                    for m in intervals
                ],
            )
        return run_id

    def get_run(self, run_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM simulation_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, attraction_id: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM simulation_runs"
        params: tuple = ()
        if attraction_id:
            sql += " WHERE attraction_id = ?"
            params = (attraction_id,)
        sql += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, (*params, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_intervals(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT bucket_start_min, arrivals, standby_avg_wait_min, priority_avg_wait_min "
                "FROM interval_metrics WHERE run_id = ? ORDER BY bucket_start_min",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def peak_interval(self, run_id: int) -> dict | None:
        """The 15-minute window with the longest standby wait."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT bucket_start_min, standby_avg_wait_min
                FROM interval_metrics
                WHERE run_id = ? AND standby_avg_wait_min IS NOT NULL
                ORDER BY standby_avg_wait_min DESC, bucket_start_min ASC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def attraction_report(self) -> list[dict]:
        """Aggregate stats per attraction across all saved runs."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT attraction_id,
                       COUNT(*)                            AS runs,
                       ROUND(AVG(standby_avg_wait_min), 1) AS avg_standby_wait_min,
                       ROUND(MAX(standby_p90_wait_min), 1) AS worst_p90_wait_min,
                       ROUND(AVG(throughput_per_hour), 1)  AS avg_throughput_per_hour
                FROM simulation_runs
                GROUP BY attraction_id
                ORDER BY avg_standby_wait_min DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]
