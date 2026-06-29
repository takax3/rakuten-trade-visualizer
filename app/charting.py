from __future__ import annotations

from collections import defaultdict

import plotly.graph_objects as go

from app.models import MinuteBar, OrderExecution

SIDE_STYLE = {
    "買建": {"color": "#2563eb", "symbol": "triangle-up", "label": "買建"},
    "売建": {"color": "#dc2626", "symbol": "triangle-down", "label": "売建"},
    "買埋": {"color": "#0891b2", "symbol": "circle", "label": "買埋"},
    "売埋": {"color": "#f97316", "symbol": "circle", "label": "売埋"},
}


def build_trade_chart(bars: list[MinuteBar], executions: list[OrderExecution]) -> str:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=[bar.datetime for bar in bars],
            open=[bar.open for bar in bars],
            high=[bar.high for bar in bars],
            low=[bar.low for bar in bars],
            close=[bar.close for bar in bars],
            name="1分足",
            increasing_line_color="#16a34a",
            decreasing_line_color="#dc2626",
        )
    )

    grouped: dict[str, list[OrderExecution]] = defaultdict(list)
    for execution in executions:
        grouped[execution.side].append(execution)

    for side, side_executions in grouped.items():
        style = SIDE_STYLE[side]
        fig.add_trace(
            go.Scatter(
                x=[execution.executed_at for execution in side_executions],
                y=[execution.price for execution in side_executions],
                mode="markers",
                name=style["label"],
                marker={
                    "size": 13,
                    "color": style["color"],
                    "symbol": style["symbol"],
                    "line": {"width": 1, "color": "#111827"},
                },
                customdata=[
                    [execution.order_id, execution.quantity, execution.symbol_name]
                    for execution in side_executions
                ],
                hovertemplate=(
                    "%{customdata[2]}<br>"
                    "%{x|%H:%M:%S}<br>"
                    f"{style['label']} "
                    "%{customdata[1]}株<br>"
                    "%{y:,.1f}円<br>"
                    "注文番号 %{customdata[0]}"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=620,
        margin={"l": 48, "r": 24, "t": 32, "b": 48},
        xaxis_title="時刻",
        yaxis_title="価格",
        legend_title_text="表示",
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"responsive": True})
