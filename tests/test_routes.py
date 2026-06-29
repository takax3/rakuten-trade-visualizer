from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO

from fastapi import UploadFile
from starlette.requests import Request

from app.main import review_detail, reviews, save_review_note, visualize
from app.models import MinuteBar
from app.storage import list_saved_trades
from tests.test_parsers import SAMPLE_ORDERS


def yahoo_bars(_: str, __) -> list[MinuteBar]:
    return [
        MinuteBar(
            datetime=datetime(2026, 6, 26, 14, 20),
            open=6120.0,
            high=6140.0,
            low=6110.0,
            close=6130.0,
            volume=10000.0,
        ),
        MinuteBar(
            datetime=datetime(2026, 6, 26, 14, 21),
            open=6130.0,
            high=6145.0,
            low=6125.0,
            close=6133.0,
            volume=9000.0,
        ),
    ]


def test_visualize_uses_yahoo_and_saves_trade(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)

    response = asyncio.run(visualize(request(), orders_csv=upload_orders()))
    context = response.context

    assert response.status_code == 200
    assert context["saved_trade"] is not None
    assert context["symbol_name"] == "フジクラ"
    assert context["bars_count"] == 2
    assert len(list_saved_trades()) == 1


def test_review_detail_and_note_update(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)
    asyncio.run(visualize(request(), orders_csv=upload_orders()))
    saved = list_saved_trades()[0]

    detail = asyncio.run(review_detail(request(), saved.id))
    detail_context = detail.context
    assert detail.status_code == 200
    assert detail_context["execution_rows"]
    assert detail_context["saved_trade"].id == saved.id

    note_response = asyncio.run(save_review_note(saved.id, review_note="損切り判断を早める。"))
    updated_detail = asyncio.run(review_detail(request(), saved.id))

    assert note_response.status_code == 303
    assert updated_detail.context["saved_trade"].review_note == "損切り判断を早める。"


def test_reviews_list_shows_final_pnl(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)
    asyncio.run(visualize(request(), orders_csv=upload_orders()))

    response = asyncio.run(reviews(request()))
    saved_trade_view = response.context["saved_trades"][0]

    assert response.status_code == 200
    assert saved_trade_view.trade.symbol_name == "フジクラ"
    assert saved_trade_view.final_pnl == 0


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def upload_orders() -> UploadFile:
    return UploadFile(file=BytesIO(SAMPLE_ORDERS.encode("utf-8")), filename="orders.csv")
