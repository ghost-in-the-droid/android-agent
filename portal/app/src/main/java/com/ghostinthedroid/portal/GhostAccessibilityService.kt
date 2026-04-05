package com.ghostinthedroid.portal

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
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
     * {className, text, contentDescription, resourceId, isClickable, boundsInScreen:{left,top,right,bottom}, children:[...]}
     */
    fun getA11yTree(): JSONObject? {
        try {
            val root = rootInActiveWindow ?: return null
            val tree = buildNodeTree(root)
            root.recycle()
            return tree
        } catch (e: Exception) {
            Log.e(TAG, "getA11yTree error: ${e.message}")
            return null
        }
    }

    private fun buildNodeTree(node: AccessibilityNodeInfo): JSONObject {
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
        obj.put("isFocused", node.isFocused)
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
            children.put(buildNodeTree(child))
            child.recycle()
        }
        obj.put("children", children)
        return obj
    }

    /**
     * Build the full UI element tree as JSON array.
     * Each element: {idx, text, content_desc, resource_id, class, bounds, clickable, scrollable}
     */
    fun getElements(): JSONArray {
        val elements = JSONArray()
        try {
            val root = rootInActiveWindow ?: return elements
            var idx = 0
            fun walk(node: AccessibilityNodeInfo) {
                val text = node.text?.toString() ?: ""
                val desc = node.contentDescription?.toString() ?: ""
                val rid = node.viewIdResourceName ?: ""
                val cls = node.className?.toString()?.split(".")?.lastOrNull() ?: ""
                val clickable = node.isClickable
                val scrollable = node.isScrollable

                if (clickable || scrollable || text.isNotEmpty() || desc.isNotEmpty()) {
                    val bounds = Rect()
                    node.getBoundsInScreen(bounds)
                    if (bounds.width() > 0 && bounds.height() > 0) {
                        val el = JSONObject()
                        el.put("idx", idx++)
                        el.put("text", text)
                        el.put("content_desc", desc)
                        el.put("resource_id", rid)
                        el.put("class", cls)
                        el.put("clickable", clickable)
                        el.put("scrollable", scrollable)
                        el.put("bounds", JSONObject().apply {
                            put("x1", bounds.left); put("y1", bounds.top)
                            put("x2", bounds.right); put("y2", bounds.bottom)
                        })
                        el.put("center", JSONObject().apply {
                            put("x", bounds.centerX()); put("y", bounds.centerY())
                        })
                        elements.put(el)
                    }
                }

                for (i in 0 until node.childCount) {
                    val child = node.getChild(i) ?: continue
                    walk(child)
                    child.recycle()
                }
            }
            walk(root)
            root.recycle()
        } catch (e: Exception) {
            Log.e(TAG, "getElements error: ${e.message}")
        }
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
