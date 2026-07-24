@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package jp.stockai.navigator

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { StockAiApp() }
    }
}

@Composable
private fun StockAiApp() {
    var selectedCode by remember { mutableStateOf<String?>(null) }
    var showOperations by remember { mutableStateOf(false) }
    var showWatchlist by remember { mutableStateOf(false) }
    var showScreening by remember { mutableStateOf(false) }
    MaterialTheme {
        if (showScreening) ScreeningScreen(
            onBack = { showScreening = false },
            onSelect = { selectedCode = it; showScreening = false },
        )
        else if (showWatchlist) WatchlistScreen(
            onBack = { showWatchlist = false },
            onSelect = { selectedCode = it; showWatchlist = false; showOperations = false },
        )
        else if (showOperations) OperationsScreen(onBack = { showOperations = false }, onWatchlist = { showWatchlist = true })
        else if (selectedCode == null) RankingScreen(
            onSelect = { selectedCode = it }, onOperations = { showOperations = true }, onScreening = { showScreening = true },
        )
        else StockDetailScreen(code = selectedCode!!, onBack = { selectedCode = null })
    }
}

@Composable
private fun RankingScreen(onSelect: (String) -> Unit, onOperations: () -> Unit, onScreening: () -> Unit) {
    var rankings by remember { mutableStateOf<List<Ranking>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        runCatching { withContext(Dispatchers.IO) { ApiClient().rankings() } }
            .onSuccess { rankings = it }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text("StockAI Navigator") }, actions = {
            TextButton(onClick = { refreshToken++ }) { Text("更新") }
            TextButton(onClick = onScreening) { Text("条件") }
            TextButton(onClick = onOperations) { Text("運用") }
        })
    }) { padding ->
        Column(Modifier.padding(padding).padding(16.dp)) {
            Text("期待値ランキング", style = MaterialTheme.typography.titleLarge)
            error?.let { Text("APIへ接続できません: ${it}", color = MaterialTheme.colorScheme.error) }
            LazyColumn {
                items(rankings) { item ->
                    ListItem(
                        headlineContent = { Text(item.code) },
                        supportingContent = { Text("スコア ${item.score ?: "-"} / グレード ${item.grade ?: "-"}") },
                        modifier = Modifier.fillMaxWidth().clickable { onSelect(item.code) }
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun ScreeningScreen(onBack: () -> Unit, onSelect: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val cloud = remember { SupabaseClient() }
    var options by remember { mutableStateOf<ScreeningOptions?>(null) }
    var mode by remember { mutableStateOf("auto") }
    var genreId by remember { mutableStateOf<String?>(null) }
    val manualValues = remember { mutableStateMapOf<String, String>() }
    var hits by remember { mutableStateOf<List<ScreeningHit>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    var cloudSession by remember { mutableStateOf<SupabaseSession?>(null) }
    var cloudStatus by remember { mutableStateOf<String?>(null) }
    var showLogin by remember { mutableStateOf(false) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var cloudBusy by remember { mutableStateOf(false) }

    fun currentPreference(): CloudPreference {
        val loaded = options
        val conditions = loaded?.manualFields?.mapNotNull { field ->
            manualValues[field.field]?.toDoubleOrNull()?.let { value ->
                ManualCondition(field.field, field.defaultOperator, value)
            }
        }.orEmpty()
        return CloudPreference(mode, genreId, "all", if (mode == "manual") conditions else emptyList())
    }

    fun saveToCloud(session: SupabaseSession) {
        cloudBusy = true
        cloudStatus = null
        val preference = currentPreference()
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { cloud.savePreference(session, preference) } }
                .onSuccess { cloudStatus = "クラウドへ保存しました" }
                .onFailure { cloudStatus = it.message }
            cloudBusy = false
        }
    }
    LaunchedEffect(Unit) {
        runCatching { withContext(Dispatchers.IO) { ApiClient().screeningOptions() } }
            .onSuccess { loaded -> options = loaded; genreId = loaded.genres.firstOrNull()?.id }
            .onFailure { error = it.message }
    }
    LaunchedEffect(mode, genreId, refreshToken, options) {
        val loaded = options ?: return@LaunchedEffect
        if (mode == "auto" && genreId == null) return@LaunchedEffect
        error = null
        runCatching {
            withContext(Dispatchers.IO) {
                if (mode == "auto") {
                    val genre = loaded.genres.first { it.id == genreId }
                    ApiClient().screening(genre.profile)
                } else {
                    val conditions = loaded.manualFields.mapNotNull { field ->
                        manualValues[field.field]?.toDoubleOrNull()?.let { value ->
                            ManualCondition(field.field, field.defaultOperator, value)
                        }
                    }
                    if (conditions.isEmpty()) emptyList() else ApiClient().manualPreview(conditions)
                }
            }
        }
            .onSuccess { hits = it }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("スクリーニング") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = {
                TextButton(
                    enabled = !cloudBusy,
                    onClick = {
                        when {
                            !cloud.isConfigured -> cloudStatus = "Supabaseの公開設定が未登録です"
                            cloudSession == null -> showLogin = true
                            else -> saveToCloud(cloudSession!!)
                        }
                    },
                ) { Text(if (cloudBusy) "保存中" else "クラウド保存") }
                TextButton(onClick = { refreshToken++ }) { Text("更新") }
            },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            item {
                Text("選び方", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    FilterChip(selected = mode == "auto", onClick = { mode = "auto" }, label = { Text("オート") })
                    FilterChip(selected = mode == "manual", onClick = { mode = "manual" }, label = { Text("マニュアル") })
                }
                Spacer(Modifier.height(12.dp))
            }
            if (mode == "auto") {
                options?.genres?.forEach { genre ->
                    item {
                        FilterChip(
                            selected = genreId == genre.id,
                            onClick = { genreId = genre.id },
                            label = { Text(genre.label) },
                        )
                        Text(genre.description, style = MaterialTheme.typography.bodySmall)
                        if (genre.evidenceStatus == "needs_validation") {
                            Text("検証中", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            } else {
                item { Text("値を入力した項目だけをAND条件で使用します。", style = MaterialTheme.typography.bodySmall) }
                options?.manualFields?.forEach { field ->
                    item {
                        OutlinedTextField(
                            value = manualValues[field.field] ?: "",
                            onValueChange = { manualValues[field.field] = it },
                            label = { Text("${field.label} ${field.defaultOperator}") },
                            supportingText = { Text("範囲 ${field.min}〜${field.max}") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                        )
                    }
                }
                item { Button(onClick = { refreshToken++ }) { Text("条件をプレビュー") } }
            }
            cloudStatus?.let { item { Text(it, color = if (it.contains("保存しました")) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error) } }
            error?.let { item { Text("APIへ接続できません: $it", color = MaterialTheme.colorScheme.error) } }
            if (hits.isEmpty() && error == null) item { Text("一致する銘柄はありません") }
            items(hits) { hit ->
                ListItem(
                    headlineContent = { Text(hit.code) },
                    supportingContent = { Text("スコア ${hit.score ?: "-"} / ${hit.reason}") },
                    modifier = Modifier.fillMaxWidth().clickable { onSelect(hit.code) },
                )
                HorizontalDivider()
            }
        }
    }
    if (showLogin) {
        AlertDialog(
            onDismissRequest = { if (!cloudBusy) showLogin = false },
            title = { Text("Supabaseへログイン") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("認証情報は端末に保存しません。ログイン後、現在の条件を保存します。")
                    OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("メール") }, singleLine = true)
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("パスワード") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !cloudBusy,
                    onClick = {
                        cloudBusy = true
                        cloudStatus = null
                        val preference = currentPreference()
                        scope.launch {
                            runCatching {
                                withContext(Dispatchers.IO) {
                                    val session = cloud.signIn(email, password)
                                    cloud.savePreference(session, preference)
                                    session
                                }
                            }.onSuccess { session ->
                                cloudSession = session
                                password = ""
                                showLogin = false
                                cloudStatus = "クラウドへ保存しました"
                            }.onFailure {
                                password = ""
                                cloudStatus = it.message
                            }
                            cloudBusy = false
                        }
                    },
                ) { Text("ログインして保存") }
            },
            dismissButton = { TextButton(onClick = { showLogin = false; password = "" }) { Text("キャンセル") } },
        )
    }
}

@Composable
private fun OperationsScreen(onBack: () -> Unit, onWatchlist: () -> Unit) {
    var report by remember { mutableStateOf<DailyReport?>(null) }
    var portfolio by remember { mutableStateOf<PortfolioSummary?>(null) }
    var operations by remember { mutableStateOf<OperationsStatus?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        runCatching {
            withContext(Dispatchers.IO) {
                val api = ApiClient()
                Triple(api.dailyReport(), api.portfolio(), api.operationsStatus())
            }
        }.onSuccess { (daily, holdings, status) ->
            report = daily
            portfolio = holdings
            operations = status
        }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("日次運用") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = {
                TextButton(onClick = { refreshToken++ }) { Text("更新") }
                TextButton(onClick = onWatchlist) { Text("監視") }
            },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            error?.let { item { Text("APIへ接続できません: $it", color = MaterialTheme.colorScheme.error) } }
            operations?.let { status ->
                item {
                    Text("運用状況", style = MaterialTheme.typography.titleLarge)
                    Text(if (status.ready) "翌朝の判定準備：完了" else "翌朝の判定準備：未完了")
                    Text("全銘柄更新日：${status.poolDate ?: "未取得"}")
                    Text(
                        "対象 ${status.universeCount ?: 0} / 判定済み ${status.evaluatedCount ?: 0} / " +
                            "更新成功 ${status.eveningUpdatedCount ?: 0} / 失敗 ${status.eveningFailedCount ?: 0}"
                    )
                    Text("翌朝候補：${status.candidateCount ?: 0} 銘柄")
                    Text(
                        "朝の価格更新：成功 ${status.morningUpdatedCount ?: 0} / " +
                            "失敗 ${status.morningFailedCount ?: 0}"
                    )
                    Text("最終判定日：${status.screeningDate ?: "未実行"} / 該当 ${status.hitCount ?: 0} 銘柄")
                    Text(
                        "使用条件：${status.effectiveProfile ?: "未実行"} / " +
                            "${status.relaxationLabel ?: "緩和なし"}"
                    )
                    Spacer(Modifier.height(16.dp))
                }
            }
            report?.let { value ->
                item { Text("状態: ${value.status}", style = MaterialTheme.typography.titleLarge) }
                item { Text("集計日時: ${value.generatedAt}") }
                item { Text("価格最終日: ${value.latestPriceDate ?: "未取得"}（${value.priceDataStatus}）") }
                item { Text("ウォッチリスト: ${value.watchlistCount} 銘柄") }
                if (value.marketRegimes.isNotEmpty()) {
                    item { Spacer(Modifier.height(16.dp)); Text("市場局面", style = MaterialTheme.typography.titleMedium) }
                    items(value.marketRegimes) { regime ->
                        ListItem(headlineContent = { Text(regime.marketCode) }, supportingContent = { Text("${regime.regime} / ${regime.date}") })
                        HorizontalDivider()
                    }
                }
                portfolio?.let { holdings ->
                    item { Spacer(Modifier.height(16.dp)); Text("ポートフォリオ", style = MaterialTheme.typography.titleMedium) }
                    item { Text("評価額: ${holdings.totalMarketValue.toLong()}") }
                    if (holdings.positions.isEmpty()) item { Text("保有銘柄はありません") }
                    items(holdings.positions) { holding ->
                        val name = holding.companyName?.let { " / $it" } ?: ""
                        val valueText = holding.marketValue?.toLong()?.toString() ?: "価格未取得"
                        val pnlText = holding.profitLoss?.toLong()?.toString() ?: "-"
                        val weightText = holding.weightPercent?.let { "${it}%" } ?: "-"
                        ListItem(
                            headlineContent = { Text("${holding.code}$name") },
                            supportingContent = { Text("評価額 $valueText / 損益 $pnlText / 構成比 $weightText") },
                        )
                        HorizontalDivider()
                    }
                }
                item { Spacer(Modifier.height(16.dp)); Text("直近の更新ジョブ", style = MaterialTheme.typography.titleMedium) }
                if (value.jobs.isEmpty()) item { Text("実行履歴はありません") }
                items(value.jobs) { job ->
                    ListItem(headlineContent = { Text(job.name) }, supportingContent = { Text("${job.status} / ${job.finishedAt}") })
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun WatchlistScreen(onBack: () -> Unit, onSelect: (String) -> Unit) {
    var watchlist by remember { mutableStateOf<List<WatchlistItem>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        runCatching { withContext(Dispatchers.IO) { ApiClient().watchlist() } }
            .onSuccess { watchlist = it }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("ウォッチリスト") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = { TextButton(onClick = { refreshToken++ }) { Text("更新") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            error?.let { item { Text("APIへ接続できません: $it", color = MaterialTheme.colorScheme.error) } }
            if (watchlist.isEmpty() && error == null) item { Text("監視銘柄はありません") }
            items(watchlist) { item ->
                val company = item.companyName?.let { " / $it" } ?: ""
                val note = item.note ?: ""
                ListItem(
                    headlineContent = { Text("${item.code}$company") },
                    supportingContent = { Text(note) },
                    modifier = Modifier.fillMaxWidth().clickable { onSelect(item.code) },
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun StockDetailScreen(code: String, onBack: () -> Unit) {
    var prices by remember { mutableStateOf<List<Price>>(emptyList()) }
    var history by remember { mutableStateOf<List<HistoryItem>>(emptyList()) }
    var overview by remember { mutableStateOf<StockOverview?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(code, refreshToken) {
        error = null
        runCatching {
            withContext(Dispatchers.IO) {
                val api = ApiClient()
                Triple(api.prices(code), api.history(code), api.overview(code))
            }
        }.onSuccess { (p, h, o) -> prices = p; history = h; overview = o }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(code) },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = { TextButton(onClick = { refreshToken++ }) { Text("更新") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            overview?.let { value ->
                item { Text(value.companyName ?: code, style = MaterialTheme.typography.titleLarge) }
                value.sector?.let { item { Text(it) } }
                item { Text("終値: ${value.close?.toString() ?: "未取得"}（${value.priceDate ?: "-"}）") }
                item { Text("PER ${value.per ?: "-"} / PBR ${value.pbr ?: "-"} / ROE ${value.roe ?: "-"}% / 実績配当利回り ${value.dividendYield ?: "-"}%") }
                if (value.relativePerformance.isNotEmpty()) {
                    item { Text("日経平均比: " + value.relativePerformance.joinToString(" / ") { "${it.sessions}日 ${it.excessReturnPercent}%" }) }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
            item { Text("終値（直近180本）", style = MaterialTheme.typography.titleLarge) }
            item { PriceChart(prices, Modifier.fillMaxWidth().height(220.dp)) }
            error?.let { item { Text("APIへ接続できません: ${it}", color = MaterialTheme.colorScheme.error) } }
            item { Text("分析履歴", style = MaterialTheme.typography.titleLarge) }
            if (history.isEmpty()) item { Text("バックテスト結果はまだありません") }
            items(history) { item ->
                val score = item.expectationScore?.let { String.format("%.1f/100", it) } ?: "未算出"
                val grade = item.grade?.let { "（$it）" } ?: ""
                val statistics = buildList {
                    item.tradeCount?.let { add("取引 ${it}件") }
                    item.winRatePercent?.let { add("勝率 ${String.format("%.1f", it)}%") }
                    item.averageReturnPercent?.let { add("平均 ${String.format("%.2f", it)}%") }
                    item.maxDrawdownPercent?.let { add("最大下落 ${String.format("%.2f", it)}%") }
                }.joinToString(" / ")
                ListItem(
                    headlineContent = { Text("${item.profile}　期待値 $score$grade") },
                    supportingContent = {
                        Column {
                            Text("${item.date} / ${item.type}")
                            if (statistics.isNotEmpty()) Text(statistics)
                            item.comment?.let { Text(it) }
                        }
                    },
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun PriceChart(prices: List<Price>, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        if (prices.size < 2) return@Canvas
        val min = prices.minOf { it.close }
        val max = prices.maxOf { it.close }
        val range = (max - min).takeIf { it > 0 } ?: 1.0
        val points = prices.mapIndexed { index, price ->
            Offset(size.width * index / (prices.size - 1), size.height * (1f - ((price.close - min) / range).toFloat()))
        }
        points.zipWithNext().forEach { (from, to) ->
            drawLine(Color(0xFF1565C0), from, to, strokeWidth = 3f, cap = StrokeCap.Round)
        }
    }
}
