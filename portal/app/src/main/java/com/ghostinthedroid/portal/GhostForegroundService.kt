package com.ghostinthedroid.portal

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo

import android.os.IBinder
import android.os.PowerManager
import android.util.Log

/**
 * Foreground service — manages MediaProjection lifecycle.
 *
 * Flow: ScreenCaptureActivity gets permission → starts this service with ACTION_START_CAPTURE
 *       → startForeground(MEDIA_PROJECTION) → getMediaProjection → WebRtcManager.startStream
 *
 * All of this runs on the main thread (Service lifecycle).
 */
class GhostForegroundService : Service() {

    companion object {
        private const val TAG = "GhostService"
        private const val CHANNEL_ID = "ghost_portal_service"
        private const val NOTIFICATION_ID = 1
        var instance: GhostForegroundService? = null
            private set
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action

        if (action == "ACTION_START_CAPTURE") {
            // STEP 1: startForeground with MEDIA_PROJECTION — MUST be first
            startForeground(
                NOTIFICATION_ID,
                buildNotification("Streaming active"),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
            Log.i(TAG, "Foreground started with MEDIA_PROJECTION type")

            // STEP 2: Pass resultData directly to WebRTC manager.
            // DO NOT call getMediaProjection() here — ScreenCapturerAndroid will call it
            // internally. Android 14+ forbids calling getMediaProjection() twice with
            // the same resultData.
            @Suppress("DEPRECATION")
            val resultData = intent.getParcelableExtra<Intent>("result_data")
            val resultCode = intent.getIntExtra("result_code", 0)

            if (resultCode == -1 && resultData != null) {
                try {
                    Log.i(TAG, "Permission result received, passing to WebRTC manager")

                    val sessionId = intent.getStringExtra(ScreenCaptureActivity.EXTRA_SESSION_ID) ?: ""
                    val callbackUrl = intent.getStringExtra(ScreenCaptureActivity.EXTRA_CALLBACK_URL) ?: ""
                    val width = intent.getIntExtra(ScreenCaptureActivity.EXTRA_WIDTH, 720)
                    val height = intent.getIntExtra(ScreenCaptureActivity.EXTRA_HEIGHT, 1280)
                    val fps = intent.getIntExtra(ScreenCaptureActivity.EXTRA_FPS, 30)

                    val manager = GhostWebRtcManager.getInstance(this)
                    if (sessionId.isNotEmpty()) {
                        manager.startStream(resultData, sessionId, callbackUrl, width, height, fps)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "WebRTC start failed: ${e.message}", e)
                }
            }
        } else {
            // Generic start (no projection)
            startForeground(
                NOTIFICATION_ID,
                buildNotification("Ghost Portal running"),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        }

        // Wake lock
        if (wakeLock == null) {
            val pm = getSystemService(POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "GhostPortal::WakeLock")
            wakeLock?.acquire()
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        wakeLock?.release()
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID, getString(R.string.notification_channel),
            NotificationManager.IMPORTANCE_LOW
        ).apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }
}
