from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from datetime import datetime

import pandas as pd

from app.models import OrderExecution, TradeSide

RAKUTEN_REQUIRED_COLUMNS = {
    "注文番号",
    "状況",
    "注文日時",
    "注文期限",
    "銘柄",
    "銘柄コード・市場",
    "取引",
    "売買",
    "約定数量[株/口]",
    "約定単価[円]",
}

VALID_SIDES: set[str] = {"買建", "売建", "買埋", "売埋"}


@dataclass(frozen=True)
class OrderCsvGroup:
    symbol_name: str
    symbol_code_market: str
    target_date: date
    orders_csv: str
    executions: list[OrderExecution]


def decode_csv_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSVをUTF-8またはCP932として読み込めませんでした。")


def read_csv_text(data: bytes) -> pd.DataFrame:
    text = decode_csv_bytes(data)
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def parse_number(value: str | int | float | None) -> float:
    if value is None:
        raise ValueError("数値が空です。")
    text = str(value).strip()
    if text in {"", "-"}:
        raise ValueError("数値が空です。")
    return float(text.replace(",", ""))


def parse_int(value: str | int | float | None) -> int:
    return int(parse_number(value))


def parse_rakuten_orders(data: bytes) -> list[OrderExecution]:
    df = read_csv_text(data)
    missing = sorted(RAKUTEN_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"楽天注文CSVの必須列が不足しています: {', '.join(missing)}")

    executions: list[OrderExecution] = []
    for _, row in df.iterrows():
        if str(row["状況"]).strip() != "約定":
            continue
        side = str(row["売買"]).strip()
        if side not in VALID_SIDES:
            continue

        quantity = parse_int(row["約定数量[株/口]"])
        if quantity <= 0:
            continue

        executions.append(
            OrderExecution(
                order_id=str(row["注文番号"]).strip(),
                symbol_name=str(row["銘柄"]).strip(),
                symbol_code_market=str(row["銘柄コード・市場"]).strip(),
                trade_type=str(row["取引"]).strip(),
                side=side,  # type: ignore[arg-type]
                executed_at=parse_execution_datetime(
                    str(row["注文期限"]).strip(),
                    str(row["注文日時"]).strip(),
                ),
                quantity=quantity,
                price=parse_number(row["約定単価[円]"]),
            )
        )

    return sorted(executions, key=lambda execution: execution.executed_at)


def group_rakuten_order_csv(data: bytes) -> list[OrderCsvGroup]:
    df = read_csv_text(data)
    missing = sorted(RAKUTEN_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"楽天注文CSVの必須列が不足しています: {', '.join(missing)}")

    group_rows: dict[tuple[str, date], list[int]] = {}
    group_executions: dict[tuple[str, date], list[OrderExecution]] = {}

    for index, row in df.iterrows():
        if str(row["状況"]).strip() != "約定":
            continue
        side = str(row["売買"]).strip()
        if side not in VALID_SIDES:
            continue

        quantity = parse_int(row["約定数量[株/口]"])
        if quantity <= 0:
            continue

        executed_at = parse_execution_datetime(
            str(row["注文期限"]).strip(),
            str(row["注文日時"]).strip(),
        )
        symbol_code_market = str(row["銘柄コード・市場"]).strip()
        key = (symbol_code_market, executed_at.date())
        execution = OrderExecution(
            order_id=str(row["注文番号"]).strip(),
            symbol_name=str(row["銘柄"]).strip(),
            symbol_code_market=symbol_code_market,
            trade_type=str(row["取引"]).strip(),
            side=side,  # type: ignore[arg-type]
            executed_at=executed_at,
            quantity=quantity,
            price=parse_number(row["約定単価[円]"]),
        )
        group_rows.setdefault(key, []).append(int(index))
        group_executions.setdefault(key, []).append(execution)

    groups: list[OrderCsvGroup] = []
    for key in sorted(group_rows, key=lambda item: (item[1], item[0])):
        row_indexes = group_rows[key]
        executions = sorted(group_executions[key], key=lambda execution: execution.executed_at)
        group_df = df.loc[row_indexes]
        groups.append(
            OrderCsvGroup(
                symbol_name=executions[0].symbol_name,
                symbol_code_market=executions[0].symbol_code_market,
                target_date=key[1],
                orders_csv=group_df.to_csv(index=False, lineterminator="\n"),
                executions=executions,
            )
        )
    return groups


def parse_execution_datetime(order_deadline: str, order_datetime: str) -> datetime:
    date_part = datetime.strptime(order_deadline, "%Y/%m/%d").date()
    time_match = re.search(r"(\d{1,2}):(\d{2}):(\d{2})$", order_datetime)
    if not time_match:
        raise ValueError(f"注文日時を解析できません: {order_datetime}")
    hour, minute, second = [int(part) for part in time_match.groups()]
    return datetime(date_part.year, date_part.month, date_part.day, hour, minute, second)


def yahoo_ticker_from_symbol_code_market(symbol_code_market: str) -> str:
    match = re.match(r"\s*(\d{4})\b", symbol_code_market)
    if not match:
        raise ValueError(f"銘柄コードを解析できません: {symbol_code_market}")
    return f"{match.group(1)}.T"
