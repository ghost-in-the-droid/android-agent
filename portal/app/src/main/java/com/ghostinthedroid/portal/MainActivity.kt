package com.ghostinthedroid.portal

import android.accessibilityservice.AccessibilityServiceInfo
import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.accessibility.AccessibilityManager
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    // Brand palette (dashboard-theme.md)
    companion object {
        const val BG_BASE   = 0xFF0A0F0C.toInt()
        const val BG_CARD   = 0xFF141E17.toInt()
        const val BORDER    = 0xFF1E2E22.toInt()
        const val TEXT_1    = 0xFFE8EDE9.toInt()
        const val TEXT_2    = 0xFFBEC8C0.toInt()
        const val TEXT_3    = 0xFF8A9A8D.toInt()
        const val TEXT_4    = 0xFF5A6E5E.toInt()
        const val ACCENT    = 0xFF00E5A0.toInt()
        const val RED       = 0xFFEF4444.toInt()
    }

    private lateinit var dotA11y: View
    private lateinit var dotHttp: View
    private lateinit var dotCapture: View
    private lateinit var lblA11y: TextView
    private lateinit var lblHttp: TextView
    private lateinit var lblCapture: TextView
    private lateinit var deviceLine: TextView

    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() { updateStatus(); handler.postDelayed(this, 2000) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = BG_BASE
        window.navigationBarColor = BG_BASE

        val root = ScrollView(this).apply { setBackgroundColor(BG_BASE) }
        val col = column()
        col.setPadding(dp(28), dp(52), dp(28), dp(40))

        // ── Header: ghost icon + title ──
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, dp(32))
        }
        header.addView(ImageView(this).apply {
            setImageResource(R.drawable.ic_ghost)
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply { rightMargin = dp(12) }
        })
        val titleCol = column()
        titleCol.addView(label("Ghost Portal", 24f, ACCENT, true))
        titleCol.addView(label("Companion", 12f, TEXT_4))
        header.addView(titleCol)
        col.addView(header)

        // ── Status ──
        val sc = card()
        sc.addView(section("STATUS"))
        val (r1, d1, l1) = dot("Accessibility"); dotA11y = d1; lblA11y = l1; sc.addView(r1)
        val (r2, d2, l2) = dot("HTTP Server :8080"); dotHttp = d2; lblHttp = l2; sc.addView(r2)
        val (r3, d3, l3) = dot("Screen Capture"); dotCapture = d3; lblCapture = l3; sc.addView(r3)
        col.addView(sc)

        // ── Device ──
        val dc = card()
        dc.addView(section("DEVICE"))
        deviceLine = label("", 13f, TEXT_3)
        dc.addView(deviceLine)
        col.addView(dc)

        // ── Setup buttons ──
        val ac = card()
        ac.addView(section("SETUP"))
        ac.addView(btn("Enable Accessibility", ACCENT) {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        ac.addView(btn("Grant Screen Capture", 0xFF6366F1.toInt()) {
            startActivity(Intent(this, ScreenCaptureActivity::class.java).apply {
                putExtra(ScreenCaptureActivity.EXTRA_SESSION_ID, "manual_grant")
            })
        })
        ac.addView(btn("Start Service", 0xFF22C55E.toInt()) {
            startForegroundService(Intent(this, GhostForegroundService::class.java))
            handler.postDelayed({ updateStatus() }, 500)
        })
        col.addView(ac)

        // ── Debug info button (subtle, at bottom) ──
        col.addView(Space(this).also { it.layoutParams = LinearLayout.LayoutParams(-1, dp(20)) })
        col.addView(label("Tap below to copy debug info", 10f, TEXT_4).also { it.gravity = Gravity.CENTER })
        col.addView(Space(this).also { it.layoutParams = LinearLayout.LayoutParams(-1, dp(6)) })
        col.addView(btn("Debug Info", 0xFF2A3A2D.toInt()) { showDebugInfo() })

        // ── Version ──
        col.addView(Space(this).also { it.layoutParams = LinearLayout.LayoutParams(-1, dp(16)) })
        val ver = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (_: Exception) { "?" }
        col.addView(label("v$ver", 10f, TEXT_4).also { it.gravity = Gravity.CENTER })

        root.addView(col)
        setContentView(root)
    }

    override fun onResume() { super.onResume(); updateStatus(); handler.removeCallbacks(tick); handler.postDelayed(tick, 2000) }
    override fun onPause() { super.onPause(); handler.removeCallbacks(tick) }

    private fun updateStatus() {
        val a = isA11yOn(); val h = a; val c = GhostForegroundService.instance != null
        setDot(dotA11y, lblA11y, a); setDot(dotHttp, lblHttp, h); setDot(dotCapture, lblCapture, c)
        deviceLine.text = "${Build.MODEL}  \u2022  Android ${Build.VERSION.RELEASE}"
    }

    private fun showDebugInfo() {
        val a11y = isA11yOn()
        val svc = GhostForegroundService.instance != null
        val pid = android.os.Process.myPid()
        val info = buildString {
            appendLine("Ghost Portal Debug Info")
            appendLine("=======================")
            appendLine("Version: ${try { packageManager.getPackageInfo(packageName, 0).versionName } catch (_: Exception) { "?" }}")
            appendLine("Package: $packageName")
            appendLine("PID: $pid")
            appendLine()
            appendLine("Device: ${Build.MODEL} (${Build.DEVICE})")
            appendLine("Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            appendLine("Manufacturer: ${Build.MANUFACTURER}")
            appendLine("Build: ${Build.DISPLAY}")
            appendLine()
            appendLine("Accessibility: ${if (a11y) "ON" else "OFF"}")
            appendLine("HTTP Server: ${if (a11y) "ON (:8080)" else "OFF"}")
            appendLine("Foreground Service: ${if (svc) "ON" else "OFF"}")
            appendLine("Capture Active: ${try { GhostWebRtcManager.getInstance(this@MainActivity).isCaptureActive() } catch (_: Exception) { "unknown" }}")
            appendLine()
            appendLine("Screen: ${resources.displayMetrics.widthPixels}x${resources.displayMetrics.heightPixels} (${resources.displayMetrics.densityDpi}dpi)")
            appendLine("RAM: ${Runtime.getRuntime().let { "${(it.totalMemory() - it.freeMemory()) / 1024 / 1024}MB / ${it.maxMemory() / 1024 / 1024}MB" }}")
        }

        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog)
            .setTitle("Debug Info")
            .setMessage(info)
            .setPositiveButton("Copy") { _, _ ->
                val cm = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("Ghost Portal Debug", info))
                Toast.makeText(this, "Copied to clipboard", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Close", null)
            .show()
    }

    // ── Helpers ──

    private fun dp(n: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, n.toFloat(), resources.displayMetrics).toInt()
    private fun column() = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

    private fun label(s: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.create("sans-serif", Typeface.BOLD)
    }

    private fun section(s: String) = TextView(this).apply {
        text = s; textSize = 10f; setTextColor(TEXT_4); isAllCaps = true; letterSpacing = 0.12f
        typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
        setPadding(0, 0, 0, dp(10))
    }

    private fun card() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        background = GradientDrawable().apply { setColor(BG_CARD); cornerRadius = dp(14).toFloat(); setStroke(1, BORDER) }
        setPadding(dp(20), dp(16), dp(20), dp(16))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) }
    }

    private fun dot(text: String): Triple<LinearLayout, View, TextView> {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(5), 0, dp(5)) }
        val d = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(8), dp(8)).apply { rightMargin = dp(10) }
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(RED) }
        }
        val t = label(text, 14f, TEXT_3)
        row.addView(d); row.addView(t)
        return Triple(row, d, t)
    }

    private fun setDot(d: View, l: TextView, ok: Boolean) {
        (d.background as GradientDrawable).setColor(if (ok) ACCENT else RED)
        l.setTextColor(if (ok) TEXT_1 else TEXT_3)
    }

    private fun btn(text: String, color: Int, onClick: () -> Unit) = TextView(this).apply {
        this.text = text; textSize = 14f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        background = GradientDrawable().apply { setColor(color); cornerRadius = dp(10).toFloat() }
        setPadding(dp(16), dp(14), dp(16), dp(14))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
        setOnClickListener { onClick() }
    }

    private fun isA11yOn(): Boolean {
        val am = getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
        return am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_GENERIC)
            .any { it.resolveInfo.serviceInfo.packageName == packageName }
    }
}
