from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.charting import build_trade_chart
from app.market_data import fetch_yahoo_minute_bars
from app.models import DailyPnlSummary, ExecutionRow, MinuteBar, OhlcSummary, OrderExecution, PositionState
from app.parsers import group_rakuten_order_csv, parse_rakuten_orders, yahoo_ticker_from_symbol_code_market
from app.profit_loss import build_daily_pnl_summary, build_execution_rows_with_opening, build_final_position
from app.storage import (
    SavedTrade,
    get_latest_saved_trade_before,
    get_saved_trade,
    list_saved_trades,
    save_trade,
    update_review_note,
    update_trade_positions,
)

app = FastAPI(title="Rakuten Trade Visualizer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@dataclass(frozen=True)
class SavedTradeView:
    trade: SavedTrade
    final_pnl: float


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "executions": [],
            "execution_rows": [],
            "warnings": [],
            "errors": [],
        },
    )


@app.post("/visualize", response_class=HTMLResponse)
async def visualize(
    request: Request,
    orders_csv: UploadFile = File(...),
) -> HTMLResponse:
    errors: list[str] = []
    warnings: list[str] = []
    chart_html: str | None = None
    executions: list[OrderExecution] = []
    execution_rows: list[ExecutionRow] = []
    bars: list[MinuteBar] = []
    pnl_summary: DailyPnlSummary | None = None
    ohlc_summary: OhlcSummary | None = None
    ticker: str | None = None
    target_date: date | None = None
    symbol_name: str | None = None
    saved_trade: SavedTrade | None = None
    opening_position = PositionState()
    saved_count = 0

    try:
        orders_csv_bytes = await orders_csv.read()
        groups = group_rakuten_order_csv(orders_csv_bytes)
        if not groups:
            errors.append("表示対象の約定がありません。状況が約定で、約定数量がある行を確認してください。")
        for group in groups:
            group_ticker = yahoo_ticker_from_symbol_code_market(group.symbol_code_market)
            past_trade = get_latest_saved_trade_before(group_ticker, group.target_date)
            group_opening_position = past_trade.final_position if past_trade else PositionState()
            group_final_position = build_final_position(group.executions, group_opening_position)

            try:
                group_bars = fetch_yahoo_minute_bars(group_ticker, group.target_date)
            except Exception as exc:
                warnings.append(f"{group.symbol_name} {group.target_date}: {exc}")
                warnings.append("Yahoo Finance取得に失敗しました。取得可能期間や銘柄コードを確認してください。")
                continue

            chart = build_trade_chart(group_bars, group.executions)
            try:
                group_saved_trade = save_trade(
                    orders_csv=group.orders_csv,
                    bars=group_bars,
                    symbol_name=group.symbol_name,
                    ticker=group_ticker,
                    target_date=group.target_date,
                    opening_position=group_opening_position,
                    final_position=group_final_position,
                )
                saved_count += 1
            except Exception as exc:
                warnings.append(f"{group.symbol_name} {group.target_date}: 振り返りデータの保存に失敗しました: {exc}")
                continue

            if saved_trade is None:
                saved_trade = group_saved_trade
                chart_html = chart
                executions = group.executions
                execution_rows = build_execution_rows_with_opening(executions, group_opening_position)
                bars = group_bars
                pnl_summary = build_visualization_pnl_summary(execution_rows, bars)
                ohlc_summary = build_ohlc_summary(bars)
                ticker = group_ticker
                target_date = group.target_date
                symbol_name = group.symbol_name
                opening_position = group_opening_position
    except Exception as exc:
        errors.append(str(exc))

    if saved_count > 1:
        warnings.append(f"{saved_count}件の銘柄・日付別データを保存しました。ほかのデータは保存済み振り返りから開けます。")

    return render_visualization(
        request,
        executions=executions,
        execution_rows=execution_rows,
        bars=bars,
        chart_html=chart_html,
        ticker=ticker,
        target_date=target_date,
        symbol_name=symbol_name,
        saved_trade=saved_trade,
        opening_position=opening_position,
        pnl_summary=pnl_summary,
        ohlc_summary=ohlc_summary,
        warnings=warnings,
        errors=errors,
    )


@app.get("/reviews", response_class=HTMLResponse)
async def reviews(request: Request) -> HTMLResponse:
    saved_trade_views = []
    for summary in list_saved_trades():
        saved_trade = get_saved_trade(summary.id)
        if saved_trade is not None:
            saved_trade_views.append(build_saved_trade_view(saved_trade))
    return templates.TemplateResponse(
        request,
        "reviews.html",
        {
            "saved_trades": saved_trade_views,
        },
    )


@app.get("/reviews/{review_id}", response_class=HTMLResponse)
async def review_detail(request: Request, review_id: int) -> HTMLResponse:
    saved_trade = get_saved_trade(review_id)
    if saved_trade is None:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "executions": [],
                "execution_rows": [],
                "warnings": [],
                "errors": ["保存済み振り返りが見つかりません。"],
            },
            status_code=404,
        )

    errors: list[str] = []
    executions: list[OrderExecution] = []
    execution_rows: list[ExecutionRow] = []
    pnl_summary: DailyPnlSummary | None = None
    ohlc_summary: OhlcSummary | None = None
    chart_html: str | None = None

    try:
        executions = parse_rakuten_orders(saved_trade.orders_csv.encode("utf-8"))
        executions = [execution for execution in executions if execution.executed_at.date() == saved_trade.target_date]
        execution_rows = build_execution_rows_with_opening(executions, saved_trade.opening_position)
        pnl_summary = build_visualization_pnl_summary(execution_rows, saved_trade.minute_bars)
        ohlc_summary = build_ohlc_summary(saved_trade.minute_bars)
        if executions and saved_trade.minute_bars:
            chart_html = build_trade_chart(saved_trade.minute_bars, executions)
    except Exception as exc:
        errors.append(str(exc))

    return render_visualization(
        request,
        executions=executions,
        execution_rows=execution_rows,
        bars=saved_trade.minute_bars,
        chart_html=chart_html,
        ticker=saved_trade.ticker,
        target_date=saved_trade.target_date,
        symbol_name=saved_trade.symbol_name,
        saved_trade=saved_trade,
        opening_position=saved_trade.opening_position,
        pnl_summary=pnl_summary,
        ohlc_summary=ohlc_summary,
        warnings=[],
        errors=errors,
    )


@app.post("/reviews/{review_id}/note")
async def save_review_note(review_id: int, review_note: str = Form("")) -> RedirectResponse:
    update_review_note(review_id, review_note)
    return RedirectResponse(url=f"/reviews/{review_id}", status_code=303)


@app.post("/reviews/{review_id}/position")
async def save_opening_position(
    review_id: int,
    opening_long_quantity: int = Form(0),
    opening_long_average_price: float = Form(0),
    opening_short_quantity: int = Form(0),
    opening_short_average_price: float = Form(0),
) -> RedirectResponse:
    saved_trade = get_saved_trade(review_id)
    if saved_trade is None:
        return RedirectResponse(url="/reviews", status_code=303)

    opening_position = PositionState(
        long_quantity=max(0, opening_long_quantity),
        long_average_price=max(0.0, opening_long_average_price),
        short_quantity=max(0, opening_short_quantity),
        short_average_price=max(0.0, opening_short_average_price),
    )
    executions = parse_rakuten_orders(saved_trade.orders_csv.encode("utf-8"))
    executions = [execution for execution in executions if execution.executed_at.date() == saved_trade.target_date]
    final_position = build_final_position(executions, opening_position)
    update_trade_positions(
        review_id,
        opening_position=opening_position,
        final_position=final_position,
    )
    return RedirectResponse(url=f"/reviews/{review_id}", status_code=303)


def render_visualization(
    request: Request,
    *,
    executions: list[OrderExecution],
    execution_rows: list[ExecutionRow],
    bars: list[MinuteBar],
    chart_html: str | None,
    ticker: str | None,
    target_date: date | None,
    symbol_name: str | None,
    saved_trade: SavedTrade | None,
    opening_position: PositionState,
    pnl_summary: DailyPnlSummary | None,
    ohlc_summary: OhlcSummary | None,
    warnings: list[str],
    errors: list[str],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "executions": executions,
            "execution_rows": execution_rows,
            "bars_count": len(bars),
            "chart_html": chart_html,
            "ticker": ticker,
            "target_date": target_date,
            "symbol_name": symbol_name,
            "saved_trade": saved_trade,
            "opening_position": opening_position,
            "pnl_summary": pnl_summary,
            "ohlc_summary": ohlc_summary,
            "warnings": warnings,
            "errors": errors,
        },
    )


def build_visualization_pnl_summary(
    execution_rows: list[ExecutionRow],
    bars: list[MinuteBar],
) -> DailyPnlSummary | None:
    if not execution_rows or not bars:
        return None
    return build_daily_pnl_summary(
        execution_rows,
        execution_rows[-1].position,
        bars[-1].close,
    )


def build_ohlc_summary(bars: list[MinuteBar]) -> OhlcSummary | None:
    if not bars:
        return None
    return OhlcSummary(
        open_price=bars[0].open,
        close_price=bars[-1].close,
        high_price=max(bar.high for bar in bars),
        low_price=min(bar.low for bar in bars),
    )


def build_saved_trade_view(saved_trade: SavedTrade) -> SavedTradeView:
    executions = parse_rakuten_orders(saved_trade.orders_csv.encode("utf-8"))
    executions = [execution for execution in executions if execution.executed_at.date() == saved_trade.target_date]
    execution_rows = build_execution_rows_with_opening(executions, saved_trade.opening_position)
    final_pnl = sum(row.realized_pnl or 0 for row in execution_rows)
    return SavedTradeView(trade=saved_trade, final_pnl=final_pnl)
