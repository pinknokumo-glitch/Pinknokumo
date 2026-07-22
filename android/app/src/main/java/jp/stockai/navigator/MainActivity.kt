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
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
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
    val profiles = listOf("momentum", "oversold", "rsi_rebound", "deep_value", "growth")
    var profile by remember { mutableStateOf("momentum") }
    var hits by remember { mutableStateOf<List<ScreeningHit>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(profile, refreshToken) {
        error = null
        runCatching { withContext(Dispatchers.IO) { ApiClient().screening(profile) } }
            .onSuccess { hits = it }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("スクリーニング") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = { TextButton(onClick = { refreshToken++ }) { Text("更新") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    profiles.take(3).forEach { name ->
                        FilterChip(selected = profile == name, onClick = { profile = name }, label = { Text(name) })
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    profiles.drop(3).forEach { name ->
                        FilterChip(selected = profile == name, onClick = { profile = name }, label = { Text(name) })
                    }
                }
            }
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
}

@Composable
private fun OperationsScreen(onBack: () -> Unit, onWatchlist: () -> Unit) {
    var report by remember { mutableStateOf<DailyReport?>(null) }
    var portfolio by remember { mutableStateOf<PortfolioSummary?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        runCatching {
            withContext(Dispatchers.IO) {
                val api = ApiClient()
                api.dailyReport() to api.portfolio()
            }
        }.onSuccess { (daily, holdings) ->
            report = daily
            portfolio = holdings
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
            items(history) { item -> ListItem(headlineContent = { Text(item.profile) }, supportingContent = { Text("${item.date} / ${item.type}") }) }
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
