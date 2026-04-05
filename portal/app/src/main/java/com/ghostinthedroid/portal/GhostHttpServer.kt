package com.ghostinthedroid.portal

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.ByteArrayOutputStream

/**
 * HTTP server on port 8080. API-compatible with what our Python backend expects.
 * ALL WebRTC operations are posted to the main thread — never called directly from HTTP threads.
 */
object GhostHttpServer {
    private const val TAG = "GhostHttp"
    private const val PORT = 8080
    private var server: Server? = null

    fun start(context: Context) {
        if (server != null) return
        try {
            server = Server(PORT, context)
            server?.start()
            Log.i(TAG, "HTTP server started on port $PORT")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start: ${e.message}")
        }
    }

    fun stop() {
        server?.stop()
        server = null
        Log.i(TAG, "HTTP server stopped")
    }

    private class Server(port: Int, private val context: Context) : NanoHTTPD(port) {
        private val mainHandler = Handler(Looper.getMainLooper())

        override fun serve(session: IHTTPSession): Response {
            val uri = session.uri.trimEnd('/')

            var body = JSONObject()
            if (session.method == Method.POST) {
                try {
                    val len = session.headers["content-length"]?.toIntOrNull() ?: 0
                    if (len > 0) {
                        val buf = ByteArray(len)
                        session.inputStream.read(buf)
                        body = JSONObject(String(buf))
                    }
                } catch (_: Exception) {}
            }

            return try {
                when (uri) {
                    "/phone_state" -> handlePhoneState()
                    "/state" -> handleState()
                    "/elements" -> handleElements()
                    "/screenshot" -> handleScreenshot(session)
                    "/status" -> ok("ok")
                    "/version" -> ok("1.0.0")
                    "/packages" -> handlePackages()
                    "/overlay", "/overlay/toggle" -> handleOverlay(body)
                    "/stream/start" -> handleStreamStart(body)
                    "/stream/stop" -> handleStreamStop(body)
                    "/webrtc/answer" -> handleWebRtcAnswer(body)
                    "/webrtc/offer" -> handleWebRtcOffer(body)
                    "/webrtc/ice" -> handleWebRtcIce(body)
                    else -> error("Unknown endpoint: $uri")
                }
            } catch (e: Exception) {
                error("${e.message}")
            }
        }

        private fun handlePhoneState(): Response {
            val service = GhostAccessibilityService.instance
                ?: return error("Accessibility service not running")
            return ok(service.getPhoneState().toString())
        }

        /**
         * /state — Full accessibility tree for fast UI queries.
         * Returns: {status: "success", result: JSON string with {a11y_tree: {...}}}
         * This is the critical endpoint the Python backend uses (33ms vs 1.2s fallback).
         */
        private fun handleState(): Response {
            val service = GhostAccessibilityService.instance
                ?: return error("Accessibility service not running")
            val tree = service.getA11yTree()
                ?: return error("No active window")
            val inner = JSONObject()
            inner.put("a11y_tree", tree)
            return ok(inner.toString())
        }

        /**
         * /elements — Flat element list (idx, text, bounds, clickable, etc.)
         */
        private fun handleElements(): Response {
            val service = GhostAccessibilityService.instance
                ?: return error("Accessibility service not running")
            return ok(service.getElements().toString())
        }

        private fun handleScreenshot(session: IHTTPSession): Response {
            // Hide overlay during screenshot if requested
            val hideOverlay = session.parms?.get("hideOverlay")?.lowercase() != "false"
            if (hideOverlay) GhostOverlayManager.hide()

            val bitmap = GhostScreenCapture.takeScreenshot(context)
                ?: return error("Screenshot failed — screen capture not available")
            val baos = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, baos)
            val b64 = Base64.encodeToString(baos.toByteArray(), Base64.NO_WRAP)
            bitmap.recycle()
            return ok(b64)
        }

        private fun handlePackages(): Response {
            val service = GhostAccessibilityService.instance
                ?: return error("Accessibility service not running")
            return ok(service.getPackages().toString())
        }

        private fun handleOverlay(body: JSONObject): Response {
            val visible = body.optBoolean("visible", true)
            mainHandler.post { GhostOverlayManager.toggle(context, visible) }
            return ok(if (visible) "overlay_on" else "overlay_off")
        }

        // ── Stream control (NEVER call WebRTC directly from HTTP thread) ────

        private fun handleStreamStart(body: JSONObject): Response {
            val sessionId = body.optString("sessionId", "")
            val callbackUrl = body.optString("callbackUrl", "")
            val width = body.optInt("width", 720)
            val height = body.optInt("height", 1280)
            val fps = body.optInt("fps", 30)

            if (sessionId.isEmpty()) return error("Missing required param: 'sessionId'")

            // Store callback URL globally
            GhostWebRtcManager.signalingCallbackUrl = callbackUrl

            // Always request fresh capture — reuse path was unreliable
            // (stale capturers, dead MediaProjection, 0fps ghost sessions)
            // Auto-accept handles the permission dialog in <1s anyway
            // Activity → onActivityResult → Service.startForeground(MEDIA_PROJECTION) → WebRtcManager.startStream
            val intent = Intent(context, ScreenCaptureActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                putExtra(ScreenCaptureActivity.EXTRA_WIDTH, width)
                putExtra(ScreenCaptureActivity.EXTRA_HEIGHT, height)
                putExtra(ScreenCaptureActivity.EXTRA_FPS, fps)
                putExtra(ScreenCaptureActivity.EXTRA_SESSION_ID, sessionId)
                putExtra(ScreenCaptureActivity.EXTRA_CALLBACK_URL, callbackUrl)
            }
            context.startActivity(intent)
            return ok("prompting_user")
        }

        private fun handleStreamStop(body: JSONObject): Response {
            val sessionId = body.optString("sessionId", "")
            mainHandler.post { GhostWebRtcManager.getInstance(context).stopStream(sessionId) }
            return ok("stopped")
        }

        private fun handleWebRtcAnswer(body: JSONObject): Response {
            val sdp = body.optString("sdp", "")
            val sessionId = body.optString("sessionId", "")
            if (sdp.isEmpty()) return error("Missing SDP")
            mainHandler.post { GhostWebRtcManager.getInstance(context).handleAnswer(sdp, sessionId) }
            return ok("answer received")
        }

        private fun handleWebRtcOffer(body: JSONObject): Response {
            val sdp = body.optString("sdp", "")
            val sessionId = body.optString("sessionId", "")
            if (sdp.isEmpty()) return error("Missing SDP")
            mainHandler.post { GhostWebRtcManager.getInstance(context).handleOffer(sdp, sessionId) }
            return ok("offer received")
        }

        private fun handleWebRtcIce(body: JSONObject): Response {
            val candidate = body.optString("candidate", "")
            val sdpMid = body.optString("sdpMid", "")
            val sdpMLineIndex = body.optInt("sdpMLineIndex", 0)
            mainHandler.post {
                GhostWebRtcManager.getInstance(context).handleIceCandidate(candidate, sdpMid, sdpMLineIndex)
            }
            return ok("ICE candidate received")
        }

        // ── Response helpers ────────────────────────────────────────────────

        private fun ok(result: String): Response {
            val json = JSONObject().put("status", "success").put("result", result)
            return newFixedLengthResponse(Response.Status.OK, "application/json", json.toString()).apply {
                addHeader("Access-Control-Allow-Origin", "*")
                addHeader("Connection", "close")
            }
        }

        private fun error(msg: String): Response {
            val json = JSONObject().put("status", "error").put("error", msg)
            return newFixedLengthResponse(Response.Status.OK, "application/json", json.toString()).apply {
                addHeader("Access-Control-Allow-Origin", "*")
                addHeader("Connection", "close")
            }
        }
    }
}
