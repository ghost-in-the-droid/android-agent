/**
 * GhostAgent H.264 stream client — decodes the WebSocket Annex-B H.264 stream
 * (proxied by the Ghost backend at /api/phone/h264/<device>) with WebCodecs and
 * renders to a <canvas>. Robust by design: auto-reconnects, surfaces detailed
 * metrics, waits for a keyframe, and BOUNDS LATENCY by dropping the backlog when
 * decode/draw can't keep up (so it stays live instead of drifting seconds behind).
 *
 * Metrics (the important part for diagnosing "lag"):
 *   recvFps    — H.264 access units arriving per second (network throughput)
 *   renderFps  — frames actually painted per second
 *   queue      — decoder backlog; if this grows, latency is accumulating
 *   latencyMs  — decode→paint latency of the most recent frame
 *   kbps       — bandwidth
 *   dropped    — frames skipped to stay live
 */
import { ref, type Ref } from 'vue'

export function h264Supported(): boolean {
  return typeof window !== 'undefined' && 'VideoDecoder' in window
}

function nalType(byte: number): number { return byte & 0x1f }
function isKeyframe(buf: Uint8Array): boolean {
  for (let i = 0; i + 4 < buf.length; i++) {
    if (buf[i] === 0 && buf[i + 1] === 0 && (buf[i + 2] === 1 || (buf[i + 2] === 0 && buf[i + 3] === 1))) {
      const s = buf[i + 2] === 1 ? i + 3 : i + 4
      const t = nalType(buf[s] ?? 0)
      if (t === 5 || t === 7) return true
      if (t === 1) return false
    }
  }
  return false
}

export interface H264Metrics {
  status: Ref<string>
  recvFps: Ref<number>
  renderFps: Ref<number>
  queue: Ref<number>
  latencyMs: Ref<number>
  kbps: Ref<number>
  dropped: Ref<number>
  stop: () => void
}

// If the decoder falls this far behind, drop everything until the next keyframe
// so latency can't run away. Keyframes arrive ~every 2s, so this bounds lag.
const MAX_QUEUE = 4

export function startH264Stream(wsUrl: string, canvas: HTMLCanvasElement): H264Metrics {
  const status = ref('connecting')
  const recvFps = ref(0)
  const renderFps = ref(0)
  const queue = ref(0)
  const latencyMs = ref(0)
  const kbps = ref(0)
  const dropped = ref(0)

  const ctx = canvas.getContext('2d')
  let decoder: VideoDecoder | null = null
  let ws: WebSocket | null = null
  let stopped = false
  let haveKeyframe = false
  let reconnectTimer: number | null = null
  let backoff = 500

  // rolling-window counters (reset each second by the metrics timer)
  let recvWin = 0, renderWin = 0, byteWin = 0
  let lastDecodeAt = 0

  const metricsTimer = window.setInterval(() => {
    recvFps.value = recvWin; renderFps.value = renderWin
    kbps.value = Math.round(byteWin * 8 / 1000)
    queue.value = decoder ? decoder.decodeQueueSize : 0
    recvWin = 0; renderWin = 0; byteWin = 0
  }, 1000)

  function setupDecoder() {
    try {
      decoder = new VideoDecoder({
        output: (frame: VideoFrame) => {
          try {
            if (ctx) {
              if (canvas.width !== frame.displayWidth) canvas.width = frame.displayWidth
              if (canvas.height !== frame.displayHeight) canvas.height = frame.displayHeight
              ctx.drawImage(frame, 0, 0)
            }
            renderWin++
            if (lastDecodeAt) latencyMs.value = Math.round(performance.now() - lastDecodeAt)
          } finally { frame.close() }
        },
        error: () => { status.value = 'decoder error — reconnecting'; scheduleReconnect() },
      })
      decoder.configure({ codec: 'avc1.42E01E', optimizeForLatency: true } as VideoDecoderConfig)
    } catch { status.value = 'WebCodecs unavailable'; decoder = null }
  }

  function onBinary(data: ArrayBuffer) {
    if (!decoder || decoder.state !== 'configured') return
    const buf = new Uint8Array(data)
    recvWin++; byteWin += buf.length
    const key = isKeyframe(buf)

    // Latency bound: if we're behind, drop until the next keyframe.
    if (decoder.decodeQueueSize > MAX_QUEUE && !key) { dropped.value++; return }
    if (!haveKeyframe) { if (!key) return; haveKeyframe = true; status.value = 'streaming' }

    try {
      lastDecodeAt = performance.now()
      decoder.decode(new EncodedVideoChunk({ type: key ? 'key' : 'delta', timestamp: lastDecodeAt * 1000, data: buf }))
    } catch { haveKeyframe = false }
  }

  function connect() {
    if (stopped) return
    haveKeyframe = false
    setupDecoder()
    try { ws = new WebSocket(wsUrl); ws.binaryType = 'arraybuffer' } catch { scheduleReconnect(); return }
    ws.onopen = () => { status.value = 'connected'; backoff = 500 }
    ws.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data === 'string') {
        try { const j = JSON.parse(ev.data); if (j.status) status.value = j.status } catch {}
        return
      }
      onBinary(ev.data as ArrayBuffer)
    }
    ws.onclose = () => { if (!stopped) scheduleReconnect() }
    ws.onerror = () => { try { ws?.close() } catch {} }
  }

  function scheduleReconnect() {
    if (stopped || reconnectTimer != null) return
    status.value = 'reconnecting'
    cleanupConnection()
    reconnectTimer = window.setTimeout(() => { reconnectTimer = null; backoff = Math.min(5000, backoff * 2); connect() }, backoff)
  }

  function cleanupConnection() {
    try { ws?.close() } catch {}
    ws = null
    try { if (decoder && decoder.state !== 'closed') decoder.close() } catch {}
    decoder = null
  }

  function stop() {
    stopped = true
    clearInterval(metricsTimer)
    if (reconnectTimer != null) { clearTimeout(reconnectTimer); reconnectTimer = null }
    cleanupConnection()
    status.value = 'stopped'
  }

  connect()
  return { status, recvFps, renderFps, queue, latencyMs, kbps, dropped, stop }
}
