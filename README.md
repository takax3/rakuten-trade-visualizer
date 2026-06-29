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
docker run --rm -p 8000:8000 -v ${PWD}\data:/app/data rakuten-trade-visualizer
```

SQLite DB is stored at `data\trades.db` on the host.

Or use Docker Compose:

```powershell
docker compose up --build
```

## 使い方

### 楽天証券からCSVを保存する

1. 楽天証券にログインします。
2. 注文照会画面を開きます。
3. 取引区分で信用取引のみを表示します。
4. 対象期間や銘柄を必要に応じて指定します。
5. 表示された注文照会結果をCSVで保存します。

### 保存したCSVを読み込む

1. アプリを起動し、<http://localhost:8000> を開きます。
2. 保存した楽天証券の注文CSVを選択します。
3. 対象銘柄と日付を確認して読み込みます。
4. 1分足ローソク足に信用取引の約定点が重ねて表示されます。

注文CSVは楽天証券の注文照会CSV形式を想定しています。`状況` が `約定` で、`約定数量[株/口]` が 0 より大きい行だけを表示します。

1分足は `yfinance` を利用してYahoo Financeから取得します。1分足は取得可能期間に制約があります。

可視化に成功した注文CSVと取得済み1分足はローカルSQLite DBに自動保存され、保存済み振り返り画面から後で読み込めます。
