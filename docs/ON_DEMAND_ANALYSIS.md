# 指定銘柄のオンデマンド分析

分析ボタンで依頼を保存し、SupabaseのRPCからGitHub Actionsの
`stock-analysis.yml` を起動する。アプリは15秒間隔で結果を確認する。
次回のdaily実行を待つ必要はない。起動待ち、依存関係の準備、計算に数分以上かかる。

## 導入順序

1. `supabase/on_demand_analysis_upgrade.sql` をSupabase SQL Editorで適用する。
2. この変更を専用ブランチからPRでmainへ反映する。
3. GitHubで、このリポジトリだけに `Actions: Read and write` を許可する
   fine-grained tokenを作成する。Supabase DashboardのVaultに
   **stockai_actions_token** という名前で保存する。
   トークン本文をチャット、ソース、SQLファイル、APKへ記載しない。
4. `evening.yml` を1回実行する。成功すると取得できた全銘柄の一覧と
   分析用DBキャッシュが公開される。RSI候補のみに限定しない。
5. 新しい署名APKを更新し、銘柄検索→選択→分析を開始する。

旧アプリの通常配信は維持される。新しいアプリはmigration適用後に使用する。
新しいdaily処理はオンデマンド依頼を処理せず、旧方式の依頼だけを扱う。

## データと再実行

- 依頼時点のクラウド設定を `input_snapshot` に保存する。
- カタログにある `dataset_run_id` の夕方DBを使用し、現在値の再取得はしない。
- 夕方DBは `stockai-evening-analysis-<run-id>` で保存され、分析側は書き戻さない。
- キャッシュが削除・失効していたら失敗を表示する。別日のデータへ黙って切り替えない。
- 1ユーザーにつき同時に1件。全体で1時間12件までに制限する。
- 依頼行を条件付き更新で取得するため、同じ依頼を二重計算しない。
- GitHub起動が拒否された場合は、アプリの状態確認時に失敗を記録する。
- ワークフロー異常終了は失敗を記録する。通信断などで記録できない場合も
  2時間後の状態確認で待機超過を表示する。
- アプリを閉じても計算は続く。指定銘柄画面を開き直すと同じ依頼の確認を再開する。

## 確認項目

夕方のカタログ件数が取得成功件数に対応すること、配信候補外の銘柄も検索できること、
依頼後に設定を変えても元の条件で計算されること、分析完了後に自動表示されることを確認する。
実環境での確認にはVault設定、migration適用、mainへのワークフロー反映が必要。

## 費用

GitHubの公開リポジトリの標準ランナー実行時間は無料。
非公開リポジトリ、保存容量、Supabaseの利用枠には別の上限がある。
アカウントの使用量・請求設定を確認し、無料枠だけで運用する場合は課金予算を追加しない。

- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://supabase.com/docs/guides/database/extensions/pg_net
- https://supabase.com/docs/guides/database/vault

## ロールバック

アプリを旧版へ戻すと新規のオンデマンド依頼は発生しない。追加カラムは維持できる。
Vaultの専用トークンを無効にすると起動を停止できるが、実行中の分析は継続する。
既存の配信結果・設定・通知データを削除する必要はない。
