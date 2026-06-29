from __future__ import annotations

from datetime import datetime

from app.models import OrderExecution
from app.profit_loss import build_execution_rows


def execution(order_id: str, side: str, quantity: int, price: float) -> OrderExecution:
    return OrderExecution(
        order_id=order_id,
        symbol_name="フジクラ",
        symbol_code_market="5803 東証(SOR)",
        trade_type="信用返済" if side in {"買埋", "売埋"} else "信用新規",
        side=side,  # type: ignore[arg-type]
        executed_at=datetime(2026, 6, 26, 9, int(order_id)),
        quantity=quantity,
        price=price,
    )


def test_buy_close_uses_short_average_price() -> None:
    rows = build_execution_rows(
        [
            execution("01", "売建", 100, 6120.0),
            execution("02", "買埋", 100, 6130.0),
        ]
    )

    assert rows[0].realized_pnl is None
    assert rows[1].realized_pnl == -1000.0


def test_sell_close_uses_long_average_price() -> None:
    rows = build_execution_rows(
        [
            execution("01", "買建", 100, 6123.0),
            execution("02", "売埋", 100, 6133.0),
        ]
    )

    assert rows[1].realized_pnl == 1000.0


def test_weighted_average_price_is_used_for_closes() -> None:
    rows = build_execution_rows(
        [
            execution("01", "買建", 100, 6100.0),
            execution("02", "買建", 100, 6200.0),
            execution("03", "売埋", 100, 6300.0),
        ]
    )

    assert rows[2].realized_pnl == 15000.0


def test_partial_close_keeps_remaining_average_price() -> None:
    rows = build_execution_rows(
        [
            execution("01", "売建", 200, 6200.0),
            execution("02", "買埋", 100, 6100.0),
            execution("03", "買埋", 100, 6150.0),
        ]
    )

    assert rows[1].realized_pnl == 10000.0
    assert rows[2].realized_pnl == 5000.0


def test_close_without_matching_position_has_no_pnl() -> None:
    rows = build_execution_rows([execution("01", "売埋", 100, 6133.0)])

    assert rows[0].realized_pnl is None


def test_close_over_position_quantity_has_no_pnl() -> None:
    rows = build_execution_rows(
        [
            execution("01", "買建", 100, 6123.0),
            execution("02", "売埋", 200, 6133.0),
        ]
    )

    assert rows[1].realized_pnl is None
