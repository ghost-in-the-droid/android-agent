package com.ghostinthedroid.portal

import android.content.Context
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager

/**
 * Manages MediaProjection for screenshots.
 * The WebRTC stream uses its own capture — this is for the /screenshot endpoint.
 */
object GhostScreenCapture {
    private const val TAG = "GhostCapture"

    @Volatile
    var mediaProjection: MediaProjection? = null
    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null

    fun takeScreenshot(context: Context): Bitmap? {
        val mp = mediaProjection ?: return null
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        val w = metrics.widthPixels
        val h = metrics.heightPixels
        val density = metrics.densityDpi

        try {
            val reader = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2)
            val vd = mp.createVirtualDisplay(
                "GhostScreenshot", w, h, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface, null, null
            )

            // Wait a bit for the first frame
            Thread.sleep(200)

            val image = reader.acquireLatestImage()
            val bitmap = if (image != null) {
                val planes = image.planes
                val buffer = planes[0].buffer
                val pixelStride = planes[0].pixelStride
                val rowStride = planes[0].rowStride
                val rowPadding = rowStride - pixelStride * w
                val bmp = Bitmap.createBitmap(w + rowPadding / pixelStride, h, Bitmap.Config.ARGB_8888)
                bmp.copyPixelsFromBuffer(buffer)
                image.close()
                // Crop to actual size (remove padding)
                Bitmap.createBitmap(bmp, 0, 0, w, h)
            } else {
                null
            }

            vd.release()
            reader.close()
            return bitmap
        } catch (e: Exception) {
            Log.e(TAG, "Screenshot failed: ${e.message}")
            return null
        }
    }

    fun release() {
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        mediaProjection = null
    }
}
