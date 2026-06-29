from __future__ import annotations

from datetime import datetime

from app.parsers import (
    parse_number,
    parse_rakuten_orders,
    yahoo_ticker_from_symbol_code_market,
)


SAMPLE_ORDERS = """注文番号,アルゴ注文番号,繰越区分,状況,状況(逆指値),セット注文,注文日時,執行条件,注文期限,銘柄,銘柄コード・市場,取引,売買,口座,注文方法,アルゴ注文情報,逆指値条件,セット注文条件,信用区分(弁済期限),注文数量[株/口],約定数量[株/口],注文金額[円],（ポイント利用）,注文単価[円],約定単価[円],現在値[円],約定代金[円],手数料[円]
"0081","","","約定","-","-","06/26 14:28:37","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用返済","売埋","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,133.0","6,133.0","6,131.0","613,300","0"
"0080","","","約定","-","-","06/26 14:26:10","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用新規","買建","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,123.0","6,123.0","6,131.0","612,300","0"
"0079","","","約定","-","-","06/26 14:22:24","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用返済","買埋","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,130.0","6,130.0","6,131.0","613,000","0"
"0078","","","約定","-","-","06/26 14:20:49","本日中","2026/06/26","フジクラ","5803 東証(SOR)","信用新規","売建","特定","通常注文","-","-","-","制度(6ヶ月)","100","100","-","-","6,120.0","6,120.0","6,131.0","612,000","0"
"""


def test_parse_rakuten_orders_extracts_executions() -> None:
    executions = parse_rakuten_orders(SAMPLE_ORDERS.encode("utf-8"))

    assert len(executions) == 4
    assert executions[0].order_id == "0078"
    assert executions[0].side == "売建"
    assert executions[0].executed_at == datetime(2026, 6, 26, 14, 20, 49)
    assert executions[-1].price == 6133.0


def test_parse_number_accepts_comma_values() -> None:
    assert parse_number("6,133.0") == 6133.0
    assert parse_number("613,300") == 613300.0


def test_yahoo_ticker_from_rakuten_symbol() -> None:
    assert yahoo_ticker_from_symbol_code_market("5803 東証(SOR)") == "5803.T"
