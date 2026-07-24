@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package jp.stockai.navigator

import android.content.Intent
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
    private var callbackSession by mutableStateOf<SupabaseSession?>(null)
    private lateinit var sessionStore: SessionStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sessionStore = SessionStore(applicationContext)
        callbackSession = runCatching { SupabaseClient().sessionFromCallback(intent?.data) }.getOrNull()
        callbackSession?.let(sessionStore::save)
        setContent {
            var activeSession by remember { mutableStateOf<SupabaseSession?>(null) }
            MaterialTheme {
                val session = activeSession
                if (session == null) {
                    StartupLoginScreen(
                        storedSession = callbackSession ?: sessionStore.load(),
                        onAuthenticated = {
                            sessionStore.save(it)
                            activeSession = it
                        },
                    )
                } else {
                    StockAiApp(
                        session = session,
                        onLogout = {
                            sessionStore.clear()
                            activeSession = null
                        },
                    )
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        callbackSession = runCatching { SupabaseClient().sessionFromCallback(intent.data) }.getOrNull()
        callbackSession?.let(sessionStore::save)
    }
}

@Composable
private fun StartupLoginScreen(
    storedSession: SupabaseSession?,
    onAuthenticated: (SupabaseSession) -> Unit,
) {
    val cloud = remember { SupabaseClient() }
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var authMode by remember { mutableStateOf("login") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(topBar = { TopAppBar(title = { Text("StockAI Navigator") }) }) { padding ->
        Column(
            Modifier.padding(padding).padding(24.dp).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("ログイン", style = MaterialTheme.typography.headlineSmall)
            Text("クラウド設定と配信結果を安全に同期します。")
            storedSession?.let { saved ->
                Button(
                    enabled = !busy,
                    onClick = {
                        busy = true
                        error = null
                        scope.launch {
                            runCatching {
                                withContext(Dispatchers.IO) {
                                    if (saved.needsRefresh()) cloud.refreshSession(saved) else saved
                                }
                            }.onSuccess(onAuthenticated)
                                .onFailure {
                                    error = "保存済みログインの有効期限が切れました。再ログインしてください。"
                                }
                            busy = false
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("${saved.email} でログイン") }
                HorizontalDivider()
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                FilterChip(
                    selected = authMode == "login",
                    onClick = { authMode = "login"; error = null },
                    label = { Text("ログイン") },
                )
                FilterChip(
                    selected = authMode == "register",
                    onClick = { authMode = "register"; error = null },
                    label = { Text("新規登録") },
                )
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            OutlinedTextField(
                value = email, onValueChange = { email = it },
                label = { Text("メール") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = password, onValueChange = { password = it },
                label = { Text("パスワード") }, visualTransformation = PasswordVisualTransformation(),
                singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
            if (authMode == "register") {
                OutlinedTextField(
                    value = confirmPassword, onValueChange = { confirmPassword = it },
                    label = { Text("パスワード（確認）") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
            }
            Button(
                enabled = !busy && email.isNotBlank() && password.isNotBlank(),
                onClick = {
                    busy = true
                    error = null
                    scope.launch {
                        runCatching {
                            withContext(Dispatchers.IO) {
                                if (authMode == "register") {
                                    require(password == confirmPassword) { "確認用パスワードが一致しません" }
                                    cloud.signUp(email, password).session
                                        ?: throw IllegalStateException(
                                            "登録メールを送信しました。メール確認後に起動してください。"
                                        )
                                } else {
                                    cloud.signIn(email, password)
                                }
                            }
                        }.onSuccess(onAuthenticated)
                            .onFailure { error = it.message ?: "ログインできませんでした" }
                        password = ""
                        confirmPassword = ""
                        busy = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (busy) "処理中" else if (authMode == "register") "登録" else "ログイン") }
        }
    }
}

@Composable
private fun StockAiApp(session: SupabaseSession, onLogout: () -> Unit) {
    var selectedCode by remember { mutableStateOf<String?>(null) }
    var showOperations by remember { mutableStateOf(false) }
    var showWatchlist by remember { mutableStateOf(false) }
    var showScreening by remember { mutableStateOf(false) }
    MaterialTheme {
        if (showScreening) ScreeningScreen(
            initialSession = session,
            onBack = { showScreening = false },
            onSelect = { selectedCode = it; showScreening = false },
        )
        else if (showWatchlist) WatchlistScreen(
            onBack = { showWatchlist = false },
            onSelect = { selectedCode = it; showWatchlist = false; showOperations = false },
        )
        else if (showOperations) OperationsScreen(onBack = { showOperations = false }, onWatchlist = { showWatchlist = true })
        else if (selectedCode == null) RankingScreen(
            onSelect = { selectedCode = it }, onOperations = { showOperations = true },
            onScreening = { showScreening = true }, onLogout = onLogout,
        )
        else StockDetailScreen(code = selectedCode!!, onBack = { selectedCode = null })
    }
}

@Composable
private fun RankingScreen(
    onSelect: (String) -> Unit,
    onOperations: () -> Unit,
    onScreening: () -> Unit,
    onLogout: () -> Unit,
) {
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
            TextButton(onClick = onLogout) { Text("ログアウト") }
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
private fun ScreeningScreen(initialSession: SupabaseSession?, onBack: () -> Unit, onSelect: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val cloud = remember { SupabaseClient() }
    var options by remember { mutableStateOf<ScreeningOptions?>(null) }
    var mode by remember { mutableStateOf("auto") }
    var genreId by remember { mutableStateOf<String?>(null) }
    var holdingDays by remember { mutableStateOf("60") }
    val manualValues = remember { mutableStateMapOf<String, String>() }
    var hits by remember { mutableStateOf<List<ScreeningHit>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var localApiAvailable by remember { mutableStateOf(true) }
    var refreshToken by remember { mutableIntStateOf(0) }
    var cloudSession by remember { mutableStateOf(initialSession) }
    var cloudResults by remember { mutableStateOf<List<CloudScreeningResult>>(emptyList()) }
    var cloudStatus by remember { mutableStateOf<String?>(null) }
    var showLogin by remember { mutableStateOf(false) }
    var loginPurpose by remember { mutableStateOf("save") }
    var authMode by remember { mutableStateOf("login") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var loginError by remember { mutableStateOf<String?>(null) }
    var cloudBusy by remember { mutableStateOf(false) }

    LaunchedEffect(initialSession) {
        if (initialSession != null) {
            cloudSession = initialSession
            cloudStatus = "メール確認が完了しました。クラウド設定を保存できます。"
        }
    }

    fun currentPreference(): CloudPreference {
        val loaded = options
        val resolvedHoldingDays = holdingDays.toIntOrNull()
            ?: throw IllegalArgumentException("保有営業日数を入力してください")
        require(resolvedHoldingDays in 1..250) { "保有営業日数は1～250日で入力してください" }
        val conditions = loaded?.manualFields?.mapNotNull { field ->
            manualValues[field.field]?.toDoubleOrNull()?.let { value ->
                ManualCondition(field.field, field.defaultOperator, value)
            }
        }.orEmpty()
        return CloudPreference(
            mode, genreId, "all",
            if (mode == "manual") conditions else emptyList(),
            resolvedHoldingDays,
        )
    }

    fun saveToCloud(session: SupabaseSession) {
        cloudBusy = true
        cloudStatus = null
        val preference = runCatching { currentPreference() }.getOrElse {
            cloudStatus = it.message
            cloudBusy = false
            return
        }
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { cloud.savePreference(session, preference) } }
                .onSuccess { cloudStatus = "クラウドへ保存しました" }
                .onFailure { cloudStatus = "クラウドエラー: ${it.message ?: "保存できませんでした"}" }
            cloudBusy = false
        }
    }

    fun loadCloudResults(session: SupabaseSession) {
        cloudBusy = true
        cloudStatus = null
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { cloud.loadLatestResults(session) } }
                .onSuccess { results ->
                    cloudResults = results
                    cloudStatus = if (results.isEmpty()) {
                        "クラウド結果はまだありません"
                    } else {
                        "${results.first().screeningDate} の結果を読み込みました"
                    }
                }
                .onFailure { cloudStatus = "クラウドエラー: ${it.message ?: "読み込めませんでした"}" }
            cloudBusy = false
        }
    }
    LaunchedEffect(Unit) {
        runCatching { withContext(Dispatchers.IO) { ApiClient().screeningOptions() } }
            .onSuccess { loaded -> options = loaded; genreId = loaded.genres.firstOrNull()?.id }
            .onFailure {
                val loaded = builtInScreeningOptions()
                localApiAvailable = false
                options = loaded
                genreId = loaded.genres.firstOrNull()?.id
                error = "スマホ単体モードです。条件の保存は利用できますが、プレビューは配信後に確認してください。"
            }
    }
    LaunchedEffect(initialSession, options) {
        val session = initialSession ?: return@LaunchedEffect
        if (options == null) return@LaunchedEffect
        runCatching { withContext(Dispatchers.IO) { cloud.loadPreference(session) } }
            .onSuccess { saved ->
                if (saved != null) {
                    mode = saved.mode
                    genreId = saved.genreId
                    holdingDays = saved.holdingDays.toString()
                    manualValues.clear()
                    saved.manualConditions.forEach {
                        manualValues[it.field] = it.value.toString()
                    }
                }
            }
    }
    LaunchedEffect(mode, genreId, refreshToken, options) {
        val loaded = options ?: return@LaunchedEffect
        if (mode == "auto" && genreId == null) return@LaunchedEffect
        if (!localApiAvailable) return@LaunchedEffect
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
                            cloudSession == null -> {
                                loginPurpose = "results"
                                loginError = null
                                showLogin = true
                            }
                            else -> loadCloudResults(cloudSession!!)
                        }
                    },
                ) { Text(if (cloudBusy) "読込中" else "最新結果") }
                TextButton(
                    enabled = !cloudBusy,
                    onClick = {
                        when {
                            !cloud.isConfigured -> cloudStatus = "Supabaseの公開設定が未登録です"
                            cloudSession == null -> {
                                loginPurpose = "save"
                                loginError = null
                                showLogin = true
                            }
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
                OutlinedTextField(
                    value = holdingDays,
                    onValueChange = { holdingDays = it.filter(Char::isDigit).take(3) },
                    label = { Text("期待値の保有営業日数") },
                    supportingText = {
                        Text("選定条件が過去に成立した翌営業日から、この日数後までの成績で算出します（1～250日）。")
                    },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
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
            cloudStatus?.let {
                item {
                    Text(
                        it,
                        color = if (it.startsWith("クラウドエラー") || it.contains("未登録")) {
                            MaterialTheme.colorScheme.error
                        } else {
                            Color(0xFF2E7D32)
                        },
                    )
                }
            }
            if (cloudResults.isNotEmpty()) {
                item {
                    Spacer(Modifier.height(16.dp))
                    Text(
                        "クラウド最新結果（${cloudResults.first().screeningDate}）",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "配信済みの候補 ${cloudResults.size}件",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                items(cloudResults) { result ->
                    val company = result.companyName?.let { " / $it" } ?: ""
                    val score = result.expectationScore?.let { String.format("%.1f", it) } ?: "未算出"
                    ListItem(
                        headlineContent = { Text("${result.position}. ${result.code}$company") },
                        supportingContent = {
                            Column {
                                Text("${result.profile} / 期待値 $score")
                                result.holdingDays?.let {
                                    Text("期待値期間: $it 営業日 / 保存した全条件で検証")
                                }
                                result.comment?.let { Text(it) }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().clickable { onSelect(result.code) },
                    )
                    HorizontalDivider()
                }
                item {
                    Spacer(Modifier.height(16.dp))
                    Text("条件プレビュー", style = MaterialTheme.typography.titleMedium)
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
    if (showLogin) {
        AlertDialog(
            onDismissRequest = { if (!cloudBusy) showLogin = false },
            title = { Text(if (authMode == "register") "アカウントを作成" else "Supabaseへログイン") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        FilterChip(
                            selected = authMode == "login",
                            onClick = {
                                authMode = "login"
                                loginError = null
                                confirmPassword = ""
                            },
                            label = { Text("ログイン") },
                        )
                        FilterChip(
                            selected = authMode == "register",
                            onClick = {
                                authMode = "register"
                                loginError = null
                            },
                            label = { Text("新規登録") },
                        )
                    }
                    Text(
                        if (authMode == "register") {
                            "メールとパスワードでアプリ用アカウントを作成します。認証情報は端末に保存しません。"
                        } else if (loginPurpose == "results") {
                            "認証情報は端末に保存しません。ログイン後、最新の配信結果を読み込みます。"
                        } else {
                            "認証情報は端末に保存しません。ログイン後、現在の条件を保存します。"
                        }
                    )
                    loginError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error)
                    }
                    OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("メール") }, singleLine = true)
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("パスワード") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                    )
                    if (authMode == "register") {
                        OutlinedTextField(
                            value = confirmPassword,
                            onValueChange = { confirmPassword = it },
                            label = { Text("パスワード（確認）") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                        )
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !cloudBusy,
                    onClick = loginClick@{
                        cloudBusy = true
                        cloudStatus = null
                        loginError = null
                        val preference = runCatching { currentPreference() }.getOrElse {
                            loginError = it.message
                            cloudBusy = false
                            return@loginClick
                        }
                        val requestedAuthMode = authMode
                        scope.launch {
                            runCatching {
                                withContext(Dispatchers.IO) {
                                    if (requestedAuthMode == "register" && password != confirmPassword) {
                                        throw IllegalArgumentException("確認用パスワードが一致しません")
                                    }
                                    val session = if (requestedAuthMode == "register") {
                                        val registration = cloud.signUp(email, password)
                                        registration.session ?: throw IllegalStateException(
                                            "登録メールを送信しました。メール確認後にログインしてください。"
                                        )
                                    } else {
                                        cloud.signIn(email, password)
                                    }
                                    val results = if (loginPurpose == "results") {
                                        cloud.loadLatestResults(session)
                                    } else {
                                        cloud.savePreference(session, preference)
                                        emptyList()
                                    }
                                    session to results
                                }
                            }.onSuccess { (session, results) ->
                                cloudSession = session
                                password = ""
                                confirmPassword = ""
                                showLogin = false
                                if (loginPurpose == "results") {
                                    cloudResults = results
                                    cloudStatus = if (results.isEmpty()) {
                                        "クラウド結果はまだありません"
                                    } else {
                                        "${results.first().screeningDate} の結果を読み込みました"
                                    }
                                } else {
                                    cloudStatus = "クラウドへ保存しました"
                                }
                            }.onFailure {
                                password = ""
                                confirmPassword = ""
                                loginError = it.message ?: "ログインできませんでした"
                            }
                            cloudBusy = false
                        }
                    },
                ) {
                    Text(
                        if (authMode == "register") {
                            if (loginPurpose == "results") "登録して表示" else "登録して保存"
                        } else {
                            if (loginPurpose == "results") "ログインして表示" else "ログインして保存"
                        }
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    showLogin = false
                    password = ""
                    confirmPassword = ""
                    loginError = null
                }) { Text("キャンセル") }
            },
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
