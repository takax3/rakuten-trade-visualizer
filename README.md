# Rakuten Trade Visualizer

楽天証券の注文CSVを読み込み、1分足ローソク足に信用取引の約定点を重ねて表示するローカルWebアプリです。

## Run locally

```powershell
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>.

## Run with Docker

```powershell
docker build -t rakuten-trade-visualizer .
docker run --rm -p 8000:8000 rakuten-trade-visualizer
```

## CSV inputs

注文CSVは楽天証券の注文照会CSV形式を想定しています。`状況` が `約定` で、`約定数量[株/口]` が 0 より大きい行だけを表示します。

1分足CSVを使う場合は以下の列が必要です。

```csv
datetime,open,high,low,close,volume
2026-06-26 09:00,6100,6110,6098,6105,12000
```

Yahoo Finance取得は `yfinance` を利用します。1分足は取得可能期間に制約があり、取得できない場合は1分足CSVをアップロードしてください。
