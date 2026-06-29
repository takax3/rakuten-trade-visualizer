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

## CSV input

注文CSVは楽天証券の注文照会CSV形式を想定しています。`状況` が `約定` で、`約定数量[株/口]` が 0 より大きい行だけを表示します。

1分足は `yfinance` を利用してYahoo Financeから取得します。1分足は取得可能期間に制約があります。

可視化に成功した注文CSVと取得済み1分足はローカルSQLite DBに自動保存され、保存済み振り返り画面から後で読み込めます。
