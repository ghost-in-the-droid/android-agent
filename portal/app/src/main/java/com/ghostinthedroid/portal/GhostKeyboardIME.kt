package com.ghostinthedroid.portal

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.inputmethodservice.InputMethodService
import android.util.Log
import android.view.View

/**
 * Custom IME for Unicode text input via broadcast.
 * Usage: adb shell am broadcast -a GHOST_INPUT_TEXT --es msg "emoji text here"
 * Supports full Unicode — emoji, CJK, accented chars — unlike adb shell input text.
 */
class GhostKeyboardIME : InputMethodService() {

    companion object {
        private const val TAG = "GhostIME"
        const val ACTION_INPUT = "GHOST_INPUT_TEXT"
        var instance: GhostKeyboardIME? = null
            private set
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val text = intent.getStringExtra("msg") ?: return
            Log.d(TAG, "Received input: ${text.take(30)}")
            val ic = currentInputConnection ?: return
            ic.commitText(text, 1)
        }
    }

    override fun onCreateInputView(): View? {
        // No visible keyboard — this is a headless IME
        return null
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        registerReceiver(receiver, IntentFilter(ACTION_INPUT), Context.RECEIVER_EXPORTED)
        Log.i(TAG, "Ghost Keyboard IME started")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        try { unregisterReceiver(receiver) } catch (_: Exception) {}
        Log.i(TAG, "Ghost Keyboard IME destroyed")
    }
}
