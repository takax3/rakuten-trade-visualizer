from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.models import MinuteBar


def fetch_yahoo_minute_bars(ticker: str, target_date: date) -> list[MinuteBar]:
    today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    if target_date < today_jst - timedelta(days=60):
        raise ValueError("Yahoo Financeの1分足は直近60日を超える日付を取得できません。")
    if target_date > today_jst:
        raise ValueError("未来日の1分足は取得できません。対象日の注文CSVを確認してください。")

    end_date = target_date + timedelta(days=1)
    df = yf.download(
        ticker,
        start=target_date.isoformat(),
        end=end_date.isoformat(),
        interval="1m",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        raise ValueError("Yahoo Financeから1分足を取得できませんでした。")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    index = pd.to_datetime(df.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    index = index.tz_convert("Asia/Tokyo").tz_localize(None)
    df = df.copy()
    df.index = index
    df = df[df.index.date == target_date]
    if df.empty:
        raise ValueError("取得した1分足に対象日のデータがありません。")

    bars: list[MinuteBar] = []
    for timestamp, row in df.iterrows():
        bars.append(
            MinuteBar(
                datetime=timestamp.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]) if "Volume" in row and not pd.isna(row["Volume"]) else None,
            )
        )
    return bars
