from __future__ import annotations

from dataclasses import dataclass

from app.models import DailyPnlSummary, ExecutionRow, OrderExecution, PositionState


@dataclass
class Position:
    quantity: int = 0
    average_price: float = 0.0

    def add(self, quantity: int, price: float) -> None:
        total_cost = self.average_price * self.quantity + price * quantity
        self.quantity += quantity
        self.average_price = total_cost / self.quantity

    def can_close(self, quantity: int) -> bool:
        return self.quantity >= quantity

    def close(self, quantity: int) -> None:
        self.quantity -= quantity
        if self.quantity == 0:
            self.average_price = 0.0


def build_execution_rows(executions: list[OrderExecution]) -> list[ExecutionRow]:
    return build_execution_rows_with_opening(executions, PositionState())


def build_execution_rows_with_opening(
    executions: list[OrderExecution],
    opening_position: PositionState,
) -> list[ExecutionRow]:
    long_position = Position(
        quantity=opening_position.long_quantity,
        average_price=opening_position.long_average_price,
    )
    short_position = Position(
        quantity=opening_position.short_quantity,
        average_price=opening_position.short_average_price,
    )
    rows: list[ExecutionRow] = []

    for execution in executions:
        realized_pnl: float | None = None

        if execution.side == "買建":
            long_position.add(execution.quantity, execution.price)
        elif execution.side == "売埋":
            if long_position.can_close(execution.quantity):
                realized_pnl = (execution.price - long_position.average_price) * execution.quantity
                long_position.close(execution.quantity)
        elif execution.side == "売建":
            short_position.add(execution.quantity, execution.price)
        elif execution.side == "買埋":
            if short_position.can_close(execution.quantity):
                realized_pnl = (short_position.average_price - execution.price) * execution.quantity
                short_position.close(execution.quantity)

        rows.append(
            ExecutionRow(
                execution=execution,
                position=PositionState(
                    long_quantity=long_position.quantity,
                    long_average_price=long_position.average_price,
                    short_quantity=short_position.quantity,
                    short_average_price=short_position.average_price,
                ),
                realized_pnl=realized_pnl,
            )
        )

    return rows


def build_final_position(
    executions: list[OrderExecution],
    opening_position: PositionState,
) -> PositionState:
    rows = build_execution_rows_with_opening(executions, opening_position)
    if rows:
        return rows[-1].position
    return opening_position


def build_daily_pnl_summary(
    execution_rows: list[ExecutionRow],
    final_position: PositionState,
    close_price: float,
) -> DailyPnlSummary:
    realized_pnl = sum(row.realized_pnl or 0 for row in execution_rows)
    long_unrealized_pnl = final_position.long_quantity * (
        close_price - final_position.long_average_price
    )
    short_unrealized_pnl = final_position.short_quantity * (
        final_position.short_average_price - close_price
    )
    unrealized_pnl = long_unrealized_pnl + short_unrealized_pnl
    return DailyPnlSummary(
        close_price=close_price,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=realized_pnl + unrealized_pnl,
    )
