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

`STOCKAI_USER_ID` is optional. Leave it unset for normal app operation so the
daily job automatically uses the preference most recently saved from the app.
Set it only when intentionally pinning the job to one specific Supabase user.

Android also uses `SUPABASE_URL` and the public `SUPABASE_ANON_KEY`. Put these only in
`android/local.properties` (which is ignored by Git):

```properties
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
```

For Android email confirmation, add this exact URL under
Authentication > URL Configuration > Redirect URLs:

```text
stockai://auth/confirm
```

The confirmation email verifies the user through Supabase and then opens the installed
Android app. The app imports the returned session without storing the password.

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

The daily cloud batch reads every saved preference. Users with identical genre/manual
conditions and identical `holding_days` share one screening and backtest calculation,
while results are written separately for each user. The expectation backtest uses the
same complete technical/fundamental AND/OR rule as screening, enters at the next
session's open, and exits after the configured number of trading sessions.

GitHub Secretsには`SUPABASE_URL`と`SUPABASE_SERVICE_ROLE_KEY`が必要です。
朝の処理は、アプリから最後に保存された設定行の`user_id`を自動採用します。
既存の`STOCKAI_USER_ID`は後方互換用で、設定行をユーザーID指定で固定したい
場合だけ使用します。

The app never stores the password. It stores the Supabase access and refresh session
encrypted with a key held by Android Keystore, shows the login screen at startup, and
allows one-tap reuse of the saved account. Logout deletes the encrypted local session.
Preference writes remain restricted by RLS.

## Database preparation

1. Create a Supabase Free project.
2. Create one application user with email/password or magic link.
3. Open the SQL Editor and run `supabase/screening_preferences.sql`.
4. Run `supabase/screening_candidates.sql` in full. It is idempotent and creates both
   the candidate rows and `screening_candidate_runs`, which records universe coverage
   even when the candidate count is zero.
5. Run `supabase/screening_results.sql` and `supabase/backtest_requests.sql`.
6. Insert the initial preference while authenticated, or use the dashboard for the first row.
7. Register the three server values above as GitHub Actions secrets.

Do not paste secret values into source files, chat logs, screenshots, or Android resources.
