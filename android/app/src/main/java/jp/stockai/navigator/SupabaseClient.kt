package jp.stockai.navigator

import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant

private const val MAX_MANUAL_CONDITIONS = 128

data class SupabaseSession(
    val accessToken: String,
    val refreshToken: String,
    val userId: String,
    val email: String,
    val expiresAtEpochSeconds: Long,
) {
    fun needsRefresh(nowEpochSeconds: Long = Instant.now().epochSecond): Boolean =
        expiresAtEpochSeconds <= nowEpochSeconds + 60
}
data class SupabaseRegistration(val session: SupabaseSession?, val confirmationRequired: Boolean)
data class SupabaseAuthenticatedValue<T>(val session: SupabaseSession, val value: T)

private class SupabaseRequestException(
    val statusCode: Int,
    message: String,
) : IllegalStateException(message)

data class CloudScreeningResult(
    val screeningDate: String,
    val profile: String,
    val position: Int,
    val code: String,
    val companyName: String?,
    val expectationScore: Double?,
    val comment: String?,
    val chartUrl: String?,
    val holdingDays: Int?,
    val conditionSummary: String?,
    val expectationConditionSummary: String?,
    val tradeDirection: String,
    val evaluationMode: String,
    val targetReturnPercent: Double,
    val outcomeProbabilityPercent: Double?,
    val profit10ProbabilityPercent: Double?,
    val profit20ProbabilityPercent: Double?,
    val averageReturnPercent: Double?,
    val winRatePercent: Double?,
    val maxDrawdownPercent: Double?,
    val referencePrice: Double?,
    val estimatedPriceMedian: Double?,
    val estimatedPriceLow: Double?,
    val estimatedPriceHigh: Double?,
    val estimateSampleCount: Int,
    val medianDaysToOutcome: Double?,
    val individualTradeCount: Int,
    val individualOutOfSampleTradeCount: Int,
    val individualOutOfSampleAverageReturnPercent: Double?,
    val individualOutOfSampleWinRatePercent: Double?,
    val sectorName: String?,
    val sectorBacktest: PooledBacktestSummary,
    val marketBacktest: PooledBacktestSummary,
    val backtestCoverageRatio: Double?,
    val backtestConfidence: String?,
)
data class PooledBacktestSummary(
    val stockCount: Int = 0,
    val tradeCount: Int = 0,
    val averageReturnPercent: Double? = null,
    val winRatePercent: Double? = null,
    val maxDrawdownPercent: Double? = null,
    val outOfSampleTradeCount: Int = 0,
    val outOfSampleAverageReturnPercent: Double? = null,
    val outOfSampleWinRatePercent: Double? = null,
)
data class CloudScreeningRun(
    val screeningDate: String,
    val profile: String,
    val holdingDays: Int,
    val hitCount: Int,
    val conditionSummary: String?,
    val expectationConditionSummary: String?,
    val tradeDirection: String,
    val evaluationMode: String,
    val targetReturnPercent: Double,
    val relaxationLabel: String?,
    val relaxationCounts: List<RelaxationCount>,
    val rsiMethod: String,
    val updatedAt: Instant,
)
data class RelaxationCount(val stage: String, val hitCount: Int)
data class RequestedBacktest(
    val code: String,
    val status: String,
    val score: Double?,
    val comment: String?,
    val prices: List<Price>,
    val errorMessage: String?,
)

data class CloudPreference(
    val mode: String,
    val genreId: String?,
    val manualLogic: String = "all",
    val manualConditions: List<ManualCondition> = emptyList(),
    val holdingDays: Int = 60,
    val expectationMode: String = "auto",
    val expectationGenreId: String? = null,
    val expectationManualLogic: String = "all",
    val expectationManualConditions: List<ManualCondition> = emptyList(),
    val tradeDirection: String = "long",
    val evaluationMode: String = "condition_exit",
    val targetReturnPercent: Double = 5.0,
    val rsiMethod: String = "rakuten",
)

class SupabaseClient(
    private val projectUrl: String = BuildConfig.SUPABASE_URL,
    private val anonKey: String = BuildConfig.SUPABASE_ANON_KEY,
) {
    val isConfigured: Boolean get() = projectUrl.startsWith("https://") && anonKey.isNotBlank()

    fun signIn(email: String, password: String): SupabaseSession {
        require(isConfigured) { "Supabaseが未設定です" }
        require(email.isNotBlank() && password.isNotBlank()) { "メールとパスワードを入力してください" }
        val response = request(
            "POST", "/auth/v1/token?grant_type=password",
            JSONObject().put("email", email.trim()).put("password", password),
        )
        return sessionFromResponse(response, email.trim())
    }

    fun signUp(email: String, password: String): SupabaseRegistration {
        require(isConfigured) { "Supabaseが未設定です" }
        require(email.isNotBlank()) { "メールを入力してください" }
        require(password.length >= 8) { "パスワードは8文字以上で入力してください" }
        val normalizedEmail = email.trim()
        val redirect = URLEncoder.encode(AUTH_REDIRECT_URL, Charsets.UTF_8.name())
        val response = request(
            "POST", "/auth/v1/signup?redirect_to=$redirect",
            JSONObject().put("email", normalizedEmail).put("password", password),
        )
        val accessToken = response.optString("access_token")
        if (accessToken.isBlank()) return SupabaseRegistration(null, confirmationRequired = true)
        return SupabaseRegistration(
            sessionFromResponse(response, normalizedEmail),
            confirmationRequired = false,
        )
    }

    fun sessionFromCallback(uri: Uri?): SupabaseSession? {
        if (uri?.scheme != "stockai" || uri.host != "auth") return null
        val values = buildMap {
            uri.fragment.orEmpty().split("&").forEach { item ->
                val pair = item.split("=", limit = 2)
                if (pair.size == 2) put(pair[0], Uri.decode(pair[1]))
            }
            uri.queryParameterNames.forEach { name ->
                uri.getQueryParameter(name)?.let { put(name, it) }
            }
        }
        val token = values["access_token"].orEmpty()
        if (token.isBlank()) return null
        val user = request("GET", "/auth/v1/user", token = token)
        val expiresAt = values["expires_at"]?.toLongOrNull()
            ?: (Instant.now().epochSecond + (values["expires_in"]?.toLongOrNull() ?: 3600))
        return SupabaseSession(
            token,
            values["refresh_token"].orEmpty(),
            user.getString("id"),
            user.optString("email"),
            expiresAt,
        )
    }

    fun refreshSession(session: SupabaseSession): SupabaseSession {
        require(session.refreshToken.isNotBlank()) { "再ログインが必要です" }
        val response = request(
            "POST", "/auth/v1/token?grant_type=refresh_token",
            JSONObject().put("refresh_token", session.refreshToken),
        )
        return sessionFromResponse(response, session.email)
    }

    fun <T> withFreshSession(
        session: SupabaseSession,
        action: (SupabaseSession) -> T,
    ): SupabaseAuthenticatedValue<T> {
        var current = if (session.needsRefresh()) refreshSession(session) else session
        return try {
            SupabaseAuthenticatedValue(current, action(current))
        } catch (error: SupabaseRequestException) {
            if (!error.isExpiredJwt()) throw error
            current = refreshSession(current)
            SupabaseAuthenticatedValue(current, action(current))
        }
    }

    fun loadPreference(session: SupabaseSession): CloudPreference? {
        val response = requestArray(
            "GET",
            "/rest/v1/screening_preferences?user_id=eq.${session.userId}" +
                "&select=mode,genre_id,manual_logic,manual_conditions,holding_days," +
                "expectation_mode,expectation_genre_id,expectation_manual_logic," +
                "expectation_manual_conditions,trade_direction," +
                "expectation_evaluation_mode,target_return_percent,rsi_method&limit=1",
            token = session.accessToken,
        )
        if (response.length() == 0) return null
        val row = response.getJSONObject(0)
        val conditions = row.optJSONArray("manual_conditions") ?: JSONArray()
        val expectationConditions =
            row.optJSONArray("expectation_manual_conditions") ?: conditions
        return CloudPreference(
            mode = row.getString("mode"),
            genreId = row.optString("genre_id").takeIf { it.isNotBlank() },
            manualLogic = row.optString("manual_logic", "all"),
            manualConditions = (0 until conditions.length()).map { index ->
                val item = conditions.getJSONObject(index)
                ManualCondition(item.getString("field"), item.getString("operator"), item.getDouble("value"))
            },
            holdingDays = row.optInt("holding_days", 60),
            expectationMode = row.optString("expectation_mode", row.getString("mode")),
            expectationGenreId = row.optString("expectation_genre_id")
                .takeIf { it.isNotBlank() } ?: row.optString("genre_id").takeIf { it.isNotBlank() },
            expectationManualLogic = row.optString("expectation_manual_logic", "all"),
            expectationManualConditions = (0 until expectationConditions.length()).map { index ->
                val item = expectationConditions.getJSONObject(index)
                ManualCondition(item.getString("field"), item.getString("operator"), item.getDouble("value"))
            },
            tradeDirection = row.optString("trade_direction", "long"),
            evaluationMode = row.optString(
                "expectation_evaluation_mode", "condition_exit"
            ),
            targetReturnPercent = row.optDouble("target_return_percent", 5.0),
            rsiMethod = row.optString("rsi_method", "rakuten"),
        )
    }

    fun savePreference(session: SupabaseSession, preference: CloudPreference) {
        require(preference.mode in setOf("auto", "manual")) { "保存モードが不正です" }
        require(preference.mode != "auto" || !preference.genreId.isNullOrBlank()) { "ジャンルを選択してください" }
        require(preference.mode != "manual" || preference.manualConditions.isNotEmpty()) {
            "マニュアルのソート条件を1件以上入力してください"
        }
        require(preference.manualConditions.size <= MAX_MANUAL_CONDITIONS) {
            "ソート条件は${MAX_MANUAL_CONDITIONS}件までです"
        }
        require(preference.expectationManualConditions.size <= MAX_MANUAL_CONDITIONS) {
            "期待値条件は${MAX_MANUAL_CONDITIONS}件までです"
        }
        require(preference.holdingDays in 1..1000) { "検証期間は1～1000営業日で入力してください" }
        require(preference.tradeDirection in setOf("long", "short")) {
            "売買方向が不正です"
        }
        require(
            preference.evaluationMode in setOf(
                "condition_exit", "period_end", "within_period_up", "target_return"
            )
        ) { "期待値の判定方式が不正です" }
        require(preference.targetReturnPercent > 0.0 &&
            preference.targetReturnPercent <= 100.0
        ) { "目標騰落率は0より大きく100以下で入力してください" }
        require(preference.rsiMethod in setOf("auto", "rakuten", "wilder")) {
            "RSI計算方式が不正です"
        }
        val conditions = JSONArray().apply {
            preference.manualConditions.forEach { item ->
                put(JSONObject().put("field", item.field).put("operator", item.operator).put("value", item.value))
            }
        }
        val expectationConditions = JSONArray().apply {
            preference.expectationManualConditions.forEach { item ->
                put(JSONObject().put("field", item.field).put("operator", item.operator).put("value", item.value))
            }
        }
        val payload = JSONObject()
            .put("user_id", session.userId)
            .put("mode", preference.mode)
            .put("genre_id", preference.genreId ?: JSONObject.NULL)
            .put("manual_logic", preference.manualLogic)
            .put("manual_conditions", conditions)
            .put("holding_days", preference.holdingDays)
            .put("expectation_mode", preference.expectationMode)
            .put("expectation_genre_id", preference.expectationGenreId ?: JSONObject.NULL)
            .put("expectation_manual_logic", preference.expectationManualLogic)
            .put("expectation_manual_conditions", expectationConditions)
            .put("trade_direction", preference.tradeDirection)
            .put("expectation_evaluation_mode", preference.evaluationMode)
            .put("target_return_percent", preference.targetReturnPercent)
            .put("rsi_method", preference.rsiMethod)
            .put("updated_at", Instant.now().toString())
        requestArray(
            "POST", "/rest/v1/screening_preferences?on_conflict=user_id", payload, session.accessToken,
            mapOf("Prefer" to "resolution=merge-duplicates,return=representation"),
        )
    }

    fun loadLatestResults(session: SupabaseSession, limit: Int = 30): List<CloudScreeningResult> {
        val safeLimit = limit.coerceIn(1, 30)
        val response = requestArray(
            "GET",
            "/rest/v1/screening_results?user_id=eq.${session.userId}" +
                "&select=screening_date,profile_name,position,code,company_name,expectation_score,comment,chart_url" +
                ",holding_days,condition_summary,expectation_condition_summary,trade_direction" +
                ",expectation_evaluation_mode,target_return_percent,outcome_probability_percent" +
                ",profit_10_probability_percent,profit_20_probability_percent" +
                ",average_return_percent,win_rate_percent,max_drawdown_percent" +
                ",reference_price,estimated_price_median,estimated_price_low,estimated_price_high" +
                ",estimate_sample_count,median_days_to_outcome" +
                ",individual_trade_count,individual_out_of_sample_trade_count" +
                ",individual_out_of_sample_average_return_percent" +
                ",individual_out_of_sample_win_rate_percent,sector_name" +
                ",sector_backtest,market_backtest,backtest_coverage_ratio" +
                ",backtest_confidence" +
                "&order=screening_date.desc,position.asc&limit=$safeLimit",
            token = session.accessToken,
        )
        if (response.length() == 0) return emptyList()
        val latestDate = response.getJSONObject(0).getString("screening_date")
        return (0 until response.length()).map { response.getJSONObject(it) }
            .takeWhile { it.getString("screening_date") == latestDate }
            .map { row ->
                CloudScreeningResult(
                    screeningDate = row.getString("screening_date"),
                    profile = row.getString("profile_name"),
                    position = row.getInt("position"),
                    code = row.getString("code"),
                    companyName = row.optString("company_name").takeIf { it.isNotEmpty() },
                    expectationScore = row.optDouble("expectation_score").takeUnless { it.isNaN() },
                    comment = row.optString("comment").takeIf { it.isNotEmpty() },
                    chartUrl = row.optString("chart_url").takeIf { it.isNotEmpty() },
                    holdingDays = row.optInt("holding_days").takeIf { !row.isNull("holding_days") },
                    conditionSummary = row.optString("condition_summary").takeIf { it.isNotEmpty() },
                    expectationConditionSummary = row.optString(
                        "expectation_condition_summary"
                    ).takeIf { it.isNotEmpty() },
                    tradeDirection = row.optString("trade_direction", "long"),
                    evaluationMode = row.optString(
                        "expectation_evaluation_mode", "condition_exit"
                    ),
                    targetReturnPercent = row.optDouble("target_return_percent", 5.0),
                    outcomeProbabilityPercent = row.optDouble(
                        "outcome_probability_percent"
                    ).takeUnless { it.isNaN() },
                    profit10ProbabilityPercent = row.optDouble(
                        "profit_10_probability_percent"
                    ).takeUnless { it.isNaN() },
                    profit20ProbabilityPercent = row.optDouble(
                        "profit_20_probability_percent"
                    ).takeUnless { it.isNaN() },
                    averageReturnPercent = row.optDouble(
                        "average_return_percent"
                    ).takeUnless { it.isNaN() },
                    winRatePercent = row.optDouble(
                        "win_rate_percent"
                    ).takeUnless { it.isNaN() },
                    maxDrawdownPercent = row.optDouble(
                        "max_drawdown_percent"
                    ).takeUnless { it.isNaN() },
                    referencePrice = row.optDouble(
                        "reference_price"
                    ).takeUnless { it.isNaN() },
                    estimatedPriceMedian = row.optDouble(
                        "estimated_price_median"
                    ).takeUnless { it.isNaN() },
                    estimatedPriceLow = row.optDouble(
                        "estimated_price_low"
                    ).takeUnless { it.isNaN() },
                    estimatedPriceHigh = row.optDouble(
                        "estimated_price_high"
                    ).takeUnless { it.isNaN() },
                    estimateSampleCount = row.optInt("estimate_sample_count", 0),
                    medianDaysToOutcome = row.optDouble(
                        "median_days_to_outcome"
                    ).takeUnless { it.isNaN() },
                    individualTradeCount = row.optInt(
                        "individual_trade_count", 0
                    ),
                    individualOutOfSampleTradeCount = row.optInt(
                        "individual_out_of_sample_trade_count", 0
                    ),
                    individualOutOfSampleAverageReturnPercent = row.optDouble(
                        "individual_out_of_sample_average_return_percent"
                    ).takeUnless { it.isNaN() },
                    individualOutOfSampleWinRatePercent = row.optDouble(
                        "individual_out_of_sample_win_rate_percent"
                    ).takeUnless { it.isNaN() },
                    sectorName = row.optString("sector_name").takeIf {
                        it.isNotEmpty()
                    },
                    sectorBacktest = pooledBacktestSummary(
                        row.optJSONObject("sector_backtest")
                    ),
                    marketBacktest = pooledBacktestSummary(
                        row.optJSONObject("market_backtest")
                    ),
                    backtestCoverageRatio = row.optDouble(
                        "backtest_coverage_ratio"
                    ).takeUnless { it.isNaN() },
                    backtestConfidence = row.optString(
                        "backtest_confidence"
                    ).takeIf { it.isNotEmpty() },
                )
            }
    }

    private fun pooledBacktestSummary(value: JSONObject?): PooledBacktestSummary {
        val row = value ?: JSONObject()
        return PooledBacktestSummary(
            stockCount = row.optInt("stock_count", 0),
            tradeCount = row.optInt("trade_count", 0),
            averageReturnPercent = row.optDouble(
                "average_return_percent"
            ).takeUnless { it.isNaN() },
            winRatePercent = row.optDouble(
                "win_rate_percent"
            ).takeUnless { it.isNaN() },
            maxDrawdownPercent = row.optDouble(
                "max_drawdown_percent"
            ).takeUnless { it.isNaN() },
            outOfSampleTradeCount = row.optInt(
                "out_of_sample_trade_count", 0
            ),
            outOfSampleAverageReturnPercent = row.optDouble(
                "out_of_sample_average_return_percent"
            ).takeUnless { it.isNaN() },
            outOfSampleWinRatePercent = row.optDouble(
                "out_of_sample_win_rate_percent"
            ).takeUnless { it.isNaN() },
        )
    }

    fun loadLatestRun(session: SupabaseSession): CloudScreeningRun? {
        val response = requestArray(
            "GET",
            "/rest/v1/screening_runs?user_id=eq.${session.userId}" +
                "&select=screening_date,profile_name,holding_days,hit_count,condition_summary,updated_at" +
                ",expectation_condition_summary,trade_direction,relaxation_label,relaxation_counts" +
                ",expectation_evaluation_mode,target_return_percent,rsi_method" +
                "&order=updated_at.desc&limit=1",
            token = session.accessToken,
        )
        if (response.length() == 0) return null
        val row = response.getJSONObject(0)
        val relaxationCounts = row.optJSONArray("relaxation_counts") ?: JSONArray()
        return CloudScreeningRun(
            screeningDate = row.getString("screening_date"),
            profile = row.getString("profile_name"),
            holdingDays = row.getInt("holding_days"),
            hitCount = row.getInt("hit_count"),
            conditionSummary = row.optString("condition_summary").takeIf { it.isNotEmpty() },
            expectationConditionSummary = row.optString(
                "expectation_condition_summary"
            ).takeIf { it.isNotEmpty() },
            tradeDirection = row.optString("trade_direction", "long"),
            evaluationMode = row.optString(
                "expectation_evaluation_mode", "condition_exit"
            ),
            targetReturnPercent = row.optDouble("target_return_percent", 5.0),
            rsiMethod = row.optString("rsi_method", "rakuten"),
            relaxationLabel = row.optString("relaxation_label").takeIf { it.isNotEmpty() },
            relaxationCounts = (0 until relaxationCounts.length()).map { index ->
                val item = relaxationCounts.getJSONObject(index)
                RelaxationCount(
                    stage = item.optString("stage"),
                    hitCount = item.optInt("hit_count"),
                )
            },
            updatedAt = Instant.parse(row.getString("updated_at")),
        )
    }

    fun loadLatestCandidates(session: SupabaseSession): CandidatePool {
        val runResponse = runCatching {
            requestArray(
                "GET",
                "/rest/v1/screening_candidate_runs?select=pool_date,universe_count," +
                    "evaluated_count,candidate_count,failed_count,coverage_ratio,status," +
                    "usable,updated_at&order=pool_date.desc&limit=1",
                token = session.accessToken,
            )
        }.getOrNull()
        if (runResponse != null && runResponse.length() > 0) {
            val run = runResponse.getJSONObject(0)
            val latestDate = run.getString("pool_date")
            val candidates = requestArray(
                "GET",
                "/rest/v1/screening_candidates?pool_date=eq.$latestDate&select=code" +
                    "&order=code.asc&limit=5000",
                token = session.accessToken,
            )
            return CandidatePool(
                poolDate = latestDate,
                codes = (0 until candidates.length()).map {
                    candidates.getJSONObject(it).getString("code")
                },
                updatedAt = run.optString("updated_at").takeIf { it.isNotBlank() },
                universeCount = run.optInt("universe_count"),
                evaluatedCount = run.optInt("evaluated_count"),
                candidateCount = run.optInt("candidate_count"),
                failedCount = run.optInt("failed_count"),
                coverageRatio = run.optDouble("coverage_ratio"),
                status = run.optString("status").takeIf { it.isNotBlank() },
                usable = run.optBoolean("usable"),
            )
        }
        val response = requestArray(
            "GET",
            "/rest/v1/screening_candidates?select=pool_date,code,updated_at" +
                "&order=pool_date.desc,code.asc&limit=500",
            token = session.accessToken,
        )
        if (response.length() == 0) return CandidatePool(null, emptyList(), null)
        val latestDate = response.getJSONObject(0).getString("pool_date")
        val updatedAt = response.getJSONObject(0).optString("updated_at").takeIf { it.isNotBlank() }
        val codes = (0 until response.length())
            .map { response.getJSONObject(it) }
            .takeWhile { it.getString("pool_date") == latestDate }
            .map { it.getString("code") }
        return CandidatePool(latestDate, codes, updatedAt)
    }

    fun requestBacktest(session: SupabaseSession, code: String) {
        val normalized = code.trim().uppercase()
        require(normalized.matches(Regex("[0-9A-Z]{4,5}"))) {
            "銘柄コードを4～5文字で入力してください"
        }
        requestArray(
            "POST",
            "/rest/v1/backtest_requests",
            JSONObject()
                .put("user_id", session.userId)
                .put("code", normalized)
                .put("status", "pending"),
            session.accessToken,
            mapOf("Prefer" to "return=representation"),
        )
    }

    fun loadLatestBacktest(session: SupabaseSession): RequestedBacktest? {
        val response = requestArray(
            "GET",
            "/rest/v1/backtest_requests?user_id=eq.${session.userId}" +
                "&select=code,status,result_json,error_message" +
                "&order=created_at.desc&limit=1",
            token = session.accessToken,
        )
        if (response.length() == 0) return null
        val row = response.getJSONObject(0)
        val result = row.optJSONObject("result_json")
        val expectation = result?.optJSONObject("expectation")
        val prices = result?.optJSONArray("prices") ?: JSONArray()
        return RequestedBacktest(
            code = row.getString("code"),
            status = row.getString("status"),
            score = expectation?.optDouble("score")?.takeUnless { it.isNaN() },
            comment = result?.optString("comment")?.takeIf { it.isNotEmpty() },
            prices = (0 until prices.length()).map { index ->
                val price = prices.getJSONObject(index)
                Price(price.getString("date"), price.getDouble("close"))
            },
            errorMessage = row.optString("error_message").takeIf { it.isNotEmpty() },
        )
    }

    private fun request(method: String, path: String, payload: JSONObject? = null, token: String? = null): JSONObject =
        JSONObject(requestText(method, path, payload?.toString(), token))

    private fun requestArray(
        method: String, path: String, payload: JSONObject? = null, token: String? = null,
        extraHeaders: Map<String, String> = emptyMap(),
    ): JSONArray = JSONArray(requestText(method, path, payload?.toString(), token, extraHeaders))

    private fun requestText(
        method: String, path: String, payload: String?, token: String?, extraHeaders: Map<String, String> = emptyMap(),
    ): String {
        require(isConfigured) { "Supabaseが未設定です" }
        val connection = URL(projectUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 10_000
            connection.readTimeout = 15_000
            connection.setRequestProperty("apikey", anonKey)
            connection.setRequestProperty("Authorization", "Bearer ${token ?: anonKey}")
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            extraHeaders.forEach(connection::setRequestProperty)
            if (payload != null) {
                connection.doOutput = true
                connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val body = (if (code in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val message = runCatching {
                    val error = JSONObject(body)
                    sequenceOf("msg", "message", "error_description", "error")
                        .map { error.optString(it) }
                        .firstOrNull { it.isNotBlank() }
                }.getOrNull().orEmpty().ifBlank { "HTTP $code" }
                throw SupabaseRequestException(code, "Supabase: $message")
            }
            body.ifBlank { if (method == "GET" || path.startsWith("/rest/")) "[]" else "{}" }
        } finally {
            connection.disconnect()
        }
    }

    private fun sessionFromResponse(response: JSONObject, fallbackEmail: String): SupabaseSession {
        val user = response.getJSONObject("user")
        return SupabaseSession(
            accessToken = response.getString("access_token"),
            refreshToken = response.optString("refresh_token"),
            userId = user.getString("id"),
            email = user.optString("email", fallbackEmail),
            expiresAtEpochSeconds = response.optLong(
                "expires_at",
                Instant.now().epochSecond + response.optLong("expires_in", 3600),
            ),
        )
    }

    private companion object {
        const val AUTH_REDIRECT_URL = "stockai://auth/confirm"
    }
}

private fun SupabaseRequestException.isExpiredJwt(): Boolean {
    if (statusCode != HttpURLConnection.HTTP_UNAUTHORIZED) return false
    val normalized = message.orEmpty().lowercase()
    return "jwt" in normalized || "token" in normalized || "expired" in normalized
}
