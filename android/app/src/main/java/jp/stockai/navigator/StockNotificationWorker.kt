package jp.stockai.navigator

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.time.DayOfWeek
import java.time.Duration
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

class StockNotificationWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val now = ZonedDateTime.now(JAPAN_ZONE)
        val isTest = inputData.getBoolean(KEY_TEST, false)
        if (!isTest && now.dayOfWeek in setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)) {
            return Result.success()
        }
        val store = SessionStore(applicationContext)
        var session = store.load() ?: return Result.success()
        return runCatching {
            val cloud = SupabaseClient()
            if (session.needsRefresh()) {
                session = cloud.refreshSession(session)
                store.save(session)
            }
            val preferences = applicationContext.getSharedPreferences(
                NotificationScheduler.PREFERENCES_NAME,
                Context.MODE_PRIVATE,
            )
            val run = cloud.loadLatestRun(session)
            if (run == null) {
                if (!isTest) {
                    waitForFreshResult(preferences, "当日結果を準備中")
                }
                return Result.success()
            }
            val runUpdatedDate = run.updatedAt.atZone(JAPAN_ZONE).toLocalDate()
            if (!isTest && runUpdatedDate != now.toLocalDate()) {
                waitForFreshResult(preferences, "当日結果を準備中")
                return Result.success()
            }
            if (!isTest &&
                preferences.getString(NotificationScheduler.KEY_LAST_RUN_UPDATED_AT, null) ==
                run.updatedAt.toString()
            ) {
                return Result.success()
            }
            val limit = preferences.getInt(NotificationScheduler.KEY_COUNT, 10).coerceIn(1, 30)
            val results = cloud.loadLatestResults(session, limit)
                .filter { it.screeningDate == run.screeningDate }
            if (!isTest && run.hitCount > 0 && results.isEmpty()) {
                waitForFreshResult(preferences, "配信結果を反映中")
                return Result.success()
            }
            val body = if (run.hitCount == 0 || results.isEmpty()) {
                "条件一致は0件でした。アプリで判定内容を確認できます。"
            } else {
                results.joinToString("、") { result ->
                    result.companyName?.let { "${result.code} $it" } ?: result.code
                }
            }
            val notified = showNotification(
                title = if (isTest) {
                    "テスト通知：${run.screeningDate} の配信結果"
                } else {
                    "${run.screeningDate} の配信結果（${run.hitCount}件）"
                },
                body = body,
            )
            if (!notified) {
                preferences.edit()
                    .putString(NotificationScheduler.KEY_LAST_STATUS, "通知権限がありません")
                    .putString(
                        NotificationScheduler.KEY_LAST_RUN_AT,
                        java.time.Instant.now().toString(),
                    )
                    .apply()
                return Result.success()
            }
            preferences.edit()
                .putString(NotificationScheduler.KEY_LAST_STATUS, "成功")
                .putString(NotificationScheduler.KEY_LAST_RUN_AT, java.time.Instant.now().toString())
                .apply {
                    if (!isTest) {
                        putString(NotificationScheduler.KEY_LAST_DATE, run.screeningDate)
                        putString(
                            NotificationScheduler.KEY_LAST_RUN_UPDATED_AT,
                            run.updatedAt.toString(),
                        )
                    }
                }
                .apply()
            Result.success()
        }.getOrElse {
            applicationContext.getSharedPreferences(
                NotificationScheduler.PREFERENCES_NAME,
                Context.MODE_PRIVATE,
            ).edit()
                .putString(NotificationScheduler.KEY_LAST_STATUS, "失敗: ${it.javaClass.simpleName}")
                .putString(NotificationScheduler.KEY_LAST_RUN_AT, java.time.Instant.now().toString())
                .apply()
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }

    private fun waitForFreshResult(
        preferences: android.content.SharedPreferences,
        status: String,
    ) {
        preferences.edit()
            .putString(NotificationScheduler.KEY_LAST_STATUS, status)
            .putString(NotificationScheduler.KEY_LAST_RUN_AT, java.time.Instant.now().toString())
            .apply()
        val retryNumber = inputData.getInt(KEY_FRESHNESS_RETRY, 0)
        if (retryNumber < MAX_FRESHNESS_RETRIES) {
            NotificationScheduler.scheduleFreshnessRetry(applicationContext, retryNumber + 1)
        } else {
            preferences.edit()
                .putString(NotificationScheduler.KEY_LAST_STATUS, "当日結果を取得できませんでした")
                .apply()
        }
    }

    private fun showNotification(title: String, body: String): Boolean {
        if (Build.VERSION.SDK_INT >= 33 &&
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return false
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "StockAI 配信結果",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "保存した時刻に最新の銘柄選定結果を通知します"
            }
        )
        val intent = Intent(applicationContext, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_START_PAGE, "results")
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pendingIntent = PendingIntent.getActivity(
            applicationContext,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(applicationContext).notify(NOTIFICATION_ID, notification)
        return true
    }

    companion object {
        private const val CHANNEL_ID = "stockai_results"
        private const val NOTIFICATION_ID = 1001
        private const val KEY_TEST = "test_notification"
        internal const val KEY_FRESHNESS_RETRY = "freshness_retry"
        private const val MAX_FRESHNESS_RETRIES = 12
        private val JAPAN_ZONE: ZoneId = ZoneId.of("Asia/Tokyo")
    }
}

object NotificationScheduler {
    const val PREFERENCES_NAME = "notification_settings"
    const val KEY_TIME = "time"
    const val KEY_COUNT = "count"
    const val KEY_LAST_DATE = "last_notified_screening_date"
    const val KEY_LAST_RUN_UPDATED_AT = "last_notified_run_updated_at"
    const val KEY_LAST_STATUS = "last_notification_status"
    const val KEY_LAST_RUN_AT = "last_notification_run_at"
    private const val WORK_NAME = "stockai_daily_app_notification"
    private const val TEST_WORK_NAME = "stockai_test_app_notification"
    private const val FRESHNESS_WORK_NAME = "stockai_fresh_result_retry"

    fun schedule(context: Context, time: String) {
        val parts = time.split(":")
        val hour = parts.getOrNull(0)?.toIntOrNull() ?: 10
        val minute = parts.getOrNull(1)?.toIntOrNull() ?: 0
        val now = ZonedDateTime.now()
        var next = now.withHour(hour).withMinute(minute).withSecond(0).withNano(0)
        if (!next.isAfter(now)) next = next.plusDays(1)
        val delay = Duration.between(now, next).toMillis().coerceAtLeast(1_000L)
        val request = PeriodicWorkRequestBuilder<StockNotificationWorker>(24, TimeUnit.HOURS)
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .setConstraints(networkConstraints())
            .addTag(WORK_NAME)
            .build()
        val workManager = WorkManager.getInstance(context)
        workManager.cancelUniqueWork(FRESHNESS_WORK_NAME)
        workManager.enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun runTest(context: Context) {
        val request = OneTimeWorkRequestBuilder<StockNotificationWorker>()
            .setInputData(workDataOf("test_notification" to true))
            .setConstraints(networkConstraints())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            TEST_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    fun scheduleFreshnessRetry(context: Context, retryNumber: Int) {
        val request = OneTimeWorkRequestBuilder<StockNotificationWorker>()
            .setInitialDelay(10, TimeUnit.MINUTES)
            .setConstraints(networkConstraints())
            .setInputData(
                workDataOf(StockNotificationWorker.KEY_FRESHNESS_RETRY to retryNumber)
            )
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            FRESHNESS_WORK_NAME,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }

    private fun networkConstraints(): Constraints =
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

    fun showImmediateTest(context: Context) {
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                "stockai_results",
                "StockAI 配信結果",
                NotificationManager.IMPORTANCE_DEFAULT,
            )
        )
        val intent = Intent(context, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_START_PAGE, "results")
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pendingIntent = PendingIntent.getActivity(
            context,
            1,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, "stockai_results")
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("StockAI テスト通知")
            .setContentText("端末通知は正常です。タップすると配信結果を開きます。")
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(1002, notification)
        context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LAST_STATUS, "テスト成功")
            .putString(KEY_LAST_RUN_AT, java.time.Instant.now().toString())
            .apply()
    }
}
