package com.ghostinthedroid.portal

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Auto-starts Ghost Portal on device boot.
 */
class GhostBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i("GhostBoot", "Boot completed — starting Ghost Portal service")
            val serviceIntent = Intent(context, GhostForegroundService::class.java)
            context.startForegroundService(serviceIntent)
        }
    }
}
