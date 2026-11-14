package com.ghostinthedroid.portal

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Build
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import org.json.JSONArray
import org.json.JSONObject

/**
 * Reads the UI tree via Android Accessibility APIs.
 * Provides phone_state and element data to the HTTP server.
 */
class GhostAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "GhostA11y"
        var instance: GhostAccessibilityService? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "Accessibility service connected")
        // Initialize WebRTC manager singleton on main thread (critical — must be first)
        GhostWebRtcManager.getInstance(this)
        // Start HTTP server
        GhostHttpServer.start(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Forward to auto-accept for MediaProjection dialog handling
        GhostAutoAccept.onAccessibilityEvent(event, this)
        // Forward to overlay for auto-refresh on navigation/scroll
        GhostOverlayManager.onAccessibilityEvent(event, this)
    }

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        GhostHttpServer.stop()
        Log.i(TAG, "Accessibility service destroyed")
    }

    /**
     * Get current phone state — app, activity, keyboard, focused element.
     */
    fun getPhoneState(): JSONObject {
        val result = JSONObject()
        try {
            val root = rootInActiveWindow ?: return result
            val pkg = root.packageName?.toString() ?: ""
            result.put("packageName", pkg)
            result.put("currentApp", pkg.split(".").lastOrNull() ?: pkg)

            // Activity name from window
            val windows = windows
            for (w in windows) {
                if (w.isActive) {
                    val title = w.title?.toString() ?: ""
                    result.put("activityName", title)
                    break
                }
            }

            // Keyboard visible — check if an IME window is showing
            var keyboardVisible = false
            for (w in windows) {
                if (w.type == AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_KEY.hashCode()) {
                    keyboardVisible = true
                }
            }
            // Fallback: check if any node is focused + editable
            val focused = findFocusedNode(root)
            if (focused != null && focused.isEditable) {
                keyboardVisible = true
            }
            result.put("keyboardVisible", keyboardVisible)
            result.put("isEditable", focused?.isEditable ?: false)

            val focusedElement = JSONObject()
            if (focused != null) {
                focusedElement.put("resourceId", focused.viewIdResourceName ?: "")
                focusedElement.put("text", focused.text?.toString() ?: "")
            }
            result.put("focusedElement", focusedElement)

            root.recycle()
        } catch (e: Exception) {
            Log.e(TAG, "getPhoneState error: ${e.message}")
        }
        return result
    }

    /**
     * Build the full a11y tree as a JSON object with nested children.
     * Format matches what the Python backend expects from /state endpoint:
     * {className, text, contentDescription, resourceId, isClickable, isEnabled, isChecked, isSelected, isFocused, boundsInScreen:{left,top,right,bottom}, children:[...]}
     */
    @Synchronized
    fun getA11yTree(): JSONObject? {
        try {
            // A long-lived accessibility client can retain old virtual children
            // when an app doesn't announce each transient board/overlay change.
            // Clear before acquiring roots; older Android needs per-node refresh.
            val refreshNodes = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || !clearCache()
            val roots = mutableListOf<AccessibilityNodeInfo>()
            val seenWindows = mutableSetOf<Int>()
            try {
                rootInActiveWindow?.let {
                    roots.add(it)
                    seenWindows.add(it.windowId)
                }
                // Popups can be separate application windows without becoming
                // active. Exclude system/IME/Portal accessibility overlay windows.
                val snapshotWindows = try {
                    windows
                } catch (e: Exception) {
                    Log.w(TAG, "Window enumeration unavailable; using active root", e)
                    emptyList()
                }
                for (window in snapshotWindows) {
                    try {
                        if (window.type == AccessibilityWindowInfo.TYPE_APPLICATION && window.id !in seenWindows) {
                            window.root?.let {
                                roots.add(it)
                                seenWindows.add(window.id)
                            }
                        }
                    } finally {
                        window.recycle()
                    }
                }
                val trees = roots.mapNotNull { buildNodeTree(it, refreshNodes) }
                return when (trees.size) {
                    0 -> null
                    1 -> trees.first()
                    else -> JSONObject().apply {
                        put("className", "android.view.WindowRoots")
                        put("children", JSONArray(trees))
                    }
                }
            } finally {
                roots.forEach { it.recycle() }
            }
        } catch (e: Exception) {
            Log.e(TAG, "getA11yTree error: ${e.message}")
            return null
        }
    }

    private fun buildNodeTree(node: AccessibilityNodeInfo, refreshNodes: Boolean): JSONObject? {
        if (refreshNodes && !node.refresh()) return null
        val obj = JSONObject()
        obj.put("className", node.className?.toString() ?: "")
        obj.put("text", node.text?.toString() ?: "")
        obj.put("contentDescription", node.contentDescription?.toString() ?: "")
        obj.put("resourceId", node.viewIdResourceName ?: "")
        obj.put("isClickable", node.isClickable)
        obj.put("isScrollable", node.isScrollable)
        obj.put("isEditable", node.isEditable)
        obj.put("isCheckable", node.isCheckable)
        obj.put("isChecked", node.isChecked)
        obj.put("isFocusable", node.isFocusable)
        obj.put("isFocused", node.isFocused)
        obj.put("isSelected", node.isSelected)
        obj.put("isEnabled", node.isEnabled)

        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        obj.put("boundsInScreen", JSONObject().apply {
            put("left", bounds.left)
            put("top", bounds.top)
            put("right", bounds.right)
            put("bottom", bounds.bottom)
        })

        val children = JSONArray()
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            try {
                buildNodeTree(child, refreshNodes)?.let { children.put(it) }
            } finally {
                child.recycle()
            }
        }
        obj.put("children", children)
        return obj
    }

    /**
     * Build the full UI element tree as JSON array.
     * Each element: {idx, text, content_desc, resource_id, class, bounds, clickable, scrollable, enabled, checkable, checked, focusable, focused, selected}
     */
    fun getElements(): JSONArray {
        val elements = JSONArray()
        val root = getA11yTree() ?: return elements
        fun walk(node: JSONObject) {
            val text = node.optString("text")
            val desc = node.optString("contentDescription")
            val rid = node.optString("resourceId")
            val clickable = node.optBoolean("isClickable")
            val scrollable = node.optBoolean("isScrollable")
            val bounds = node.optJSONObject("boundsInScreen")
            if (bounds != null && (clickable || scrollable || text.isNotEmpty() || desc.isNotEmpty() || rid.isNotEmpty())) {
                val left = bounds.optInt("left")
                val top = bounds.optInt("top")
                val right = bounds.optInt("right")
                val bottom = bounds.optInt("bottom")
                if (right > left && bottom > top) {
                    val el = JSONObject()
                    el.put("idx", elements.length())
                    el.put("text", text)
                    el.put("content_desc", desc)
                    el.put("resource_id", rid)
                    el.put("class", node.optString("className").substringAfterLast('.'))
                    el.put("clickable", clickable)
                    el.put("scrollable", scrollable)
                    for ((key, source) in listOf("enabled" to "isEnabled", "checkable" to "isCheckable",
                            "checked" to "isChecked", "focusable" to "isFocusable",
                            "focused" to "isFocused", "selected" to "isSelected")) {
                        el.put(key, node.optBoolean(source, key == "enabled"))
                    }
                    el.put("bounds", JSONObject().apply {
                        put("x1", left); put("y1", top); put("x2", right); put("y2", bottom)
                    })
                    el.put("center", JSONObject().apply {
                        put("x", (left + right) / 2); put("y", (top + bottom) / 2)
                    })
                    elements.put(el)
                }
            }
            val children = node.optJSONArray("children") ?: return
            for (i in 0 until children.length()) walk(children.getJSONObject(i))
        }
        walk(root)
        return elements
    }

    /**
     * Get installed packages list.
     */
    fun getPackages(): JSONArray {
        val packages = JSONArray()
        try {
            val pm = applicationContext.packageManager
            for (pkg in pm.getInstalledPackages(0)) {
                packages.put(pkg.packageName)
            }
        } catch (e: Exception) {
            Log.e(TAG, "getPackages error: ${e.message}")
        }
        return packages
    }

    private fun findFocusedNode(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (root.isFocused) return root
        for (i in 0 until root.childCount) {
            val child = root.getChild(i) ?: continue
            val found = findFocusedNode(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }
}
