from __future__ import annotations

import sqlite3
from datetime import date, datetime

from app.models import MinuteBar, PositionState
from app.storage import (
    get_latest_saved_trade_before,
    get_saved_trade,
    init_db,
    list_saved_trades,
    save_trade,
    update_review_note,
    update_trade_positions,
)
from tests.test_parsers import SAMPLE_ORDERS


def bars() -> list[MinuteBar]:
    return [
        MinuteBar(
            datetime=datetime(2026, 6, 26, 9, 0),
            open=6100.0,
            high=6110.0,
            low=6098.0,
            close=6105.0,
            volume=12000.0,
        )
    ]


def test_save_and_load_trade(test_db) -> None:
    saved = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
    )
    loaded = get_saved_trade(saved.id)

    assert loaded is not None
    assert loaded.orders_csv == SAMPLE_ORDERS
    assert loaded.symbol_name == "フジクラ"
    assert loaded.minute_bars[0].close == 6105.0
    assert loaded.opening_position == PositionState()
    assert loaded.final_position == PositionState()
    assert list_saved_trades()[0].id == saved.id


def test_save_trade_deduplicates_same_content(test_db) -> None:
    first = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
    )
    second = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
    )

    assert second.id == first.id
    assert len(list_saved_trades()) == 1


def test_update_review_note(test_db) -> None:
    saved = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
    )

    update_review_note(saved.id, "エントリーを待てた。")

    loaded = get_saved_trade(saved.id)
    assert loaded is not None
    assert loaded.review_note == "エントリーを待てた。"


def test_save_and_load_positions(test_db) -> None:
    saved = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
        opening_position=PositionState(long_quantity=100, long_average_price=6100.0),
        final_position=PositionState(short_quantity=100, short_average_price=6120.0),
    )

    loaded = get_saved_trade(saved.id)

    assert loaded is not None
    assert loaded.opening_position.long_quantity == 100
    assert loaded.opening_position.long_average_price == 6100.0
    assert loaded.final_position.short_quantity == 100
    assert loaded.final_position.short_average_price == 6120.0


def test_update_trade_positions(test_db) -> None:
    saved = save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 26),
    )

    update_trade_positions(
        saved.id,
        opening_position=PositionState(long_quantity=200, long_average_price=6000.0),
        final_position=PositionState(long_quantity=100, long_average_price=6000.0),
    )
    loaded = get_saved_trade(saved.id)

    assert loaded is not None
    assert loaded.opening_position.long_quantity == 200
    assert loaded.final_position.long_quantity == 100


def test_latest_saved_trade_before_returns_same_ticker_prior_date(test_db) -> None:
    save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=bars(),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=date(2026, 6, 25),
        final_position=PositionState(long_quantity=100, long_average_price=6100.0),
    )
    save_trade(
        orders_csv=SAMPLE_ORDERS + "\n",
        bars=bars(),
        symbol_name="別銘柄",
        ticker="9999.T",
        target_date=date(2026, 6, 26),
        final_position=PositionState(short_quantity=100, short_average_price=6200.0),
    )

    latest = get_latest_saved_trade_before("5803.T", date(2026, 6, 26))

    assert latest is not None
    assert latest.final_position.long_quantity == 100


def test_init_db_adds_position_columns_to_existing_database(test_db) -> None:
    test_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(test_db) as connection:
        connection.execute(
            """
            CREATE TABLE saved_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                symbol_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                target_date TEXT NOT NULL,
                bars_count INTEGER NOT NULL,
                orders_csv TEXT NOT NULL,
                minute_bars_json TEXT NOT NULL,
                review_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    init_db()

    with sqlite3.connect(test_db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(saved_trades)")}
    assert "opening_long_quantity" in columns
    assert "final_short_average_price" in columns
