# StockAI Navigator プロジェクト状況

更新日: 2026-07-22

## 現在の状態

- J-Quants API連携済み
- LINE Messaging API連携・テキスト／画像通知確認済み
- GitHub Pagesでチャート画像を公開済み
- 公開先リポジトリ: `pinknokumo-glitch/Pinknokumo`
- 監視対象: TOPIX Core30を中心とする31銘柄
- 平日10:00のWindows自動実行タスクを登録済み
- PC起動・Windowsログイン・ネット接続中は自動実行可能
- ローカル回帰テスト: 35件成功
- 2026-07-22 10:00の初回タスクは、外部ライブラリの非推奨警告をPowerShellがエラー扱いして停止。警告抑制を追加して修正済み。

## 日次処理

`scripts/run_daily_pipeline.py` が次を一括実行する。

1. 株価・財務データ更新
2. 市場レジーム判定
3. 一括バックテスト
4. 期待値スコア・分析コメント生成
5. スクリーニング
6. 日次JSONレポート作成
7. 候補チャートのGitHub Pages公開
8. LINE通知

手動実行:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -Notify
```

## スクリーニング

- 本番プロファイル: `oversold`
- 通知確認用の緩和プロファイル: `notification_demo`
- `notification_demo` は本番投資判断には使用しない
- 本番条件は通知テストのために変更していない

## 通知内容

- 判定基準日
- 会社名・銘柄コード
- 期待値スコア
- 抽出理由
- バックテスト由来の分析コメント
- 最大3銘柄のチャート画像
- データ取得やチャート更新失敗時の警告

## セキュリティ

- `.env` はGit管理対象外
- SQLite DBもGit管理対象外
- APIキー、LINEトークン、送信先ID、GitHubトークンの値は文書へ記載しない
- 外部サービスへの送信・公開、課金、認証情報操作、大量削除、重大な設計変更は事前確認する

## GitHub Actions移行準備

PCを起動していなくても平日10:00に実行できるクラウド版をローカルに準備済み。

- ワークフロー: `.github/workflows/daily.yml`
- 初期化: `scripts/bootstrap_cloud.py`
- SQLite DBはGitHub Actions Cacheで引き継ぐ
- レポートはActions Artifactへ30日保存
- GitHubへはまだソース一式を公開していない
- GitHub Secretsもまだ登録していない

有効化に必要なSecrets:

- `JQUANTS_API_KEY`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_RECIPIENT_ID`

`GITHUB_CHARTS_TOKEN` はActions内で `${{ github.token }}` を利用するため、追加登録しない。

## 現在の保留事項

GitHub CLI (`gh`) が未導入のため、ソース公開を保留中。

精度向上候補としてMicrosoft Qlibの安全統合計画を `docs/QLIB_INTEGRATION_PLAN.md` に作成済み。外部パッケージの導入や本番判定への反映はまだ行っていない。

公開前監査は `scripts/audit_publish.py` で実行する。生成レポート、チャート、ログ、SQLite DB、`.env` はGitHub公開対象外。

再開手順:

```powershell
winget install --id GitHub.cli
gh auth login
```

ログイン後は `scripts/enable_cloud.ps1` により、監査、テスト、PR、Secrets登録、マージ、初回Actions実行を一括で行える。

ログイン後、秘密情報が除外されていることを再確認し、ソースを `pinknokumo-glitch/Pinknokumo` へ反映する。その後、GitHub Secretsを登録してActionsを手動実行し、成功確認後にPC側の定期実行を残すか停止するか決定する。

## スマホからの許可

ChatGPTデスクトップアプリの「Set up Remote」でスマホとペアリングすると、ChatGPTモバイルアプリから進捗確認、返答、許可操作が可能。Remote利用中はホストPCとChatGPTデスクトップアプリが利用可能な状態である必要がある。
