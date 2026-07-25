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
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.time.DayOfWeek
import java.time.Duration
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

class StockNotificationWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val now = ZonedDateTime.now()
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
            val run = cloud.loadLatestRun(session) ?: return Result.success()
            val preferences = applicationContext.getSharedPreferences(
                NotificationScheduler.PREFERENCES_NAME,
                Context.MODE_PRIVATE,
            )
            if (!isTest && preferences.getString(NotificationScheduler.KEY_LAST_DATE, null) == run.screeningDate) {
                return Result.success()
            }
            val limit = preferences.getInt(NotificationScheduler.KEY_COUNT, 10).coerceIn(1, 30)
            val results = cloud.loadLatestResults(session, limit)
            val body = if (results.isEmpty()) {
                "条件一致は0件でした。アプリで判定内容を確認できます。"
            } else {
                results.joinToString("、") { result ->
                    result.companyName?.let { "${result.code} $it" } ?: result.code
                }
            }
            showNotification(
                title = if (isTest) {
                    "テスト通知：${run.screeningDate} の配信結果"
                } else {
                    "${run.screeningDate} の配信結果（${run.hitCount}件）"
                },
                body = body,
            )
            preferences.edit()
                .putString(NotificationScheduler.KEY_LAST_STATUS, "成功")
                .putString(NotificationScheduler.KEY_LAST_RUN_AT, java.time.Instant.now().toString())
                .apply {
                    if (!isTest) putString(NotificationScheduler.KEY_LAST_DATE, run.screeningDate)
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

    private fun showNotification(title: String, body: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return
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
    }

    private companion object {
        const val CHANNEL_ID = "stockai_results"
        const val NOTIFICATION_ID = 1001
        const val KEY_TEST = "test_notification"
    }
}

object NotificationScheduler {
    const val PREFERENCES_NAME = "notification_settings"
    const val KEY_TIME = "time"
    const val KEY_COUNT = "count"
    const val KEY_LAST_DATE = "last_notified_screening_date"
    const val KEY_LAST_STATUS = "last_notification_status"
    const val KEY_LAST_RUN_AT = "last_notification_run_at"
    private const val WORK_NAME = "stockai_daily_app_notification"
    private const val TEST_WORK_NAME = "stockai_test_app_notification"

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
            .addTag(WORK_NAME)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun runTest(context: Context) {
        val request = OneTimeWorkRequestBuilder<StockNotificationWorker>()
            .setInputData(workDataOf("test_notification" to true))
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            TEST_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

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
