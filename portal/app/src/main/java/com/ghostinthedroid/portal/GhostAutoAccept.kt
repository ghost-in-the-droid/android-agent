package com.ghostinthedroid.portal

import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * Auto-accepts MediaProjection permission dialogs.
 *
 * Handles TWO flows:
 *   Android ≤13: Single dialog with "Start now" / "Allow" button → click it
 *   Android 14+: Three-step dialog:
 *     Step 0: Spinner "Share one app" → click spinner
 *     Step 1: Select "Entire screen" from dropdown
 *     Step 2: Click "Start" / "Start now" / "Next" button
 *
 * Key fix: After selecting "Entire screen", the dialog needs time to update.
 * We use scheduled retries to poll for the final button, and also walk the
 * full root window (not just event source) to find buttons in the updated dialog.
 */
object GhostAutoAccept {
    private const val TAG = "GhostAutoAccept"
    private const val TTL_MS = 60_000L

    private val armedUntil = AtomicLong(0L)
    private val step = AtomicInteger(0)  // 0 = waiting, 1 = spinner clicked, 2 = need final click
    private val mainHandler = Handler(Looper.getMainLooper())
    private var retryRunnable: Runnable? = null

    fun arm() {
        armedUntil.set(System.currentTimeMillis() + TTL_MS)
        step.set(0)
        cancelRetries()
        Log.i(TAG, "Armed for ${TTL_MS / 1000}s")
    }

    fun isArmed(): Boolean = System.currentTimeMillis() < armedUntil.get()

    fun onAccessibilityEvent(event: AccessibilityEvent?, service: GhostAccessibilityService) {
        if (!isArmed()) return
        if (event?.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            event?.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return

        val source = event.source ?: return

        try {
            val currentStep = step.get()

            // === Android ≤13: Simple "Start now" / "Allow" button ===
            // Only try this if we haven't entered the multi-step spinner flow
            if (currentStep == 0) {
                // First check if this is a multi-step dialog (has spinner)
                val spinners = source.findAccessibilityNodeInfosByViewId(
                    "com.android.systemui:id/screen_share_mode_options"
                )
                if (spinners.isNotEmpty()) {
                    // Android 14+ multi-step flow — click spinner
                    spinners[0].performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    Log.i(TAG, "Step 0: Clicked spinner to open options")
                    step.set(1)
                    return
                }

                // No spinner — try simple single-button flow
                for (label in listOf("Start now", "Allow", "Start")) {
                    val nodes = source.findAccessibilityNodeInfosByText(label)
                    for (node in nodes) {
                        if (node.isClickable && node.className?.toString()?.contains("Button") == true) {
                            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                            Log.i(TAG, "Clicked '$label' (simple flow)")
                            disarm()
                            return
                        }
                    }
                }

                // Fallback: try button1 directly (only in simple flow)
                val btn1 = source.findAccessibilityNodeInfosByViewId("android:id/button1")
                for (node in btn1) {
                    if (node.isClickable) {
                        node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                        Log.i(TAG, "Fallback: Clicked button1")
                        disarm()
                        return
                    }
                }
            }

            // === Android 14+: Step 1 — select "Entire screen" from dropdown ===
            if (currentStep == 1) {
                for (text in listOf("Entire screen", "Share entire screen")) {
                    val options = source.findAccessibilityNodeInfosByText(text)
                    for (node in options) {
                        // The text node may not be clickable — walk up to clickable parent
                        val target = findClickableParent(node) ?: node
                        target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                        Log.i(TAG, "Step 1: Selected '$text' (clickable=${target.isClickable}, class=${target.className})")
                        step.set(2)
                        // Schedule retries to find the final button after dropdown closes
                        scheduleStep2Retries(service)
                        return
                    }
                }
            }

            // === Android 14+: Step 2 — click final button ===
            if (currentStep == 2) {
                if (tryClickFinalButton(source, "event")) return
                // Also try from the root window directly
                tryClickFinalButtonFromRoot(service)
            }

        } catch (e: Exception) {
            Log.w(TAG, "Error: ${e.message}")
        } finally {
            source.recycle()
        }
    }

    /**
     * Try clicking "Start" / "Start now" / "Next" in the given node tree.
     */
    private fun tryClickFinalButton(root: AccessibilityNodeInfo, via: String): Boolean {
        for (label in listOf("Start", "Start now", "Next")) {
            val buttons = root.findAccessibilityNodeInfosByText(label)
            for (node in buttons) {
                // Skip dropdown items that contain "Share" — those are spinner options, not buttons
                val nodeText = node.text?.toString() ?: ""
                if (nodeText.contains("Share", ignoreCase = true)) continue
                val target = if (node.isClickable) node else findClickableParent(node) ?: node
                if (target.isClickable) {
                    target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    Log.i(TAG, "Step 2: Clicked '$label' (via $via, class=${target.className})")
                    disarm()
                    return true
                }
            }
        }
        // Try by view ID
        val btn1 = root.findAccessibilityNodeInfosByViewId("android:id/button1")
        for (node in btn1) {
            if (node.isClickable) {
                node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.i(TAG, "Step 2: Clicked button1 (via $via)")
                disarm()
                return true
            }
        }
        return false
    }

    /**
     * Walk up the node tree to find the nearest clickable ancestor.
     */
    private fun findClickableParent(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current = node.parent
        var depth = 0
        while (current != null && depth < 5) {
            if (current.isClickable) return current
            current = current.parent
            depth++
        }
        return null
    }

    /**
     * Walk the full root window to find the final button.
     * The event source may be stale/narrow after dropdown closes.
     */
    private fun tryClickFinalButtonFromRoot(service: GhostAccessibilityService) {
        try {
            val root = service.rootInActiveWindow ?: return
            try {
                if (tryClickFinalButton(root, "root")) return
            } finally {
                root.recycle()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Root walk error: ${e.message}")
        }
    }

    /**
     * After selecting "Entire screen", schedule multiple retries to find and
     * click the final button. The dialog needs time to update after the
     * dropdown closes — accessibility events may not fire for the update.
     */
    private fun scheduleStep2Retries(service: GhostAccessibilityService) {
        cancelRetries()
        val delays = longArrayOf(300, 600, 1000, 1500, 2000, 3000, 5000)
        for (delay in delays) {
            val r = Runnable {
                if (!isArmed() || step.get() != 2) return@Runnable
                Log.d(TAG, "Step 2 retry (${delay}ms)")
                tryClickFinalButtonFromRoot(service)
            }
            scheduledRunnables.add(r)
            mainHandler.postDelayed(r, delay)
        }
        retryRunnable = Runnable {} // sentinel
    }

    private val scheduledRunnables = mutableListOf<Runnable>()

    private fun cancelRetries() {
        for (r in scheduledRunnables) mainHandler.removeCallbacks(r)
        scheduledRunnables.clear()
        retryRunnable = null
    }

    private fun disarm() {
        armedUntil.set(0)
        step.set(0)
        cancelRetries()
    }
}
