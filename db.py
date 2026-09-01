# -*- coding: utf-8 -*-
"""SQLite 저장소: 월별 기록 및 실거래가 이력."""

import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from config import DATA_DIR, DB_PATH, ALL_COMPLEXES

MONTHLY_FIELDS = [
    "t13_price", "t13_low_floor",
    "t12_price", "t12_low_floor",
    "dusan_price", "dusan_low_floor",
    "boram_price", "boram_low_floor",
    "loan_self", "loan_spouse",
    "cash_self", "cash_spouse",
    "reserve_fund",
]


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_records (
            year_month TEXT PRIMARY KEY,
            t13_price INTEGER NOT NULL DEFAULT 0,
            t13_low_floor INTEGER NOT NULL DEFAULT 0,
            t12_price INTEGER NOT NULL DEFAULT 0,
            t12_low_floor INTEGER NOT NULL DEFAULT 0,
            dusan_price INTEGER NOT NULL DEFAULT 0,
            dusan_low_floor INTEGER NOT NULL DEFAULT 1,
            boram_price INTEGER NOT NULL DEFAULT 0,
            boram_low_floor INTEGER NOT NULL DEFAULT 0,
            loan_self INTEGER NOT NULL DEFAULT 0,
            loan_spouse INTEGER NOT NULL DEFAULT 0,
            cash_self INTEGER NOT NULL DEFAULT 0,
            cash_spouse INTEGER NOT NULL DEFAULT 0,
            reserve_fund INTEGER NOT NULL DEFAULT 300000000,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS real_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complex_key TEXT NOT NULL,
            apt_name TEXT,
            deal_date TEXT NOT NULL,
            price INTEGER NOT NULL,
            area_m2 REAL,
            floor INTEGER,
            dong TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE(complex_key, deal_date, price, area_m2, floor, apt_name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_monthly_record(year_month: str, values: dict):
    conn = _connect()
    cur = conn.cursor()
    cols = ", ".join(MONTHLY_FIELDS)
    placeholders = ", ".join(f":{f}" for f in MONTHLY_FIELDS)
    update_clause = ", ".join(f"{f}=excluded.{f}" for f in MONTHLY_FIELDS)
    params = {f: values.get(f, 0) for f in MONTHLY_FIELDS}
    params["year_month"] = year_month
    params["updated_at"] = datetime.now(timezone.utc).isoformat()
    cur.execute(
        f"""
        INSERT INTO monthly_records (year_month, {cols}, updated_at)
        VALUES (:year_month, {placeholders}, :updated_at)
        ON CONFLICT(year_month) DO UPDATE SET
            {update_clause},
            updated_at=excluded.updated_at
        """,
        params,
    )
    conn.commit()
    conn.close()


def get_monthly_record(year_month: str):
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM monthly_records WHERE year_month = ?", (year_month,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_year_months():
    conn = _connect()
    rows = conn.execute(
        "SELECT year_month FROM monthly_records ORDER BY year_month DESC"
    ).fetchall()
    conn.close()
    return [r["year_month"] for r in rows]


def get_latest_record():
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM monthly_records ORDER BY year_month DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_monthly_records_df() -> pd.DataFrame:
    conn = _connect()
    df = pd.read_sql_query(
        "SELECT * FROM monthly_records ORDER BY year_month ASC", conn
    )
    conn.close()
    return df


def insert_transactions(rows: list):
    """rows: list of dict with keys complex_key, apt_name, deal_date, price,
    area_m2, floor, dong. 중복은 무시."""
    if not rows:
        return 0
    conn = _connect()
    cur = conn.cursor()
    fetched_at = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for r in rows:
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO real_transactions
                    (complex_key, apt_name, deal_date, price, area_m2, floor, dong, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.get("complex_key"),
                    r.get("apt_name"),
                    r.get("deal_date"),
                    r.get("price"),
                    r.get("area_m2"),
                    r.get("floor"),
                    r.get("dong"),
                    fetched_at,
                ),
            )
            if cur.rowcount:
                inserted += 1
        except sqlite3.Error:
            continue
    conn.commit()
    conn.close()
    return inserted


def get_recent_transactions(complex_key: str, limit: int = 15) -> pd.DataFrame:
    conn = _connect()
    df = pd.read_sql_query(
        """
        SELECT deal_date, apt_name, price, area_m2, floor, dong
        FROM real_transactions
        WHERE complex_key = ?
        ORDER BY deal_date DESC, id DESC
        LIMIT ?
        """,
        conn,
        params=(complex_key, limit),
    )
    conn.close()
    return df


def get_last_fetch_time() -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT MAX(fetched_at) AS ts FROM real_transactions"
    ).fetchone()
    conn.close()
    return row["ts"] if row else None


def get_setting(key: str, default=None):
    conn = _connect()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, json.JSONDecodeError):
        return default


def set_setting(key: str, value):
    conn = _connect()
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_complex_config() -> dict:
    """설정 테이블에 저장된 단지 설정(LAWD_CD/키워드)이 있으면 이를 우선 사용,
    없으면 config.py의 기본값을 반환."""
    stored = get_setting("complex_config")
    merged = {}
    for key, base in ALL_COMPLEXES.items():
        merged[key] = dict(base)
        if stored and key in stored:
            merged[key].update(stored[key])
    return merged
