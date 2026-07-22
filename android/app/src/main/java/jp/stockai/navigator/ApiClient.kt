package jp.stockai.navigator

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Ranking(val code: String, val score: Double?, val grade: String?)
data class Price(val date: String, val close: Double)
data class HistoryItem(val date: String, val profile: String, val type: String)
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
data class ManualField(val field: String, val label: String, val min: Double, val max: Double, val defaultOperator: String)
data class ScreeningOptions(val genres: List<ScreeningGenre>, val manualFields: List<ManualField>)
data class ManualCondition(val field: String, val operator: String, val value: Double)
data class StockOverview(
    val companyName: String?, val sector: String?, val close: Double?, val priceDate: String?,
    val per: Double?, val pbr: Double?, val roe: Double?, val dividendYield: Double?,
    val relativePerformance: List<RelativePerformance>,
)
data class RelativePerformance(val sessions: Int, val excessReturnPercent: Double)

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
        HistoryItem(value.getString("as_of_date"), value.getString("profile_name"), value.getString("analysis_type"))
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
                field.getString("default_operator"),
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
}
