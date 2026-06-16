import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from settings import Database

_db_path = Path(Database.path)
_db_path.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (code, date)
        );
        CREATE INDEX IF NOT EXISTS idx_ohlcv_code ON ohlcv(code);
        CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON ohlcv(date);

        CREATE TABLE IF NOT EXISTS fetch_log (
            code TEXT PRIMARY KEY,
            last_fetched TEXT NOT NULL
        );
    """)
    conn.close()


def is_cache_fresh(code: str) -> bool:
    if Database.cache_hours == 0:
        return False
    conn = _get_conn()
    row = conn.execute(
        "SELECT last_fetched FROM fetch_log WHERE code = ?", (code,)
    ).fetchone()
    conn.close()
    if row is None:
        return False
    last = datetime.fromisoformat(row[0])
    return datetime.now() - last < timedelta(hours=Database.cache_hours)


def save_ohlcv(code: str, df: pd.DataFrame):
    if df.empty:
        return
    conn = _get_conn()
    rows = []
    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        rows.append((
            code, date_str,
            float(row["Open"]), float(row["High"]),
            float(row["Low"]), float(row["Close"]),
            int(row["Volume"]),
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO ohlcv (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO fetch_log (code, last_fetched) VALUES (?, ?)",
        (code, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_ohlcv(code: str, days: int = 500) -> pd.DataFrame:
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM ohlcv WHERE code = ? AND date >= ? ORDER BY date",
        (code, cutoff),
    ).fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


init_db()
