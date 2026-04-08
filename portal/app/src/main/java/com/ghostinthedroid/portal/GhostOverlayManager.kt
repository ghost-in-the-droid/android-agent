package com.ghostinthedroid.portal

import android.content.Context
import android.graphics.*
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Numbered element overlay — matches droidrun Portal behavior:
 *
 * - Auto-refreshes on accessibility events (window change, scroll, content change)
 * - Full-screen edge-to-edge via FLAG_LAYOUT_NO_LIMITS
 * - Badges at top-right of each element (droidrun style)
 * - Apple-inspired 8-color palette
 * - Hardware accelerated canvas
 * - Tries backend element fetch for index sync, falls back to local walk
 */
object GhostOverlayManager {
    private const val TAG = "GhostOverlay"
    private const val REFRESH_INTERVAL_MS = 800L   // Periodic refresh
    private const val MIN_REFRESH_GAP_MS = 500L    // Throttle rapid events

    private var overlayView: OverlayView? = null
    private var isVisible = false
    private var lastRefreshTime = 0L
    private val mainHandler = Handler(Looper.getMainLooper())
    private var refreshRunnable: Runnable? = null

    // Apple-style colors (droidrun palette)
    private val COLORS = intArrayOf(
        Color.rgb(0, 122, 255),     // Blue
        Color.rgb(255, 45, 85),     // Red
        Color.rgb(52, 199, 89),     // Green
        Color.rgb(255, 149, 0),     // Orange
        Color.rgb(175, 82, 222),    // Purple
        Color.rgb(255, 204, 0),     // Yellow
        Color.rgb(90, 200, 250),    // Light Blue
        Color.rgb(88, 86, 214),     // Indigo
    )

    fun toggle(context: Context, visible: Boolean) {
        isVisible = visible
        if (visible) {
            refresh(context)
            startPeriodicRefresh(context)
        } else {
            stopPeriodicRefresh()
            hide()
        }
    }

    private var pendingRefresh: Runnable? = null

    /** Called from GhostAccessibilityService on relevant events. */
    fun onAccessibilityEvent(event: AccessibilityEvent?, context: Context) {
        if (!isVisible) return
        val type = event?.eventType ?: return
        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||
            type == AccessibilityEvent.TYPE_VIEW_SCROLLED) {
            val now = System.currentTimeMillis()
            if (now - lastRefreshTime < MIN_REFRESH_GAP_MS) return
            // Cancel previous pending refresh
            pendingRefresh?.let { mainHandler.removeCallbacks(it) }
            val r = Runnable { refresh(context) }
            pendingRefresh = r
            mainHandler.postDelayed(r, 300)
        }
    }

    private fun startPeriodicRefresh(context: Context) {
        stopPeriodicRefresh()
        val r = object : Runnable {
            override fun run() {
                if (isVisible) {
                    refresh(context)
                    mainHandler.postDelayed(this, REFRESH_INTERVAL_MS)
                }
            }
        }
        refreshRunnable = r
        mainHandler.postDelayed(r, REFRESH_INTERVAL_MS)
    }

    private fun stopPeriodicRefresh() {
        refreshRunnable?.let { mainHandler.removeCallbacks(it) }
        refreshRunnable = null
        pendingRefresh?.let { mainHandler.removeCallbacks(it) }
    }

    private fun refresh(context: Context) {
        lastRefreshTime = System.currentTimeMillis()
        val elements = fetchBackendElements() ?: collectLocalElements()
        Log.d(TAG, "Refresh: ${elements.size} elements")
        if (elements.isEmpty()) { hide(); return }

        if (overlayView != null) {
            // Update existing overlay (avoid remove/add flicker)
            overlayView?.updateElements(elements)
        } else {
            showOverlay(context, elements)
        }
    }

    private fun showOverlay(context: Context, elements: List<ElementInfo>) {
        hide()
        try {
            val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val view = OverlayView(context, elements)
            val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_SYSTEM_OVERLAY

            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                PixelFormat.TRANSLUCENT
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                params.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
            wm.addView(view, params)
            overlayView = view
        } catch (e: Exception) {
            Log.e(TAG, "Overlay failed: ${e.message}")
        }
    }

    fun hide() {
        val view = overlayView ?: return
        try {
            (view.context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).removeView(view)
        } catch (_: Exception) {}
        overlayView = null
    }

    /** Fetch from backend for index sync. */
    private fun fetchBackendElements(): List<ElementInfo>? {
        try {
            val cbUrl = GhostWebRtcManager.signalingCallbackUrl
            if (cbUrl.isEmpty()) return null
            val match = Regex("(https?://[^/]+)/api/phone/webrtc-callback/(.+)").find(cbUrl) ?: return null
            val url = "${match.groupValues[1]}/api/phone/elements/${match.groupValues[2]}"

            val conn = java.net.URL(url).openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 1500
            conn.readTimeout = 1500
            val body = conn.inputStream.bufferedReader().readText()
            conn.disconnect()

            val arr = org.json.JSONArray(body)
            val elements = mutableListOf<ElementInfo>()
            for (i in 0 until arr.length()) {
                val el = arr.getJSONObject(i)
                val b = el.getJSONObject("bounds")
                val rect = Rect(b.getInt("x1"), b.getInt("y1"), b.getInt("x2"), b.getInt("y2"))
                if (rect.width() > 5 && rect.height() > 5) {
                    elements.add(ElementInfo(el.getInt("idx"), rect,
                        el.optBoolean("clickable"), el.optBoolean("scrollable")))
                }
            }
            return if (elements.isNotEmpty()) elements else null
        } catch (_: Exception) { return null }
    }

    /** Fallback: local accessibility tree walk. */
    private fun collectLocalElements(): List<ElementInfo> {
        val service = GhostAccessibilityService.instance ?: return emptyList()
        val root = service.rootInActiveWindow ?: return emptyList()
        val elements = mutableListOf<ElementInfo>()
        var idx = 0
        fun walk(node: AccessibilityNodeInfo) {
            val text = node.text?.toString() ?: ""
            val desc = node.contentDescription?.toString() ?: ""
            if (node.isClickable || node.isScrollable || text.isNotEmpty() || desc.isNotEmpty()) {
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                if (bounds.width() > 5 && bounds.height() > 5)
                    elements.add(ElementInfo(idx++, bounds, node.isClickable, node.isScrollable))
            }
            for (i in 0 until node.childCount) { node.getChild(i)?.let { walk(it); it.recycle() } }
        }
        walk(root); root.recycle()
        return elements
    }

    data class ElementInfo(val idx: Int, val bounds: Rect, val clickable: Boolean, val scrollable: Boolean)

    private class OverlayView(ctx: Context, private var els: List<ElementInfo>) : View(ctx) {
        private val dp = ctx.resources.displayMetrics.density

        // Droidrun exact values: textSize=32f, strokeWidth=2f, pad=4f, textHeight=36f
        private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 32f
            typeface = Typeface.DEFAULT_BOLD
        }
        private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
        private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2f
        }

        fun updateElements(newEls: List<ElementInfo>) {
            els = newEls
            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            val pad = 4f
            val textH = 36f

            for (el in els) {
                val c = COLORS[el.idx % COLORS.size]

                // Element border — match droidrun alpha
                borderPaint.color = Color.argb(180, Color.red(c), Color.green(c), Color.blue(c))
                canvas.drawRect(
                    el.bounds.left.toFloat(), el.bounds.top.toFloat(),
                    el.bounds.right.toFloat(), el.bounds.bottom.toFloat(),
                    borderPaint
                )

                // Badge at top-RIGHT (droidrun position)
                val label = el.idx.toString()
                val tw = textPaint.measureText(label)
                val textX = el.bounds.right - tw - pad
                val textY = el.bounds.top + textH

                // Background rect
                bgPaint.color = Color.argb(200, Color.red(c), Color.green(c), Color.blue(c))
                canvas.drawRect(
                    textX - pad, (textY - textH),
                    textX + tw + pad, textY + pad,
                    bgPaint
                )
                canvas.drawText(label, textX, textY, textPaint)
            }
        }
    }
}
