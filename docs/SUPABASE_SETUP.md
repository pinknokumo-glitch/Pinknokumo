# Supabase screening preference setup

This is the planned secure control plane for Android-to-cloud screening settings.

## Security boundary

- Android uses the public project URL, public anon key, and the signed-in user's short-lived JWT.
- Row Level Security restricts the user to their own preference row.
- `SUPABASE_SERVICE_ROLE_KEY` is stored only as a GitHub Actions secret and must never be included in Android or committed to Git.
- The cloud value is validated again against `config/screening_options.yaml` before use.
- Until all three server environment variables are configured, the daily job continues using the repository configuration.

## Required Supabase values

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (GitHub Actions only)
- `STOCKAI_USER_ID`

Android also uses `SUPABASE_URL` and the public `SUPABASE_ANON_KEY`. Put these only in
`android/local.properties` (which is ignored by Git):

```properties
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
```

## 設定が翌日の処理へ反映される流れ

1. Androidの「クラウド保存」で、ログインユーザーの行を
   `screening_preferences`へ保存します。
2. 朝のGitHub Actionsは`STOCKAI_USER_ID`の行だけを読み込みます。
3. オート設定は選択したジャンルのプロファイルへ、マニュアル設定は
   保存した条件をAND/ORルールへ変換してスクリーニングします。
4. Actionsログに`Cloud screening preference: <mode> / <profile>`が出れば、
   クラウド設定がその実行に採用されています。
5. 配信候補は`screening_results`へ保存され、Androidの「最新結果」から
   同じユーザーの最新配信日を確認できます。

GitHub Secretsには`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、
`STOCKAI_USER_ID`の3つが必要です。`STOCKAI_USER_ID`はSupabase Authで
作成したAndroidログインユーザーのUUIDと一致させてください。

The app does not store the email, password, or session after it closes. The password is
used only for the sign-in request, and preference writes are restricted by RLS.

## Database preparation

1. Create a Supabase Free project.
2. Create one application user with email/password or magic link.
3. Open the SQL Editor and run `supabase/screening_preferences.sql`.
4. Insert the initial preference while authenticated, or use the dashboard for the first row.
5. Register the three server values above as GitHub Actions secrets.

Do not paste secret values into source files, chat logs, screenshots, or Android resources.
