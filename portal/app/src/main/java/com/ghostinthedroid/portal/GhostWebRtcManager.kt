package com.ghostinthedroid.portal

import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjection
import android.os.Handler
import android.os.Looper
import android.util.Log
import org.json.JSONObject
import org.webrtc.*
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger

/**
 * WebRTC streaming manager — ports droidrun Portal's threading and synchronization patterns.
 *
 * Critical rules:
 *   1. PeerConnectionFactory initialized ONCE on main thread
 *   2. ALL PeerConnection state changes go through synchronized(streamLock)
 *   3. ICE candidates queued until remote description is set
 *   4. HTTP signaling POSTs happen on separate threads
 *   5. Cleanup follows strict order: capturer → source → track → helper → peer
 *
 * Singleton — one instance per app, created from GhostAccessibilityService.
 */
class GhostWebRtcManager private constructor(private val context: Context) {

    companion object {
        private const val TAG = "GhostWebRTC"
        private const val VIDEO_TRACK_ID = "GhostScreenTrack"
        private const val MAX_ICE_RESTARTS = 1
        private const val STATS_INTERVAL_MS = 5000L
        private const val IDLE_TIMEOUT_MS = 10 * 60 * 1000L  // 10 minutes

        @Volatile
        private var instance: GhostWebRtcManager? = null
        var signalingCallbackUrl: String = ""

        fun getInstance(context: Context): GhostWebRtcManager {
            return instance ?: synchronized(this) {
                instance ?: GhostWebRtcManager(context.applicationContext).also {
                    instance = it
                }
            }
        }
    }

    // ── Threading ────────────────────────────────────────────────────────────
    private val streamLock = Any()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val streamGeneration = AtomicInteger(0)
    private val outgoingMessageId = AtomicInteger(1)
    private var statsRunnable: Runnable? = null
    private var idleStopRunnable: Runnable? = null

    // ── WebRTC objects (protected by streamLock) ────────────────────────────
    private val eglBase: EglBase by lazy { EglBase.create() }
    private var peerConnectionFactory: PeerConnectionFactory? = null
    private var peerConnection: PeerConnection? = null
    private var dataChannel: DataChannel? = null
    private var screenCapturer: ScreenCapturerAndroid? = null
    private var videoSource: VideoSource? = null
    private var videoTrack: VideoTrack? = null
    private var surfaceTextureHelper: SurfaceTextureHelper? = null

    // ── State ───────────────────────────────────────────────────────────────
    private var primarySessionId: String? = null
    private var isRemoteDescriptionSet = false
    private val pendingIceCandidates = mutableListOf<IceCandidate>()
    private var iceRestartAttempts = 0

    // ── Initialization (ONCE, on main thread) ───────────────────────────────

    init {
        check(Looper.myLooper() == Looper.getMainLooper()) {
            "GhostWebRtcManager must be created on the main thread"
        }
        initializeFactory()
    }

    private fun initializeFactory() {
        if (peerConnectionFactory != null) return
        Log.i(TAG, "Initializing PeerConnectionFactory")
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .setEnableInternalTracer(false)
                .createInitializationOptions()
        )
        // Use H.264-preferred encoder — hardware accelerated on most phones (10x less CPU than VP8)
        val hwEncoder = DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true)
        val filteredEncoder = FilteringVideoEncoderFactory(hwEncoder, setOf("H264", "VP8"))
        peerConnectionFactory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(filteredEncoder)
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(eglBase.eglBaseContext))
            .setOptions(PeerConnectionFactory.Options())
            .createPeerConnectionFactory()
        val codecs = filteredEncoder.supportedCodecs.map { it.name }
        Log.i(TAG, "PeerConnectionFactory initialized, codecs: $codecs")
    }

    /** Filter encoder to only allow H264 + VP8 (prevents suboptimal codec negotiation). */
    private class FilteringVideoEncoderFactory(
        private val delegate: VideoEncoderFactory,
        allowedCodecNames: Set<String>,
    ) : VideoEncoderFactory {
        private val allowed = allowedCodecNames.map { it.uppercase(Locale.US) }.toSet()

        override fun createEncoder(info: VideoCodecInfo): VideoEncoder? {
            return if (info.name.uppercase(Locale.US) in allowed) delegate.createEncoder(info) else null
        }

        override fun getSupportedCodecs(): Array<VideoCodecInfo> {
            return delegate.supportedCodecs.filter { it.name.uppercase(Locale.US) in allowed }.toTypedArray()
        }
    }

    // ── Public API ──────────────────────────────────────────────────────────

    // Volatile flag for lock-free check from HTTP thread (avoids deadlock with streamLock)
    @Volatile
    private var captureActive = false

    fun isCaptureActive(): Boolean = captureActive

    fun isStreamActive(): Boolean = synchronized(streamLock) { peerConnection != null }

    fun isCurrentSession(sessionId: String): Boolean =
        synchronized(streamLock) { primarySessionId == sessionId }

    /**
     * Start a new WebRTC stream. MUST be called on main thread.
     * Called from GhostForegroundService.onStartCommand after startForeground(MEDIA_PROJECTION).
     */
    fun startStream(
        permissionResultData: Intent,
        sessionId: String,
        callbackUrl: String,
        width: Int = 720,
        height: Int = 1280,
        fps: Int = 30,
    ) {
        check(Looper.myLooper() == Looper.getMainLooper()) { "startStream must run on main thread" }
        if (callbackUrl.isNotEmpty()) signalingCallbackUrl = callbackUrl

        Log.i(TAG, "startStream: session=$sessionId ${width}x${height}@${fps}fps")
        cancelIdleStop()
        val streamId = streamGeneration.incrementAndGet()

        synchronized(streamLock) {
            // 1. Full cleanup — new permission token means old capturer is dead
            cleanupStreamLocked()

            // 2. Store session
            primarySessionId = sessionId

            // 3. Create PeerConnection
            createPeerConnectionLocked(streamId)

            // 4. Create fresh video track with the new permission result
            createVideoTrackLocked(permissionResultData, width, height, fps, streamId)

            // 5. Add track to peer connection + configure bitrate
            videoTrack?.let { track ->
                val sender = peerConnection?.addTrack(track, listOf(VIDEO_TRACK_ID))
                configureVideoSender(sender, width, height, fps)
                Log.i(TAG, "Video track added to PeerConnection")
            }

            // 6. Create and send offer
            createOfferLocked(streamId)
        }
    }

    /**
     * Reuse existing capture — create new PeerConnection but keep the capturer.
     * MUST be called on main thread (via mainHandler.post from HTTP server).
     * Returns false if capturer/track is dead (caller should re-request permission).
     */
    fun startStreamWithExistingCapture(
        sessionId: String,
        callbackUrl: String,
        width: Int = 720,
        height: Int = 1280,
        fps: Int = 30,
    ): Boolean {
        check(Looper.myLooper() == Looper.getMainLooper()) { "Must run on main thread" }
        if (callbackUrl.isNotEmpty()) signalingCallbackUrl = callbackUrl

        Log.i(TAG, "startStreamWithExistingCapture: session=$sessionId")

        synchronized(streamLock) {
            // Verify capturer and track are actually alive
            if (screenCapturer == null || videoTrack == null) {
                Log.w(TAG, "Capturer or track is dead — cannot reuse")
                captureActive = false
                return false
            }

            cancelIdleStop()
            val streamId = streamGeneration.incrementAndGet()

            // Close old peer connection but keep capturer
            peerConnection?.close()
            peerConnection = null
            isRemoteDescriptionSet = false
            pendingIceCandidates.clear()
            primarySessionId = sessionId

            // Create new peer connection
            createPeerConnectionLocked(streamId)

            // Re-add existing video track + configure bitrate
            val sender = peerConnection?.addTrack(videoTrack!!, listOf(VIDEO_TRACK_ID))
            configureVideoSender(sender, width, height, fps)
            Log.i(TAG, "Existing video track re-added")

            // Create offer
            createOfferLocked(streamId)
        }
        return true
    }

    fun stopStream(sessionId: String) {
        Log.i(TAG, "stopStream: $sessionId")
        streamGeneration.incrementAndGet()
        synchronized(streamLock) {
            if (primarySessionId == sessionId || sessionId.isEmpty()) {
                primarySessionId = null
                closePeerConnectionLocked()
            }
        }
        // Schedule idle stop — if no new stream starts within 10 min, release capturer
        scheduleIdleStop("stream stopped")
    }

    /** Full cleanup — kills capturer too. Call on app exit or force-stop. */
    fun destroyAll() {
        Log.i(TAG, "destroyAll")
        synchronized(streamLock) {
            cleanupStreamLocked()
        }
    }

    fun handleAnswer(sdp: String, sessionId: String) {
        val pc: PeerConnection?
        synchronized(streamLock) {
            if (primarySessionId != sessionId) {
                Log.w(TAG, "handleAnswer: session mismatch ($sessionId != $primarySessionId)")
                return
            }
            pc = peerConnection
        }
        if (pc == null) {
            Log.w(TAG, "handleAnswer: no active PeerConnection")
            return
        }

        Log.i(TAG, "Setting remote description (answer)")
        pc.setRemoteDescription(
            object : SdpObserverAdapter("setRemoteDescription") {
                override fun onSetSuccess() {
                    super.onSetSuccess()
                    synchronized(streamLock) {
                        isRemoteDescriptionSet = true
                        // Flush queued ICE candidates
                        if (pendingIceCandidates.isNotEmpty()) {
                            Log.i(TAG, "Flushing ${pendingIceCandidates.size} queued ICE candidates")
                            for (candidate in pendingIceCandidates) {
                                peerConnection?.addIceCandidate(candidate)
                            }
                            pendingIceCandidates.clear()
                        }
                    }
                }
            },
            SessionDescription(SessionDescription.Type.ANSWER, sdp)
        )
    }

    fun handleOffer(sdp: String, sessionId: String) {
        val pc: PeerConnection?
        synchronized(streamLock) {
            if (primarySessionId != sessionId) return
            pc = peerConnection
        }
        if (pc == null) return

        Log.i(TAG, "Setting remote description (offer)")
        pc.setRemoteDescription(
            object : SdpObserverAdapter("setRemoteDescription") {
                override fun onSetSuccess() {
                    super.onSetSuccess()
                    synchronized(streamLock) { isRemoteDescriptionSet = true }
                    // Create answer
                    pc.createAnswer(
                        object : SdpObserverAdapter("createAnswer") {
                            override fun onCreateSuccess(desc: SessionDescription) {
                                super.onCreateSuccess(desc)
                                pc.setLocalDescription(SdpObserverAdapter("setLocalAnswer"), desc)
                                sendSignaling("webrtc/answer", JSONObject().apply {
                                    put("sdp", desc.description)
                                    put("sessionId", sessionId)
                                })
                            }
                        },
                        MediaConstraints()
                    )
                }
            },
            SessionDescription(SessionDescription.Type.OFFER, sdp)
        )
    }

    fun handleIceCandidate(candidate: String, sdpMid: String, sdpMLineIndex: Int) {
        val ice = IceCandidate(sdpMid, sdpMLineIndex, candidate)
        synchronized(streamLock) {
            if (!isRemoteDescriptionSet) {
                Log.d(TAG, "Queuing ICE candidate (remote desc not set yet)")
                pendingIceCandidates.add(ice)
                return
            }
            peerConnection?.addIceCandidate(ice)
        }
    }

    // ── Private: PeerConnection creation (must hold streamLock) ─────────────

    private fun createPeerConnectionLocked(streamId: Int) {
        val iceServers = listOf(
            PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
            PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer(),
        )
        val rtcConfig = PeerConnection.RTCConfiguration(iceServers).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE
            tcpCandidatePolicy = PeerConnection.TcpCandidatePolicy.DISABLED
            iceCandidatePoolSize = 1  // Pre-allocate for faster ICE
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        }

        peerConnection = peerConnectionFactory?.createPeerConnection(
            rtcConfig,
            object : PeerConnection.Observer {
                override fun onIceCandidate(candidate: IceCandidate) {
                    val sid = synchronized(streamLock) { primarySessionId } ?: return
                    sendSignaling("webrtc/ice", JSONObject().apply {
                        put("candidate", candidate.sdp)
                        put("sdpMid", candidate.sdpMid)
                        put("sdpMLineIndex", candidate.sdpMLineIndex)
                        put("sessionId", sid)
                    })
                }
                override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {
                    Log.i(TAG, "ICE state: $state (gen=$streamId)")
                    when (state) {
                        PeerConnection.IceConnectionState.CONNECTED -> {
                            iceRestartAttempts = 0  // Reset on success
                            mainHandler.post { requestKeyframe() }
                            mainHandler.postDelayed({ rampBitrate() }, 2000)
                            startStatsLogging(streamId)
                        }
                        PeerConnection.IceConnectionState.FAILED -> {
                            // Auto ICE restart (max 1 attempt)
                            if (iceRestartAttempts < MAX_ICE_RESTARTS) {
                                iceRestartAttempts++
                                Log.w(TAG, "ICE failed — restarting ($iceRestartAttempts/$MAX_ICE_RESTARTS)")
                                synchronized(streamLock) {
                                    isRemoteDescriptionSet = false
                                    pendingIceCandidates.clear()
                                    peerConnection?.restartIce()
                                }
                            } else {
                                Log.e(TAG, "ICE failed — max restarts reached")
                            }
                        }
                        else -> {}
                    }
                }
                override fun onSignalingChange(state: PeerConnection.SignalingState) {
                    Log.d(TAG, "Signaling state: $state")
                }
                override fun onIceConnectionReceivingChange(receiving: Boolean) {}
                override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                    Log.d(TAG, "ICE gathering: $state")
                }
                override fun onAddStream(stream: MediaStream) {}
                override fun onRemoveStream(stream: MediaStream) {}
                override fun onDataChannel(dc: DataChannel) {}
                override fun onRenegotiationNeeded() {}
                override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) {}
                override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) {}
            }
        )

        // Create DataChannel for low-latency input events (tap/swipe/key)
        val dcInit = DataChannel.Init().apply {
            ordered = true
            negotiated = true
            id = 1
        }
        dataChannel = peerConnection?.createDataChannel("control", dcInit)
        dataChannel?.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(prev: Long) {}
            override fun onStateChange() {
                Log.i(TAG, "DataChannel state: ${dataChannel?.state()}")
            }
            override fun onMessage(buffer: DataChannel.Buffer) {
                if (buffer.binary) return
                val msg = buffer.data.let { buf ->
                    val bytes = ByteArray(buf.remaining())
                    buf.get(bytes)
                    String(bytes)
                }
                handleDataChannelMessage(msg)
            }
        })
        Log.i(TAG, "PeerConnection + DataChannel created")
    }

    /** Handle input commands received over DataChannel (tap, swipe, key). */
    private fun handleDataChannelMessage(msg: String) {
        try {
            val json = JSONObject(msg)
            val action = json.optString("action", "")
            Thread {
                try {
                    val rt = Runtime.getRuntime()
                    when (action) {
                        "tap" -> {
                            val x = json.getInt("x")
                            val y = json.getInt("y")
                            rt.exec(arrayOf("input", "tap", "$x", "$y")).waitFor()
                        }
                        "swipe" -> {
                            val x1 = json.getInt("x1"); val y1 = json.getInt("y1")
                            val x2 = json.getInt("x2"); val y2 = json.getInt("y2")
                            val dur = json.optInt("duration", 300)
                            rt.exec(arrayOf("input", "swipe", "$x1", "$y1", "$x2", "$y2", "$dur")).waitFor()
                        }
                        "key" -> {
                            val keycode = json.getString("keycode")
                            rt.exec(arrayOf("input", "keyevent", keycode)).waitFor()
                        }
                        "text" -> {
                            val text = json.getString("text")
                            rt.exec(arrayOf("input", "text", text)).waitFor()
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "DataChannel input failed: ${e.message}")
                }
            }.start()
        } catch (e: Exception) {
            Log.w(TAG, "DataChannel message parse error: ${e.message}")
        }
    }

    // ── Private: Video track creation (must hold streamLock) ────────────────

    private fun createVideoTrackLocked(
        permissionResultData: Intent,
        width: Int,
        height: Int,
        fps: Int,
        streamId: Int,
    ) {
        val factory = peerConnectionFactory ?: return

        // 1. Create screen capturer with the permission Intent
        screenCapturer = ScreenCapturerAndroid(
            permissionResultData,
            object : MediaProjection.Callback() {
                override fun onStop() {
                    Log.i(TAG, "MediaProjection stopped callback")
                    mainHandler.post { stopStream(primarySessionId ?: "") }
                }
            }
        )

        // 2. Create video source
        videoSource = factory.createVideoSource(screenCapturer!!.isScreencast)

        // 3. Create SurfaceTextureHelper (dedicated thread + EGL context)
        surfaceTextureHelper = SurfaceTextureHelper.create("GhostCaptureThread", eglBase.eglBaseContext)

        // 4. Initialize capturer (order: helper first, then observer)
        screenCapturer!!.initialize(surfaceTextureHelper, context, videoSource!!.capturerObserver)

        // 5. Start capture
        try {
            screenCapturer!!.startCapture(width, height, fps)
            captureActive = true
            Log.i(TAG, "Screen capture started: ${width}x${height}@${fps}fps")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start capture: ${e.message}", e)
            captureActive = false
            throw RuntimeException("Screen capture failed", e)
        }

        // 6. Create video track from source
        videoTrack = factory.createVideoTrack(VIDEO_TRACK_ID, videoSource)
        Log.i(TAG, "Video track created")
    }

    // ── Private: Offer creation (must hold streamLock) ──────────────────────

    private fun createOfferLocked(streamId: Int) {
        val pc = peerConnection ?: return
        Log.i(TAG, "Creating offer...")

        pc.createOffer(
            object : SdpObserverAdapter("createOffer") {
                override fun onCreateSuccess(desc: SessionDescription) {
                    super.onCreateSuccess(desc)
                    // Prefer VP8 — H264 hardware encoder drops frames with ScreenCapturer
                    val mungedSdp = preferVP8(desc.description)
                    val mungedDesc = SessionDescription(desc.type, mungedSdp)
                    Log.i(TAG, "Offer created (${mungedSdp.length} chars, VP8-preferred)")

                    // Set local description
                    pc.setLocalDescription(
                        object : SdpObserverAdapter("setLocalDescription") {
                            override fun onSetSuccess() {
                                super.onSetSuccess()
                                val sid = synchronized(streamLock) { primarySessionId }
                                if (!sid.isNullOrBlank()) {
                                    Log.i(TAG, "Local description set, sending offer to callback")
                                    sendSignaling("webrtc/offer", JSONObject().apply {
                                        put("sdp", mungedSdp)
                                        put("sessionId", sid)
                                    })
                                }
                            }
                        },
                        mungedDesc
                    )
                }
            },
            MediaConstraints()
        )
    }

    // ── Private: Cleanup (must hold streamLock) ─────────────────────────────

    /** Close only the PeerConnection — keep capturer alive for fast restart. */
    private fun closePeerConnectionLocked() {
        stopStatsLogging()
        try { dataChannel?.close() } catch (_: Exception) {}
        dataChannel = null
        try { peerConnection?.close() } catch (e: Exception) { Log.w(TAG, "close peer: ${e.message}") }
        peerConnection = null
        isRemoteDescriptionSet = false
        pendingIceCandidates.clear()
        Log.i(TAG, "PeerConnection closed (capturer still alive)")
    }

    /** Full cleanup — kills capturer + peer. Used on app exit or fresh stream/start. */
    private fun cleanupStreamLocked() {
        captureActive = false  // Set immediately before any blocking cleanup
        try { dataChannel?.close() } catch (_: Exception) {}
        dataChannel = null
        try { screenCapturer?.stopCapture() } catch (e: Exception) { Log.w(TAG, "stopCapture: ${e.message}") }
        try { screenCapturer?.dispose() } catch (e: Exception) { Log.w(TAG, "dispose capturer: ${e.message}") }
        try { videoSource?.dispose() } catch (e: Exception) { Log.w(TAG, "dispose source: ${e.message}") }
        try { videoTrack?.dispose() } catch (e: Exception) { Log.w(TAG, "dispose track: ${e.message}") }
        try { surfaceTextureHelper?.dispose() } catch (e: Exception) { Log.w(TAG, "dispose helper: ${e.message}") }
        try { peerConnection?.close() } catch (e: Exception) { Log.w(TAG, "close peer: ${e.message}") }

        screenCapturer = null
        videoSource = null
        videoTrack = null
        surfaceTextureHelper = null
        peerConnection = null
        primarySessionId = null
        isRemoteDescriptionSet = false
        pendingIceCandidates.clear()
        Log.i(TAG, "All stream resources cleaned up")
    }

    // ── Private: Signaling (HTTP POST on separate thread) ───────────────────

    private fun sendSignaling(method: String, params: JSONObject) {
        val url = signalingCallbackUrl
        if (url.isEmpty()) {
            Log.w(TAG, "No callback URL — signaling message dropped: $method")
            return
        }
        val json = JSONObject().apply {
            put("id", outgoingMessageId.getAndIncrement())
            put("method", method)
            put("params", params)
        }
        Thread {
            try {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                conn.connectTimeout = 3000
                conn.readTimeout = 3000
                conn.outputStream.use { it.write(json.toString().toByteArray()) }
                val code = conn.responseCode
                conn.disconnect()
                Log.d(TAG, "Signaling POST $method → $code")
            } catch (e: Exception) {
                Log.w(TAG, "Signaling POST $method failed: ${e.message}")
            }
        }.start()
    }

    // ── SDP Observer adapter ────────────────────────────────────────────────

    // ── Video sender configuration (bitrate, fps, degradation) ────────────

    private fun configureVideoSender(sender: RtpSender?, width: Int, height: Int, fps: Int) {
        if (sender == null) return
        val params = sender.parameters
        val maxBitrate = computeMaxBitrate(width, height, fps)
        var updated = false
        for (encoding in params.encodings) {
            val cur = encoding.maxBitrateBps
            if (cur == null || cur > maxBitrate) {
                encoding.maxBitrateBps = maxBitrate
                updated = true
            }
            val curFps = encoding.maxFramerate
            if (curFps == null || curFps > fps) {
                encoding.maxFramerate = fps
                updated = true
            }
        }
        if (params.degradationPreference != RtpParameters.DegradationPreference.BALANCED) {
            params.degradationPreference = RtpParameters.DegradationPreference.BALANCED
            updated = true
        }
        if (updated) {
            sender.setParameters(params)
            Log.i(TAG, "Video sender: maxBitrate=${maxBitrate/1000}kbps maxFps=$fps")
        }
    }

    private fun computeMaxBitrate(width: Int, height: Int, fps: Int): Int {
        val minDim = minOf(width, height)  // Use shorter dimension (width in portrait)
        val base = when {
            minDim >= 1080 -> 4_000_000
            minDim >= 720 -> 2_000_000
            minDim >= 480 -> 1_200_000
            else -> 800_000
        }
        return when {
            fps <= 10 -> base * 3 / 5
            fps <= 15 -> base * 3 / 4
            else -> base
        }
    }

    /** Request keyframe from the video encoder — gets first frame to viewer faster. */
    private fun requestKeyframe() {
        synchronized(streamLock) {
            val pc = peerConnection ?: return
            for (sender in pc.senders) {
                if (sender.track()?.kind() == "video") {
                    val params = sender.parameters
                    // Toggle a parameter to force a keyframe request
                    for (enc in params.encodings) {
                        // Temporarily set a very low maxBitrate to trigger encoder reset
                        val original = enc.maxBitrateBps
                        enc.maxBitrateBps = 500_000 // Low to force fast keyframe
                        sender.setParameters(params)
                        // Restore immediately
                        enc.maxBitrateBps = original
                        sender.setParameters(params)
                    }
                    Log.i(TAG, "Keyframe requested")
                    break
                }
            }
        }
    }

    /** Ramp bitrate up after initial connection — start fast then increase quality. */
    private fun rampBitrate() {
        synchronized(streamLock) {
            val pc = peerConnection ?: return
            for (sender in pc.senders) {
                if (sender.track()?.kind() == "video") {
                    val params = sender.parameters
                    for (enc in params.encodings) {
                        // Full bitrate after 2s of stable connection
                        enc.maxBitrateBps = 2_500_000  // 2.5Mbps for quality
                    }
                    sender.setParameters(params)
                    Log.i(TAG, "Bitrate ramped to 2.5Mbps")
                    break
                }
            }
        }
    }

    // ── Idle timeout (release capturer after 10 min of no active stream) ──

    private fun scheduleIdleStop(reason: String) {
        cancelIdleStop()
        if (!captureActive) return
        val r = Runnable {
            if (captureActive && !isStreamActive()) {
                Log.i(TAG, "Idle timeout ($reason) — releasing capturer")
                synchronized(streamLock) { cleanupStreamLocked() }
            }
        }
        idleStopRunnable = r
        mainHandler.postDelayed(r, IDLE_TIMEOUT_MS)
        Log.d(TAG, "Idle stop scheduled in ${IDLE_TIMEOUT_MS / 60000} min ($reason)")
    }

    private fun cancelIdleStop() {
        idleStopRunnable?.let { mainHandler.removeCallbacks(it) }
        idleStopRunnable = null
    }

    // ── Stats logging (every 5s) ─────────────────────────────────────────

    private fun startStatsLogging(streamId: Int) {
        stopStatsLogging()
        val runnable = object : Runnable {
            override fun run() {
                if (streamGeneration.get() != streamId) return
                val pc = synchronized(streamLock) { peerConnection } ?: return
                pc.getStats { report ->
                    var codec = ""; var fps = 0; var w = 0; var h = 0
                    var bytesSent = 0L; var rtt = 0.0; var limitation = ""
                    for (stats in report.statsMap.values) {
                        when (stats.type) {
                            "outbound-rtp" -> {
                                bytesSent = (stats.members["bytesSent"] as? Long) ?: 0L
                                fps = ((stats.members["framesPerSecond"] as? Number)?.toInt()) ?: 0
                                w = ((stats.members["frameWidth"] as? Number)?.toInt()) ?: 0
                                h = ((stats.members["frameHeight"] as? Number)?.toInt()) ?: 0
                                limitation = (stats.members["qualityLimitationReason"] as? String) ?: ""
                            }
                            "candidate-pair" -> {
                                if (stats.members["state"] == "succeeded") {
                                    rtt = ((stats.members["currentRoundTripTime"] as? Number)?.toDouble()) ?: 0.0
                                }
                            }
                            "codec" -> {
                                val mime = (stats.members["mimeType"] as? String) ?: ""
                                if (mime.startsWith("video/")) codec = mime.removePrefix("video/")
                            }
                        }
                    }
                    if (w > 0) Log.i(TAG, "Stats: ${w}x${h}@${fps}fps codec=$codec rtt=${(rtt*1000).toInt()}ms sent=${bytesSent/1024}KB limit=$limitation")
                }
                mainHandler.postDelayed(this, STATS_INTERVAL_MS)
            }
        }
        statsRunnable = runnable
        mainHandler.postDelayed(runnable, STATS_INTERVAL_MS)
    }

    private fun stopStatsLogging() {
        statsRunnable?.let { mainHandler.removeCallbacks(it) }
        statsRunnable = null
    }

    // ── SDP munging: prefer H.264 over VP8 ───────────────────────────────

    /**
     * Reorder video codecs in SDP so VP8 comes first.
     * H264 hardware encoder drops frames with ScreenCapturerAndroid — VP8 works reliably.
     */
    private fun preferVP8(sdp: String): String {
        val lines = sdp.split("\r\n").toMutableList()
        for (i in lines.indices) {
            if (!lines[i].startsWith("m=video")) continue
            val vp8Pts = mutableListOf<String>()
            val otherPts = mutableListOf<String>()
            for (j in (i + 1) until lines.size) {
                if (lines[j].startsWith("m=")) break
                val m = Regex("^a=rtpmap:(\\d+) VP8/").find(lines[j])
                if (m != null) vp8Pts.add(m.groupValues[1])
            }
            if (vp8Pts.isEmpty()) break
            val parts = lines[i].split(" ").toMutableList()
            if (parts.size < 4) break
            val allPts = parts.subList(3, parts.size).toList()
            for (pt in allPts) { if (pt !in vp8Pts) otherPts.add(pt) }
            lines[i] = (parts.subList(0, 3) + vp8Pts + otherPts).joinToString(" ")
            break
        }
        return lines.joinToString("\r\n")
    }

    // ── SDP Observer adapter ────────────────────────────────────────────────

    private open class SdpObserverAdapter(private val label: String) : SdpObserver {
        override fun onCreateSuccess(desc: SessionDescription) {
            Log.d(TAG, "$label onCreateSuccess")
        }
        override fun onCreateFailure(error: String) {
            Log.e(TAG, "$label onCreateFailure: $error")
        }
        override fun onSetSuccess() {
            Log.d(TAG, "$label onSetSuccess")
        }
        override fun onSetFailure(error: String) {
            Log.e(TAG, "$label onSetFailure: $error")
        }
    }
}
