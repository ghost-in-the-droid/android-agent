/**
 * GhostAgent H.264 stream client — decodes the WebSocket Annex-B H.264 stream
 * (proxied by the Ghost backend at /api/phone/h264/<device>) with WebCodecs and
 * renders to a <canvas>. Robust by design: auto-reconnects, surfaces status, and
 * waits for a keyframe before decoding so a mid-stream join can't wedge it.
 *
 * Falls back gracefully: if WebCodecs/VideoDecoder is unavailable the caller
 * should use the MJPEG path instead (see `h264Supported`).
 */
import { ref, type Ref } from 'vue'

export function h264Supported(): boolean {
  return typeof window !== 'undefined' && 'VideoDecoder' in window
}

// NAL unit type from the first byte after a start code (lower 5 bits).
function nalType(byte: number): number { return byte & 0x1f }

// Scan an Annex-B access unit: is it a keyframe (contains IDR=5 or SPS=7)?
function isKeyframe(buf: Uint8Array): boolean {
  for (let i = 0; i + 4 < buf.length; i++) {
    // start code 00 00 00 01 or 00 00 01
    if (buf[i] === 0 && buf[i + 1] === 0 && (buf[i + 2] === 1 || (buf[i + 2] === 0 && buf[i + 3] === 1))) {
      const nalStart = buf[i + 2] === 1 ? i + 3 : i + 4
      const t = nalType(buf[nalStart] ?? 0)
      if (t === 5 || t === 7) return true
      if (t === 1) return false   // first slice is a non-IDR → delta frame
    }
  }
  return false
}

export interface H264StreamHandle {
  status: Ref<string>
  fps: Ref<number>
  stop: () => void
}

export function startH264Stream(wsUrl: string, canvas: HTMLCanvasElement): H264StreamHandle {
  const status = ref('connecting')
  const fps = ref(0)

  const ctx = canvas.getContext('2d')
  let decoder: VideoDecoder | null = null
  let ws: WebSocket | null = null
  let stopped = false
  let haveKeyframe = false
  let reconnectTimer: number | null = null
  let backoff = 500
  let frameTimes: number[] = []

  const ts = () => performance.now() * 1000   // microseconds for EncodedVideoChunk

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
            // rolling fps over ~1s
            const now = performance.now()
            frameTimes.push(now)
            while (frameTimes.length && now - frameTimes[0]! > 1000) frameTimes.shift()
            fps.value = frameTimes.length
          } finally {
            frame.close()
          }
        },
        error: (e: DOMException) => {
          status.value = 'decoder error — reconnecting'
          scheduleReconnect()
        },
      })
      // Baseline H.264, Annex-B (no description) + low latency.
      decoder.configure({ codec: 'avc1.42E01E', optimizeForLatency: true } as VideoDecoderConfig)
    } catch {
      status.value = 'WebCodecs unavailable'
      decoder = null
    }
  }

  function onBinary(data: ArrayBuffer) {
    if (!decoder || decoder.state !== 'configured') return
    const buf = new Uint8Array(data)
    const key = isKeyframe(buf)
    if (!haveKeyframe) {
      if (!key) return          // wait for the first keyframe before decoding
      haveKeyframe = true
      status.value = 'streaming'
    }
    try {
      decoder.decode(new EncodedVideoChunk({
        type: key ? 'key' : 'delta',
        timestamp: ts(),
        data: buf,
      }))
    } catch {
      // a bad chunk shouldn't kill the stream; wait for the next keyframe
      haveKeyframe = false
    }
  }

  function connect() {
    if (stopped) return
    haveKeyframe = false
    setupDecoder()
    try {
      ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'
    } catch {
      scheduleReconnect(); return
    }
    ws.onopen = () => { status.value = 'connected'; backoff = 500 }
    ws.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data === 'string') {
        // status JSON from the backend proxy (connecting/reconnecting/…)
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
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      backoff = Math.min(5000, backoff * 2)
      connect()
    }, backoff)
  }

  function cleanupConnection() {
    try { ws?.close() } catch {}
    ws = null
    try { if (decoder && decoder.state !== 'closed') decoder.close() } catch {}
    decoder = null
  }

  function stop() {
    stopped = true
    if (reconnectTimer != null) { clearTimeout(reconnectTimer); reconnectTimer = null }
    cleanupConnection()
    status.value = 'stopped'
  }

  connect()
  return { status, fps, stop }
}
