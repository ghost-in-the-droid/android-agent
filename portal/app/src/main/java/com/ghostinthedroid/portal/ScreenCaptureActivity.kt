package com.ghostinthedroid.portal

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.util.Log

/**
 * Invisible activity — only job is request MediaProjection permission,
 * then forward result to GhostForegroundService. Finishes immediately after.
 */
class ScreenCaptureActivity : Activity() {

    companion object {
        private const val TAG = "GhostCapActivity"
        private const val REQUEST_CODE = 1001
        const val EXTRA_WIDTH = "width"
        const val EXTRA_HEIGHT = "height"
        const val EXTRA_FPS = "fps"
        const val EXTRA_SESSION_ID = "sessionId"
        const val EXTRA_CALLBACK_URL = "callbackUrl"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(TAG, "Requesting screen capture permission")
        val autoAccept = intent.getStringExtra(EXTRA_CALLBACK_URL)?.isNotEmpty() == true
        if (autoAccept) GhostAutoAccept.arm()
        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        startActivityForResult(mpm.createScreenCaptureIntent(), REQUEST_CODE)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQUEST_CODE) {
            if (resultCode == RESULT_OK && data != null) {
                Log.i(TAG, "Permission granted — starting capture service")
                val serviceIntent = Intent(this, GhostForegroundService::class.java).apply {
                    action = "ACTION_START_CAPTURE"
                    putExtra("result_code", resultCode)
                    putExtra("result_data", data)
                    putExtra(EXTRA_WIDTH, intent.getIntExtra(EXTRA_WIDTH, 720))
                    putExtra(EXTRA_HEIGHT, intent.getIntExtra(EXTRA_HEIGHT, 1280))
                    putExtra(EXTRA_FPS, intent.getIntExtra(EXTRA_FPS, 30))
                    putExtra(EXTRA_SESSION_ID, intent.getStringExtra(EXTRA_SESSION_ID) ?: "")
                    putExtra(EXTRA_CALLBACK_URL, intent.getStringExtra(EXTRA_CALLBACK_URL) ?: "")
                }
                startForegroundService(serviceIntent)
            } else {
                Log.w(TAG, "Permission denied")
            }
            finish()
        } else {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }
}
