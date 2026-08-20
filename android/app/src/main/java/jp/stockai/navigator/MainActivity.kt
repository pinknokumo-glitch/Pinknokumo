@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package jp.stockai.navigator

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val StockAiDarkColors = darkColorScheme(
    primary = Color(0xFF49E7E0),
    onPrimary = Color(0xFF001F20),
    primaryContainer = Color(0xFF063B3E),
    onPrimaryContainer = Color(0xFF9DFFFA),
    secondary = Color(0xFF80CBC4),
    background = Color.Transparent,
    onBackground = Color(0xFFE5F8F7),
    surface = Color(0xFF071119),
    onSurface = Color(0xFFE5F8F7),
    surfaceVariant = Color(0xFF0C1C25),
    onSurfaceVariant = Color(0xFFA8C7C7),
    outline = Color(0xFF277D80),
    error = Color(0xFFFF6B7A),
)

private val StockAiTypography = Typography(
    headlineSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 24.sp,
        letterSpacing = 1.2.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
        letterSpacing = 1.1.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        letterSpacing = .7.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        letterSpacing = .35.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        letterSpacing = .25.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 12.sp,
        letterSpacing = 1.4.sp,
    ),
)

private class OnboardingStore(context: Context) {
    private val preferences = context.getSharedPreferences(
        "stockai_onboarding",
        Context.MODE_PRIVATE,
    )

    fun isCompleted(userId: String): Boolean =
        preferences.getBoolean("completed_$userId", false)

    fun markCompleted(userId: String) {
        preferences.edit().putBoolean("completed_$userId", true).apply()
    }
}

class MainActivity : ComponentActivity() {
    private var callbackSession by mutableStateOf<SupabaseSession?>(null)
    private var activeSession by mutableStateOf<SupabaseSession?>(null)
    private var launchPage by mutableStateOf("home")
    private lateinit var sessionStore: SessionStore
    private lateinit var onboardingStore: OnboardingStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        launchPage = intent?.getStringExtra(EXTRA_START_PAGE)
            ?.takeIf { it in VALID_START_PAGES } ?: "home"
        sessionStore = SessionStore(applicationContext)
        onboardingStore = OnboardingStore(applicationContext)
        NotificationScheduler.rescheduleSaved(applicationContext)
        callbackSession = runCatching { SupabaseClient().sessionFromCallback(intent?.data) }.getOrNull()
        callbackSession?.let(sessionStore::save)
        setContent {
            MaterialTheme(colorScheme = StockAiDarkColors, typography = StockAiTypography) {
                StockAiBackground {
                    val session = activeSession
                    if (session == null) {
                        var storedSession by remember(callbackSession) {
                            mutableStateOf(callbackSession ?: sessionStore.load())
                        }
                        StartupLoginScreen(
                            storedSession = storedSession,
                            onAuthenticated = {
                                sessionStore.save(it)
                                storedSession = it
                                activeSession = it
                            },
                            onForgetStoredSession = {
                                sessionStore.clear()
                                callbackSession = null
                                storedSession = null
                            },
                        )
                    } else {
                        StockAiApp(
                            session = session,
                            initialPage = launchPage,
                            requiresOnboarding = !onboardingStore.isCompleted(session.userId),
                            onOnboardingCompleted = {
                                onboardingStore.markCompleted(session.userId)
                                launchPage = "home"
                            },
                            onSessionUpdated = {
                                sessionStore.save(it)
                                activeSession = it
                            },
                            onLogout = {
                                sessionStore.clear()
                                activeSession = null
                                launchPage = "home"
                            },
                        )
                    }
                }
            }
        }
    }

    override fun onStop() {
        super.onStop()
        // Keep the encrypted refresh token, but lock the visible app whenever it
        // leaves the foreground. Returning users can unlock with one tap.
        activeSession = null
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        launchPage = intent.getStringExtra(EXTRA_START_PAGE)
            ?.takeIf { it in VALID_START_PAGES } ?: "home"
        callbackSession = runCatching { SupabaseClient().sessionFromCallback(intent.data) }.getOrNull()
        callbackSession?.let(sessionStore::save)
    }

    companion object {
        const val EXTRA_START_PAGE = "stockai_start_page"
        private val VALID_START_PAGES = setOf(
            "home", "results", "candidates", "stock", "settings", "operations", "menu",
        )
    }
}

@Composable
private fun StockAiBackground(content: @Composable () -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(
                    colors = listOf(
                        Color(0xFF0A3540),
                        Color(0xFF06151E),
                        Color(0xFF01050A),
                    ),
                    radius = 1300f,
                )
            )
    ) {
        Canvas(Modifier.matchParentSize()) {
            val cyan = Color(0xFF34D8E1)
            val points = listOf(
                Offset(size.width * .05f, size.height * .18f),
                Offset(size.width * .25f, size.height * .10f),
                Offset(size.width * .46f, size.height * .23f),
                Offset(size.width * .78f, size.height * .12f),
                Offset(size.width * .94f, size.height * .31f),
                Offset(size.width * .15f, size.height * .48f),
                Offset(size.width * .39f, size.height * .42f),
                Offset(size.width * .70f, size.height * .50f),
                Offset(size.width * .90f, size.height * .67f),
                Offset(size.width * .24f, size.height * .76f),
                Offset(size.width * .58f, size.height * .82f),
                Offset(size.width * .82f, size.height * .91f),
            )
            val links = listOf(
                0 to 1, 1 to 2, 2 to 3, 3 to 4,
                0 to 5, 2 to 6, 3 to 7, 4 to 8,
                5 to 6, 6 to 7, 7 to 8,
                5 to 9, 6 to 9, 6 to 10, 7 to 10,
                7 to 11, 8 to 11, 9 to 10, 10 to 11,
            )
            links.forEach { (start, end) ->
                drawLine(cyan.copy(alpha = .13f), points[start], points[end], strokeWidth = 1.5f)
            }
            points.forEachIndexed { index, point ->
                drawCircle(cyan.copy(alpha = .08f), radius = 18f + index % 3 * 6f, center = point)
                drawCircle(cyan.copy(alpha = .48f), radius = 3.5f, center = point)
            }
            repeat(7) { index ->
                val y = size.height * (.18f + index * .105f)
                drawLine(
                    Color(0xFF1A9DA5).copy(alpha = .05f),
                    Offset(0f, y),
                    Offset(size.width, y),
                    strokeWidth = 1f,
                )
            }
        }
        content()
    }
}

@Composable
private fun StartupLoginScreen(
    storedSession: SupabaseSession?,
    onAuthenticated: (SupabaseSession) -> Unit,
    onForgetStoredSession: () -> Unit,
) {
    val cloud = remember { SupabaseClient() }
    val scope = rememberCoroutineScope()
    val focusManager = LocalFocusManager.current
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var authMode by remember { mutableStateOf("login") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var information by remember { mutableStateOf<String?>(null) }
    var showPassword by remember { mutableStateOf(false) }
    var showPolicy by remember { mutableStateOf(false) }

    Scaffold(topBar = { TopAppBar(title = { Text("StockAI Navigator") }) }) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
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
                        information = null
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
                TextButton(
                    enabled = !busy,
                    onClick = {
                        onForgetStoredSession()
                        error = null
                        information = "保存済みログインを解除しました。"
                    },
                    modifier = Modifier.align(Alignment.End),
                ) { Text("別のアカウントを使う") }
                HorizontalDivider()
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                FilterChip(
                    selected = authMode == "login",
                    onClick = {
                        authMode = "login"
                        error = null
                        information = null
                    },
                    label = { Text("ログイン") },
                )
                FilterChip(
                    selected = authMode == "register",
                    onClick = {
                        authMode = "register"
                        error = null
                        information = null
                    },
                    label = { Text("新規登録") },
                )
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            information?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
            OutlinedTextField(
                value = email, onValueChange = { email = it },
                label = { Text("メール") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = password, onValueChange = { password = it },
                label = { Text("パスワード") },
                visualTransformation = if (showPassword) {
                    VisualTransformation.None
                } else {
                    PasswordVisualTransformation()
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                trailingIcon = {
                    TextButton(onClick = { showPassword = !showPassword }) {
                        Text(if (showPassword) "隠す" else "表示")
                    }
                },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            if (authMode == "register") {
                OutlinedTextField(
                    value = confirmPassword, onValueChange = { confirmPassword = it },
                    label = { Text("パスワード（確認）") },
                    visualTransformation = if (showPassword) {
                        VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Button(
                enabled = !busy && email.isNotBlank() && password.isNotBlank(),
                onClick = {
                    focusManager.clearFocus()
                    busy = true
                    error = null
                    information = null
                    scope.launch {
                        runCatching {
                            withContext(Dispatchers.IO) {
                                if (authMode == "register") {
                                    require(password == confirmPassword) { "確認用パスワードが一致しません" }
                                    cloud.signUp(email, password).session
                                } else {
                                    cloud.signIn(email, password)
                                }
                            }
                        }.onSuccess { authenticated ->
                            if (authenticated == null) {
                                information =
                                    "登録確認メールを送信しました。メール内のリンクを開いた後、この画面からログインしてください。"
                                authMode = "login"
                            } else {
                                onAuthenticated(authenticated)
                            }
                        }
                            .onFailure { error = it.message ?: "ログインできませんでした" }
                        password = ""
                        confirmPassword = ""
                        busy = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (busy) "処理中" else if (authMode == "register") "登録" else "ログイン") }
            TextButton(
                onClick = { showPolicy = !showPolicy },
                modifier = Modifier.align(Alignment.CenterHorizontally),
            ) {
                Text(if (showPolicy) "プライバシー・免責事項を閉じる" else "プライバシー・免責事項")
            }
            if (showPolicy) {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .72f),
                    ),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                ) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text("認証", fontWeight = FontWeight.Bold)
                        Text("認証にはSupabaseを利用します。パスワードをアプリ独自のデータベースへ保存しません。")
                        Text("設定データ", fontWeight = FontWeight.Bold)
                        Text("ソート条件・期待値条件・分析依頼はログインユーザーごとに分離して保存します。")
                        Text("免責事項", fontWeight = FontWeight.Bold)
                        Text("本アプリの情報は投資助言ではなく、将来の利益を保証しません。最終判断は利用者自身で行ってください。")
                    }
                }
            }
        }
    }
}

@Composable
private fun StockAiApp(
    session: SupabaseSession,
    initialPage: String = "home",
    requiresOnboarding: Boolean,
    onOnboardingCompleted: () -> Unit,
    onSessionUpdated: (SupabaseSession) -> Unit,
    onLogout: () -> Unit,
) {
    val context = LocalContext.current
    val favoriteStore = remember(session.userId) {
        FavoriteStore(context.applicationContext, session.userId)
    }
    val favorites = remember(session.userId) {
        mutableStateListOf<FavoriteStock>().apply { addAll(favoriteStore.load()) }
    }
    fun toggleFavorite(code: String, companyName: String?) {
        val existing = favorites.indexOfFirst { it.code == code }
        if (existing >= 0) {
            favorites.removeAt(existing)
        } else {
            favorites.add(FavoriteStock(code, companyName))
        }
        favoriteStore.save(favorites)
    }
    var selectedCode by remember { mutableStateOf<String?>(null) }
    var selectedResult by remember { mutableStateOf<CloudScreeningResult?>(null) }
    var showWatchlist by remember { mutableStateOf(false) }
    var page by remember(session.userId, initialPage, requiresOnboarding) {
        mutableStateOf(if (requiresOnboarding) "onboarding_privacy" else initialPage)
    }
    BackHandler(
        enabled = selectedResult != null ||
            selectedCode != null ||
            showWatchlist ||
            page != "home"
    ) {
        when {
            page == "onboarding_privacy" -> Unit
            page == "onboarding_tutorial" -> page = "onboarding_privacy"
            selectedResult != null -> selectedResult = null
            selectedCode != null -> selectedCode = null
            showWatchlist -> showWatchlist = false
            else -> page = "home"
        }
    }
    when {
        selectedResult != null -> CloudResultDetailScreen(
            result = selectedResult!!,
            isFavorite = favorites.any { it.code == selectedResult!!.code },
            onToggleFavorite = {
                toggleFavorite(selectedResult!!.code, selectedResult!!.companyName)
            },
            onBack = { selectedResult = null },
        )
        selectedCode != null -> StockDetailScreen(
            code = selectedCode!!,
            onBack = { selectedCode = null },
        )
        showWatchlist -> WatchlistScreen(
            session = session,
            favorites = favorites,
            onBack = { showWatchlist = false },
            onSelect = { result ->
                selectedResult = result
                showWatchlist = false
            },
            onRemove = { favorite ->
                toggleFavorite(favorite.code, favorite.companyName)
            },
        )
        else -> when (page) {
            "onboarding_privacy" -> OnboardingPrivacyScreen(
                onContinue = { page = "onboarding_tutorial" },
            )
            "onboarding_tutorial" -> TutorialScreen(
                onBack = { page = "onboarding_privacy" },
                onComplete = {
                    onOnboardingCompleted()
                    page = "home"
                },
            )
            "home" -> HomeMenuScreen(onOpen = { page = it })
            "results" -> DeliveryResultsScreen(
                session,
                favoriteCodes = favorites.map { it.code }.toSet(),
                onSessionUpdated = onSessionUpdated,
                onBack = { page = "home" },
                onSelect = { selectedResult = it },
                onToggleFavorite = {
                    toggleFavorite(it.code, it.companyName)
                },
            )
            "candidates" -> CandidatePoolScreen(
                session,
                onBack = { page = "home" },
                onSelect = { selectedCode = it },
            )
            "settings" -> ScreeningScreen(
                        initialSession = session,
                        onBack = { page = "home" },
                        onSelect = { selectedCode = it },
            )
            "stock" -> ScreeningScreen(
                initialSession = session,
                initialPage = "stock",
                onBack = { page = "home" },
                onSelect = { selectedCode = it },
            )
            "operations" -> OperationsScreen(
                        favoriteCount = favorites.size,
                        onBack = { page = "home" },
                        onWatchlist = { showWatchlist = true },
            )
            "menu" -> MenuScreen(onBack = { page = "home" }, onOpen = { page = it })
            "tutorial" -> TutorialScreen(onBack = { page = "menu" })
            "data_status" -> DataUpdateStatusScreen(session, onBack = { page = "menu" })
            "faq" -> FaqScreen(onBack = { page = "menu" })
            "privacy" -> PrivacyScreen(onBack = { page = "menu" })
            "app_info" -> AppInfoScreen(onBack = { page = "menu" })
            else -> LogoutScreen(session.email, onBack = { page = "home" }, onLogout)
        }
    }
}

@Composable
private fun HomeMenuScreen(onOpen: (String) -> Unit) {
    Scaffold(topBar = {
        TopAppBar(
            title = {
                Column {
                    Text("StockAI", fontWeight = FontWeight.Bold)
                    Text(
                        "SMART MARKET NAVIGATOR",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            },
        )
    }) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            DigitalRainLayer(Modifier.matchParentSize())
            LazyColumn(
                Modifier.padding(horizontal = 16.dp, vertical = 14.dp).fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                contentPadding = PaddingValues(bottom = 28.dp),
            ) {
                item {
                    Text(
                        "MARKET CONTROL",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                        letterSpacing = 2.sp,
                    )
                }
                item { PanelButton("▣", "配信結果", Modifier.fillMaxWidth().height(106.dp)) { onOpen("results") } }
                item { PanelButton("◷", "前日候補銘柄", Modifier.fillMaxWidth().height(106.dp)) { onOpen("candidates") } }
                item { PanelButton("⌕", "指定銘柄分析", Modifier.fillMaxWidth().height(106.dp)) { onOpen("stock") } }
                item { PanelButton("⚙", "設定", Modifier.fillMaxWidth().height(106.dp)) { onOpen("settings") } }
                item { PanelButton("●", "運用", Modifier.fillMaxWidth().height(106.dp)) { onOpen("operations") } }
                item { PanelButton("☰", "メニュー", Modifier.fillMaxWidth().height(106.dp)) { onOpen("menu") } }
                item { PanelButton("↪", "ログアウト", Modifier.fillMaxWidth().height(96.dp)) { onOpen("logout") } }
            }
        }
    }
}

@Composable
private fun DigitalRainLayer(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val columnWidth = 22.dp.toPx()
        val segmentHeight = 9.dp.toPx()
        val columnCount = (size.width / columnWidth).toInt() + 1
        repeat(columnCount) { column ->
            val x = column * columnWidth + columnWidth / 2
            val phase = ((column * 47) % 13) / 13f
            val headY = size.height * (.12f + phase * .88f)
            repeat(14) { trail ->
                val y = headY - trail * segmentHeight * 1.8f
                if (y in 0f..size.height) {
                    val alpha = (.42f - trail * .027f).coerceAtLeast(.025f)
                    val width = if ((column + trail) % 3 == 0) 7.dp.toPx() else 3.dp.toPx()
                    drawLine(
                        color = Color(0xFF43F7E8).copy(alpha = alpha),
                        start = Offset(x, y),
                        end = Offset(x + width, y),
                        strokeWidth = if (trail == 0) 2.5.dp.toPx() else 1.dp.toPx(),
                        cap = StrokeCap.Round,
                    )
                }
            }
        }
        drawRect(
            brush = Brush.verticalGradient(
                listOf(Color.Transparent, Color(0x3300070B), Color(0xD901050A))
            )
        )
    }
}

@Composable
private fun MenuScreen(onBack: () -> Unit, onOpen: (String) -> Unit) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("メニュー") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
        )
    }) { padding ->
        LazyColumn(
            Modifier.padding(padding).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item { PanelButton("?", "チュートリアル", Modifier.fillMaxWidth().height(110.dp)) { onOpen("tutorial") } }
            item { PanelButton("↻", "データ更新状況", Modifier.fillMaxWidth().height(100.dp)) { onOpen("data_status") } }
            item { PanelButton("Q", "よくある質問", Modifier.fillMaxWidth().height(100.dp)) { onOpen("faq") } }
            item { PanelButton("盾", "プライバシー・免責事項", Modifier.fillMaxWidth().height(100.dp)) { onOpen("privacy") } }
            item { PanelButton("i", "アプリ情報", Modifier.fillMaxWidth().height(100.dp)) { onOpen("app_info") } }
            item { PanelButton("▣", "配信結果", Modifier.fillMaxWidth().height(100.dp)) { onOpen("results") } }
            item { PanelButton("◷", "前日候補", Modifier.fillMaxWidth().height(100.dp)) { onOpen("candidates") } }
            item { PanelButton("⌕", "指定銘柄分析", Modifier.fillMaxWidth().height(100.dp)) { onOpen("stock") } }
            item { PanelButton("⚙", "設定", Modifier.fillMaxWidth().height(100.dp)) { onOpen("settings") } }
            item { PanelButton("●", "運用", Modifier.fillMaxWidth().height(100.dp)) { onOpen("operations") } }
            item { PanelButton("↪", "ログアウト", Modifier.fillMaxWidth().height(100.dp)) { onOpen("logout") } }
        }
    }
}

private val privacyItems = listOf(
    "個人情報" to "認証にはSupabaseを利用します。パスワードをアプリ独自のデータベースへ保存しません。",
    "設定データ" to "ソート条件、期待値条件、分析依頼はログインユーザーごとに分離して保存します。",
    "投資判断" to "本アプリの情報は投資助言ではありません。期待値やバックテストは将来の利益を保証しません。",
    "データ" to "市場データには遅延、欠損、訂正が発生する可能性があります。最終判断は利用者自身で行ってください。",
)

@Composable
private fun OnboardingPrivacyScreen(onContinue: () -> Unit) {
    var acknowledged by remember { mutableStateOf(false) }
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("ご利用前の確認") })
        },
    ) { padding ->
        LazyColumn(
            Modifier.padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                Text(
                    "プライバシー・免責事項",
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text("StockAIを利用する前に、次の内容をご確認ください。")
            }
            items(privacyItems) { (title, body) ->
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .72f),
                    ),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                ) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(title, fontWeight = FontWeight.Bold)
                        Text(body)
                    }
                }
            }
            item {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable { acknowledged = !acknowledged },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = acknowledged,
                        onCheckedChange = { acknowledged = it },
                    )
                    Text(
                        "内容を確認し、投資判断は自分の責任で行うことに同意します。",
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            item {
                Button(
                    enabled = acknowledged,
                    onClick = onContinue,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("同意してチュートリアルへ")
                }
            }
        }
    }
}

@Composable
private fun TutorialScreen(
    onBack: () -> Unit,
    onComplete: (() -> Unit)? = null,
) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("チュートリアル") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
        )
    }) { padding ->
        LazyColumn(
            Modifier.padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            item {
                Text(
                    "StockAIの基本的な使い方",
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text("指定期間内に株価が上がる可能性を、過去データと現在の分析から確認するアプリです。")
            }
            item {
                Text("1. 条件を設定する", fontWeight = FontWeight.Bold)
                Text("ソート条件で候補の選び方を決め、期待値条件に「以上・以下」と数値を設定します。買い・売り方向、保有営業日数、期間内上昇または条件到達での評価方法も選べます。最後に「設定を保存」を押します。")
            }
            item {
                Text("2. データ更新と候補抽出", fontWeight = FontWeight.Bold)
                Text("夕方に全市場データを更新して前日候補を作成し、翌朝に最新データで条件判定と配信結果を生成します。取得件数、失敗件数、カバー率は「データ更新状況」で確認できます。")
            }
            item {
                Text("3. 配信カードを見る", fontWeight = FontWeight.Bold)
                Text("カードには銘柄、スコア、平均リターン、勝率、最大含み損を表示します。スコア70以上はブロンズ、80以上はシルバー、90以上はゴールドです。カードをタップすると詳細を開けます。")
            }
            item {
                Text("4. 分析詳細を確認する", fontWeight = FontWeight.Bold)
                Text("テクニカル分析では日足・週足・月足のRSIや移動平均線をまとめて確認します。ファンダメンタル分析では業界平均と比べた割安・割高、財務、成長性、配当を確認し、最後に総合コメントを表示します。")
            }
            item {
                Text("5. バックテストを比較する", fontWeight = FontWeight.Bold)
                Text("同じ売買条件を個別銘柄、同業種、取得済み全銘柄で検証します。事例数、期間外検証、カバー率、信頼度を併せて確認し、一つの銘柄だけに偏らない判断材料にします。")
            }
            item {
                Text("6. 監視対象と指定銘柄分析", fontWeight = FontWeight.Bold)
                Text("気になる銘柄はカードから監視対象へ追加できます。任意の銘柄コードを指定して、保存済み条件による分析とバックテストを依頼することもできます。")
            }
            item {
                Text("注意", fontWeight = FontWeight.Bold)
                Text("期待値やバックテストは過去データによる参考情報であり、将来の利益を保証するものではありません。")
            }
            if (onComplete != null) {
                item {
                    Button(
                        onClick = onComplete,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("チュートリアルを完了して始める")
                    }
                }
            }
        }
    }
}

@Composable
private fun DataUpdateStatusScreen(session: SupabaseSession, onBack: () -> Unit) {
    val cloud = remember { SupabaseClient() }
    var run by remember { mutableStateOf<CloudScreeningRun?>(null) }
    var pool by remember { mutableStateOf<CandidatePool?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    LaunchedEffect(refresh) {
        runCatching {
            withContext(Dispatchers.IO) {
                cloud.loadLatestRun(session) to cloud.loadLatestCandidates(session)
            }
        }.onSuccess {
            run = it.first
            pool = it.second
            error = null
        }.onFailure { error = it.message }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("データ更新状況") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
            actions = { TextButton(onClick = { refresh++ }) { Text("更新") } },
        )
    }) { padding ->
        Column(
            Modifier.padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("最終取得日時: ${pool?.updatedAt ?: pool?.poolDate ?: "未取得"}")
            Text(
                "全市場対象: ${pool?.universeCount ?: "-"}件 / " +
                    "判定済み: ${pool?.evaluatedCount ?: "-"}件"
            )
            Text(
                "候補銘柄数: ${pool?.candidateCount ?: pool?.codes?.size ?: 0}件 / " +
                    "取得失敗: ${pool?.failedCount ?: "-"}件"
            )
            pool?.coverageRatio?.let {
                Text("カバー率: ${String.format("%.1f", it * 100)}%")
            }
            Text("夕方処理状態: ${pool?.status ?: "未取得"}")
            Text("配信判定最終日: ${run?.screeningDate ?: "未実行"}")
            Text(
                run?.let {
                    "配信該当銘柄数: ${it.hitCount}件（${screeningRunStatus(it.hitCount)}）"
                } ?: "配信該当銘柄数: 未判定"
            )
            run?.let { Text("配信結果更新: ${formatJst(it.updatedAt)}") }
            run?.let {
                Text("売買方向: ${tradeDirectionLabel(it.tradeDirection)}")
                Text("使用した緩和: ${it.relaxationLabel ?: "基準条件"}")
                if (it.relaxationCounts.isNotEmpty()) {
                    Text(
                        "段階別件数: " + it.relaxationCounts.joinToString(" / ") { count ->
                            "${count.stage} ${count.hitCount}件"
                        }
                    )
                }
            }
            val hasPoolProblem = pool?.usable == false
            Text(
                "障害状況: ${when {
                    error != null -> error
                    hasPoolProblem -> "全市場データの取得率が基準未満です"
                    else -> "確認された障害なし"
                }}"
            )
        }
    }
}

@Composable
private fun FaqScreen(onBack: () -> Unit) {
    InfoListScreen("よくある質問", onBack, listOf(
        "条件一致が0件になる理由" to "保存した全条件を同時に満たす銘柄がない、前日候補データが未更新、または必要な財務情報が不足している場合があります。",
        "期待値とは" to "同じ期待値条件が過去に成立した場面を調べ、設定した保有営業日数後の成績から算出した参考スコアです。",
        "オートとマニュアルの違い" to "オートは目的別の標準条件、マニュアルは入力した指標だけをAND条件として使います。",
        "指定銘柄分析がすぐ完了しない" to "クラウドで安全に計算するため受付後に非同期処理します。次回更新後に結果を再読込してください。",
    ))
}

@Composable
private fun PrivacyScreen(onBack: () -> Unit) {
    InfoListScreen("プライバシー・免責事項", onBack, privacyItems)
}

@Composable
private fun AppInfoScreen(onBack: () -> Unit) {
    InfoListScreen("アプリ情報", onBack, listOf(
        "バージョン" to "StockAI Navigator 0.21.1",
        "0.21.1" to "期待値条件なしを正式に許可し、指定営業日の期間最終日決済として処理。入口の手動条件なしは保存時に検知。",
        "0.21.0" to "営業日数を最大監視期間として扱い、期間内の条件初回達成で決済。条件なしは期間最終日決済とし、10%・20%含み益確率を追加。",
        "0.20.0" to "配信カードをブロンズ・シルバー・ゴールドのスコア色へ変更。初回ログイン時の免責確認と最新チュートリアルを追加。",
        "0.19.0" to "同じ売買条件を個別銘柄・同業種・取得全銘柄で比較。直近20%の期間外検証、対象銘柄数・事例数・カバー率・データ充足度を追加。",
        "0.18.2" to "Supabase認証期限切れ時にセッションを自動更新。",
        "0.18.1" to "過去事例0件をスコア0.0と誤表示しないよう修正。監視対象から最新のクラウド分析詳細を表示。",
        "0.18.0" to "配信結果をスコア・平均リターン・勝率・最大含み損の一覧へ簡潔化。タップ式の分析詳細とユーザー別の監視登録を追加。",
        "0.17.1" to "長期検証の履歴不足を明示し、達成事例0件の場合も参考価格の算出状態を表示。",
        "0.17.0" to "期待値条件の達成事例から参考株価の中央値・価格帯・検証件数・到達日数を表示。",
        "0.16.0" to "期待値の検証期間を最大1000営業日へ拡張し、360営業日などの長期検証に対応。",
        "0.15.0" to "期待値を条件到達、期間末の騰落、期間内の価格改善、目標騰落率到達から選択でき、達成確率を表示。",
        "0.14.0" to "条件に以下・以上を追加。入口と出口を対にした買い→売り／空売り→買い戻しの条件到達型バックテストに対応。",
        "0.13.1" to "配信結果の0件を正常終了として明示し、結果更新時刻を日本時間で表示。該当件数と結果詳細の不一致も検知。",
        "0.13.0" to "全市場の対象数・判定済み数・候補数・失敗数・カバー率・利用可否をクラウド運用状況へ追加。",
        "0.12.5" to "保存済み通知設定をアプリ起動時に自動再予約し、更新後の手動再保存を不要化。",
        "0.12.4" to "通知権限がない状態を成功扱いしないよう修正し、クラウド通知処理をネットワーク接続時だけ実行。",
        "0.12.3" to "登録確認メール送信を成功表示に変更し、保存済みログインから別アカウントへ切り替える操作を追加。",
        "0.12.2" to "ログイン画面のスクロール、キーボード収納、パスワード表示切替、登録前のプライバシー・免責確認を追加。",
        "0.12.1" to "当日結果の完成待ち、10分間隔の自動再確認、前回結果の誤通知防止を追加。",
        "0.12.0" to "時・分の分離入力、保存完了表示、キーボード制御、即時テスト通知を追加。",
        "0.11.2" to "端末内のテスト通知と通知処理結果の記録を追加。",
        "0.11.1" to "通知タップ後に配信結果を直接開く導線と通知予定表示を追加。",
        "0.11.0" to "保存した時刻・件数上限によるAndroid端末通知を追加。",
        "0.10.0" to "Particle Streamアイコン、テック系フォント、半透明カードを追加。",
        "0.9.1" to "戻るジェスチャーの画面遷移を修正し、トップへデジタル・レイン背景を追加。",
        "0.9.0" to "濃紺・シアンを基調とした金融ダッシュボードUIへ刷新。",
        "0.8.0" to "設定保存を明確化し、アプリ通知の時刻・件数上限、更新状況、FAQ、プライバシー、更新履歴を整理。LINE配信を停止。",
        "0.7.0" to "週足・月足指標、折りたたみ条件、通知設定、更新状況、FAQ、免責事項を追加。",
        "0.6.0" to "テクニカル・ファンダメンタル条件を拡充。",
        "0.5.0" to "コマ割りメニュー、チュートリアルを追加。",
        "0.3.0" to "指定銘柄バックテストと複数ユーザー対応を追加。",
    ))
}

@Composable
private fun InfoListScreen(
    title: String,
    onBack: () -> Unit,
    entries: List<Pair<String, String>>,
) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(title) },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
        )
    }) { padding ->
        LazyColumn(
            Modifier.padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            entries.forEach { (heading, body) ->
                item {
                    Text(heading, style = MaterialTheme.typography.titleMedium)
                    Text(body)
                }
            }
        }
    }
}

@Composable
private fun ParticleStreamIcon(symbol: String, modifier: Modifier = Modifier) {
    Canvas(modifier.size(54.dp)) {
        val particles = mutableListOf<Offset>()
        fun point(x: Float, y: Float) {
            particles += Offset(x * size.width, y * size.height)
        }
        fun segment(x1: Float, y1: Float, x2: Float, y2: Float, count: Int = 10) {
            repeat(count) { index ->
                val t = if (count == 1) 0f else index.toFloat() / (count - 1)
                val jitter = (((index * 17 + symbol.hashCode()) % 5) - 2) * .0035f
                point(x1 + (x2 - x1) * t + jitter, y1 + (y2 - y1) * t - jitter)
            }
        }
        fun circle(cx: Float, cy: Float, radius: Float, count: Int = 28) {
            repeat(count) { index ->
                val angle = Math.PI * 2.0 * index / count
                point(
                    cx + kotlin.math.cos(angle).toFloat() * radius,
                    cy + kotlin.math.sin(angle).toFloat() * radius,
                )
            }
        }

        when (symbol) {
            "✓" -> {
                segment(.23f, .55f, .43f, .74f, 13)
                segment(.43f, .74f, .82f, .25f, 22)
                segment(.18f, .17f, .18f, .78f, 14)
            }
            "⇅" -> {
                segment(.20f, .77f, .76f, .22f, 26)
                segment(.56f, .22f, .76f, .22f, 8)
                segment(.76f, .22f, .76f, .42f, 8)
                segment(.20f, .57f, .20f, .77f, 8)
                segment(.20f, .77f, .40f, .77f, 8)
            }
            "◎", "◷", "⚙" -> {
                circle(.52f, .48f, .30f, 34)
                circle(.52f, .48f, .10f, 14)
                repeat(8) { index ->
                    val angle = Math.PI * 2.0 * index / 8
                    segment(
                        .52f + kotlin.math.cos(angle).toFloat() * .12f,
                        .48f + kotlin.math.sin(angle).toFloat() * .12f,
                        .52f + kotlin.math.cos(angle).toFloat() * .38f,
                        .48f + kotlin.math.sin(angle).toFloat() * .38f,
                        6,
                    )
                }
            }
            "⌕", "Q" -> {
                circle(.43f, .39f, .25f, 34)
                segment(.60f, .58f, .86f, .84f, 18)
            }
            "▣" -> {
                segment(.18f, .20f, .82f, .20f, 18)
                segment(.18f, .20f, .18f, .80f, 16)
                segment(.18f, .80f, .82f, .80f, 18)
                segment(.82f, .20f, .82f, .80f, 16)
                segment(.31f, .66f, .31f, .48f, 8)
                segment(.50f, .66f, .50f, .34f, 12)
                segment(.69f, .66f, .69f, .26f, 15)
            }
            "●", "♢" -> {
                val heights = listOf(.25f, .46f, .70f, .36f, .80f, .54f, .30f)
                heights.forEachIndexed { index, height ->
                    val x = .18f + index * .105f
                    segment(x, .50f - height / 2, x, .50f + height / 2, 10)
                }
            }
            "☰" -> {
                segment(.18f, .27f, .82f, .27f, 22)
                segment(.18f, .50f, .70f, .50f, 18)
                segment(.18f, .73f, .82f, .73f, 22)
            }
            "↪" -> {
                segment(.18f, .52f, .76f, .52f, 24)
                segment(.58f, .30f, .80f, .52f, 12)
                segment(.80f, .52f, .58f, .74f, 12)
            }
            else -> {
                circle(.50f, .48f, .28f, 30)
                segment(.24f, .68f, .76f, .28f, 24)
            }
        }

        repeat(18) { index ->
            val x = ((index * 37 + symbol.hashCode()) and 255) / 255f
            val y = .18f + ((index * 61 + symbol.hashCode()) and 127) / 180f
            point(x.coerceIn(.08f, .92f), y.coerceIn(.08f, .92f))
        }
        particles.forEachIndexed { index, particle ->
            val strong = index % 7 == 0
            drawCircle(
                color = Color(0xFF66FFF4).copy(alpha = if (strong) .95f else .56f),
                radius = if (strong) 2.2.dp.toPx() else 1.15.dp.toPx(),
                center = particle,
            )
            if (strong) {
                drawCircle(
                    color = Color(0xFF18DAD5).copy(alpha = .12f),
                    radius = 5.5.dp.toPx(),
                    center = particle,
                )
            }
        }
    }
}

@Composable
private fun PanelButton(
    mark: String,
    label: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val highlighted = label.contains("保存")
    Card(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        border = BorderStroke(
            if (highlighted) 2.dp else 1.dp,
            if (highlighted) Color(0xFF52FFF5) else Color(0xFF1CA4A7),
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = if (highlighted) 14.dp else 8.dp),
    ) {
        Row(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.horizontalGradient(
                        if (highlighted) {
                            listOf(
                                Color(0xB3073035),
                                Color(0xB80D4A4D),
                                Color(0xA8073035),
                            )
                        } else {
                            listOf(
                                Color(0xA8071119),
                                Color(0xB20A2028),
                                Color(0x98071119),
                            )
                        }
                    )
                )
                .padding(horizontal = 18.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                label,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            ParticleStreamIcon(mark)
        }
    }
}

@Composable
private fun ConditionFieldsPanel(
    title: String,
    fields: List<ManualField>,
    values: MutableMap<String, String>,
    operators: MutableMap<String, String>,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Row(
                Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(if (expanded) "▲ 閉じる" else "▼ 開く")
            }
            if (expanded) {
                var previousGroup: String? = null
                fields.forEach { field ->
                    val group = manualFieldGroup(field.field)
                    if (field.category == "technical" && group != previousGroup) {
                        Text(
                            group,
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(top = 12.dp, bottom = 4.dp),
                        )
                        previousGroup = group
                    }
                    val selectedOperator = operators[field.field] ?: field.defaultOperator
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        FilterChip(
                            selected = selectedOperator == "<=",
                            onClick = { operators[field.field] = "<=" },
                            label = { Text("以下（≤）") },
                        )
                        FilterChip(
                            selected = selectedOperator == ">=",
                            onClick = { operators[field.field] = ">=" },
                            label = { Text("以上（≥）") },
                        )
                    }
                    OutlinedTextField(
                        value = values[field.field] ?: "",
                        onValueChange = { values[field.field] = it },
                        label = {
                            Text(
                                "${field.label} " +
                                    if (selectedOperator == "<=") "以下" else "以上"
                            )
                        },
                        supportingText = { Text("範囲 ${field.min}〜${field.max}") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                }
            }
        }
    }
}

@Composable
private fun DeliveryResultsScreen(
    session: SupabaseSession,
    favoriteCodes: Set<String>,
    onSessionUpdated: (SupabaseSession) -> Unit,
    onBack: () -> Unit,
    onSelect: (CloudScreeningResult) -> Unit,
    onToggleFavorite: (CloudScreeningResult) -> Unit,
) {
    val cloud = remember { SupabaseClient() }
    var requestSession by remember(session.userId) { mutableStateOf(session) }
    var results by remember { mutableStateOf<List<CloudScreeningResult>>(emptyList()) }
    var run by remember { mutableStateOf<CloudScreeningRun?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        val currentSession = requestSession
        runCatching {
            withContext(Dispatchers.IO) {
                cloud.withFreshSession(currentSession) { validSession ->
                    cloud.loadLatestRun(validSession) to cloud.loadLatestResults(validSession)
                }
            }
        }.onSuccess { authenticated ->
            if (authenticated.session.accessToken != requestSession.accessToken) {
                requestSession = authenticated.session
                onSessionUpdated(authenticated.session)
            }
            run = authenticated.value.first
            results = authenticated.value.second
        }.onFailure { error = it.message }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("配信結果") },
                navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
                actions = { TextButton(onClick = { refreshToken++ }) { Text("更新") } },
            )
        },
    ) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            run?.let { latest ->
                item {
                    ElevatedCard(Modifier.fillMaxWidth()) {
                        Column(
                            Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Text(
                                "${latest.screeningDate}　${latest.hitCount}銘柄",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            Text(
                                "${latest.holdingDays}営業日以内の検証 / " +
                                    "${latest.relaxationLabel ?: "基準条件"}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                "更新 ${formatJst(latest.updatedAt)}",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                }
            }
            error?.let {
                item { Text("配信結果を取得できません: $it", color = MaterialTheme.colorScheme.error) }
            }
            if (results.isEmpty() && error == null) {
                item {
                    val message = when {
                        run == null -> "配信処理はまだ実行されていません"
                        run?.hitCount == 0 -> "処理は正常に完了しました。現在の条件に一致する銘柄は0件です"
                        else -> "該当件数と結果詳細が一致しません。更新を押して再取得してください"
                    }
                    Text(
                        message,
                        color = if ((run?.hitCount ?: 0) > 0) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurface
                        },
                    )
                }
            }
            items(results) { result ->
                val isFavorite = result.code in favoriteCodes
                val rank = resultCardRank(result.expectationScore)
                ElevatedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 10.dp)
                        .clickable { onSelect(result) },
                    colors = CardDefaults.elevatedCardColors(
                        containerColor = rank?.containerColor
                            ?: MaterialTheme.colorScheme.surface.copy(alpha = .76f),
                    ),
                ) {
                    Column(
                        Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "${result.position}. ${result.code}",
                                    style = MaterialTheme.typography.titleMedium,
                                )
                                result.companyName?.let {
                                    Text(
                                        it,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                            rank?.let {
                                Text(
                                    it.label,
                                    color = it.accentColor,
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                                Spacer(Modifier.width(4.dp))
                            }
                            TextButton(onClick = { onToggleFavorite(result) }) {
                                Text(if (isFavorite) "★ 監視中" else "☆ 監視")
                            }
                        }
                        if (result.hasBacktestMetrics()) {
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                ResultMetric(
                                    "スコア",
                                    result.expectationScore.percentValue(false),
                                    Modifier.weight(1f),
                                )
                                ResultMetric(
                                    "平均リターン",
                                    result.averageReturnPercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                            }
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                ResultMetric(
                                    "勝率",
                                    result.winRatePercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                                ResultMetric(
                                    "最大含み損",
                                    result.maxDrawdownPercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                            }
                        } else {
                            Text(
                                "過去に同じ期待値条件が成立した事例がなく、統計を算出できません。",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Text(
                            "タップして分析詳細を表示",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }
        }
    }
}

private data class ResultCardRank(
    val label: String,
    val containerColor: Color,
    val accentColor: Color,
)

private fun resultCardRank(score: Double?): ResultCardRank? = when {
    score == null || score < 70.0 -> null
    score >= 90.0 -> ResultCardRank(
        label = "GOLD",
        containerColor = Color(0xFFD5A62E).copy(alpha = .36f),
        accentColor = Color(0xFFFFD86B),
    )
    score >= 80.0 -> ResultCardRank(
        label = "SILVER",
        containerColor = Color(0xFF94A9B4).copy(alpha = .32f),
        accentColor = Color(0xFFDCE8ED),
    )
    else -> ResultCardRank(
        label = "BRONZE",
        containerColor = Color(0xFF9A623A).copy(alpha = .38f),
        accentColor = Color(0xFFE5A875),
    )
}

@Composable
private fun ResultMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, fontWeight = FontWeight.Bold)
    }
}

private fun CloudScreeningResult.hasBacktestMetrics(): Boolean =
    averageReturnPercent != null &&
        winRatePercent != null &&
        maxDrawdownPercent != null

@Composable
private fun CloudResultDetailScreen(
    result: CloudScreeningResult,
    isFavorite: Boolean,
    onToggleFavorite: () -> Unit,
    onBack: () -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(result.code) },
                navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
                actions = {
                    TextButton(onClick = onToggleFavorite) {
                        Text(if (isFavorite) "★ 監視中" else "☆ 監視へ追加")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            Modifier.padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    result.companyName ?: result.code,
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text(
                    "${result.screeningDate} / ${result.holdingDays ?: "-"}営業日以内",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        if (result.hasBacktestMetrics()) {
                            Row(Modifier.fillMaxWidth()) {
                                ResultMetric(
                                    "スコア",
                                    result.expectationScore.percentValue(false),
                                    Modifier.weight(1f),
                                )
                                ResultMetric(
                                    "平均リターン",
                                    result.averageReturnPercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                            }
                            Row(Modifier.fillMaxWidth()) {
                                ResultMetric(
                                    "勝率",
                                    result.winRatePercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                                ResultMetric(
                                    "最大含み損",
                                    result.maxDrawdownPercent.percentValue(),
                                    Modifier.weight(1f),
                                )
                            }
                        } else {
                            Text(
                                "この条件での過去事例がないため、バックテスト統計はありません。",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
            item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            "バックテスト比較",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            "同じ売買条件を個別・同業種・取得全銘柄で検証",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            "平均リターンは各売買事例の損益率の算術平均。" +
                                "同業種・全銘柄は事例数で加重集計します。",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        BacktestScopeRow(
                            "この銘柄",
                            PooledBacktestSummary(
                                stockCount = 1,
                                tradeCount = result.individualTradeCount,
                                averageReturnPercent =
                                    result.averageReturnPercent,
                                winRatePercent = result.winRatePercent,
                                maxDrawdownPercent =
                                    result.maxDrawdownPercent,
                                outOfSampleTradeCount =
                                    result.individualOutOfSampleTradeCount,
                                outOfSampleAverageReturnPercent =
                                    result.individualOutOfSampleAverageReturnPercent,
                                outOfSampleWinRatePercent =
                                    result.individualOutOfSampleWinRatePercent,
                            ),
                        )
                        HorizontalDivider()
                        BacktestScopeRow(
                            result.sectorName?.let { "同業種（$it）" }
                                ?: "同業種",
                            result.sectorBacktest,
                        )
                        HorizontalDivider()
                        BacktestScopeRow("取得全銘柄", result.marketBacktest)
                        val coverage = result.backtestCoverageRatio
                        Text(
                            "データ充足度: ${result.backtestConfidence ?: "低"}" +
                                if (coverage != null) {
                                    " / 全銘柄カバー率 " +
                                        String.format("%.1f%%", coverage * 100)
                                } else {
                                    ""
                                },
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "直近20%は過去の古い期間と分けた期間外検証です。" +
                                "母数が多くても将来の利益を保証するものではありません。",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp),
                    ) {
                        Text("期間内の達成確率", style = MaterialTheme.typography.titleMedium)
                        when (result.evaluationMode) {
                            "condition_exit" -> Text(
                                "指定条件の達成確率 " +
                                    result.outcomeProbabilityPercent.percentValue()
                            )
                            "period_end" -> Text(
                                "期間最終日の値上がり確率 " +
                                    result.winRatePercent.percentValue()
                            )
                            "target_return" -> Text(
                                "設定した${String.format("%.1f", result.targetReturnPercent)}%含み益の達成確率 " +
                                    result.outcomeProbabilityPercent.percentValue()
                            )
                            else -> Text(
                                "値上がり・値下がり条件の達成確率 " +
                                    result.outcomeProbabilityPercent.percentValue()
                            )
                        }
                        if (result.evaluationMode != "period_end") {
                            Text(
                                "10%以上の含み益となる確率 " +
                                    result.profit10ProbabilityPercent.percentValue()
                            )
                            Text(
                                "20%以上の含み益となる確率 " +
                                    result.profit20ProbabilityPercent.percentValue()
                            )
                        }
                        Text(
                            "営業日数は決済日ではなく、条件を監視する最大期間です。" +
                                "条件未達の場合だけ期間最終日に決済します。",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            result.referencePrice?.let { price ->
                item {
                    ElevatedCard(Modifier.fillMaxWidth()) {
                        Column(
                            Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(5.dp),
                        ) {
                            Text("価格シミュレーション", style = MaterialTheme.typography.titleMedium)
                            Text("配信時価格 ${String.format("%,.2f円", price)}")
                            result.estimatedPriceMedian?.let {
                                Text(
                                    (if (result.evaluationMode == "period_end") {
                                        "期間最終日の参考価格中央値 "
                                    } else {
                                        "条件達成時の参考価格中央値 "
                                    }) + String.format("%,.2f円", it)
                                )
                            }
                            if (
                                result.estimatedPriceLow != null &&
                                result.estimatedPriceHigh != null
                            ) {
                                Text(
                                    "中心50%価格帯 " +
                                        String.format(
                                            "%,.2f～%,.2f円",
                                            result.estimatedPriceLow,
                                            result.estimatedPriceHigh,
                                        )
                                )
                            }
                            Text("達成事例 ${result.estimateSampleCount}件")
                            result.medianDaysToOutcome?.let {
                                Text("到達まで中央値 ${String.format("%.1f", it)}営業日")
                            }
                        }
                    }
                }
            }
            item {
                AnalysisDetailCard(
                    "テクニカル分析",
                    analysisSection(result.comment, "テクニカル"),
                )
            }
            item {
                AnalysisDetailCard(
                    "ファンダメンタル分析",
                    analysisSection(result.comment, "ファンダメンタル"),
                )
            }
            item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp),
                    ) {
                        Text("検証条件", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "評価方法: " +
                                evaluationModeLabel(
                                    result.evaluationMode,
                                    result.targetReturnPercent,
                                )
                        )
                        result.conditionSummary?.let {
                            Text("買い・入口: ${formatConditionSummary(it)}")
                        }
                        if (result.evaluationMode == "condition_exit") {
                            result.expectationConditionSummary?.let {
                                Text("売却・達成: ${formatConditionSummary(it)}")
                            }
                        }
                    }
                }
            }
            item {
                AnalysisDetailCard(
                    "コメント",
                    listOfNotNull(
                        analysisSection(result.comment, "バックテスト"),
                        analysisSection(result.comment, "総合所見"),
                    ).filter { it.isNotBlank() }.joinToString("\n\n")
                        .ifBlank { result.comment ?: "コメントはありません。" },
                )
            }
            item {
                Text(
                    "過去データに基づく参考情報であり、将来の価格や利益を保証しません。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun BacktestScopeRow(
    label: String,
    summary: PooledBacktestSummary,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            "$label / ${summary.stockCount}銘柄・${summary.tradeCount}事例",
            fontWeight = FontWeight.Bold,
        )
        Row(Modifier.fillMaxWidth()) {
            ResultMetric(
                "平均リターン",
                summary.averageReturnPercent.percentValue(),
                Modifier.weight(1f),
            )
            ResultMetric(
                "勝率",
                summary.winRatePercent.percentValue(),
                Modifier.weight(1f),
            )
            ResultMetric(
                "最大含み損",
                summary.maxDrawdownPercent.percentValue(),
                Modifier.weight(1f),
            )
        }
        if (summary.outOfSampleTradeCount > 0) {
            Text(
                "直近20%（${summary.outOfSampleTradeCount}事例）: " +
                    "平均 ${summary.outOfSampleAverageReturnPercent.percentValue()} / " +
                    "勝率 ${summary.outOfSampleWinRatePercent.percentValue()}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun AnalysisDetailCard(title: String, body: String?) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(body?.takeIf { it.isNotBlank() } ?: "取得できる情報がありません。")
        }
    }
}

@Composable
private fun CandidatePoolScreen(
    session: SupabaseSession,
    onBack: () -> Unit,
    onSelect: (String) -> Unit,
) {
    val cloud = remember { SupabaseClient() }
    var pool by remember { mutableStateOf<CandidatePool?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshToken by remember { mutableIntStateOf(0) }
    LaunchedEffect(refreshToken) {
        error = null
        runCatching { withContext(Dispatchers.IO) { cloud.loadLatestCandidates(session) } }
            .onSuccess { pool = it }
            .onFailure { error = it.message }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("前日取得候補銘柄") },
                navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
                actions = { TextButton(onClick = { refreshToken++ }) { Text("更新") } },
            )
        },
    ) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            item { Text("取得日: ${pool?.poolDate ?: "未取得"}") }
            error?.let {
                item { Text("候補銘柄を取得できません: $it", color = MaterialTheme.colorScheme.error) }
            }
            if (pool?.codes?.isEmpty() == true) item { Text("候補銘柄はありません") }
            items(pool?.codes.orEmpty()) { code ->
                ListItem(
                    headlineContent = { Text(code) },
                    modifier = Modifier.fillMaxWidth().clickable { onSelect(code) },
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun LogoutScreen(email: String, onBack: () -> Unit, onLogout: () -> Unit) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("ログアウト") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
        )
    }) { padding ->
        Column(
            Modifier.padding(padding).padding(24.dp).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("ログイン中: $email")
            Text("ログアウトすると、次回はメールアドレスとパスワードでの認証が必要です。")
            Button(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
                Text("ログアウト")
            }
        }
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
private fun ScreeningScreen(
    initialSession: SupabaseSession?,
    initialPage: String = "home",
    onBack: () -> Unit,
    onSelect: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val cloud = remember { SupabaseClient() }
    var options by remember { mutableStateOf<ScreeningOptions?>(null) }
    var mode by remember { mutableStateOf("auto") }
    var genreId by remember { mutableStateOf<String?>(null) }
    var expectationMode by remember { mutableStateOf("auto") }
    var expectationGenreId by remember { mutableStateOf<String?>(null) }
    var holdingDays by remember { mutableStateOf("60") }
    var tradeDirection by remember { mutableStateOf("long") }
    var evaluationMode by remember { mutableStateOf("condition_exit") }
    var targetReturnPercent by remember { mutableStateOf("5.0") }
    val manualValues = remember { mutableStateMapOf<String, String>() }
    val manualOperators = remember { mutableStateMapOf<String, String>() }
    val expectationManualValues = remember { mutableStateMapOf<String, String>() }
    val expectationManualOperators = remember {
        mutableStateMapOf<String, String>()
    }
    var hits by remember { mutableStateOf<List<ScreeningHit>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var localApiAvailable by remember { mutableStateOf(true) }
    var refreshToken by remember { mutableIntStateOf(0) }
    var cloudSession by remember { mutableStateOf(initialSession) }
    var cloudResults by remember { mutableStateOf<List<CloudScreeningResult>>(emptyList()) }
    var cloudRun by remember { mutableStateOf<CloudScreeningRun?>(null) }
    var cloudStatus by remember { mutableStateOf<String?>(null) }
    var showLogin by remember { mutableStateOf(false) }
    var loginPurpose by remember { mutableStateOf("save") }
    var authMode by remember { mutableStateOf("login") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var loginError by remember { mutableStateOf<String?>(null) }
    var cloudBusy by remember { mutableStateOf(false) }
    var specifiedCode by remember { mutableStateOf("") }
    var requestedBacktest by remember { mutableStateOf<RequestedBacktest?>(null) }
    var settingsPage by remember(initialPage) { mutableStateOf(initialPage) }
    var sortCategory by remember { mutableStateOf<String?>(null) }
    var expectationCategory by remember { mutableStateOf<String?>(null) }
    val expandedGroups = remember {
        mutableStateMapOf(
            "sort_daily" to true,
            "sort_weekly" to false,
            "sort_monthly" to false,
            "sort_fundamental" to true,
            "expect_daily" to true,
            "expect_weekly" to false,
            "expect_monthly" to false,
            "expect_fundamental" to true,
        )
    }
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val notificationPreferences = remember {
        context.getSharedPreferences(
            NotificationScheduler.PREFERENCES_NAME,
            android.content.Context.MODE_PRIVATE,
        )
    }
    val savedNotificationTime = remember {
        notificationPreferences.getString(NotificationScheduler.KEY_TIME, "10:00") ?: "10:00"
    }
    var notificationHour by remember {
        mutableStateOf(savedNotificationTime.substringBefore(":").padStart(2, '0'))
    }
    var notificationMinute by remember {
        mutableStateOf(savedNotificationTime.substringAfter(":", "00").padStart(2, '0'))
    }
    var notificationLimit by remember {
        mutableStateOf(notificationPreferences.getInt("count", 10).toString())
    }
    var notificationStatus by remember { mutableStateOf<String?>(null) }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        notificationStatus = if (granted) {
            "通知設定を保存し、アプリ通知を有効にしました"
        } else {
            "設定は保存しました。端末通知を使うには通知権限を許可してください"
        }
    }

    BackHandler {
        when {
            settingsPage == "sort_manual" && sortCategory != null -> sortCategory = null
            settingsPage == "expect_manual" && expectationCategory != null -> expectationCategory = null
            settingsPage != initialPage -> settingsPage = initialPage
            else -> onBack()
        }
    }

    LaunchedEffect(initialSession) {
        if (initialSession != null) {
            cloudSession = initialSession
            cloudStatus = "メール確認が完了しました。クラウド設定を保存できます。"
            requestedBacktest = runCatching {
                withContext(Dispatchers.IO) { cloud.loadLatestBacktest(initialSession) }
            }.getOrNull()
        }
    }

    fun currentPreference(): CloudPreference {
        val loaded = options
        val resolvedHoldingDays = holdingDays.toIntOrNull()
            ?: throw IllegalArgumentException("保有営業日数を入力してください")
        require(resolvedHoldingDays in 1..1000) { "検証期間は1～1000営業日で入力してください" }
        val conditions = loaded?.manualFields?.mapNotNull { field ->
            manualValues[field.field]?.toDoubleOrNull()?.let { value ->
                ManualCondition(
                    field.field,
                    manualOperators[field.field] ?: field.defaultOperator,
                    value,
                )
            }
        }.orEmpty()
        val expectationConditions = loaded?.manualFields?.mapNotNull { field ->
            expectationManualValues[field.field]?.toDoubleOrNull()?.let { value ->
                ManualCondition(
                    field.field,
                    expectationManualOperators[field.field] ?: field.defaultOperator,
                    value,
                )
            }
        }.orEmpty()
        val resolvedTarget = targetReturnPercent.toDoubleOrNull()
            ?: throw IllegalArgumentException("目標騰落率を入力してください")
        require(resolvedTarget > 0.0 && resolvedTarget <= 100.0) {
            "目標騰落率は0より大きく100以下で入力してください"
        }
        val resolvedEvaluationMode = when {
            expectationMode == "manual" && expectationConditions.isEmpty() &&
                evaluationMode in setOf("condition_exit", "period_end") -> "period_end"
            evaluationMode == "period_end" -> "condition_exit"
            else -> evaluationMode
        }
        return CloudPreference(
            mode = mode,
            genreId = genreId,
            manualLogic = "all",
            manualConditions = if (mode == "manual") conditions else emptyList(),
            holdingDays = resolvedHoldingDays,
            expectationMode = expectationMode,
            expectationGenreId = expectationGenreId,
            expectationManualLogic = "all",
            expectationManualConditions =
                if (expectationMode == "manual") expectationConditions else emptyList(),
            tradeDirection = tradeDirection,
            evaluationMode = resolvedEvaluationMode,
            targetReturnPercent = resolvedTarget,
        )
    }

    fun saveNotificationSettings(): Boolean {
        focusManager.clearFocus(force = true)
        val hour = notificationHour.toIntOrNull()
        val minute = notificationMinute.toIntOrNull()
        val count = notificationLimit.toIntOrNull()
        if (hour == null || hour !in 0..23 || minute == null || minute !in 0..59 ||
            count == null || count !in 1..30
        ) {
            notificationStatus = "時・分・件数を正しく入力してください"
            cloudStatus = notificationStatus
            scope.launch { snackbarHostState.showSnackbar(notificationStatus!!) }
            return false
        }
        val normalizedTime = "%02d:%02d".format(hour, minute)
        notificationHour = "%02d".format(hour)
        notificationMinute = "%02d".format(minute)
        notificationPreferences.edit()
            .putString(NotificationScheduler.KEY_TIME, normalizedTime)
            .putInt(NotificationScheduler.KEY_COUNT, count)
            .remove("line")
            .remove("app")
            .apply()
        NotificationScheduler.schedule(context, normalizedTime)
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            notificationStatus = "通知設定を保存し、アプリ通知を予約しました"
        }
        scope.launch { snackbarHostState.showSnackbar("通知設定を保存しました ✓") }
        return true
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
                .onSuccess {
                    cloudStatus = "すべての設定を保存しました"
                    snackbarHostState.showSnackbar("設定を保存しました ✓")
                }
                .onFailure {
                    cloudStatus = "クラウドエラー: ${it.message ?: "保存できませんでした"}"
                    snackbarHostState.showSnackbar("保存できませんでした")
                }
            cloudBusy = false
        }
    }

    fun triggerSave() {
        focusManager.clearFocus(force = true)
        if (!saveNotificationSettings()) return
        when {
            !cloud.isConfigured -> cloudStatus = "Supabaseの公開設定が未登録です"
            cloudSession == null -> {
                loginPurpose = "save"
                loginError = null
                showLogin = true
            }
            else -> saveToCloud(cloudSession!!)
        }
    }

    fun loadCloudResults(session: SupabaseSession) {
        cloudBusy = true
        cloudStatus = null
        scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    cloud.loadLatestRun(session) to cloud.loadLatestResults(session)
                }
            }
                .onSuccess { (run, results) ->
                    cloudRun = run
                    cloudResults = results
                    cloudStatus = if (run == null) {
                        "クラウド結果はまだありません"
                    } else {
                        "${run.screeningDate} の処理完了（該当${run.hitCount}件）"
                    }
                }
                .onFailure { cloudStatus = "クラウドエラー: ${it.message ?: "読み込めませんでした"}" }
            cloudBusy = false
        }
    }
    LaunchedEffect(Unit) {
        runCatching { withContext(Dispatchers.IO) { ApiClient().screeningOptions() } }
            .onSuccess { loaded ->
                options = loaded
                genreId = loaded.genres.firstOrNull()?.id
                expectationGenreId = loaded.genres.firstOrNull()?.id
            }
            .onFailure {
                val loaded = jp.stockai.navigator.builtInScreeningOptions()
                localApiAvailable = false
                options = loaded
                genreId = loaded.genres.firstOrNull()?.id
                expectationGenreId = loaded.genres.firstOrNull()?.id
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
                    manualOperators.clear()
                    saved.manualConditions.forEach {
                        manualValues[it.field] = it.value.toString()
                        manualOperators[it.field] = it.operator
                    }
                    expectationMode = saved.expectationMode
                    expectationGenreId = saved.expectationGenreId
                    expectationManualValues.clear()
                    expectationManualOperators.clear()
                    saved.expectationManualConditions.forEach {
                        expectationManualValues[it.field] = it.value.toString()
                        expectationManualOperators[it.field] = it.operator
                    }
                    tradeDirection = saved.tradeDirection
                    evaluationMode = when {
                        saved.expectationMode == "manual" &&
                            saved.expectationManualConditions.isEmpty() &&
                            saved.evaluationMode in setOf("condition_exit", "period_end") ->
                            "period_end"
                        saved.evaluationMode == "period_end" -> "condition_exit"
                        else -> saved.evaluationMode
                    }
                    targetReturnPercent = saved.targetReturnPercent.toString()
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
                            ManualCondition(
                                field.field,
                                manualOperators[field.field] ?: field.defaultOperator,
                                value,
                            )
                        }
                    }
                    if (conditions.isEmpty()) emptyList() else ApiClient().manualPreview(conditions)
                }
            }
        }
            .onSuccess { hits = it }.onFailure { error = it.message }
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
        TopAppBar(
            title = {
                Text(
                    when (settingsPage) {
                        "home" -> "設定"
                        "sort_mode", "sort_auto", "sort_manual" -> "ソート条件"
                        "expect_mode", "expect_auto", "expect_manual" -> "期待値条件"
                        "notifications" -> "通知設定"
                        else -> "指定銘柄分析"
                    }
                )
            },
            navigationIcon = {
                TextButton(onClick = {
                    when {
                        settingsPage == "sort_manual" && sortCategory != null ->
                            sortCategory = null
                        settingsPage == "expect_manual" && expectationCategory != null ->
                            expectationCategory = null
                        settingsPage == initialPage -> onBack()
                        else -> settingsPage = initialPage
                    }
                }) { Text("戻る") }
            },
            actions = {
                if (settingsPage != "home" && settingsPage != "stock") {
                    TextButton(
                        enabled = !cloudBusy,
                        onClick = {
                            if (settingsPage == "notifications") {
                                saveNotificationSettings()
                            } else {
                                triggerSave()
                            }
                        },
                    ) { Text("保存") }
                }
                TextButton(onClick = { refreshToken++ }) { Text("更新") }
            },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            if (settingsPage == "home") item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PanelButton("✓", if (cloudBusy) "保存中" else "すべての設定を保存",
                        Modifier.fillMaxWidth().height(120.dp)) {
                        if (!cloudBusy) triggerSave()
                    }
                    PanelButton("⇅", "ソート条件",
                        Modifier.fillMaxWidth().height(120.dp)) { settingsPage = "sort_mode" }
                    PanelButton("◎", "期待値条件",
                        Modifier.fillMaxWidth().height(120.dp)) { settingsPage = "expect_mode" }
                    PanelButton("♢", "通知設定",
                        Modifier.fillMaxWidth().height(120.dp)) { settingsPage = "notifications" }
                }
            }
            if (settingsPage == "sort_mode") item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PanelButton("A", "オート",
                        Modifier.fillMaxWidth().height(160.dp)) {
                        mode = "auto"
                        settingsPage = "sort_auto"
                    }
                    PanelButton("M", "マニュアル",
                        Modifier.fillMaxWidth().height(160.dp)) {
                        mode = "manual"
                        sortCategory = null
                        settingsPage = "sort_manual"
                    }
                }
            }
            if (settingsPage == "sort_auto") {
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
            }
            if (settingsPage == "sort_manual" && sortCategory == null) item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PanelButton("⌁", "テクニカル",
                        Modifier.fillMaxWidth().height(160.dp)) { sortCategory = "technical" }
                    PanelButton("￥", "ファンダメンタル",
                        Modifier.fillMaxWidth().height(160.dp)) { sortCategory = "fundamental" }
                }
            }
            if (settingsPage == "sort_manual" && sortCategory != null) {
                item {
                    Text(
                        "${if (sortCategory == "technical") "テクニカル" else "ファンダメンタル"}条件（入力項目をANDで使用）",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (sortCategory == "technical") {
                        Text(
                            "短期・標準・長期は別々の条件として入力できます。空欄の期間は判定に使用しません。",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                if (sortCategory == "technical") {
                    listOf("daily" to "日足", "weekly" to "週足", "monthly" to "月足").forEach { (prefix, label) ->
                        item {
                            ConditionFieldsPanel(
                                label,
                                options?.manualFields.orEmpty().filter { it.field.startsWith("$prefix.") },
                                manualValues,
                                manualOperators,
                                expandedGroups["sort_$prefix"] == true,
                            ) {
                                expandedGroups["sort_$prefix"] =
                                    expandedGroups["sort_$prefix"] != true
                            }
                        }
                    }
                } else {
                    item {
                        ConditionFieldsPanel(
                            "ファンダメンタル",
                            options?.manualFields.orEmpty().filter { it.category == "fundamental" },
                            manualValues,
                            manualOperators,
                            expandedGroups["sort_fundamental"] == true,
                        ) {
                            expandedGroups["sort_fundamental"] =
                                expandedGroups["sort_fundamental"] != true
                        }
                    }
                }
                item { Button(onClick = { refreshToken++ }) { Text("条件をプレビュー") } }
            }
            if (settingsPage == "expect_mode") item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PanelButton("A", "オート",
                        Modifier.fillMaxWidth().height(160.dp)) {
                        expectationMode = "auto"
                        settingsPage = "expect_auto"
                    }
                    PanelButton("M", "マニュアル",
                        Modifier.fillMaxWidth().height(160.dp)) {
                        expectationMode = "manual"
                        expectationCategory = null
                        settingsPage = "expect_manual"
                    }
                }
            }
            if (settingsPage in setOf("expect_auto", "expect_manual")) item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("売買方向", style = MaterialTheme.typography.titleMedium)
                    FilterChip(
                        selected = tradeDirection == "long",
                        onClick = { tradeDirection = "long" },
                        label = { Text("低い時に買う → 高い時に売る") },
                    )
                    FilterChip(
                        selected = tradeDirection == "short",
                        onClick = { tradeDirection = "short" },
                        label = { Text("高い時に売る → 低い時に買い戻す") },
                    )
                    Text(
                        if (tradeDirection == "long") {
                            "ソート条件を買いの入口、期待値条件を売りの出口として検証します。"
                        } else {
                            "ソート条件を空売りの入口、期待値条件を買い戻しの出口として検証します。"
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text("期待値の判定方式", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "営業日数は条件を監視する最大期間です。条件が設定されている場合は" +
                            "期間内の初回達成時に決済し、条件がない場合だけ期間最終日に決済します。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    FilterChip(
                        selected = evaluationMode == "within_period_up",
                        onClick = { evaluationMode = "within_period_up" },
                        label = { Text("期間内に配信価格を一度でも上回る／下回る") },
                    )
                    FilterChip(
                        selected = evaluationMode == "target_return",
                        onClick = { evaluationMode = "target_return" },
                        label = { Text("期間内に目標騰落率へ到達") },
                    )
                    FilterChip(
                        selected = evaluationMode == "condition_exit",
                        onClick = { evaluationMode = "condition_exit" },
                        label = { Text("期待値条件へ到達") },
                    )
                    if (evaluationMode == "target_return") {
                        OutlinedTextField(
                            value = targetReturnPercent,
                            onValueChange = {
                                targetReturnPercent = it.filter { char ->
                                    char.isDigit() || char == '.'
                                }.take(6)
                            },
                            label = { Text("目標騰落率（%）") },
                            supportingText = {
                                Text("買いは値上がり率、空売りは値下がり率として判定します。")
                            },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                        )
                    }
                    if (tradeDirection == "short") {
                        Text(
                            "空売り可能銘柄の制限、貸株料、逆日歩、売買手数料、スリッページは現在の参考計算に含みません。",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    OutlinedTextField(
                        value = holdingDays,
                        onValueChange = { holdingDays = it.filter(Char::isDigit).take(4) },
                        label = { Text("検証期間（営業日）") },
                        supportingText = {
                            Text("選択した結果が何日以内に起きるかを調べます（1～1000営業日）。")
                        },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                }
            }
            if (settingsPage == "expect_auto") {
                options?.genres?.forEach { genre ->
                    item {
                        FilterChip(
                            selected = expectationGenreId == genre.id,
                            onClick = { expectationGenreId = genre.id },
                            label = { Text(genre.label) },
                        )
                        Text(genre.description, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            if (settingsPage == "expect_manual") {
                if (expectationCategory == null) item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        PanelButton("⌁", "テクニカル",
                            Modifier.fillMaxWidth().height(160.dp)) {
                            expectationCategory = "technical"
                        }
                        PanelButton("￥", "ファンダメンタル",
                            Modifier.fillMaxWidth().height(160.dp)) {
                            expectationCategory = "fundamental"
                        }
                    }
                }
            }
            if (settingsPage == "expect_manual" && expectationCategory != null) {
                item {
                    Text(
                        "${if (expectationCategory == "technical") "テクニカル" else "ファンダメンタル"}期待値条件（入力項目をANDで使用）",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (expectationCategory == "technical") {
                        Text(
                            "期間内に達成させたい短期・標準・長期の条件だけ入力してください。",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                if (expectationCategory == "technical") {
                    listOf("daily" to "日足", "weekly" to "週足", "monthly" to "月足").forEach { (prefix, label) ->
                        item {
                            ConditionFieldsPanel(
                                label,
                                options?.manualFields.orEmpty().filter { it.field.startsWith("$prefix.") },
                                expectationManualValues,
                                expectationManualOperators,
                                expandedGroups["expect_$prefix"] == true,
                            ) {
                                expandedGroups["expect_$prefix"] =
                                    expandedGroups["expect_$prefix"] != true
                            }
                        }
                    }
                } else {
                    item {
                        ConditionFieldsPanel(
                            "ファンダメンタル",
                            options?.manualFields.orEmpty().filter { it.category == "fundamental" },
                            expectationManualValues,
                            expectationManualOperators,
                            expandedGroups["expect_fundamental"] == true,
                        ) {
                            expandedGroups["expect_fundamental"] =
                                expandedGroups["expect_fundamental"] != true
                        }
                    }
                }
            }
            if (settingsPage == "stock") item {
                Spacer(Modifier.height(24.dp))
                Text("指定銘柄の期待値分析", style = MaterialTheme.typography.titleMedium)
                Text(
                    "現在の期待値条件を保存し、最新チャートを使ったバックテストをクラウドへ依頼します。",
                    style = MaterialTheme.typography.bodySmall,
                )
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = {
                            expectationMode = "manual"
                            expectationCategory = "technical"
                            settingsPage = "expect_manual"
                        },
                        modifier = Modifier.weight(1f),
                    ) { Text("テクニカル条件") }
                    Button(
                        onClick = {
                            expectationMode = "manual"
                            expectationCategory = "fundamental"
                            settingsPage = "expect_manual"
                        },
                        modifier = Modifier.weight(1f),
                    ) { Text("ファンダメンタル条件") }
                }
                OutlinedTextField(
                    value = specifiedCode,
                    onValueChange = {
                        specifiedCode = it.uppercase().filter(Char::isLetterOrDigit).take(5)
                    },
                    label = { Text("銘柄コード") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                Button(
                    enabled = !cloudBusy && specifiedCode.length >= 4,
                    onClick = {
                        val session = cloudSession
                        if (session == null) {
                            cloudStatus = "ログインが必要です"
                        } else {
                            cloudBusy = true
                            cloudStatus = null
                            scope.launch {
                                runCatching {
                                    val preference = currentPreference()
                                    withContext(Dispatchers.IO) {
                                        cloud.savePreference(session, preference)
                                        cloud.requestBacktest(session, specifiedCode)
                                    }
                                }.onSuccess {
                                    cloudStatus = "バックテストを受け付けました。次回クラウド更新後に結果を確認できます。"
                                    requestedBacktest = RequestedBacktest(
                                        specifiedCode, "pending", null, null, emptyList(), null
                                    )
                                }.onFailure {
                                    cloudStatus = "クラウドエラー: ${it.message}"
                                }
                                cloudBusy = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("この銘柄をバックテスト") }
                TextButton(
                    enabled = !cloudBusy,
                    onClick = {
                        val session = cloudSession ?: return@TextButton
                        scope.launch {
                            requestedBacktest = runCatching {
                                withContext(Dispatchers.IO) { cloud.loadLatestBacktest(session) }
                            }.getOrNull()
                        }
                    },
                ) { Text("分析結果を更新") }
                requestedBacktest?.let { result ->
                    Text("銘柄: ${result.code} / 状態: ${backtestStatusLabel(result.status)}")
                    result.score?.let { Text("期待値スコア: ${String.format("%.1f", it)}") }
                    result.comment?.let { Text(it) }
                    result.errorMessage?.let {
                        Text(it, color = MaterialTheme.colorScheme.error)
                    }
                    if (result.prices.size >= 2) {
                        PriceChart(
                            prices = result.prices,
                            modifier = Modifier.fillMaxWidth().height(220.dp),
                        )
                    }
                }
            }
            if (settingsPage == "notifications") item {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("アプリ通知の設定", style = MaterialTheme.typography.titleMedium)
                    Text("LINE配信は使用しません。")
                    Text(
                        "指定時刻以降、当日のクラウド処理が完了してから通知します。" +
                            "処理中の場合は10分ごとに自動確認します。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        "保存中の予定: 平日 ${
                            notificationHour.ifBlank { "--" }
                        }:${
                            notificationMinute.ifBlank { "--" }
                        } 頃／最大${notificationLimit.ifBlank { "未設定" }}件",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        "前回処理: ${
                            notificationPreferences.getString(
                                NotificationScheduler.KEY_LAST_STATUS,
                                "未実行",
                            )
                        }／${
                            notificationPreferences.getString(
                                NotificationScheduler.KEY_LAST_RUN_AT,
                                "日時なし",
                            )
                        }",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text("通知時刻", style = MaterialTheme.typography.labelLarge)
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        OutlinedTextField(
                            value = notificationHour,
                            onValueChange = {
                                notificationHour = it.filter(Char::isDigit).take(2)
                            },
                            label = { Text("時") },
                            placeholder = { Text("10") },
                            suffix = { Text("時") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true,
                            modifier = Modifier.width(125.dp),
                        )
                        Text(
                            "：",
                            style = MaterialTheme.typography.headlineSmall,
                            modifier = Modifier.padding(horizontal = 8.dp),
                        )
                        OutlinedTextField(
                            value = notificationMinute,
                            onValueChange = {
                                notificationMinute = it.filter(Char::isDigit).take(2)
                            },
                            label = { Text("分") },
                            placeholder = { Text("00") },
                            suffix = { Text("分") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true,
                            modifier = Modifier.width(125.dp),
                        )
                    }
                    Text(
                        "例：午前10時なら「10 時 ： 00 分」",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedTextField(
                        value = notificationLimit,
                        onValueChange = {
                            notificationLimit = it.filter(Char::isDigit).take(2)
                        },
                        label = { Text("通知件数上限（1～30件）") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = {
                            saveNotificationSettings()
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("通知設定を保存") }
                    OutlinedButton(
                        onClick = {
                            if (Build.VERSION.SDK_INT >= 33 &&
                                context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                                PackageManager.PERMISSION_GRANTED
                            ) {
                                notificationStatus =
                                    "通知を許可した後、もう一度テスト通知を押してください"
                                notificationPermissionLauncher.launch(
                                    Manifest.permission.POST_NOTIFICATIONS
                                )
                            } else {
                                NotificationScheduler.showImmediateTest(context)
                                notificationStatus = "テスト通知を送信しました"
                                scope.launch {
                                    snackbarHostState.showSnackbar("テスト通知を送信しました ✓")
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("この端末でテスト通知") }
                    notificationStatus?.let { Text(it) }
                }
            }
            if (settingsPage in setOf("sort_mode", "sort_auto", "sort_manual")) item {
                Spacer(Modifier.height(16.dp))
                Button(
                    enabled = !cloudBusy,
                    onClick = { triggerSave() },
                    modifier = Modifier.fillMaxWidth().height(56.dp),
                ) {
                    Text(if (cloudBusy) "保存中" else "ソート条件を保存")
                }
            }
            if (settingsPage in setOf("expect_mode", "expect_auto", "expect_manual")) item {
                Spacer(Modifier.height(16.dp))
                Button(
                    enabled = !cloudBusy,
                    onClick = { triggerSave() },
                    modifier = Modifier.fillMaxWidth().height(56.dp),
                ) {
                    Text(if (cloudBusy) "保存中" else "期待値条件を保存")
                }
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
            if (settingsPage in setOf("sort_auto", "sort_manual")) item {
                Spacer(Modifier.height(16.dp))
                Text("条件プレビュー", style = MaterialTheme.typography.titleMedium)
            }
            if (settingsPage in setOf("sort_auto", "sort_manual")) {
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
private fun OperationsScreen(
    favoriteCount: Int,
    onBack: () -> Unit,
    onWatchlist: () -> Unit,
) {
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
            item {
                ElevatedCard(
                    Modifier
                        .fillMaxWidth()
                        .clickable(onClick = onWatchlist)
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("監視対象", style = MaterialTheme.typography.titleMedium)
                            Text("${favoriteCount}銘柄を端末で監視登録中")
                        }
                        Text("開く")
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
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
private fun WatchlistScreen(
    session: SupabaseSession,
    favorites: List<FavoriteStock>,
    onBack: () -> Unit,
    onSelect: (CloudScreeningResult) -> Unit,
    onRemove: (FavoriteStock) -> Unit,
) {
    val cloud = remember { SupabaseClient() }
    var latestResults by remember { mutableStateOf<List<CloudScreeningResult>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(session.userId) {
        runCatching {
            withContext(Dispatchers.IO) { cloud.loadLatestResults(session) }
        }.onSuccess {
            latestResults = it
        }.onFailure {
            error = it.message
        }
    }
    val resultByCode = latestResults.associateBy { it.code }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("監視対象") },
            navigationIcon = { TextButton(onClick = onBack) { Text("戻る") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(16.dp)) {
            error?.let {
                item {
                    Text(
                        "監視情報を取得できません: $it",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            if (favorites.isEmpty()) {
                item {
                    Text("監視対象はありません。配信結果の「☆ 監視」から追加できます。")
                }
            }
            items(favorites, key = { it.code }) { favorite ->
                val cloudResult = resultByCode[favorite.code]
                ListItem(
                    headlineContent = { Text(favorite.code) },
                    supportingContent = {
                        Text(
                            favorite.companyName
                                ?: cloudResult?.companyName
                                ?: "銘柄情報を確認"
                        )
                    },
                    trailingContent = {
                        TextButton(onClick = { onRemove(favorite) }) {
                            Text("解除")
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = cloudResult != null) {
                            cloudResult?.let(onSelect)
                        },
                )
                if (cloudResult == null) {
                    Text(
                        "最新の配信結果に詳細がありません",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
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

private fun formatConditionSummary(summary: String): String {
    val labels = mapOf(
        "daily.rsi_14" to "日足RSI（標準・14本）",
        "weekly.rsi_14" to "週足RSI（標準・14本）",
        "monthly.rsi_14" to "月足RSI（標準・14本）",
        "daily.close" to "日足終値",
        "daily.sma_25" to "25日移動平均",
        "daily.sma_75" to "75日移動平均",
        "daily.macd" to "日足MACD（標準・12/26/9本）",
        "daily.macd_signal" to "日足MACDシグナル（標準・12/26/9本）",
        "daily.macd_histogram" to "日足MACDヒストグラム（標準・12/26/9本）",
        "daily.adx_14" to "日足ADX",
        "daily.stoch_k" to "日足ストキャスティクス%K（標準・14/3本）",
        "daily.stoch_d" to "日足ストキャスティクス%D（標準・14/3本）",
        "daily.bb_percent_b" to "ボリンジャー%B",
        "daily.atr_14_percent" to "ATR比率",
        "daily.price_vs_sma_5_percent" to "5日移動平均乖離率",
        "daily.price_vs_sma_25_percent" to "25日移動平均乖離率",
        "daily.price_vs_sma_75_percent" to "75日移動平均乖離率",
        "daily.price_vs_sma_200_percent" to "200日移動平均乖離率",
        "daily.return_5_percent" to "5日騰落率",
        "daily.return_20_percent" to "20日騰落率",
        "daily.return_60_percent" to "60日騰落率",
        "daily.volume_ratio_20" to "20日平均出来高比",
        "fundamental.per" to "PER",
        "fundamental.pbr" to "PBR",
        "fundamental.roe" to "ROE",
        "fundamental.roa" to "ROA",
        "fundamental.equity_ratio" to "自己資本比率",
        "fundamental.dividend_yield" to "配当利回り",
        "fundamental.operating_cash_flow" to "営業CF",
        "fundamental.operating_margin" to "営業利益率",
    )
    return runCatching {
        val rule = JSONObject(summary)
        val logic = when {
            rule.has("all") -> "all"
            rule.has("any") -> "any"
            else -> return@runCatching summary
        }
        val conditions = rule.getJSONArray(logic)
        val parts = (0 until conditions.length()).map { index ->
            val condition = conditions.getJSONObject(index)
            val field = condition.optString("field")
            val operator = when (condition.optString("operator")) {
                "<=" -> "以下"
                ">=" -> "以上"
                "<" -> "未満"
                ">" -> "超"
                else -> condition.optString("operator")
            }
            val right = if (condition.has("value_from")) {
                val source = condition.optString("value_from")
                labels[source] ?: readableIndicatorName(source)
            } else {
                condition.opt("value")?.toString().orEmpty()
            }
            "${labels[field] ?: readableIndicatorName(field)} $operator $right"
        }
        parts.joinToString(if (logic == "all") " かつ " else " または ")
    }.getOrDefault(summary)
}

private fun Double?.percentValue(includeSign: Boolean = true): String {
    if (this == null || !isFinite()) return "—"
    val pattern = if (includeSign) "%+.1f%%" else "%.1f"
    return String.format(pattern, this)
}

private fun analysisSection(comment: String?, title: String): String? {
    if (comment.isNullOrBlank()) return null
    val marker = "【$title】"
    val start = comment.indexOf(marker)
    if (start < 0) return null
    val bodyStart = start + marker.length
    val next = comment.indexOf("【", bodyStart)
    return comment.substring(bodyStart, if (next >= 0) next else comment.length).trim()
}

private fun screeningRunStatus(hitCount: Int): String =
    if (hitCount == 0) "正常終了・条件一致0件" else "正常終了"

private fun formatJst(instant: Instant): String =
    JST_DATE_TIME_FORMATTER.format(instant.atZone(JAPAN_ZONE))

private val JAPAN_ZONE: ZoneId = ZoneId.of("Asia/Tokyo")
private val JST_DATE_TIME_FORMATTER: DateTimeFormatter =
    DateTimeFormatter.ofPattern("yyyy/MM/dd HH:mm:ss 'JST'")

private fun tradeDirectionLabel(direction: String): String =
    if (direction == "short") {
        "高い時に売る → 低い時に買い戻す"
    } else {
        "低い時に買う → 高い時に売る"
    }

private fun evaluationModeLabel(mode: String, targetReturnPercent: Double): String =
    when (mode) {
        "period_end" -> "他条件なし：期間最終日に決済"
        "within_period_up" -> "最大期間内に配信価格を上回る／下回る"
        "target_return" -> "最大期間内に目標騰落率${String.format("%.1f", targetReturnPercent)}%到達"
        else -> "最大期間内に期待値条件を達成した時点で決済"
    }

private fun readableIndicatorName(field: String): String {
    val prefix = when {
        field.startsWith("daily.") -> "日足"
        field.startsWith("weekly.") -> "週足"
        field.startsWith("monthly.") -> "月足"
        field.startsWith("fundamental.") -> ""
        else -> ""
    }
    val key = field.substringAfter('.')
    val name = when {
        key.startsWith("rsi_") -> "RSI（${key.removePrefix("rsi_")}本）"
        key == "macd" -> "MACD（標準・12/26/9本）"
        key == "macd_histogram" -> "MACDヒストグラム（標準・12/26/9本）"
        key.startsWith("macd_histogram_") -> "MACDヒストグラム（${macdPeriodLabel(key.removePrefix("macd_histogram_"))}）"
        key.startsWith("macd_") -> "MACD（${macdPeriodLabel(key.removePrefix("macd_"))}）"
        key == "stoch_k" -> "ストキャスティクス%K（標準・14/3本）"
        key == "stoch_d" -> "ストキャスティクス%D（標準・14/3本）"
        key.startsWith("stoch_k_") -> "ストキャスティクス%K（${stochasticPeriodLabel(key.removePrefix("stoch_k_"))}）"
        key.startsWith("stoch_d_") -> "ストキャスティクス%D（${stochasticPeriodLabel(key.removePrefix("stoch_d_"))}）"
        key == "adx_14" -> "ADX"
        key == "bb_percent_b" -> "ボリンジャー%B"
        key == "atr_14_percent" -> "ATR比率"
        key.startsWith("price_vs_sma_") -> key
            .removePrefix("price_vs_sma_").removeSuffix("_percent") + "本移動平均乖離率"
        key.startsWith("return_") -> key
            .removePrefix("return_").removeSuffix("_percent") + "本騰落率"
        key == "volume_ratio_20" -> "20本平均出来高比"
        else -> key
    }
    return prefix + name
}

private fun macdPeriodLabel(periods: String): String = when (periods) {
    "5_25_9" -> "短期・5/25/9本"
    "12_26_9" -> "標準・12/26/9本"
    "25_75_14" -> "長期・25/75/14本"
    else -> periods.replace('_', '/') + "本"
}

private fun stochasticPeriodLabel(periods: String): String = when (periods) {
    "9_3" -> "短期・9/3本"
    "14_3" -> "標準・14/3本"
    else -> periods.replace('_', '/') + "本"
}

private fun manualFieldGroup(field: String): String {
    val key = field.substringAfter('.')
    return when {
        key.startsWith("rsi_") -> "RSI"
        key.startsWith("macd") -> "MACD"
        key.startsWith("stoch_") -> "ストキャスティクス"
        key.startsWith("price_vs_sma_") -> "移動平均乖離率"
        key.startsWith("adx_") -> "トレンド強度（ADX）"
        key.startsWith("bb_") -> "ボリンジャーバンド"
        key.startsWith("atr_") -> "値動き幅（ATR）"
        key.startsWith("return_") -> "騰落率"
        key.startsWith("volume_ratio_") -> "出来高"
        else -> "その他"
    }
}

private fun backtestStatusLabel(status: String): String = when (status) {
    "pending" -> "受付済み"
    "processing" -> "計算中"
    "complete" -> "完了"
    "failed" -> "失敗"
    else -> status
}
