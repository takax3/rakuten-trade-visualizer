from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


TradeSide = Literal["買建", "売建", "買埋", "売埋"]


@dataclass(frozen=True)
class OrderExecution:
    order_id: str
    symbol_name: str
    symbol_code_market: str
    trade_type: str
    side: TradeSide
    executed_at: datetime
    quantity: int
    price: float


@dataclass(frozen=True)
class ExecutionRow:
    execution: OrderExecution
    realized_pnl: float | None = None


@dataclass(frozen=True)
class MinuteBar:
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
