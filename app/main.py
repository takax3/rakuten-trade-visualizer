from __future__ import annotations

from datetime import date

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.charting import build_trade_chart
from app.market_data import fetch_yahoo_minute_bars
from app.models import ExecutionRow, MinuteBar, OrderExecution
from app.parsers import parse_minute_bars_csv, parse_rakuten_orders, yahoo_ticker_from_symbol_code_market
from app.profit_loss import build_execution_rows

app = FastAPI(title="Rakuten Trade Visualizer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "bar_source": "yahoo",
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
    bar_source: str = Form("yahoo"),
    minute_csv: UploadFile | None = File(None),
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

    try:
        executions = parse_rakuten_orders(await orders_csv.read())
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
        if bar_source == "csv":
            if minute_csv is None or not minute_csv.filename:
                errors.append("1分足CSVを選択してください。")
            else:
                try:
                    bars = parse_minute_bars_csv(await minute_csv.read())
                    bars = [bar for bar in bars if bar.datetime.date() == target_date]
                    if not bars:
                        errors.append("1分足CSVに対象日のデータがありません。")
                except Exception as exc:
                    errors.append(str(exc))
        else:
            try:
                if ticker is None:
                    raise ValueError("Yahoo Finance用ティッカーを生成できませんでした。")
                bars = fetch_yahoo_minute_bars(ticker, target_date)
            except Exception as exc:
                warnings.append(str(exc))
                warnings.append("Yahoo Finance取得に失敗しました。取得可能期間や銘柄コードを確認し、必要なら1分足CSVをアップロードしてください。")

    if bars and executions:
        chart_html = build_trade_chart(bars, executions)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "bar_source": bar_source,
            "executions": executions,
            "execution_rows": execution_rows,
            "bars_count": len(bars),
            "chart_html": chart_html,
            "ticker": ticker,
            "target_date": target_date,
            "symbol_name": symbol_name,
            "warnings": warnings,
            "errors": errors,
        },
    )
