package jp.stockai.navigator

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Ranking(val code: String, val score: Double?, val grade: String?)
data class CandidatePool(
    val poolDate: String?,
    val codes: List<String>,
    val updatedAt: String? = null,
    val universeCount: Int? = null,
    val evaluatedCount: Int? = null,
    val candidateCount: Int? = null,
    val failedCount: Int? = null,
    val coverageRatio: Double? = null,
    val status: String? = null,
    val usable: Boolean? = null,
)
data class Price(val date: String, val close: Double)
data class HistoryItem(
    val date: String,
    val profile: String,
    val type: String,
    val expectationScore: Double?,
    val grade: String?,
    val tradeCount: Int?,
    val winRatePercent: Double?,
    val averageReturnPercent: Double?,
    val maxDrawdownPercent: Double?,
    val comment: String?,
)
data class JobRun(val name: String, val status: String, val finishedAt: String)
data class MarketRegime(val marketCode: String, val date: String, val regime: String)
data class DailyReport(
    val generatedAt: String,
    val status: String,
    val latestPriceDate: String?,
    val priceDataStatus: String,
    val watchlistCount: Int,
    val marketRegimes: List<MarketRegime>,
    val jobs: List<JobRun>,
)
data class OperationsStatus(
    val ready: Boolean,
    val poolDate: String?,
    val poolStatus: String?,
    val universeCount: Int?,
    val evaluatedCount: Int?,
    val eveningUpdatedCount: Int?,
    val eveningFailedCount: Int?,
    val candidateCount: Int?,
    val morningUpdatedCount: Int?,
    val morningFailedCount: Int?,
    val screeningDate: String?,
    val hitCount: Int?,
    val effectiveProfile: String?,
    val relaxationLabel: String?,
)
data class Holding(
    val code: String,
    val companyName: String?,
    val marketValue: Double?,
    val profitLoss: Double?,
    val weightPercent: Double?,
)
data class PortfolioSummary(val totalMarketValue: Double, val positions: List<Holding>)
data class WatchlistItem(val code: String, val note: String?, val companyName: String?)
data class ScreeningHit(val code: String, val score: Double?, val reason: String)
data class ScreeningGenre(val id: String, val label: String, val description: String, val profile: String, val evidenceStatus: String)
data class ManualField(
    val field: String,
    val label: String,
    val min: Double,
    val max: Double,
    val defaultOperator: String,
    val category: String = "technical",
)
data class ScreeningOptions(val genres: List<ScreeningGenre>, val manualFields: List<ManualField>)
data class ManualCondition(val field: String, val operator: String, val value: Double)
data class StockOverview(
    val companyName: String?, val sector: String?, val close: Double?, val priceDate: String?,
    val per: Double?, val pbr: Double?, val roe: Double?, val dividendYield: Double?,
    val relativePerformance: List<RelativePerformance>,
)
data class RelativePerformance(val sessions: Int, val excessReturnPercent: Double)

private fun builtInTechnicalManualFields(): List<ManualField> = buildList {
    for ((prefix, timeframe) in listOf(
        "daily" to "日足", "weekly" to "週足", "monthly" to "月足",
    )) {
        add(ManualField("$prefix.rsi_9", "${timeframe}RSI（短期・9本）", 0.0, 100.0, "<="))
        add(ManualField("$prefix.rsi_14", "${timeframe}RSI（標準・14本）", 0.0, 100.0, "<="))
        for ((fieldSuffix, periodLabel) in listOf(
            "macd_5_25_9" to "短期・5/25/9本",
            "macd" to "標準・12/26/9本",
            "macd_25_75_14" to "長期・25/75/14本",
        )) {
            add(ManualField(
                "$prefix.$fieldSuffix", "${timeframe}MACD（$periodLabel）",
                -100000.0, 100000.0, ">=",
            ))
        }
        for ((fieldSuffix, periodLabel) in listOf(
            "macd_histogram_5_25_9" to "短期・5/25/9本",
            "macd_histogram" to "標準・12/26/9本",
            "macd_histogram_25_75_14" to "長期・25/75/14本",
        )) {
            add(ManualField(
                "$prefix.$fieldSuffix", "${timeframe}MACDヒストグラム（$periodLabel）",
                -100000.0, 100000.0, ">=",
            ))
        }
        for ((suffix, periodLabel) in listOf("9_3" to "短期・9/3本", "" to "標準・14/3本")) {
            val separator = if (suffix.isBlank()) "" else "_$suffix"
            add(ManualField(
                "$prefix.stoch_k$separator", "${timeframe}ストキャスティクス%K（$periodLabel）",
                0.0, 100.0, "<=",
            ))
            add(ManualField(
                "$prefix.stoch_d$separator", "${timeframe}ストキャスティクス%D（$periodLabel）",
                0.0, 100.0, "<=",
            ))
        }
        add(ManualField("$prefix.adx_14", "${timeframe}ADX", 0.0, 100.0, ">="))
        add(ManualField("$prefix.bb_percent_b", "${timeframe}ボリンジャー%B", -100.0, 200.0, "<="))
        add(ManualField("$prefix.atr_14_percent", "${timeframe}ATR比率", 0.0, 100.0, "<="))
        for ((period, horizon) in listOf(5 to "短期", 25 to "中期", 75 to "長期", 200 to "超長期")) {
            add(ManualField(
                "$prefix.price_vs_sma_${period}_percent",
                "${timeframe}${period}本移動平均乖離率（$horizon）",
                -100.0, 500.0, ">=",
            ))
        }
        val returnFields = when (prefix) {
            "daily" -> listOf(
                Triple(5, "5日", 500.0),
                Triple(20, "20日", 500.0),
                Triple(60, "60日", 1000.0),
            )
            "weekly" -> listOf(
                Triple(20, "週足20本", 1000.0),
                Triple(60, "週足60本", 5000.0),
            )
            else -> listOf(
                Triple(20, "月足20本", 10000.0),
                Triple(60, "月足60本", 100000.0),
            )
        }
        for ((period, labelPrefix, maximum) in returnFields) {
            add(ManualField(
                "$prefix.return_${period}_percent", "${labelPrefix}騰落率",
                -100.0, maximum, ">=",
            ))
        }
        add(ManualField(
            "$prefix.volume_ratio_20", "${timeframe}20本平均出来高比",
            0.0, 10000.0, ">=",
        ))
    }
}

fun builtInScreeningOptions(): ScreeningOptions = ScreeningOptions(
    genres = listOf(
        ScreeningGenre("value", "割安株", "PER・PBR・財務健全性を重視します。", "value", "baseline"),
        ScreeningGenre("high_dividend", "高配当株", "実績配当利回り・自己資本比率・営業CFを重視します。", "high_dividend", "baseline"),
        ScreeningGenre("growth", "成長株", "ROE・営業利益率・中期上昇トレンドを重視します。", "growth", "baseline"),
        ScreeningGenre("momentum", "上昇モメンタム", "移動平均とMACDによる上昇傾向を重視します。", "momentum", "baseline"),
        ScreeningGenre("rebound", "反発候補", "RSIの改善を重視します。", "rsi_rebound", "baseline"),
        ScreeningGenre("adjustment", "調整局面", "日・週・月のRSIが低い銘柄を探します。", "oversold", "needs_validation"),
    ),
    manualFields = builtInTechnicalManualFields() + listOf(
        ManualField("fundamental.per", "PER", -1000.0, 2000.0, "<=", "fundamental"),
        ManualField("fundamental.pbr", "PBR", -100.0, 200.0, "<=", "fundamental"),
        ManualField("fundamental.roe", "ROE", -1000.0, 1000.0, ">=", "fundamental"),
        ManualField("fundamental.roa", "ROA", -1000.0, 1000.0, ">=", "fundamental"),
        ManualField("fundamental.operating_margin", "営業利益率", -1000.0, 1000.0, ">=", "fundamental"),
        ManualField("fundamental.equity_ratio", "自己資本比率", -100.0, 100.0, ">=", "fundamental"),
        ManualField("fundamental.dividend_yield", "配当利回り", 0.0, 100.0, ">=", "fundamental"),
        ManualField("fundamental.operating_cash_flow", "営業CF", -1e14, 1e14, ">=", "fundamental"),
    ),
)

class ApiClient(private val baseUrl: String = "http://10.0.2.2:8000") {
    private fun get(path: String): JSONObject {
        val connection = URL(baseUrl + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 5_000
            connection.readTimeout = 10_000
            if (connection.responseCode !in 200..299) error("API error: ${connection.responseCode}")
            JSONObject(connection.inputStream.bufferedReader().readText())
        } finally { connection.disconnect() }
    }

    private fun post(path: String, payload: JSONObject): JSONObject {
        val connection = URL(baseUrl + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 5_000
            connection.readTimeout = 20_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            if (connection.responseCode !in 200..299) error("API error: ${connection.responseCode}")
            JSONObject(connection.inputStream.bufferedReader().readText())
        } finally { connection.disconnect() }
    }

    fun rankings(): List<Ranking> = get("/rankings").getJSONArray("rankings").mapItems { item ->
        val value = item as JSONObject
        Ranking(value.getString("code"), value.optDouble("expectation_score").takeUnless { it.isNaN() }, value.optString("grade"))
    }
    fun prices(code: String): List<Price> = get("/stocks/${code}/prices?timeframe=daily&limit=180").getJSONArray("prices").mapItems { item ->
        val value = item as JSONObject
        Price(value.getString("trade_date"), value.getDouble("close"))
    }
    fun history(code: String): List<HistoryItem> = get("/stocks/${code}/history").getJSONArray("history").mapItems { item ->
        val value = item as JSONObject
        val result = value.optJSONObject("result")
        val expectation = result?.optJSONObject("expectation")
        val summary = result?.optJSONObject("summary")
        HistoryItem(
            date = value.getString("as_of_date"),
            profile = value.getString("profile_name"),
            type = value.getString("analysis_type"),
            expectationScore = expectation?.optionalDouble("score"),
            grade = expectation?.optString("grade")?.takeIf { it.isNotEmpty() },
            tradeCount = summary?.optionalInt("trade_count"),
            winRatePercent = summary?.optionalDouble("win_rate_percent"),
            averageReturnPercent = summary?.optionalDouble("average_return_percent"),
            maxDrawdownPercent = summary?.optionalDouble("max_drawdown_percent"),
            comment = result?.optString("comment")?.takeIf { it.isNotEmpty() },
        )
    }
    fun overview(code: String): StockOverview {
        val value = get("/stocks/${code}/overview")
        val master = value.optJSONObject("master")
        val price = value.optJSONObject("latest_price")
        val fundamentals = value.getJSONObject("fundamentals")
        val performance = value.getJSONArray("relative_performance").mapItems { item ->
            val period = item as JSONObject
            RelativePerformance(period.getInt("sessions"), period.getDouble("excess_return_percent"))
        }
        return StockOverview(
            companyName = master?.optString("company_name")?.takeIf { it.isNotEmpty() },
            sector = master?.optString("sector_33_name")?.takeIf { it.isNotEmpty() },
            close = price?.optDouble("close")?.takeUnless { it.isNaN() },
            priceDate = price?.optString("trade_date")?.takeIf { it.isNotEmpty() },
            per = fundamentals.optDouble("per").takeUnless { it.isNaN() },
            pbr = fundamentals.optDouble("pbr").takeUnless { it.isNaN() },
            roe = fundamentals.optDouble("roe").takeUnless { it.isNaN() },
            dividendYield = fundamentals.optDouble("dividend_yield").takeUnless { it.isNaN() },
            relativePerformance = performance,
        )
    }
    fun dailyReport(): DailyReport {
        val value = get("/reports/daily")
        val health = value.getJSONObject("health")
        val jobs = value.getJSONArray("recent_jobs").mapItems { item ->
            val job = item as JSONObject
            JobRun(job.getString("job_name"), job.getString("status"), job.getString("finished_at"))
        }
        val regimes = value.getJSONArray("market_regimes").mapItems { item ->
            val regime = item as JSONObject
            MarketRegime(regime.getString("market_code"), regime.getString("trade_date"), regime.getString("regime"))
        }
        return DailyReport(
            generatedAt = value.getString("generated_at"),
            status = health.getString("status"),
            latestPriceDate = health.optString("latest_price_date").takeIf { it.isNotEmpty() },
            priceDataStatus = health.getString("price_data_status"),
            watchlistCount = health.getInt("watchlist_count"),
            marketRegimes = regimes,
            jobs = jobs,
        )
    }
    fun portfolio(): PortfolioSummary {
        val value = get("/portfolio")
        val positions = value.getJSONArray("positions").mapItems { item ->
            val position = item as JSONObject
            Holding(
                code = position.getString("code"),
                companyName = position.optString("company_name").takeIf { it.isNotEmpty() },
                marketValue = position.optDouble("market_value").takeUnless { it.isNaN() },
                profitLoss = position.optDouble("unrealized_profit_loss").takeUnless { it.isNaN() },
                weightPercent = position.optDouble("weight_percent").takeUnless { it.isNaN() },
            )
        }
        return PortfolioSummary(value.getDouble("total_market_value"), positions)
    }
    fun operationsStatus(): OperationsStatus {
        val value = get("/operations/status")
        val pool = value.optJSONObject("pool")
        val evening = value.optJSONObject("evening_update")?.optJSONObject("details")
        val morning = value.optJSONObject("morning_update")?.optJSONObject("details")
        val screening = value.optJSONObject("morning_screening")?.optJSONObject("details")
        fun JSONObject?.optionalInt(name: String): Int? =
            this?.takeIf { it.has(name) && !it.isNull(name) }?.getInt(name)
        fun JSONObject?.optionalText(name: String): String? =
            this?.optString(name)?.takeIf { it.isNotEmpty() }
        return OperationsStatus(
            ready = value.optBoolean("ready"),
            poolDate = pool.optionalText("pool_date"),
            poolStatus = pool.optionalText("status"),
            universeCount = pool.optionalInt("universe_count"),
            evaluatedCount = pool.optionalInt("evaluated_count"),
            eveningUpdatedCount = evening.optionalInt("updated_count"),
            eveningFailedCount = evening.optionalInt("failed_count"),
            candidateCount = pool.optionalInt("candidate_count"),
            morningUpdatedCount = morning.optionalInt("updated_count"),
            morningFailedCount = morning.optionalInt("failed_count"),
            screeningDate = screening.optionalText("screening_date"),
            hitCount = screening.optionalInt("hit_count"),
            effectiveProfile = screening.optionalText("effective_profile"),
            relaxationLabel = screening.optionalText("relaxation_label"),
        )
    }
    fun latestCandidates(): CandidatePool {
        val value = get("/candidates/latest")
        return CandidatePool(
            poolDate = value.optString("pool_date").takeIf { it.isNotEmpty() },
            codes = value.getJSONArray("candidates").mapItems { it.toString() },
        )
    }
    fun watchlist(): List<WatchlistItem> = get("/watchlist").getJSONArray("watchlist").mapItems { item ->
        val value = item as JSONObject
        WatchlistItem(
            code = value.getString("code"),
            note = value.optString("note").takeIf { it.isNotEmpty() },
            companyName = value.optString("company_name").takeIf { it.isNotEmpty() },
        )
    }
    fun screening(profile: String): List<ScreeningHit> = get("/screening/$profile").getJSONArray("hits").mapItems { item ->
        val value = item as JSONObject
        ScreeningHit(
            code = value.getString("code"),
            score = value.optDouble("expectation_score").takeUnless { it.isNaN() },
            reason = value.optString("reason"),
        )
    }
    fun screeningOptions(): ScreeningOptions {
        val value = get("/screening-options")
        val genres = value.getJSONArray("genres").mapItems { item ->
            val genre = item as JSONObject
            ScreeningGenre(
                genre.getString("id"), genre.getString("label"), genre.getString("description"),
                genre.getString("profile"), genre.optString("evidence_status", "baseline"),
            )
        }
        val fields = value.getJSONArray("manual_fields").mapItems { item ->
            val field = item as JSONObject
            ManualField(
                field.getString("field"), field.getString("label"), field.getDouble("min"), field.getDouble("max"),
                field.getString("default_operator"), field.optString("category", "technical"),
            )
        }
        return ScreeningOptions(genres, fields)
    }
    fun manualPreview(conditions: List<ManualCondition>): List<ScreeningHit> {
        val items = JSONArray()
        conditions.forEach { condition ->
            items.put(JSONObject().put("field", condition.field).put("operator", condition.operator).put("value", condition.value))
        }
        val value = post("/screening-preview", JSONObject().put("logic", "all").put("conditions", items))
        return value.getJSONArray("hits").mapItems { item ->
            val hit = item as JSONObject
            ScreeningHit(
                code = hit.getString("code"),
                score = hit.optDouble("expectation_score").takeUnless { it.isNaN() },
                reason = hit.optString("reason"),
            )
        }
    }
    private fun <T> JSONArray.mapItems(transform: (Any) -> T): List<T> = (0 until length()).map { transform(get(it)) }

    private fun JSONObject.optionalDouble(name: String): Double? =
        takeIf { has(name) && !isNull(name) }?.getDouble(name)

    private fun JSONObject.optionalInt(name: String): Int? =
        takeIf { has(name) && !isNull(name) }?.getInt(name)
}
