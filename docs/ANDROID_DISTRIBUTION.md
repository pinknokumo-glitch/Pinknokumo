# Androidアプリの安全な更新配布

## 目的

GitHub Actionsで署名済みAPKを作り、同じアプリを上書き更新できるようにします。
署名鍵はリポジトリへ保存せず、GitHub Secretsからビルド時だけ読み込みます。

## 必要なGitHub Secrets

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

`SUPABASE_SERVICE_ROLE_KEY`はAndroidアプリへ組み込みません。
サービスロール鍵は管理者用であり、端末へ配布してはいけません。

## 一度だけ行う署名設定

次のスクリプトは署名鍵をPC内に作成し、上記4件の署名用Secretsをまとめて登録します。
パスワードは8文字以上で1回入力し、忘れないよう安全な場所へ記録してください。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\pinkn\Documents\Codex\2026-07-20\https-chatgpt-com-share-6a5d871b-d9f8\outputs\StockAI\scripts\setup_android_signing.ps1"
```

作成される `android\signing\stockai-release.jks` はGit管理対象外です。
PC故障に備えて、パスワードとともに安全な場所へバックアップしてください。

## ビルド画面

[Android APKビルドを開く](https://github.com/pinknokumo-glitch/Pinknokumo/actions/workflows/android.yml)

Secrets登録後に上記ページの「Run workflow」を1回押すと、署名済みAPKが作成されます。
完了した実行を開き、画面下部のArtifactsから
`StockAI-Navigator-Android`をダウンロードします。

## 更新時の注意

- 初回と更新版は必ず同じ署名鍵を使います。
- 署名鍵を失うと、既存アプリへ上書き更新できません。
- 署名鍵やパスワードをチャット、Git、APK内へ保存しません。
- APKの配布範囲は、GitHubリポジトリの公開範囲に合わせます。
