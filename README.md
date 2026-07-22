# StockAI Navigator — Phase 1

日本株の価格・銘柄マスタ・財務データをSQLiteへ蓄積する最初の土台です。価格はyfinance、マスタと財務はJ-Quants API V2を利用します。

## 初回セットアップ（PowerShell）

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` の `JQUANTS_API_KEY` にAPIキーを設定してください。APIキーなしでも価格データの確認はできます。

## 動作確認

```powershell
python main.py --ticker 7203.T --code 72030 --period 1y --skip-jquants
```

APIキー設定後は次を実行します。

```powershell
python main.py --ticker 7203.T --code 72030
```

生成される `data/stockai.db` には `master_stock`、`price_daily`、`price_weekly`、`price_monthly`、`financial` の5テーブルが作られます。すべてUPSERTのため、同じ処理を再実行しても重複しません。

## フェーズ2：テクニカル分析とスクリーニング

`config/indicators.yaml` の設定をもとに、RSI、MACD、移動平均、ボリンジャーバンド、ATR、ADX、ストキャスティクスを計算します。`config/screening.yaml` のプロファイルは `all` / `any` / `not` と比較演算子を組み合わせる安全な宣言形式であり、任意のPython式は実行しません。

既存のSQLiteデータをスクリーニングするには、次を実行します。

```powershell
python main.py --screen --profile oversold
```

初期プロファイルは `oversold`、`momentum`、`rsi_rebound` です。条件は `config/screening.yaml` のみを編集して追加・変更できます。

`deep_value` と `value` は、J-Quantsで取得した最新の財務値と終値からPER・PBR・ROE・自己資本比率を計算して使います。財務情報を未取得の場合は、これらのプロファイルには一致しません。

`high_dividend` は保存済み日足から直近12か月の実績配当を合計して利回りを算出し、自己資本比率と営業CFも確認します。将来の配当額を予測するものではありません。

そのほか、`growth` はROE・営業利益率・75日移動平均を、`swing` は25日移動平均・MACD・ADXを使います。すべての閾値は `config/screening.yaml` で変更できます。

スクリーニング結果は、同一プロファイルで保存済みの期待値スコアがある場合、その高い順に表示します。スコア未計算の候補も除外されません。

## フェーズ3：バックテストと期待値スコア

日足・週足・月足・財務で表現できるプロファイル（初期値は `rsi_rebound`）について、シグナル翌営業日の始値でエントリーし、指定営業日後の終値で決済する検証を実行できます。各日付時点で確定済みの週足・月足、および開示済みの最新財務だけを参照するため、先読みバイアスを避けます。

```powershell
python main.py --backtest --code 72030 --profile rsi_rebound --holding-days 60
```

出力には取引件数、平均・中央値リターン、勝率、最大含み損、平均最大含み益と、設定可能な0〜100の期待値スコアを含みます。複数時間足を同時に使う `oversold` のようなプロファイルは、時間足整合性を確保する拡張を追加するまでは日足バックテストには使用しないでください。

## フェーズ4：分析コメントと履歴

バックテスト実行時には、統計値のみを根拠とする日本語コメントを生成して `analysis_snapshot` テーブルに保存します。価格予測や売買指示は行いません。保存済みの結果は次で確認できます。

```powershell
python main.py --history --code 72030
```

## フェーズ5：通知

LINE Messaging APIのチャネルアクセストークンと送信先IDを `.env` に設定し、`config/notification.yaml` の `enabled: true` と `--notify` を両方指定した場合だけ送信します。

```powershell
python main.py --screen --profile oversold --notify
```

通知の成否は `notification_log` テーブルに保存されます。トークン・送信先IDはログへ保存されません。
保存済みバックテストがある候補では、期待値スコアと統計コメントも通知本文へ含めます。チャート画像のLINE配信には公開HTTPS URLが必要なため、ローカル運用版では送信しません。

## フェーズ6準備：Android向けREST API

`api.py` は読み取り専用のローカルAPIです。価格履歴、分析履歴、期待値ランキング、プロファイル別スクリーニング結果を返します。
`GET /stocks/{code}/overview` では、保存済みの会社情報・最新価格・最新開示ベースの財務指標をまとめて取得できます。
市場指数を保存済みの場合は、20・60・120営業日の指数比超過リターンも含まれます。

```powershell
uvicorn api:app --host 127.0.0.1 --port 8000
```

起動後、ブラウザで `http://127.0.0.1:8000/docs` を開くとAPI仕様を確認できます。初期状態はローカル専用です。スマートフォンなど外部端末からアクセス可能にする場合は、認証・TLS・ネットワークのアクセス制御を追加してから公開してください。

### Androidクライアント

`android/` にはJetpack Composeの最小クライアントを含めています。エミュレーターでは `http://10.0.2.2:8000` を開発PC上のAPIとして使います。先にAPIを起動してから、Android Studioで `android/` を開いて実行してください。
ランキング画面の「運用」では、日次サマリー、保有銘柄の評価、直近の更新ジョブを確認できます。注文機能は含みません。
運用画面の「監視」からは、ウォッチリストと各銘柄の詳細を確認できます。
ランキング画面の「条件」では、代表的なスクリーニングプロファイルの候補を確認できます。
各画面の「更新」はローカルAPIを再読込します。データ取得ジョブや通知は実行しません。

この開発用クライアントはローカルAPIへのHTTP接続を許可しています。実機配布や外部公開時には、HTTPS・認証・証明書検証を実装し、`usesCleartextTraffic` を削除してください。

## Version 2：市場レジーム分析

市場指数を通常の価格データとして先に保存し、50日・200日移動平均との位置関係で `bullish`、`bearish`、`neutral` を判定します。例えば日経平均を保存してから判定します。

```powershell
python main.py --ticker ^N225 --code NIKKEI225 --period 5y --skip-jquants
python main.py --market-regime --code NIKKEI225
```

日次の判定は `market_regime` テーブルに保存されます。これは過去データからの市場状態の分類であり、将来の市場を予測するものではありません。

市場レジームを保存した後は、日足・週足・月足で表現したプロファイルのバックテストを局面別に集計できます。

局面別の集計も過去シグナルを対象とした検証であり、将来の市場状態や投資成果を予測するものではありません。

```powershell
python main.py --backtest-by-regime --code 72030 --profile rsi_rebound --market-code NIKKEI225 --holding-days 60
```

## Version 2：業種別分析

J-Quantsの銘柄マスタにある33業種を使い、スクリーニング結果を業種別に集計できます。

```powershell
python main.py --sector-report --profile deep_value
```

APIでは `GET /screening/{profile_name}/sectors` でも同じ集計を取得できます。

## Version 2：ウォッチリスト

```powershell
python main.py --watch-add 72030 --note "長期監視"
python main.py --watchlist
python main.py --watch-remove 72030
```

ウォッチリストはSQLiteに保存され、APIでは `GET /watchlist` で読み取れます。

## ヒット件数最適化

スクリーニング条件を勝手に書き換えず、指定した一つの数値条件について目標件数に近い閾値を提案します。

```powershell
python main.py --optimize-hits --field daily.rsi_14 --operator "<=" --target-min 5 --target-max 20
```

提案結果を確認してから、`config/screening.yaml` を手動で更新してください。

## シミュレーションモード

バックテストで得た取引を、初期資金・1回の投資額・最大保有数の制約下で再生します。初期値は1銘柄ずつの実現損益ベースのシミュレーションです。

```powershell
python main.py --simulate --code 72030 --profile rsi_rebound --holding-days 60
```

資金設定は `config/simulation.yaml` で変更できます。結果は過去の仮定に基づくものであり、将来の成績を保証しません。

## Version 2：ポートフォリオ分析

保有数と平均取得単価を登録すると、保存済みの最新終値から評価額・含み損益・構成比を確認できます。

```powershell
python main.py --portfolio-add 72030 --quantity 100 --average-cost 2500 --note "長期"
python main.py --portfolio
python main.py --portfolio-remove 72030
```

APIでは `GET /portfolio` を利用できます。入力値の保存と評価表示のみで、売買注文は行いません。

## 日次更新ジョブ

ウォッチリストの価格を更新し、実行結果を `job_run` テーブルへ記録します。通知や外部公開は行いません。

`config/settings.yaml` の `market_indices` にある市場指数も更新し、局面判定を再計算します。
J-Quants APIキーが設定済みで `daily_financial_update: true` の場合、国内株のウォッチリスト銘柄について財務開示も更新します。市場指数・海外ティッカーは対象外です。

```powershell
python main.py --daily-update
```

Windowsのタスクスケジューラなどでこのコマンドを平日の任意時刻に実行すれば、日次更新を自動化できます。初回は手動で実行して取得結果を確認してください。

更新と日次JSONレポートの作成をまとめて実行する場合は、次を利用できます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1
```

標準の `.venv\Scripts\python.exe` を優先して使用します。タスクスケジューラには `powershell.exe` と上記の `-File` 引数を設定してください。スクリプトはローカルDBと `reports/` だけを更新し、通知・公開・注文は行いません。

Yahoo Finance側の一時的な接続失敗に備え、`config/settings.yaml` の `retries` と `retry_delay_seconds` で再試行回数を設定できます。2回目以降の日次更新は、直近価格日の前から `daily_update_overlap_days` 日分だけ重ねて取得するため、訂正に追随しながら取得量を抑えられます。
国内株の4・5桁コードは自動的にYahoo Finance用の `.T` ティッカーへ変換し、`^N225` などの指数・海外銘柄ティッカーはそのまま使用します。

直近の更新結果は次のコマンド、またはローカルAPIの `GET /jobs` で確認できます。

```powershell
python main.py --job-history
```

## ローカルテスト

ネットワークを使わない中核ロジック、データ取得の再試行、先読み防止のバックテスト、ローカルAPIの回帰テストです。

    python -m unittest discover -s tests -v

APIテストには開発用依存関係が必要です。初回だけ次を実行してください。

    pip install -r requirements-dev.txt

## ヘルスチェック

SQLiteのテーブル、価格データ最終日と鮮度、ウォッチリスト、ポートフォリオの件数を確認します。価格が未取得、または最終日から7日を超えている場合は `degraded` になります。データを更新・送信しません。

    python main.py --healthcheck

APIでは GET /system/health から同じ情報を確認できます。

## スコア変化の検出

同じ銘柄・プロファイルについて、保存済みバックテストの最新スコアと直前スコアを比較します。

    python main.py --score-changes --minimum-delta 10

APIでは GET /rankings/changes?minimum_delta=10 を利用できます。

## 一括バックテスト

保存済み価格データを持つ全銘柄に、日足・週足・月足で表現したプロファイルを適用して結果を保存します。初回は件数を絞ることを推奨します。

```powershell
python main.py --batch-backtest --profile rsi_rebound --holding-days 60 --batch-limit 20
```

完了後、`/rankings` とスクリーニングの期待値順表示に結果が反映されます。
市場局面用に保存した指数は、個別株候補ではないため一括バックテスト・スクリーニング・ランキングから自動的に除外されます。

## 保有期間の比較

`config/backtest.yaml` にあるすべての保有期間を一度に比較します。

```powershell
python main.py --backtest-horizons --code 72030 --profile rsi_rebound
```

## 日次サマリーレポート

保存済みのヘルス、上位ランキング、スコア変化、市場局面、直近の更新ジョブ、ウォッチリスト、ポートフォリオをJSONへまとめます。

```powershell
python main.py --daily-report
```

既定では `reports/daily_summary_YYYY-MM-DD.json` に出力されます。

ファイルを作らずに同じ内容を取得する場合は、ローカルAPIの `GET /reports/daily` を利用できます。

### ローカル株価チャート

保存済みの日足から、ローソク足と25日・75日移動平均のSVGチャートを生成できます。外部へ公開・送信はしません。

```powershell
python main.py --chart --code 72030
```

既定では `reports/charts/72030_YYYYMMDD.svg` に出力されます。ローカルAPIでは `GET /stocks/72030/chart.svg` でも取得できます。LINE画像メッセージへ添付するには、別途HTTPSで到達可能なPNGまたはJPEGの公開URLが必要です。

公開環境を用意した後だけ、`config/notification.yaml` の `chart_public_url_template` に `https://.../charts/{code}.png` 形式のURLを設定してください。設定されるまでは、`--screen --notify` はコメント付きテキストのみを送ります。

LINE対応のPNGをローカル生成するには、次を実行します（追加パッケージや外部への送信は不要です）。

```powershell
python scripts/render_chart_png.py --code 72030
```

### GitHub Pagesへの公開（任意）

GitHub App連携が使えない場合は、`Pinknokumo` リポジトリだけに限定したFine-grained personal access tokenで公開できます。トークン作成時は対象リポジトリを `Only select repositories` の `Pinknokumo` に限定し、以下だけを許可します。

- `Contents`: Read and write（PNGの更新）
- `Pages`: Read and write と `Administration`: Read and write（初回のPages有効化時だけ必要）

トークンを `.env` の `GITHUB_CHARTS_TOKEN` に保存後、初回のみ次を実行します。これはGitHubへチャートをアップロードしてPagesを公開する外部操作です。

```powershell
python scripts/publish_chart_github.py --code 72030 --enable-pages
```

2回目以降は `--enable-pages` を省略できます。公開URLは `https://pinknokumo-glitch.github.io/Pinknokumo/charts/72030.png` です。

## 設定ファイルの検証

スクリーニング条件の入力ミスを確認します。DBや設定ファイルは変更しません。

    python main.py --validate-config

> yfinanceのデータはYahooの利用規約に従ってください。J-Quantsの利用可能エンドポイントと契約条件は、ご自身のプランで確認してください。

## 日次一括実行

データ更新、一括バックテスト、期待値スコア・コメント更新、日次レポート、スクリーニングをまとめて実行します。`-Notify` を付けた場合だけ、該当銘柄のチャートをGitHub Pagesへ公開してLINE通知を送信します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -Notify
```

初期監視対象としてTOPIX Core30を登録する場合は次を実行します。既存の個別登録やメモは保持されます。

```powershell
python main.py --watch-import-scale "TOPIX Core30" --note "TOPIX Core30"
```

### Windowsでの平日自動実行

次のコマンドは、ログイン中の平日18:00に日次処理とLINE通知を実行するタスクを登録します。実行ログは `reports/logs/` に保存されます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1 -Time "18:00"
```

### PC不要のGitHub Actions実行（準備済み）

`.github/workflows/daily.yml` は平日10:00（日本時間）にクラウドで日次処理を実行します。公開前にGitHubリポジトリへソース一式を反映し、Repository secretsへ `JQUANTS_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_RECIPIENT_ID` を登録する必要があります。秘密値はファイルへ保存しません。
