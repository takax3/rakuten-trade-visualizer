from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO

from fastapi import UploadFile
from starlette.requests import Request

from app.main import review_detail, reviews, save_opening_position, save_review_note, visualize
from app.models import MinuteBar, PositionState
from app.storage import get_saved_trade, list_saved_trades, save_trade
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
    assert context["ohlc_summary"].open_price == 6120.0
    assert context["ohlc_summary"].close_price == 6133.0
    assert context["ohlc_summary"].high_price == 6145.0
    assert context["ohlc_summary"].low_price == 6110.0
    assert len(list_saved_trades()) == 1
    assert context["opening_position"] == PositionState()
    assert context["pnl_summary"].close_price == 6133.0
    assert context["pnl_summary"].realized_pnl == 0
    assert context["pnl_summary"].unrealized_pnl == 0
    assert context["pnl_summary"].total_pnl == 0


def test_review_detail_and_note_update(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)
    asyncio.run(visualize(request(), orders_csv=upload_orders()))
    saved = list_saved_trades()[0]

    detail = asyncio.run(review_detail(request(), saved.id))
    detail_context = detail.context
    assert detail.status_code == 200
    assert detail_context["execution_rows"]
    assert detail_context["saved_trade"].id == saved.id
    assert detail_context["pnl_summary"].close_price == 6133.0
    assert detail_context["ohlc_summary"].high_price == 6145.0

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


def test_visualize_saves_multiple_symbol_date_groups(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)

    response = asyncio.run(visualize(request(), orders_csv=upload_text(MULTI_GROUP_ORDERS)))

    assert response.status_code == 200
    assert len(list_saved_trades()) == 3
    assert "3件の銘柄・日付別データを保存しました" in response.context["warnings"][-1]


def test_visualize_inherits_latest_position_for_same_ticker(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)
    save_trade(
        orders_csv=SAMPLE_ORDERS,
        bars=yahoo_bars("5803.T", None),
        symbol_name="フジクラ",
        ticker="5803.T",
        target_date=datetime(2026, 6, 25).date(),
        final_position=PositionState(long_quantity=100, long_average_price=6100.0),
    )

    response = asyncio.run(visualize(request(), orders_csv=upload_text(CLOSE_LONG_ORDERS)))
    rows = response.context["execution_rows"]

    assert response.context["opening_position"].long_quantity == 100
    assert rows[0].realized_pnl == 3000.0
    assert rows[0].position.long_quantity == 0


def test_save_opening_position_recalculates_rows(monkeypatch, test_db) -> None:
    monkeypatch.setattr("app.main.fetch_yahoo_minute_bars", yahoo_bars)
    asyncio.run(visualize(request(), orders_csv=upload_text(CLOSE_LONG_ORDERS)))
    saved = list_saved_trades()[0]

    response = asyncio.run(
        save_opening_position(
            saved.id,
            opening_long_quantity=100,
            opening_long_average_price=6100.0,
            opening_short_quantity=0,
            opening_short_average_price=0,
        )
    )
    loaded = get_saved_trade(saved.id)

    assert response.status_code == 303
    assert loaded is not None
    assert loaded.opening_position.long_quantity == 100
    assert loaded.final_position.long_quantity == 0

    detail = asyncio.run(review_detail(request(), saved.id))
    summary = detail.context["pnl_summary"]
    assert summary.realized_pnl == 3000.0
    assert summary.unrealized_pnl == 0
    assert summary.total_pnl == 3000.0


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def upload_orders() -> UploadFile:
    return UploadFile(file=BytesIO(SAMPLE_ORDERS.encode("utf-8")), filename="orders.csv")


def upload_text(text: str) -> UploadFile:
    return UploadFile(file=BytesIO(text.encode("utf-8")), filename="orders.csv")


CSV_HEADER = (
    "注文番号,アルゴ注文番号,繰越区分,状況,状況(逆指値),セット注文,注文日時,執行条件,注文期限,銘柄,"
    "銘柄コード・市場,取引,売買,口座,注文方法,アルゴ注文情報,逆指値条件,セット注文条件,信用区分(弁済期限),"
    "注文数量[株/口],約定数量[株/口],注文金額[円],（ポイント利用）,注文単価[円],約定単価[円],現在値[円],約定代金[円],手数料[円]"
)


CLOSE_LONG_ORDERS = CSV_HEADER + """
"0101","","","約定","-","-","06/26 09:01:00","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用返済","売埋","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,130.0","6,130.0","6,130.0","613,000","0"
"""


MULTI_GROUP_ORDERS = CSV_HEADER + """
"0201","","","約定","-","-","06/26 09:01:00","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用新規","買建","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,100.0","6,100.0","6,100.0","610,000","0"
"0202","","","約定","-","-","06/27 09:01:00","本日中","2026/06/27","フジクラ","5803 東証(SOR)","信用新規","買建","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,200.0","6,200.0","6,200.0","620,000","0"
"0203","","","約定","-","-","06/26 09:01:00","本日中","2026/06/26","トヨタ","7203 東証(SOR)","信用新規","売建","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","3,000.0","3,000.0","3,000.0","300,000","0"
"""
