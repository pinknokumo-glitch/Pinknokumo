package jp.stockai.navigator

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class SupabaseSession(val accessToken: String, val userId: String, val email: String)

data class CloudScreeningResult(
    val screeningDate: String,
    val profile: String,
    val position: Int,
    val code: String,
    val companyName: String?,
    val expectationScore: Double?,
    val comment: String?,
    val chartUrl: String?,
)

data class CloudPreference(
    val mode: String,
    val genreId: String?,
    val manualLogic: String = "all",
    val manualConditions: List<ManualCondition> = emptyList(),
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
        val user = response.getJSONObject("user")
        return SupabaseSession(response.getString("access_token"), user.getString("id"), user.optString("email", email.trim()))
    }

    fun loadPreference(session: SupabaseSession): CloudPreference? {
        val response = requestArray(
            "GET",
            "/rest/v1/screening_preferences?user_id=eq.${session.userId}&select=mode,genre_id,manual_logic,manual_conditions&limit=1",
            token = session.accessToken,
        )
        if (response.length() == 0) return null
        val row = response.getJSONObject(0)
        val conditions = row.optJSONArray("manual_conditions") ?: JSONArray()
        return CloudPreference(
            mode = row.getString("mode"),
            genreId = row.optString("genre_id").takeIf { it.isNotBlank() },
            manualLogic = row.optString("manual_logic", "all"),
            manualConditions = (0 until conditions.length()).map { index ->
                val item = conditions.getJSONObject(index)
                ManualCondition(item.getString("field"), item.getString("operator"), item.getDouble("value"))
            },
        )
    }

    fun savePreference(session: SupabaseSession, preference: CloudPreference) {
        require(preference.mode in setOf("auto", "manual")) { "保存モードが不正です" }
        require(preference.mode != "auto" || !preference.genreId.isNullOrBlank()) { "ジャンルを選択してください" }
        require(preference.manualConditions.size <= 8) { "手動条件は8件までです" }
        val conditions = JSONArray().apply {
            preference.manualConditions.forEach { item ->
                put(JSONObject().put("field", item.field).put("operator", item.operator).put("value", item.value))
            }
        }
        val payload = JSONObject()
            .put("user_id", session.userId)
            .put("mode", preference.mode)
            .put("genre_id", preference.genreId ?: JSONObject.NULL)
            .put("manual_logic", preference.manualLogic)
            .put("manual_conditions", conditions)
        requestArray(
            "POST", "/rest/v1/screening_preferences?on_conflict=user_id", payload, session.accessToken,
            mapOf("Prefer" to "resolution=merge-duplicates,return=representation"),
        )
    }

    fun loadLatestResults(session: SupabaseSession): List<CloudScreeningResult> {
        val response = requestArray(
            "GET",
            "/rest/v1/screening_results?user_id=eq.${session.userId}" +
                "&select=screening_date,profile_name,position,code,company_name,expectation_score,comment,chart_url" +
                "&order=screening_date.desc,position.asc&limit=10",
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
                )
            }
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
                val message = runCatching { JSONObject(body).optString("msg").ifBlank { JSONObject(body).optString("message") } }
                    .getOrNull().orEmpty().ifBlank { "HTTP $code" }
                error("Supabase: $message")
            }
            body.ifBlank { if (method == "GET" || path.startsWith("/rest/")) "[]" else "{}" }
        } finally {
            connection.disconnect()
        }
    }
}
