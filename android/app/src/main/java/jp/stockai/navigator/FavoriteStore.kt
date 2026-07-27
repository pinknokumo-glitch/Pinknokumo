package jp.stockai.navigator

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class FavoriteStock(
    val code: String,
    val companyName: String?,
)

class FavoriteStore(context: Context, userId: String) {
    private val preferences = context.getSharedPreferences(
        "stockai_favorites_${userId.replace("-", "")}",
        Context.MODE_PRIVATE,
    )

    fun load(): List<FavoriteStock> {
        val source = preferences.getString(KEY_ITEMS, "[]") ?: "[]"
        return runCatching {
            val values = JSONArray(source)
            (0 until values.length()).map { index ->
                val item = values.getJSONObject(index)
                FavoriteStock(
                    code = item.getString("code"),
                    companyName = if (item.isNull("company_name")) {
                        null
                    } else {
                        item.optString("company_name").takeIf { it.isNotBlank() }
                    },
                )
            }.distinctBy { it.code }
        }.getOrDefault(emptyList())
    }

    fun save(items: List<FavoriteStock>) {
        val payload = JSONArray().apply {
            items.distinctBy { it.code }.forEach { item ->
                put(
                    JSONObject()
                        .put("code", item.code)
                        .put("company_name", item.companyName ?: JSONObject.NULL)
                )
            }
        }
        preferences.edit().putString(KEY_ITEMS, payload.toString()).apply()
    }

    companion object {
        private const val KEY_ITEMS = "items"
    }
}
