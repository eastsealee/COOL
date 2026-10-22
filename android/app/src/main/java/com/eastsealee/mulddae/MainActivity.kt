package com.eastsealee.mulddae

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsets
import android.Manifest
import android.content.pm.PackageManager
import android.webkit.CookieManager
import android.webkit.GeolocationPermissions
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView

/**
 * 물때 시계 앱 — Streamlit 앱(BuildConfig.APP_URL)을 전체 화면으로 여는 WebView 앱.
 * - 처음엔 물때 시계, 이후엔 마지막으로 보던 화면(항구 포함)으로 다시 열림
 * - 바다타임·블로그·예약 사이트 같은 바깥 링크는 휴대폰 기본 브라우저로 엶
 * - 인터넷이 끊기면 '다시 시도' 화면
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private lateinit var bar: ProgressBar
    private lateinit var errorView: LinearLayout
    private var geoPending: Pair<String, GeolocationPermissions.Callback>? = null   // 위치 권한 묻는 중인 웹 요청
    private var splash: WebView? = null                 // 시작화면 (assets/splash.html)
    private val splashStart = System.currentTimeMillis()
    private var splashClosing = false
    private val prefs by lazy { getSharedPreferences("mulddae", MODE_PRIVATE) }

    private val bg = Color.parseColor("#08131D")
    private val sea = Color.parseColor("#4CC3E6")

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this).apply { setBackgroundColor(bg) }

        web = WebView(this).apply {
            setBackgroundColor(bg)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.loadWithOverviewMode = true
            settings.useWideViewPort = true
            settings.textZoom = 100                       // 휴대폰 글자 크기 설정과 상관없이 화면 비율 유지
            settings.setSupportZoom(true)                 // 두 손가락으로 확대·축소
            settings.builtInZoomControls = true
            settings.displayZoomControls = false          // +/- 버튼은 숨김
            settings.userAgentString = settings.userAgentString + " MulddaeApp/1"   // 물때 시계 화면이 앱 모양으로 바뀌는 표시
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.setSupportMultipleWindows(false)      // 새 창 링크도 아래 규칙으로 처리
            settings.mediaPlaybackRequiresUserGesture = true
            webViewClient = Client()
            @Suppress("DEPRECATION") settings.setGeolocationEnabled(true)
            webChromeClient = object : WebChromeClient() {
                // 채비 계산기 'GPS 켜기' → 휴대폰 위치 권한을 묻고, 허용하면 웹 화면에 위치를 넘겨줌
                override fun onGeolocationPermissionsShowPrompt(origin: String, callback: GeolocationPermissions.Callback) {
                    if (hasLocation()) { callback.invoke(origin, true, false); return }
                    geoPending = origin to callback
                    requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,
                        Manifest.permission.ACCESS_COARSE_LOCATION), REQ_LOCATION)
                }

                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    bar.progress = newProgress
                    bar.visibility = if (newProgress < 100) View.VISIBLE else View.GONE
                }
            }
        }
        // 두 손가락 확대 예비 장치: 화면이 스스로 확대되지 않으면 손가락 벌린 만큼 직접 확대
        val pinch = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            var startScale = 1f
            var factor = 1f
            override fun onScaleBegin(d: ScaleGestureDetector): Boolean {
                @Suppress("DEPRECATION") startScale = web.scale
                factor = 1f
                return true
            }
            override fun onScale(d: ScaleGestureDetector): Boolean { factor *= d.scaleFactor; return true }
            override fun onScaleEnd(d: ScaleGestureDetector) {
                @Suppress("DEPRECATION") val now = web.scale
                if (kotlin.math.abs(now - startScale) < 0.01f && kotlin.math.abs(factor - 1f) > 0.05f) {
                    web.zoomBy(factor.coerceIn(0.2f, 5f))
                }
            }
        })
        web.setOnTouchListener { _, e: MotionEvent -> pinch.onTouchEvent(e); false }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(web, true)
        }

        bar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progressTintList = android.content.res.ColorStateList.valueOf(sea)
        }

        errorView = buildErrorView()

        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(bar, FrameLayout.LayoutParams(MATCH_PARENT, dp(3)).apply { gravity = Gravity.TOP })
        root.addView(errorView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        // 시작화면: 물속에서 주꾸미·갑오징어가 둥실거리는 그림. 물때 시계가 다 뜨면 서서히 사라짐
        if (savedInstanceState == null) {
            splash = WebView(this).apply {
                setBackgroundColor(Color.parseColor("#071520"))
                settings.javaScriptEnabled = true
                isVerticalScrollBarEnabled = false
                isHorizontalScrollBarEnabled = false
                setOnTouchListener { _, _ -> true }    // 시작화면 동안은 터치 막기
                loadUrl("file:///android_asset/splash.html")
            }
            root.addView(splash, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
            root.postDelayed({ closeSplash() }, 25_000)   // 서버가 너무 늦어도 25초 뒤엔 닫음
        }
        setContentView(root)

        // 안드로이드 15(갤럭시 S25)는 화면 끝까지 그리므로, 상태바·내비게이션바·키보드 높이만큼 비워 둠
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            root.setOnApplyWindowInsetsListener { v, insets ->
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
                v.setPadding(b.left, b.top, b.right, b.bottom)
                WindowInsets.CONSUMED
            }
        }

        if (savedInstanceState != null) web.restoreState(savedInstanceState) else web.loadUrl(startUrl())
    }

    /** 앱은 항상 물때 시계로 시작 — 마지막으로 보던 물때 시계(항구 포함)가 있으면 그 주소 */
    private fun startUrl(): String {
        val last = prefs.getString("last_url", null)
        if (last != null && isDialUrl(Uri.parse(last))) return withEmbed(last)
        return withEmbed(BuildConfig.APP_URL)
    }

    private fun isDialUrl(u: Uri): Boolean =
        isAppUrl(u) && (u.path ?: "").trimEnd('/') == (Uri.parse(BuildConfig.APP_URL).path ?: "").trimEnd('/')

    private fun rememberDial(url: String) {
        if (isDialUrl(Uri.parse(url))) prefs.edit().putString("last_url", url).apply()
    }

    /** Streamlit 머리줄·메뉴를 숨겨 앱처럼 보이게 (?embed=true) */
    private fun withEmbed(url: String): String {
        val u = Uri.parse(url)
        if (u.getQueryParameter("embed") != null) return url
        return u.buildUpon().appendQueryParameter("embed", "true").build().toString()
    }

    private fun isAppUrl(u: Uri): Boolean {
        val host = u.host ?: return false
        val appHost = Uri.parse(BuildConfig.APP_URL).host
        return host == appHost || host.endsWith(".streamlit.app") || host.endsWith("streamlit.io")
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val u = request.url
            if (u.scheme == "http" || u.scheme == "https") {
                if (isAppUrl(u)) return false              // 앱 안에서 계속
            }
            // 바깥 사이트(바다타임, 선상24, 블로그 등)·전화·지도 링크는 휴대폰 앱/브라우저로
            return try {
                startActivity(Intent(Intent.ACTION_VIEW, u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                true
            } catch (e: Exception) {
                true
            }
        }

        override fun onPageFinished(view: WebView, url: String) {
            view.evaluateJavascript(TIDY_JS, null)
            if (isAppUrl(Uri.parse(url))) waitForDialThenCloseSplash()
            rememberDial(url)
        }

        // Streamlit은 화면을 바꿀 때 주소만 바꾸므로 여기서도 기억 (예약조회 등 다른 화면은 기억하지 않음)
        override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean) {
            rememberDial(url)
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame) { errorView.visibility = View.VISIBLE; closeSplash() }
        }
    }

    /** 물때 시계(원) 화면이 실제로 그려질 때까지 기다렸다가 시작화면을 닫음 — 최소 2.2초는 보여줌 */
    private fun waitForDialThenCloseSplash() {
        if (splash == null || splashClosing) return
        val check = object : Runnable {
            var tries = 0
            override fun run() {
                if (splash == null || splashClosing) return
                web.evaluateJavascript(READY_JS) { v ->
                    tries++
                    if (v == "true" || tries > 40) {
                        val wait = (2200 - (System.currentTimeMillis() - splashStart)).coerceAtLeast(0)
                        web.postDelayed({ closeSplash() }, wait + 300)
                    } else web.postDelayed(this, 500)
                }
            }
        }
        web.post(check)
    }

    private fun closeSplash() {
        val s = splash ?: return
        if (splashClosing) return
        splashClosing = true
        s.animate().alpha(0f).setDuration(450).withEndAction {
            (s.parent as? android.view.ViewGroup)?.removeView(s)
            s.destroy()
            splash = null
        }.start()
    }

    private fun buildErrorView(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        setBackgroundColor(bg)
        visibility = View.GONE
        val pad = dp(28)
        setPadding(pad, pad, pad, pad)
        addView(TextView(context).apply {
            text = "물때 시계를 열 수 없습니다"
            setTextColor(Color.WHITE)
            textSize = 19f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        })
        addView(TextView(context).apply {
            text = "인터넷 연결을 확인한 뒤 다시 시도해 주세요."
            setTextColor(Color.parseColor("#A3B6C8"))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(20))
        })
        addView(Button(context).apply {
            text = "다시 시도"
            setOnClickListener {
                errorView.visibility = View.GONE
                web.reload()
            }
        }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
    }

    @Deprecated("뒤로 가기: 앱 안 이전 화면 → 없으면 앱 닫기")
    override fun onBackPressed() {
        if (splash != null) { closeSplash(); return }
        if (errorView.visibility == View.VISIBLE) { errorView.visibility = View.GONE; web.reload(); return }
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    private fun hasLocation() =
        checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_LOCATION) return
        val (origin, cb) = geoPending ?: return
        geoPending = null
        cb.invoke(origin, hasLocation(), false)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onPause() { super.onPause(); web.onPause(); CookieManager.getInstance().flush() }
    override fun onResume() { super.onResume(); web.onResume() }
    override fun onDestroy() { web.destroy(); super.onDestroy() }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    companion object {
        private const val REQ_LOCATION = 7
        /** 물때 시계 원 그림(#dial)이 Streamlit 화면 안 iframe에 그려졌는지 확인 */
        private const val READY_JS = """
(function(){
  function has(doc,d){ if(!doc||d>3) return false;
    try{ if(doc.querySelector('#dial circle')) return true;
      var fs=doc.querySelectorAll('iframe'); for(var i=0;i<fs.length;i++){ try{ if(has(fs[i].contentDocument,d+1)) return true; }catch(e){} } }catch(e){}
    return false; }
  return has(document,0);
})()
"""

        /** Streamlit 머리줄·메뉴 버튼·'Built with Streamlit' 띠를 숨기고 위아래 여백을 줄여 앱처럼 보이게.
         *  앱 화면은 같은 주소 안의 iframe이라 1.5초마다 새로 생긴 화면에도 다시 적용 */
        private const val TIDY_JS = """
(function(){
  var CSS = 'header,[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],' +
    '[data-testid="stSidebarCollapsedControl"],[data-testid="stSidebar"],[data-testid="stStatusWidget"],footer,' +
    '[class*="viewerBadge"],[class*="ViewerBadge"]{display:none!important}' +
    '[data-testid="stMainBlockContainer"],.block-container{padding:0.25rem 0 0.5rem!important;max-width:none!important}' +
    '[data-testid="stAppViewContainer"],[data-testid="stMain"],.stApp,body{background:#08131d!important}' +
    '[data-testid="stCaptionContainer"]{padding:0 14px!important}';
  function tidy(doc){
    try{
      if(!doc||!doc.head) return;
      if(!doc.getElementById('mulddae-app-css')){var s=doc.createElement('style');s.id='mulddae-app-css';s.textContent=CSS;doc.head.appendChild(s);}
      doc.querySelectorAll('a,div,span').forEach(function(el){
        if(el.childElementCount<6 && /Built with Streamlit|Fullscreen/.test(el.textContent||'')){
          var n=el; for(var i=0;i<6&&n&&n!==doc.body;i++){var p=getComputedStyle(n).position; if(p==='fixed'||p==='sticky'){n.style.setProperty('display','none','important');break;} n=n.parentElement;}
        }
      });
      doc.querySelectorAll('iframe').forEach(function(f){try{tidy(f.contentDocument)}catch(e){}});
    }catch(e){}
  }
  // 두 손가락 확대: Streamlit 화면이 확대를 막아 두는 경우(maximum-scale=1 등)가 있어 맨 바깥 화면 설정을 '확대 허용'으로 바꿈
  function zoomable(){
    try{
      var c='width=device-width, initial-scale=1, minimum-scale=1, maximum-scale=5, user-scalable=yes';
      var ms=document.querySelectorAll('meta[name="viewport"]');
      if(!ms.length){var m=document.createElement('meta');m.name='viewport';m.content=c;document.head.appendChild(m);}
      ms.forEach(function(m){if(m.content!==c)m.content=c;});
      ['html','body'].forEach(function(t){var e=document.querySelector(t);if(e)e.style.setProperty('touch-action','manipulation','important');});
    }catch(e){}
  }
  zoomable(); tidy(document);
  if(!window.__mulddaeTidy){window.__mulddaeTidy=setInterval(function(){zoomable();tidy(document)},1500);}
})();
"""
    }
}
