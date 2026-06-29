from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.charting import build_trade_chart
from app.market_data import fetch_yahoo_minute_bars
from app.models import ExecutionRow, MinuteBar, OrderExecution
from app.parsers import decode_csv_bytes, parse_rakuten_orders, yahoo_ticker_from_symbol_code_market
from app.profit_loss import build_execution_rows
from app.storage import SavedTrade, get_saved_trade, list_saved_trades, save_trade, update_review_note

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
    ticker: str | None = None
    target_date: date | None = None
    symbol_name: str | None = None
    saved_trade: SavedTrade | None = None
    orders_csv_text = ""

    try:
        orders_csv_bytes = await orders_csv.read()
        orders_csv_text = decode_csv_bytes(orders_csv_bytes)
        executions = parse_rakuten_orders(orders_csv_bytes)
        if not executions:
            errors.append("表示対象の約定がありません。状況が約定で、約定数量がある行を確認してください。")
        else:
            first_execution = executions[0]
            target_date = first_execution.executed_at.date()
            symbol_name = first_execution.symbol_name
            ticker = yahoo_ticker_from_symbol_code_market(first_execution.symbol_code_market)
            executions = [execution for execution in executions if execution.executed_at.date() == target_date]
            execution_rows = build_execution_rows(executions)
    except Exception as exc:
        errors.append(str(exc))

    if executions and target_date:
        try:
            if ticker is None:
                raise ValueError("Yahoo Finance用ティッカーを生成できませんでした。")
            bars = fetch_yahoo_minute_bars(ticker, target_date)
        except Exception as exc:
            warnings.append(str(exc))
            warnings.append("Yahoo Finance取得に失敗しました。取得可能期間や銘柄コードを確認してください。")

    if bars and executions:
        chart_html = build_trade_chart(bars, executions)
        if target_date and symbol_name and ticker:
            try:
                saved_trade = save_trade(
                    orders_csv=orders_csv_text,
                    bars=bars,
                    symbol_name=symbol_name,
                    ticker=ticker,
                    target_date=target_date,
                )
            except Exception as exc:
                warnings.append(f"振り返りデータの保存に失敗しました: {exc}")

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
    chart_html: str | None = None

    try:
        executions = parse_rakuten_orders(saved_trade.orders_csv.encode("utf-8"))
        executions = [execution for execution in executions if execution.executed_at.date() == saved_trade.target_date]
        execution_rows = build_execution_rows(executions)
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
        warnings=[],
        errors=errors,
    )


@app.post("/reviews/{review_id}/note")
async def save_review_note(review_id: int, review_note: str = Form("")) -> RedirectResponse:
    update_review_note(review_id, review_note)
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
            "warnings": warnings,
            "errors": errors,
        },
    )


def build_saved_trade_view(saved_trade: SavedTrade) -> SavedTradeView:
    executions = parse_rakuten_orders(saved_trade.orders_csv.encode("utf-8"))
    executions = [execution for execution in executions if execution.executed_at.date() == saved_trade.target_date]
    execution_rows = build_execution_rows(executions)
    final_pnl = sum(row.realized_pnl or 0 for row in execution_rows)
    return SavedTradeView(trade=saved_trade, final_pnl=final_pnl)
