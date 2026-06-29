from __future__ import annotations

from datetime import date, datetime

from app.models import MinuteBar
from app.storage import get_saved_trade, list_saved_trades, save_trade, update_review_note
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
