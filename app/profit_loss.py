from __future__ import annotations

from dataclasses import dataclass

from app.models import ExecutionRow, OrderExecution


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
    long_position = Position()
    short_position = Position()
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

        rows.append(ExecutionRow(execution=execution, realized_pnl=realized_pnl))

    return rows
