from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.models import MinuteBar, PositionState


DEFAULT_DB_PATH = Path("data/trades.db")


@dataclass(frozen=True)
class SavedTrade:
    id: int
    content_hash: str
    symbol_name: str
    ticker: str
    target_date: date
    bars_count: int
    orders_csv: str
    minute_bars: list[MinuteBar]
    opening_position: PositionState
    final_position: PositionState
    review_note: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SavedTradeSummary:
    id: int
    symbol_name: str
    ticker: str
    target_date: date
    bars_count: int
    review_note: str
    created_at: datetime
    updated_at: datetime


def get_db_path() -> Path:
    configured = os.environ.get("TRADE_VISUALIZER_DB_PATH")
    return Path(configured) if configured else DEFAULT_DB_PATH


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                symbol_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                target_date TEXT NOT NULL,
                bars_count INTEGER NOT NULL,
                orders_csv TEXT NOT NULL,
                minute_bars_json TEXT NOT NULL,
                opening_long_quantity INTEGER NOT NULL DEFAULT 0,
                opening_long_average_price REAL NOT NULL DEFAULT 0,
                opening_short_quantity INTEGER NOT NULL DEFAULT 0,
                opening_short_average_price REAL NOT NULL DEFAULT 0,
                final_long_quantity INTEGER NOT NULL DEFAULT 0,
                final_long_average_price REAL NOT NULL DEFAULT 0,
                final_short_quantity INTEGER NOT NULL DEFAULT 0,
                final_short_average_price REAL NOT NULL DEFAULT 0,
                review_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(saved_trades)").fetchall()
        }
        for column_name, column_type in POSITION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE saved_trades ADD COLUMN {column_name} {column_type} NOT NULL DEFAULT 0"
                )


POSITION_COLUMNS = {
    "opening_long_quantity": "INTEGER",
    "opening_long_average_price": "REAL",
    "opening_short_quantity": "INTEGER",
    "opening_short_average_price": "REAL",
    "final_long_quantity": "INTEGER",
    "final_long_average_price": "REAL",
    "final_short_quantity": "INTEGER",
    "final_short_average_price": "REAL",
}


def save_trade(
    *,
    orders_csv: str,
    bars: list[MinuteBar],
    symbol_name: str,
    ticker: str,
    target_date: date,
    opening_position: PositionState | None = None,
    final_position: PositionState | None = None,
) -> SavedTrade:
    init_db()
    opening_position = opening_position or PositionState()
    final_position = final_position or opening_position
    minute_bars_json = serialize_minute_bars(bars)
    content_hash = build_content_hash(orders_csv, minute_bars_json)
    now = datetime.now().replace(microsecond=0).isoformat()

    with sqlite3.connect(get_db_path()) as connection:
        connection.row_factory = sqlite3.Row
        existing = connection.execute(
            "SELECT id FROM saved_trades WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO saved_trades (
                    content_hash, symbol_name, ticker, target_date, bars_count,
                    orders_csv, minute_bars_json,
                    opening_long_quantity, opening_long_average_price,
                    opening_short_quantity, opening_short_average_price,
                    final_long_quantity, final_long_average_price,
                    final_short_quantity, final_short_average_price,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_hash,
                    symbol_name,
                    ticker,
                    target_date.isoformat(),
                    len(bars),
                    orders_csv,
                    minute_bars_json,
                    opening_position.long_quantity,
                    opening_position.long_average_price,
                    opening_position.short_quantity,
                    opening_position.short_average_price,
                    final_position.long_quantity,
                    final_position.long_average_price,
                    final_position.short_quantity,
                    final_position.short_average_price,
                    now,
                    now,
                ),
            )
            trade_id = int(cursor.lastrowid)
        else:
            trade_id = int(existing["id"])
            connection.execute(
                """
                UPDATE saved_trades
                SET symbol_name = ?, ticker = ?, target_date = ?, bars_count = ?,
                    orders_csv = ?, minute_bars_json = ?,
                    opening_long_quantity = ?, opening_long_average_price = ?,
                    opening_short_quantity = ?, opening_short_average_price = ?,
                    final_long_quantity = ?, final_long_average_price = ?,
                    final_short_quantity = ?, final_short_average_price = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    symbol_name,
                    ticker,
                    target_date.isoformat(),
                    len(bars),
                    orders_csv,
                    minute_bars_json,
                    opening_position.long_quantity,
                    opening_position.long_average_price,
                    opening_position.short_quantity,
                    opening_position.short_average_price,
                    final_position.long_quantity,
                    final_position.long_average_price,
                    final_position.short_quantity,
                    final_position.short_average_price,
                    now,
                    trade_id,
                ),
            )

    saved = get_saved_trade(trade_id)
    if saved is None:
        raise RuntimeError("保存した振り返りデータを読み込めませんでした。")
    return saved


def list_saved_trades() -> list[SavedTradeSummary]:
    init_db()
    with sqlite3.connect(get_db_path()) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, symbol_name, ticker, target_date, bars_count, review_note, created_at, updated_at
            FROM saved_trades
            ORDER BY target_date DESC, updated_at DESC, id DESC
            """
        ).fetchall()
    return [summary_from_row(row) for row in rows]


def get_latest_saved_trade_before(ticker: str, target_date: date) -> SavedTrade | None:
    init_db()
    with sqlite3.connect(get_db_path()) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM saved_trades
            WHERE ticker = ? AND target_date < ?
            ORDER BY target_date DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (ticker, target_date.isoformat()),
        ).fetchone()
    return trade_from_row(row) if row is not None else None


def get_saved_trade(trade_id: int) -> SavedTrade | None:
    init_db()
    with sqlite3.connect(get_db_path()) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM saved_trades WHERE id = ?",
            (trade_id,),
        ).fetchone()
    return trade_from_row(row) if row is not None else None


def update_review_note(trade_id: int, review_note: str) -> None:
    init_db()
    now = datetime.now().replace(microsecond=0).isoformat()
    with sqlite3.connect(get_db_path()) as connection:
        connection.execute(
            "UPDATE saved_trades SET review_note = ?, updated_at = ? WHERE id = ?",
            (review_note, now, trade_id),
        )


def update_trade_positions(
    trade_id: int,
    *,
    opening_position: PositionState,
    final_position: PositionState,
) -> None:
    init_db()
    now = datetime.now().replace(microsecond=0).isoformat()
    with sqlite3.connect(get_db_path()) as connection:
        connection.execute(
            """
            UPDATE saved_trades
            SET opening_long_quantity = ?, opening_long_average_price = ?,
                opening_short_quantity = ?, opening_short_average_price = ?,
                final_long_quantity = ?, final_long_average_price = ?,
                final_short_quantity = ?, final_short_average_price = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                opening_position.long_quantity,
                opening_position.long_average_price,
                opening_position.short_quantity,
                opening_position.short_average_price,
                final_position.long_quantity,
                final_position.long_average_price,
                final_position.short_quantity,
                final_position.short_average_price,
                now,
                trade_id,
            ),
        )


def serialize_minute_bars(bars: list[MinuteBar]) -> str:
    payload = [
        {
            "datetime": bar.datetime.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def deserialize_minute_bars(data: str) -> list[MinuteBar]:
    payload: list[dict[str, Any]] = json.loads(data)
    return [
        MinuteBar(
            datetime=datetime.fromisoformat(item["datetime"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]) if item["volume"] is not None else None,
        )
        for item in payload
    ]


def build_content_hash(orders_csv: str, minute_bars_json: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(orders_csv.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(minute_bars_json.encode("utf-8"))
    return hasher.hexdigest()


def trade_from_row(row: sqlite3.Row) -> SavedTrade:
    return SavedTrade(
        id=int(row["id"]),
        content_hash=str(row["content_hash"]),
        symbol_name=str(row["symbol_name"]),
        ticker=str(row["ticker"]),
        target_date=date.fromisoformat(str(row["target_date"])),
        bars_count=int(row["bars_count"]),
        orders_csv=str(row["orders_csv"]),
        minute_bars=deserialize_minute_bars(str(row["minute_bars_json"])),
        opening_position=PositionState(
            long_quantity=int(row["opening_long_quantity"]),
            long_average_price=float(row["opening_long_average_price"]),
            short_quantity=int(row["opening_short_quantity"]),
            short_average_price=float(row["opening_short_average_price"]),
        ),
        final_position=PositionState(
            long_quantity=int(row["final_long_quantity"]),
            long_average_price=float(row["final_long_average_price"]),
            short_quantity=int(row["final_short_quantity"]),
            short_average_price=float(row["final_short_average_price"]),
        ),
        review_note=str(row["review_note"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def summary_from_row(row: sqlite3.Row) -> SavedTradeSummary:
    return SavedTradeSummary(
        id=int(row["id"]),
        symbol_name=str(row["symbol_name"]),
        ticker=str(row["ticker"]),
        target_date=date.fromisoformat(str(row["target_date"])),
        bars_count=int(row["bars_count"]),
        review_note=str(row["review_note"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )
