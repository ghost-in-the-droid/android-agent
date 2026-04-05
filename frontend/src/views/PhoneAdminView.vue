<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '@/composables/useApi'

const devices = ref<any[]>([])
const selectedDevice = ref('')
const streaming = ref(false)
const subTab = ref<'single' | 'multi'>('single')
const nickname = ref('')
const editingNickname = ref(false)
let logTimer: number | null = null
const srvLogs = ref<string[]>([])
const botLogs = ref<string[]>([])
let srvSeq = 0
const statusText = ref('')

/* ── log level filter ─────────────────────────────────────────────────── */
const logFilter = ref<string>('All')
const LOG_FILTERS = ['All', 'Error', 'Warn', 'App', 'Flask'] as const
const logsOpen = ref(false)

const filteredSrvLogs = computed(() => {
  const logs = srvLogs.value.slice(-50)
  const f = logFilter.value
  if (f === 'All') return logs
  if (f === 'Error') return logs.filter(l => l.includes('[ERROR]') || l.includes('[CRITICAL]'))
  if (f === 'Warn') return logs.filter(l => l.includes('[WARN') || l.includes('[WARNING]'))
  if (f === 'App') return logs.filter(l => !l.includes('[Flask]') && !l.includes('werkzeug'))
  if (f === 'Flask') return logs.filter(l => l.includes('[Flask]') || l.includes('werkzeug') || l.includes('HTTP'))
  return logs
})

/* ── bot log type selector ────────────────────────────────────────────── */
const botLogType = ref('bot')
const BOT_LOG_TYPES = [
  { value: 'bot', label: 'Bot' },
  { value: 'post', label: 'Post Bot' },
]

/* ══════════════════════════════════════════════════════════════════════════
   WebRTC streaming — shared logic for single + multi device
   ══════════════════════════════════════════════════════════════════════════ */
interface RtcSession { pc: RTCPeerConnection; sessionId: string; pollTimer: number; sse: EventSource | null; status: string }
const rtcSessions = ref<Record<string, RtcSession>>({})
const rtcStatus = ref<Record<string, string>>({})

function uuid(): string {
  return ([1e7] as any + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c: any) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & 15) >> c / 4).toString(16))
}

async function rtcFixPortal(serial: string) {
  rtcStatus.value[serial] = 'Fixing Portal...'
  try {
    const r = await api(`/api/phone/portal-fix/${serial}`, { method: 'POST' })
    rtcStatus.value[serial] = r.ok ? 'Portal fixed — retry stream' : ('Fix failed: ' + (r.error || ''))
  } catch { rtcStatus.value[serial] = 'Fix failed' }
}

async function rtcStart(serial: string, _reconnectAttempt = 0) {
  console.log(`[RTC ${serial}] rtcStart called (attempt=${_reconnectAttempt})`)
  if (rtcSessions.value[serial]) rtcStop(serial)
  const sessionId = uuid()
  const t0 = performance.now()
  rtcStatus.value[serial] = 'Requesting...'

  const startRes = await api('/api/phone/webrtc-signal', {
    method: 'POST',
    body: JSON.stringify({ device: serial, method: 'stream/start', params: { sessionId, width: 720, height: 1280, fps: 30 } })
  })

  console.log(`[RTC ${serial}] stream/start response:`, JSON.stringify(startRes).substring(0, 100))
  if (!startRes.ok) {
    const err = startRes.error || 'unknown'
    if (err.includes('Accessibility') || err.includes('Portal not')) {
      rtcStatus.value[serial] = 'Portal down — fixing...'
      await rtcFixPortal(serial)
      const retry = await api('/api/phone/webrtc-signal', {
        method: 'POST',
        body: JSON.stringify({ device: serial, method: 'stream/start', params: { sessionId, width: 720, height: 1280, fps: 30 } })
      })
      if (!retry.ok) { rtcStatus.value[serial] = 'Portal fix failed: ' + (retry.error || err); return }
    } else { rtcStatus.value[serial] = 'Failed: ' + err; return }
  }

  const pc = new RTCPeerConnection({
    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    iceCandidatePoolSize: 1,  // Pre-allocate candidates for faster ICE
  })
  setupDataChannel(serial, pc)

  pc.ontrack = (evt) => {
    rtcStatus.value[serial] = 'Streaming'
    const videoEl = document.getElementById(`rtc-video-${serial}`) as HTMLVideoElement
    if (videoEl) {
      videoEl.srcObject = evt.streams[0]
      videoEl.play().catch(() => {})
    }
    startBlackCheck(serial)
    console.log(`[RTC ${serial}] First frame in ${(performance.now() - t0).toFixed(0)}ms`)
  }

  pc.onicecandidate = (evt) => {
    if (evt.candidate) {
      api('/api/phone/webrtc-signal', {
        method: 'POST',
        body: JSON.stringify({ device: serial, method: 'webrtc/ice',
          params: { candidate: evt.candidate.candidate, sdpMid: evt.candidate.sdpMid,
            sdpMLineIndex: evt.candidate.sdpMLineIndex, sessionId } })
      })
    }
  }

  // Auto-reconnect on ICE failure (up to 3 attempts)
  pc.oniceconnectionstatechange = () => {
    const st = pc.iceConnectionState
    if (st === 'connected' || st === 'completed') {
      rtcStatus.value[serial] = 'Streaming'
      // Close SSE once ICE is stable — signals no longer needed
      const sess = rtcSessions.value[serial]
      if (sess?.sse) { sess.sse.close(); sess.sse = null }
    } else if (st === 'disconnected') {
      rtcStatus.value[serial] = 'Reconnecting...'
    } else if (st === 'failed') {
      rtcStatus.value[serial] = 'ICE failed'
      if (_reconnectAttempt < 3) {
        console.log(`[RTC ${serial}] Auto-reconnect attempt ${_reconnectAttempt + 1}/3`)
        rtcStatus.value[serial] = `Reconnecting (${_reconnectAttempt + 1}/3)...`
        setTimeout(() => rtcStart(serial, _reconnectAttempt + 1), 500)
      }
    } else if (st === 'checking') {
      rtcStatus.value[serial] = 'Connecting...'
    }
  }

  // Register session and start signal polling
  rtcStatus.value[serial] = 'Waiting for offer...'

  // Poll for signaling messages from phone
  let sse: EventSource | null = null
  console.log(`[RTC ${serial}] Starting poll timer (100ms interval)`)
  const pollTimer = window.setInterval(async () => {
    try {
      const r = await fetch(`/api/phone/webrtc-poll-signals/${serial}`)
      const d = await r.json()
      if (d.ok && d.messages?.length) {
        // Sort: process offers/answers BEFORE ICE candidates (they may arrive out of order)
        const msgs = d.messages.filter((m: any) => m.result !== 'prompting_user' && m.result !== 'reusing_capture')
        const parsed = msgs.map((data: any) => {
          const payload = data.payload ? (typeof data.payload === 'string' ? JSON.parse(data.payload) : data.payload) : data
          return { method: payload.method || data.method, params: payload.params || payload }
        })
        // Offers first, then answers, then ICE
        const ordered = [
          ...parsed.filter((m: any) => m.method === 'webrtc/offer'),
          ...parsed.filter((m: any) => m.method === 'webrtc/answer'),
          ...parsed.filter((m: any) => m.method === 'webrtc/ice'),
        ]
        for (const { method: m, params: p } of ordered) {
          if (m === 'webrtc/offer' && p.sdp) {
            rtcStatus.value[serial] = 'Got offer...'
            await pc.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: p.sdp }))
            const answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await api('/api/phone/webrtc-signal', {
              method: 'POST',
              body: JSON.stringify({ device: serial, method: 'webrtc/answer',
                params: { sdp: pc.localDescription!.sdp, sessionId: p.sessionId || sessionId } })
            })
            rtcStatus.value[serial] = 'Connecting...'
          } else if (m === 'webrtc/answer' && p.sdp) {
            await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: p.sdp }))
          } else if (m === 'webrtc/ice' && p.candidate && pc.remoteDescription) {
            await pc.addIceCandidate(new RTCIceCandidate({ candidate: p.candidate, sdpMid: p.sdpMid, sdpMLineIndex: p.sdpMLineIndex }))
          }
        }
      }
    } catch (e: any) { console.error(`[RTC ${serial}] poll error:`, e?.message || e) }
  }, 100)  // 100ms poll for fast signaling

  rtcSessions.value[serial] = { pc, sessionId, pollTimer, sse: null, status: 'connecting' }
}

function rtcStop(serial: string) {
  clearBlackCheck(serial)
  const sess = rtcSessions.value[serial]
  if (!sess) return
  if (sess.pollTimer) clearInterval(sess.pollTimer)
  if (sess.sse) { sess.sse.close(); sess.sse = null }
  api('/api/phone/webrtc-signal', {
    method: 'POST',
    body: JSON.stringify({ device: serial, method: 'stream/stop', params: { sessionId: sess.sessionId } })
  }).catch(() => {})
  sess.pc.close()
  delete rtcSessions.value[serial]
  rtcStatus.value[serial] = ''
  const videoEl = document.getElementById(`rtc-video-${serial}`) as HTMLVideoElement
  if (videoEl) videoEl.srcObject = null
}

/* ── DataChannel input (low-latency) with HTTP fallback ─────────────── */
function sendInput(_serial: string, _msg: object): boolean {
  // DataChannel input disabled — portal can't exec shell "input" commands
  // without root. Will implement via AccessibilityService dispatchGesture() later.
  // For now, always fall through to HTTP → backend → ADB.
  return false
}

function setupDataChannel(serial: string, pc: RTCPeerConnection) {
  try {
    const dc = pc.createDataChannel('control', { ordered: true, negotiated: true, id: 1 })
    dc.onopen = () => { console.log(`[RTC ${serial}] DataChannel open`); (rtcSessions.value[serial] as any)._dc = dc }
    dc.onclose = () => { (rtcSessions.value[serial] as any)._dc = undefined }
  } catch (e) { console.warn('[RTC] DataChannel setup failed:', e) }
}

/* ── tap/swipe on video element ──────────────────────────────────────── */
interface DragState { x: number; y: number; t: number }
const dragState = ref<Record<string, DragState | null>>({})
const dragMoved = ref<Record<string, boolean>>({})

function videoMouseDown(serial: string, e: MouseEvent) {
  e.preventDefault()
  const video = e.target as HTMLVideoElement
  const rect = video.getBoundingClientRect()
  const sx = video.videoWidth / rect.width, sy = video.videoHeight / rect.height
  dragState.value[serial] = { x: Math.round((e.clientX - rect.left) * sx), y: Math.round((e.clientY - rect.top) * sy), t: Date.now() }
  dragMoved.value[serial] = false
}

function videoMouseMove(serial: string) {
  if (dragState.value[serial]) dragMoved.value[serial] = true
}

function videoMouseUp(serial: string, e: MouseEvent) {
  const ds = dragState.value[serial]
  if (!ds) return
  e.preventDefault()
  const video = e.target as HTMLVideoElement
  const rect = video.getBoundingClientRect()
  const sx = video.videoWidth / rect.width, sy = video.videoHeight / rect.height
  const ex = Math.round((e.clientX - rect.left) * sx), ey = Math.round((e.clientY - rect.top) * sy)
  const sw = video.videoWidth, sh = video.videoHeight
  const dx = ex - ds.x, dy = ey - ds.y, dist = Math.sqrt(dx * dx + dy * dy)
  if (!dragMoved.value[serial] || dist < 20) {
    if (!sendInput(serial, { action: 'tap', x: ex, y: ey }))
      api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: serial, x: ex, y: ey, stream_w: sw, stream_h: sh }) })
  } else {
    if (!sendInput(serial, { action: 'swipe', x1: ds.x, y1: ds.y, x2: ex, y2: ey, duration: 300 }))
      api('/api/phone/swipe', { method: 'POST', body: JSON.stringify({ device: serial, x1: ds.x, y1: ds.y, x2: ex, y2: ey, stream_w: sw, stream_h: sh }) })
  }
  dragState.value[serial] = null
}

function videoMouseLeave(serial: string) { dragState.value[serial] = null }

function videoTouchStart(serial: string, e: TouchEvent) {
  if (!e.touches.length) return; e.preventDefault()
  const touch = e.touches[0], video = e.target as HTMLVideoElement, rect = video.getBoundingClientRect()
  const sx = video.videoWidth / rect.width, sy = video.videoHeight / rect.height
  dragState.value[serial] = { x: Math.round((touch.clientX - rect.left) * sx), y: Math.round((touch.clientY - rect.top) * sy), t: Date.now() }
  dragMoved.value[serial] = false
}
function videoTouchMove(serial: string) { if (dragState.value[serial]) dragMoved.value[serial] = true }
function videoTouchEnd(serial: string, e: TouchEvent) {
  const ds = dragState.value[serial]; if (!ds) return; e.preventDefault()
  const touch = e.changedTouches[0], video = e.target as HTMLVideoElement, rect = video.getBoundingClientRect()
  const sx = video.videoWidth / rect.width, sy = video.videoHeight / rect.height
  const ex = Math.round((touch.clientX - rect.left) * sx), ey = Math.round((touch.clientY - rect.top) * sy)
  const sw = video.videoWidth, sh = video.videoHeight
  const dx = ex - ds.x, dy = ey - ds.y, dist = Math.sqrt(dx * dx + dy * dy)
  if (!dragMoved.value[serial] || dist < 20) {
    if (!sendInput(serial, { action: 'tap', x: ex, y: ey }))
      api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: serial, x: ex, y: ey, stream_w: sw, stream_h: sh }) })
  } else {
    if (!sendInput(serial, { action: 'swipe', x1: ds.x, y1: ds.y, x2: ex, y2: ey, duration: 300 }))
      api('/api/phone/swipe', { method: 'POST', body: JSON.stringify({ device: serial, x1: ds.x, y1: ds.y, x2: ex, y2: ey, stream_w: sw, stream_h: sh }) })
  }
  dragState.value[serial] = null
}

function sendKeyTo(serial: string, key: number | string) {
  // Use /api/phone/key for string keys (BACK, HOME, etc.) and /api/phone/input for numeric keycodes
  if (typeof key === 'string') {
    api('/api/phone/key', { method: 'POST', body: JSON.stringify({ device: serial, key }) })
  } else {
    api('/api/phone/input', { method: 'POST', body: JSON.stringify({ device: serial, action: 'keyevent', keycode: key }) })
  }
}

/* ── Frozen stream detection ──────────────────────────────────────────── */
const streamFrozen = ref<Record<string, boolean>>({})
const frozenTimers = ref<Record<string, number>>({})
const lastFrameHash = ref<Record<string, string>>({})
const frozenCount = ref<Record<string, number>>({})
// Also keep blackWarning for FLAG_SECURE
const blackWarning = ref<Record<string, boolean>>({})

function startBlackCheck(serial: string) {
  clearBlackCheck(serial)
  lastFrameHash.value[serial] = ''
  frozenCount.value[serial] = 0
  streamFrozen.value[serial] = false

  // Start periodic check: every 3s, sample video frame, compare hash
  frozenTimers.value[serial] = window.setInterval(() => {
    const video = document.getElementById(`rtc-video-${serial}`) as HTMLVideoElement
    if (!video || !video.videoWidth) return
    try {
      const c = document.createElement('canvas')
      c.width = 8; c.height = 8
      c.getContext('2d')!.drawImage(video, 0, 0, 8, 8)
      const data = c.getContext('2d')!.getImageData(0, 0, 8, 8).data
      // Simple hash: sum of all pixel values
      let hash = 0
      for (let i = 0; i < data.length; i += 4) hash += data[i] + data[i+1] + data[i+2]
      const hashStr = hash.toString()

      // Black screen check (first time only)
      if (!lastFrameHash.value[serial] && hash / (8 * 8 * 3) < 3) {
        blackWarning.value[serial] = true
        setTimeout(() => { blackWarning.value[serial] = false }, 6000)
      }

      // Only check ICE state — if ICE is dead, stream is dead. Period.
      const sess = rtcSessions.value[serial]
      const iceState = sess?.pc?.iceConnectionState
      if (iceState === 'disconnected' || iceState === 'failed' || iceState === 'closed') {
        streamFrozen.value[serial] = true
      } else {
        streamFrozen.value[serial] = false
      }
    } catch {}
  }, 3000)
}

function clearBlackCheck(serial: string) {
  if (frozenTimers.value[serial]) { clearInterval(frozenTimers.value[serial]); delete frozenTimers.value[serial] }
  streamFrozen.value[serial] = false
  blackWarning.value[serial] = false
  frozenCount.value[serial] = 0
  lastFrameHash.value[serial] = ''
}

function reconnectStream(serial: string) {
  streamFrozen.value[serial] = false
  rtcStop(serial)
  setTimeout(() => rtcStart(serial), 500)
}

/* ── toggle stream mode (switch while streaming) ────────────────────── */
function toggleMultiMode(serial: string) {
  if (!multiStreaming.value[serial]) return
  const newMode = multiStreamMode.value[serial] === 'rtc' ? 'mjpeg' : 'rtc'
  stopMultiStream(serial)
  startMultiStream(serial, newMode)
}

function toggleSingleMode() {
  if (!streaming.value || !selectedDevice.value) return
  stopStream()
  singleStreamMode.value = singleStreamMode.value === 'rtc' ? 'mjpeg' : 'rtc'
  startStream()
}

/* ── UI grid overlay toggle ──────────────────────────────────────────── */
const overlayOn = ref<Record<string, boolean>>({})

async function toggleOverlay(serial: string) {
  overlayOn.value[serial] = !overlayOn.value[serial]
  await api(`/api/phone/overlay/${serial}`, {
    method: 'POST', body: JSON.stringify({ visible: overlayOn.value[serial] })
  })
}

/* ── multi-device ────────────────────────────────────────────────────── */
const multiStreaming = ref<Record<string, boolean>>({})
const multiStreamMode = ref<Record<string, 'rtc' | 'mjpeg'>>({})
const mjpegUrls = ref<Record<string, string>>({})

function startMultiStream(serial: string, mode: 'rtc' | 'mjpeg' = 'rtc') {
  // Clean up any existing stream first
  if (multiStreaming.value[serial]) stopMultiStream(serial)
  multiStreaming.value[serial] = true
  multiStreamMode.value[serial] = mode
  if (mode === 'rtc') {
    rtcStart(serial)
  } else {
    mjpegUrls.value[serial] = `/api/phone/stream?device=${encodeURIComponent(serial)}&fps=5`
  }
}
function stopMultiStream(serial: string) {
  multiStreaming.value[serial] = false
  if (multiStreamMode.value[serial] === 'rtc') rtcStop(serial)
  mjpegUrls.value[serial] = ''
  multiStreamMode.value[serial] = 'rtc'
}
function startAllStreams(mode: 'rtc' | 'mjpeg' = 'rtc') {
  for (const d of devices.value) { if (!multiStreaming.value[d.serial]) startMultiStream(d.serial, mode) }
}
function stopAllStreams() { for (const d of devices.value) stopMultiStream(d.serial) }

/* ── single device ───────────────────────────────────────────────────── */
const singleStreamMode = ref<'rtc' | 'mjpeg'>('rtc')
const singleMjpegUrl = ref('')

function startStream() {
  if (!selectedDevice.value) return
  streaming.value = true
  if (singleStreamMode.value === 'rtc') {
    rtcStart(selectedDevice.value)
  } else {
    singleMjpegUrl.value = `/api/phone/stream?device=${encodeURIComponent(selectedDevice.value)}&fps=5`
  }
}
function stopStream() {
  if (selectedDevice.value) rtcStop(selectedDevice.value)
  singleMjpegUrl.value = ''
  streaming.value = false
}

/* ── MJPEG tap/swipe (uses naturalWidth/Height for coordinate scaling) ─ */
function mjpegMouseDown(serial: string, e: MouseEvent) {
  e.preventDefault()
  const img = e.target as HTMLImageElement
  const rect = img.getBoundingClientRect()
  const sx = img.naturalWidth / rect.width, sy = img.naturalHeight / rect.height
  dragState.value[serial] = { x: Math.round((e.clientX - rect.left) * sx), y: Math.round((e.clientY - rect.top) * sy), t: Date.now() }
  dragMoved.value[serial] = false
}
function mjpegMouseUp(serial: string, e: MouseEvent) {
  const ds = dragState.value[serial]; if (!ds) return; e.preventDefault()
  const img = e.target as HTMLImageElement
  const rect = img.getBoundingClientRect()
  const sx = img.naturalWidth / rect.width, sy = img.naturalHeight / rect.height
  const ex = Math.round((e.clientX - rect.left) * sx), ey = Math.round((e.clientY - rect.top) * sy)
  const sw = img.naturalWidth, sh = img.naturalHeight
  const dx = ex - ds.x, dy = ey - ds.y, dist = Math.sqrt(dx * dx + dy * dy)
  if (!dragMoved.value[serial] || dist < 20) {
    api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: serial, x: ex, y: ey, stream_w: sw, stream_h: sh }) })
  } else {
    api('/api/phone/swipe', { method: 'POST', body: JSON.stringify({ device: serial, x1: ds.x, y1: ds.y, x2: ex, y2: ey, stream_w: sw, stream_h: sh }) })
  }
  dragState.value[serial] = null
}

/* ── per-device logs ─────────────────────────────────────────────────── */
const multiLogs = ref<Record<string, string[]>>({})
async function pollMultiLogs() {
  for (const d of devices.value) {
    try {
      const resp = await api(`/api/logs?device=${d.serial}&limit=30`)
      const lines = (resp.lines || []).map((l: any) => `[${l.level}] ${l.msg}`)
      multiLogs.value[d.serial] = lines
    } catch { if (!multiLogs.value[d.serial]) multiLogs.value[d.serial] = [] }
  }
}

/* ── device health ──────────────────────────────────────────────────── */
const healthData = ref<Record<string, any>>({})
const healthLoading = ref<Record<string, boolean>>({})
const showWirelessModal = ref(false)
const wirelessIp = ref('')
const wirelessPort = ref('5555')
const wirelessCode = ref('')
const wirelessResult = ref('')

async function loadHealth(serial: string) {
  healthLoading.value[serial] = true
  try {
    healthData.value[serial] = await api(`/api/phone/health/${serial}`)
  } catch { healthData.value[serial] = null }
  healthLoading.value[serial] = false
}

async function loadAllHealth() {
  for (const d of devices.value) loadHealth(d.serial)
}

function healthDots(serial: string): string[] {
  const h = healthData.value[serial]
  if (!h) return []
  const dots: string[] = []
  dots.push(h.portal?.http_responding ? 'green' : h.portal?.installed ? 'yellow' : 'red')
  dots.push(h.wifi?.connected ? 'green' : 'gray')
  dots.push(h.battery?.level > 20 ? 'green' : h.battery?.level > 5 ? 'yellow' : 'red')
  dots.push(h.storage?.free_mb > 1000 ? 'green' : h.storage?.free_mb > 500 ? 'yellow' : 'red')
  dots.push(h.screen_on ? 'green' : 'yellow')
  return dots
}

async function fixIssue(serial: string, issue: string) {
  await api(`/api/phone/health/${serial}/fix`, { method: 'POST', body: JSON.stringify({ issue }) })
  await loadHealth(serial)
}

async function goWireless(serial: string) {
  const res = await api('/api/phone/wireless/enable', { method: 'POST', body: JSON.stringify({ device: serial }) })
  if (res.ok) statusText.value = `WiFi enabled: ${res.wifi_ip}:${res.wifi_port}`
  else statusText.value = res.error || 'WiFi enable failed'
  await loadDevices()
}

async function wirelessConnect() {
  wirelessResult.value = 'Connecting...'
  const res = wirelessCode.value
    ? await api('/api/phone/wireless/pair', { method: 'POST', body: JSON.stringify({ ip: wirelessIp.value, port: parseInt(wirelessPort.value), code: wirelessCode.value }) })
    : await api('/api/phone/wireless/connect', { method: 'POST', body: JSON.stringify({ ip: wirelessIp.value, port: parseInt(wirelessPort.value) }) })
  wirelessResult.value = res.ok ? `Connected: ${res.device_serial || wirelessIp.value}` : (res.error || 'Failed')
  if (res.ok) { showWirelessModal.value = false; await loadDevices() }
}

/* ── agent chat ─────────────────────────────────────────────────────── */
const chatMessages = ref<{role: string; content: string; tool_name?: string; tool_args?: any; image?: string}[]>([])
const chatInput = ref('')
const chatSending = ref(false)
const chatSessionId = ref('')
let chatAbortController: AbortController | null = null
const chatTokens = ref(0)
const chatActivity = ref('')  // brief status during thinking
const chatVerbose = ref(false) // show tool calls inline in chat

// Markdown rendering
function renderMd(text: string): string {
  const w = window as any
  if (w.marked) return w.marked.parse(text)
  return text.replace(/\n/g, '<br>')
}
// Load marked.js
if (!(window as any).marked) {
  const s = document.createElement('script')
  s.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js'
  document.head.appendChild(s)
}
const chatProvider = ref(localStorage.getItem('agent_provider') || 'claude-code')
const chatModel = ref(localStorage.getItem('agent_model') || 'sonnet')
const CHAT_PROVIDERS = [
  { id: 'claude-code', label: 'Claude Code (free)', models: ['sonnet', 'opus', 'haiku'] },
  { id: 'anthropic', label: 'Claude API', models: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514'] },
  { id: 'openrouter', label: 'OpenRouter', models: ['anthropic/claude-sonnet-4', 'google/gemini-2.5-pro'] },
  { id: 'ollama', label: 'Ollama', models: [] },
]
const chatConversations = ref<{id: string; title: string; provider: string; model: string; message_count: number; updated_at: string}[]>([])

async function loadConversations() {
  if (!selectedDevice.value) return
  try {
    const resp = await fetch(`/api/agent-chat/conversations?device=${selectedDevice.value}`)
    chatConversations.value = await resp.json()
  } catch { chatConversations.value = [] }
}

async function resumeConversation(cid: string) {
  try {
    const resp = await fetch(`/api/agent-chat/conversation/${cid}/resume`, { method: 'POST' })
    const data = await resp.json()
    if (data.ok) {
      chatSessionId.value = data.session_id
      chatProvider.value = data.provider || chatProvider.value
      chatModel.value = data.model || chatModel.value
      chatMessages.value = (data.messages || []).map((m: any) => ({
        role: m.role, content: m.content, tool_name: m.tool_name, tool_args: m.tool_args
      }))
      await nextTick()
      const el = document.getElementById('agent-chat-scroll')
      if (el) el.scrollTop = el.scrollHeight
    }
  } catch (e: any) { console.error('resume failed', e) }
}

async function deleteConversation(cid: string) {
  try { await fetch(`/api/agent-chat/conversation/${cid}`, { method: 'DELETE' }) } catch {}
  await loadConversations()
  if (chatSessionId.value === cid) chatClear()
}

function onProviderChange() {
  localStorage.setItem('agent_provider', chatProvider.value)
  const p = CHAT_PROVIDERS.find(p => p.id === chatProvider.value)
  if (p?.models.length) { chatModel.value = p.models[0]; localStorage.setItem('agent_model', chatModel.value) }
  chatSessionId.value = '' // reset session on provider change
}
function onModelChange() { localStorage.setItem('agent_model', chatModel.value); chatSessionId.value = '' }

async function chatSend() {
  if (!chatInput.value.trim() || chatSending.value || !selectedDevice.value) return
  const msg = chatInput.value.trim()
  chatInput.value = ''
  chatMessages.value.push({ role: 'user', content: msg })
  chatSending.value = true
  chatActivity.value = 'Reading screen...'
  chatTokens.value += msg.length / 4  // rough estimate
  // Auto-start stream
  if (!streaming.value) { singleStreamMode.value = 'mjpeg'; startStream() }

  try {
    chatAbortController = new AbortController()
    const body: any = { content: msg, device: selectedDevice.value, provider: chatProvider.value, model: chatModel.value }
    if (chatSessionId.value) body.session_id = chatSessionId.value
    const resp = await fetch('/api/agent-chat/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: chatAbortController.signal,
    })
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentText = ''

    while (reader) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'session' && event.session_id) {
            chatSessionId.value = event.session_id
          } else if (event.type === 'text') {
            chatActivity.value = ''
            // Check if last message is assistant — append to it. Otherwise start new.
            const last = chatMessages.value[chatMessages.value.length - 1]
            if (last?.role === 'assistant') {
              last.content += event.content
            } else {
              chatMessages.value.push({ role: 'assistant', content: event.content })
            }
          } else if (event.type === 'tool_call') {
            const TOOL_EMOJI: Record<string, string> = {
              screenshot: '📸', get_screen_tree: '🌳', get_elements: '🔍', tap: '👆', tap_element: '👆',
              swipe: '👋', type_text: '⌨️', press_key: '🔘', launch_app: '🚀', force_stop: '⛔',
              ocr_screen: '🔤', find_on_screen: '🔎', classify_screen: '📋', get_phone_state: '📱',
              shell: '💻', list_packages: '📦', clipboard_get: '📋', clipboard_set: '📋', list_skills: '🧩', run_skill: '⚡',
              long_press: '✊', open_notifications: '🔔', get_notifications: '🔔', wait: '⏳',
            }
            const SHORT_NAME: Record<string, string> = {
              get_screen_tree: 'tree', get_elements: 'elements', get_phone_state: 'state',
              screenshot_annotated: 'annotated ss', screenshot_cropped: 'crop ss',
              find_on_screen: 'find', classify_screen: 'classify', ocr_screen: 'OCR',
              ocr_region: 'OCR region', list_packages: 'packages', list_skills: 'skills',
              launch_app: 'launch', force_stop: 'stop', type_text: 'type', press_key: 'key',
              tap_element: 'tap #', long_press: 'hold', open_notifications: 'notifs',
              get_notifications: 'notifs', clipboard_get: 'clip', clipboard_set: 'clip set',
              run_skill: 'skill', screenshot: 'screenshot',
            }
            const emoji = TOOL_EMOJI[event.name] || '🔧'
            const short = SHORT_NAME[event.name] || event.name
            chatActivity.value = `${emoji} ${short}...`
            if (chatVerbose.value) {
              chatMessages.value.push({ role: 'tool_call', content: `${emoji} ${event.name}(${JSON.stringify(event.args).slice(0, 120)})`, tool_name: event.name, tool_args: event.args })
            } else {
              // Brief: just emoji, or emoji + key info
              let brief = `${emoji} ${short}`
              const a = event.args || {}
              if (event.name === 'tap' && a.x) brief = `${emoji} (${a.x},${a.y})`
              else if (event.name === 'type_text' && a.text) brief = `${emoji} "${a.text.slice(0, 20)}"`
              else if (event.name === 'launch_app' && a.package) brief = `${emoji} ${a.package.split('.').pop()}`
              else if (event.name === 'press_key' && a.key) brief = `${emoji} ${a.key.replace('KEYCODE_', '')}`
              else if (event.name === 'swipe') brief = `${emoji} swipe`
              else if (event.name === 'shell' && a.command) brief = `${emoji} $ ${a.command.slice(0, 25)}`
              chatMessages.value.push({ role: 'tool_call', content: brief, tool_name: event.name })
            }
          } else if (event.type === 'tool_result') {
            chatActivity.value = '🤔 Thinking...'
            if (chatVerbose.value) {
              chatMessages.value.push({ role: 'tool_result', content: event.result?.slice(0, 300) || '', tool_name: event.name })
            }
          } else if (event.type === 'activity') {
            chatActivity.value = event.content || 'Working...'
          } else if (event.type === 'tokens') {
            // Real token count from Claude Code
            chatTokens.value = (event.input || 0) + (event.output || 0)
            if (event.cost) chatActivity.value = `💰 $${event.cost.toFixed(4)}`
          } else if (event.type === 'screenshot') {
            chatMessages.value.push({ role: 'screenshot', content: '', image: event.image })
          } else if (event.type === 'error') {
            chatMessages.value.push({ role: 'error', content: event.content })
            chatActivity.value = ''
          } else if (event.type === 'done') {
            currentText = ''
            chatActivity.value = ''
          }
          // Auto-scroll
          const el = document.getElementById('agent-chat-scroll')
          if (el) el.scrollTop = el.scrollHeight
        } catch {}
      }
    }
  } catch (e: any) {
    chatMessages.value.push({ role: 'error', content: e.message })
  }
  chatSending.value = false
  loadConversations()  // refresh conversation list after each turn
}

function chatStop() {
  if (chatAbortController) { chatAbortController.abort(); chatAbortController = null }
  // Kill the backend subprocess too
  if (chatSessionId.value) {
    fetch(`/api/agent-chat/stop/${chatSessionId.value}`, { method: 'POST' }).catch(() => {})
  }
  chatSending.value = false
  chatActivity.value = ''
  chatMessages.value.push({ role: 'error', content: 'Stopped by user' })
}

function chatClear() {
  chatMessages.value = []
  chatSessionId.value = ''
  chatTokens.value = 0
  chatActivity.value = ''
}

/* ── general ─────────────────────────────────────────────────────────── */
async function loadDevices() {
  try {
    const resp = await api('/api/phone/devices')
    devices.value = resp.devices || resp || []
    if (devices.value.length && !selectedDevice.value) selectedDevice.value = devices.value[0].serial
    statusText.value = devices.value.length ? `${devices.value.length} device(s)` : 'No devices'
  } catch (e: any) { statusText.value = e.message || 'ADB error' }
}

function updateNicknameRow() {
  const dev = devices.value.find(d => d.serial === selectedDevice.value)
  nickname.value = dev?.nickname || ''
}

async function saveNickname() {
  await api('/api/phone/nickname', { method: 'POST', body: JSON.stringify({ serial: selectedDevice.value, nickname: nickname.value }) })
  statusText.value = 'Nickname saved'
  await loadDevices()
}

async function pollLogs() {
  try {
    const resp = await api(`/api/logs?from=${srvSeq}&limit=50`)
    if (resp.lines?.length) {
      srvLogs.value.push(...resp.lines.map((l: any) => `[${l.level}] ${l.msg}`))
      srvSeq += resp.lines.length
      if (srvLogs.value.length > 200) srvLogs.value = srvLogs.value.slice(-100)
    }
  } catch {}
}

let multiLogTimer: number | null = null

onMounted(async () => {
  await loadDevices()
  loadAllHealth()
  loadConversations()
  logTimer = window.setInterval(pollLogs, 3000)
  multiLogTimer = window.setInterval(pollMultiLogs, 4000)
  pollMultiLogs()
})
watch(selectedDevice, () => { loadConversations(); chatClear() })
onUnmounted(() => {
  // Clean up all RTC sessions
  for (const serial of Object.keys(rtcSessions.value)) rtcStop(serial)
  if (logTimer) clearInterval(logTimer)
  if (multiLogTimer) clearInterval(multiLogTimer)
})
</script>

<template>
  <div class="phone-admin">
    <!-- Tab bar -->
    <div class="tab-bar">
      <div class="tab-group">
        <button class="tab-btn" :class="{ active: subTab === 'single' }" @click="subTab = 'single'">Single Device</button>
        <button class="tab-btn" :class="{ active: subTab === 'multi' }" @click="subTab = 'multi'">Multi Device</button>
      </div>
      <span class="status-text">{{ statusText }}</span>
    </div>

    <!-- ═══════════════ Single Device ═══════════════ -->
    <div v-if="subTab === 'single'" class="single-layout" style="grid-template-columns: 200px 1fr 280px">
      <!-- LEFT: Controls sidebar -->
      <div class="sidebar" style="overflow-y: auto">
        <!-- Device selector -->
        <div class="sidebar-section">
          <div class="section-label">DEVICE</div>
          <div class="device-row">
            <select v-model="selectedDevice" @change="updateNicknameRow" class="device-select">
              <option value="">-- no device --</option>
              <option v-for="d in devices" :key="d.serial" :value="d.serial">
                {{ d.connection === 'wifi' ? '\uD83D\uDCF6' : '\uD83D\uDD0C' }} {{ d.nickname || d.model || d.serial }}
              </option>
            </select>
            <button class="ctrl-btn" @click="loadDevices" title="Refresh devices">&#x27F3;</button>
          </div>
        </div>

        <!-- Stream controls -->
        <div class="sidebar-section">
          <div class="section-label">STREAM</div>
          <div class="btn-grid">
            <template v-if="!streaming">
              <button class="ctrl-btn ctrl-btn--webrtc" @click="singleStreamMode = 'rtc'; startStream()">&#x26A1; WebRTC</button>
              <button class="ctrl-btn ctrl-btn--mjpeg" @click="singleStreamMode = 'mjpeg'; startStream()">&#x25B6; MJPEG</button>
            </template>
            <template v-else>
              <button class="ctrl-btn ctrl-btn--stop" @click="stopStream">&#x23F9; Stop</button>
              <button class="ctrl-btn" @click="toggleSingleMode"
                :style="{ background: singleStreamMode === 'rtc' ? '#0ea5e922' : '#6366f122', color: singleStreamMode === 'rtc' ? '#38bdf8' : '#a5b4fc', borderColor: singleStreamMode === 'rtc' ? '#0ea5e955' : '#6366f155' }">
                &#x21C4;
              </button>
            </template>
          </div>
        </div>

        <!-- Hardware keys -->
        <div class="sidebar-section">
          <div class="section-label">CONTROLS</div>
          <div class="hw-keys-grid">
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_BACK')">&#x25C0; Back</button>
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_HOME')">&#x23FA; Home</button>
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_APP_SWITCH')">&#x2B1C; Rec</button>
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_POWER')">&#x23FB; Screen</button>
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_VOLUME_UP')">&#x1F50A; Vol+</button>
            <button class="ctrl-btn" @click="sendKeyTo(selectedDevice, 'KEYCODE_VOLUME_DOWN')">&#x1F509; Vol-</button>
            <button class="ctrl-btn" @click="toggleOverlay(selectedDevice)"
              :style="{ background: overlayOn[selectedDevice] ? '#fbbf24' : '', color: overlayOn[selectedDevice] ? '#000' : '#fbbf24' }"
              title="Toggle UI Grid">&#x1F522; Grid</button>
          </div>
        </div>

        <!-- Server logs (collapsible, closed by default) -->
        <div class="sidebar-section" :class="{ 'sidebar-section--grow': logsOpen }">
          <div class="section-label" style="cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px" @click="logsOpen = !logsOpen">
            <span style="font-size: 10px; transition: transform 0.2s" :style="{ transform: logsOpen ? 'rotate(90deg)' : 'rotate(0deg)' }">&#9654;</span>
            LOGS
            <span v-if="!logsOpen" style="font-size: 9px; color: var(--text-4); font-weight: 400">{{ filteredSrvLogs.length }} lines</span>
          </div>
          <template v-if="logsOpen">
            <div class="log-filter-row">
              <button v-for="f in LOG_FILTERS" :key="f"
                class="log-filter-btn" :class="{ active: logFilter === f }"
                @click="logFilter = f">{{ f }}</button>
            </div>
            <div class="log-scroll">
              <div v-for="(line, i) in filteredSrvLogs" :key="i"
                class="log-line"
                :style="{ color: line.includes('[ERROR]') || line.includes('[CRITICAL]') ? '#f87171' : line.includes('[WARN') ? '#fbbf24' : 'var(--text-4)' }">{{ line }}</div>
              <div v-if="!filteredSrvLogs.length" class="log-empty">Waiting for logs...</div>
            </div>
          </template>
        </div>
      </div>

      <!-- MIDDLE: Agent Chat -->
      <div style="display: flex; flex-direction: column; min-width: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden">
        <!-- Chat header -->
        <div style="padding: 6px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap">
          <span style="width: 6px; height: 6px; border-radius: 50%"
            :style="{ background: chatSending ? '#f59e0b' : chatMessages.length ? '#22c55e' : '#475569' }"></span>
          <span style="font-size: 11px; font-weight: 600; color: var(--text-2)">Agent</span>
          <!-- Conversation picker -->
          <select @change="(e: any) => { if (e.target.value === '__new__') chatClear(); else resumeConversation(e.target.value); e.target.value = chatSessionId || '__new__'; }"
            style="font-size: 10px; padding: 2px 6px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 4px; color: var(--text-3); max-width: 130px">
            <option value="__new__">+ New chat</option>
            <option v-for="c in chatConversations" :key="c.id" :value="c.id"
              :selected="c.id === chatSessionId">
              {{ c.title || 'Untitled' }} ({{ c.message_count }})
            </option>
          </select>
          <select v-model="chatProvider" @change="onProviderChange"
            style="font-size: 10px; padding: 2px 6px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 4px; color: var(--text-3)">
            <option v-for="p in CHAT_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
          <select v-model="chatModel" @change="onModelChange"
            style="font-size: 10px; padding: 2px 6px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 4px; color: var(--text-3); max-width: 140px">
            <option v-for="m in (CHAT_PROVIDERS.find(p => p.id === chatProvider)?.models || [])" :key="m" :value="m">{{ m }}</option>
          </select>
          <span style="margin-left: auto; display: flex; align-items: center; gap: 6px">
            <button @click="chatVerbose = !chatVerbose"
              style="font-size: 9px; padding: 2px 6px; border-radius: 4px; cursor: pointer; border: 1px solid #2a3044"
              :style="{ background: chatVerbose ? '#6366f133' : '#1a1f2e', color: chatVerbose ? '#a5b4fc' : '#64748b' }"
              :title="chatVerbose ? 'Verbose: showing all tool calls + results' : 'Brief: showing tool names only'">
              {{ chatVerbose ? 'Verbose' : 'Brief' }}
            </button>
            <span v-if="chatTokens > 0" style="font-size: 9px; color: var(--text-4); font-family: monospace" :title="`~${Math.round(chatTokens)} tokens used`">
              ~{{ chatTokens > 1000 ? (chatTokens / 1000).toFixed(1) + 'k' : Math.round(chatTokens) }} tok
            </span>
            <button v-if="chatMessages.length" @click="chatClear" style="font-size: 9px; padding: 2px 8px; background: #1a1f2e; border: 1px solid #2a3044; border-radius: 4px; color: #94a3b8; cursor: pointer">Clear</button>
            <button v-if="chatSessionId && chatConversations.some(c => c.id === chatSessionId)" @click="deleteConversation(chatSessionId)"
              style="font-size: 9px; padding: 2px 6px; background: #1a1f2e; border: 1px solid #2a3044; border-radius: 4px; color: #ef4444; cursor: pointer" title="Delete conversation">&#x1F5D1;</button>
          </span>
        </div>
        <!-- Messages -->
        <div id="agent-chat-scroll" style="flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px">
          <div v-if="!chatMessages.length" style="color: var(--text-4); font-size: 12px; text-align: center; padding: 40px 20px; line-height: 1.6">
            Chat with the agent to control this phone.<br/>
            Try: "What app is open?" or "Open TikTok and search for cats"
          </div>
          <div v-for="(m, i) in chatMessages" :key="i"
            :style="{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: m.role === 'screenshot' ? '200px' : '85%',
            }">
            <!-- User message -->
            <div v-if="m.role === 'user'" style="background: #6366f1; color: white; padding: 8px 12px; border-radius: 12px 12px 2px 12px; font-size: 12px; line-height: 1.5">
              {{ m.content }}
            </div>
            <!-- Assistant text (markdown) -->
            <div v-else-if="m.role === 'assistant'" class="agent-md" style="background: var(--bg-deep); color: var(--text-1); padding: 8px 12px; border-radius: 12px 12px 12px 2px; font-size: 12px; line-height: 1.6"
              v-html="renderMd(m.content)"></div>
            <!-- Tool call (compact inline) -->
            <div v-else-if="m.role === 'tool_call'"
              style="font-size: 10px; color: #38bdf8; padding: 2px 8px; display: inline-block; background: #0ea5e908; border-radius: 10px; border: 1px solid #0ea5e922">
              {{ m.content }}
            </div>
            <!-- Tool result (verbose only, compact) -->
            <div v-else-if="m.role === 'tool_result'"
              style="font-size: 9px; font-family: 'JetBrains Mono', monospace; color: #475569; padding: 2px 8px; max-height: 60px; overflow: hidden; text-overflow: ellipsis; border-left: 2px solid #1e293b; margin-left: 8px">
              {{ m.content }}
            </div>
            <!-- Screenshot -->
            <img v-else-if="m.role === 'screenshot' && m.image" :src="'data:image/jpeg;base64,' + m.image"
              style="width: 100%; border-radius: 8px; border: 1px solid var(--border)" />
            <!-- Error -->
            <div v-else-if="m.role === 'error'" style="font-size: 11px; color: #f87171; padding: 6px 10px; background: #ef444411; border-radius: 6px; border-left: 2px solid #ef4444">
              {{ m.content }}
            </div>
          </div>
          <!-- Activity indicator -->
          <div v-if="chatSending" style="align-self: flex-start; padding: 4px 12px; display: flex; align-items: center; gap: 6px">
            <span style="display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: #f59e0b; animation: pulse 1s infinite"></span>
            <span style="font-size: 10px; color: #f59e0b; font-family: monospace">{{ chatActivity || 'Thinking...' }}</span>
          </div>
        </div>
        <!-- Input -->
        <div style="padding: 8px 12px; border-top: 1px solid var(--border); display: flex; gap: 8px; flex-shrink: 0">
          <input v-model="chatInput" @keyup.enter="!chatSending && chatSend()" :disabled="!selectedDevice"
            :placeholder="chatSending ? 'Agent is working... type your next message' : 'Tell the agent what to do...'"
            style="flex: 1; padding: 8px 12px; font-size: 12px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 8px; color: var(--text-1); outline: none" />
          <button v-if="chatSending" @click="chatStop"
            style="padding: 8px 14px; font-size: 11px; font-weight: 600; background: #ef4444; color: white; border: none; border-radius: 8px; cursor: pointer">Stop</button>
          <button v-else @click="chatSend" :disabled="!selectedDevice || !chatInput.trim()"
            style="padding: 8px 16px; font-size: 11px; font-weight: 600; background: #6366f1; color: white; border: none; border-radius: 8px; cursor: pointer; transition: opacity 0.15s"
            :style="{ opacity: !selectedDevice || !chatInput.trim() ? 0.3 : 1 }">Send</button>
        </div>
      </div>

      <!-- RIGHT: Phone stream -->
      <div class="stream-panel">
        <div class="stream-viewport">
          <video v-if="streaming && singleStreamMode === 'rtc'" :id="`rtc-video-${selectedDevice}`" autoplay playsinline muted
            class="stream-media"
            @mousedown="videoMouseDown(selectedDevice, $event)"
            @mousemove="videoMouseMove(selectedDevice)"
            @mouseup="videoMouseUp(selectedDevice, $event)"
            @mouseleave="videoMouseLeave(selectedDevice)"
            @touchstart="videoTouchStart(selectedDevice, $event)"
            @touchmove="videoTouchMove(selectedDevice)"
            @touchend="videoTouchEnd(selectedDevice, $event)" />
          <img v-else-if="streaming && singleStreamMode === 'mjpeg' && singleMjpegUrl"
            :src="singleMjpegUrl"
            class="stream-media"
            draggable="false"
            @mousedown="mjpegMouseDown(selectedDevice, $event)"
            @mousemove="videoMouseMove(selectedDevice)"
            @mouseup="mjpegMouseUp(selectedDevice, $event)"
            @mouseleave="videoMouseLeave(selectedDevice)"
            @dragstart.prevent />
          <div v-if="!streaming" class="stream-placeholder">
            Select device &amp; start stream<br/>or chat — auto-starts
          </div>
          <div v-if="blackWarning[selectedDevice]" class="black-warning">
            FLAG_SECURE — switch to MJPEG
            <button @click="blackWarning[selectedDevice] = false; toggleSingleMode()" class="black-warning-btn">Switch</button>
          </div>
          <!-- Frozen stream overlay -->
          <div v-if="streamFrozen[selectedDevice]" class="frozen-overlay" @click="reconnectStream(selectedDevice)">
            <div class="frozen-ghost">&#x1F47B;</div>
            <div class="frozen-text">Stream frozen</div>
            <div class="frozen-hint">Tap to reconnect</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ Multi Device ═══════════════ -->
    <div v-if="subTab === 'multi'">
      <!-- Controls header -->
      <div class="multi-header">
        <button class="ctrl-btn ctrl-btn--webrtc" @click="startAllStreams('rtc')">&#x26A1; Start All (WebRTC)</button>
        <button class="ctrl-btn ctrl-btn--mjpeg" @click="startAllStreams('mjpeg')">&#x25B6; Start All (MJPEG)</button>
        <button class="ctrl-btn ctrl-btn--stop" @click="stopAllStreams">&#x23F9; Stop All</button>
        <button class="ctrl-btn" @click="showWirelessModal = true" style="background: #0ea5e922; color: #38bdf8; border-color: #0ea5e955">&#x1F4F6; WiFi Connect</button>
        <button class="ctrl-btn" @click="loadAllHealth" style="font-size: 10px">Health &#x27F3;</button>
        <span class="device-count">{{ devices.length }} device(s)</span>
      </div>

      <div class="multi-grid"
        :style="{ gridTemplateColumns: devices.length <= 1 ? '1fr' : devices.length === 2 ? 'repeat(2, 1fr)' : devices.length === 3 ? 'repeat(3, 1fr)' : 'repeat(4, 1fr)' }">
        <div v-for="d in devices" :key="d.serial" class="multi-card">
          <!-- Header -->
          <div class="multi-card-header">
            <span class="multi-device-name">{{ d.connection === 'wifi' ? '\uD83D\uDCF6' : '\uD83D\uDD0C' }} {{ d.nickname || d.model || d.serial }}</span>
            <span v-if="healthData[d.serial]" class="health-dots" :title="'Portal / WiFi / Battery / Storage / Screen'">
              <span v-for="(c, i) in healthDots(d.serial)" :key="i" class="health-dot" :style="{ background: c === 'green' ? '#22c55e' : c === 'yellow' ? '#f59e0b' : c === 'red' ? '#ef4444' : '#475569' }"></span>
            </span>
            <button v-if="healthData[d.serial]?.wifi?.ip && !d.serial.includes(':')" class="hw-key-btn"
              @click="goWireless(d.serial)" title="Go Wireless" style="color: #38bdf8">&#x1F4F6;</button>
            <div class="multi-hw-keys">
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 4)" title="Back">&#x25C0;</button>
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 3)" title="Home">&#x2302;</button>
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 187)" title="Recents">&#x25A6;</button>
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 26)" title="Power">&#x23FB;</button>
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 24)" title="Vol+">&#x1F50A;</button>
              <button class="hw-key-btn" @click="sendKeyTo(d.serial, 25)" title="Vol-">&#x1F509;</button>
              <button class="hw-key-btn" @click="toggleOverlay(d.serial)"
                :style="{ background: overlayOn[d.serial] ? '#fbbf24' : '', color: overlayOn[d.serial] ? '#000' : '#fbbf24' }" title="Toggle UI Grid">&#x1F522;</button>
            </div>
            <div class="multi-stream-btns">
              <span class="multi-mode-badge"
                :style="multiStreamMode[d.serial] === 'mjpeg' ? { background: '#6366f133', color: '#a5b4fc' } : rtcStatus[d.serial] === 'Streaming' ? { background: '#22c55e22', color: '#4ade80' } : { color: '#475569' }">
                {{ multiStreaming[d.serial] ? (multiStreamMode[d.serial] === 'mjpeg' ? 'MJPEG' : (rtcStatus[d.serial] || 'RTC')) : '' }}
              </span>
              <button v-if="rtcStatus[d.serial]?.includes('Portal') || rtcStatus[d.serial]?.includes('fix')"
                class="ctrl-btn ctrl-btn--fix"
                @click="rtcFixPortal(d.serial)" title="Fix Portal">Fix</button>
              <template v-if="!multiStreaming[d.serial]">
                <button class="ctrl-btn ctrl-btn--webrtc ctrl-btn--tiny" @click="startMultiStream(d.serial, 'rtc')" title="WebRTC">&#x26A1;</button>
                <button class="ctrl-btn ctrl-btn--mjpeg ctrl-btn--tiny" @click="startMultiStream(d.serial, 'mjpeg')" title="MJPEG">&#x25B6;</button>
              </template>
              <template v-else>
                <button class="ctrl-btn ctrl-btn--stop ctrl-btn--tiny" @click="stopMultiStream(d.serial)">&#x23F9;</button>
                <button class="ctrl-btn ctrl-btn--tiny" @click="toggleMultiMode(d.serial)"
                  :style="{ background: multiStreamMode[d.serial] === 'rtc' ? '#0ea5e922' : '#6366f122', color: multiStreamMode[d.serial] === 'rtc' ? '#38bdf8' : '#a5b4fc', borderColor: multiStreamMode[d.serial] === 'rtc' ? '#0ea5e955' : '#6366f155' }"
                  :title="'Switch to ' + (multiStreamMode[d.serial] === 'rtc' ? 'MJPEG' : 'WebRTC')">&#x21C4;</button>
              </template>
              <button class="ctrl-btn ctrl-btn--tiny" @click="selectedDevice = d.serial; subTab = 'single'; startStream()" title="Expand">&#x2197;</button>
            </div>
          </div>

          <!-- Stream area -->
          <div class="multi-stream-area">
            <!-- WebRTC video -->
            <video v-if="multiStreaming[d.serial] && multiStreamMode[d.serial] === 'rtc'" :id="`rtc-video-${d.serial}`" autoplay playsinline muted
              class="multi-stream-media"
              @mousedown="videoMouseDown(d.serial, $event)"
              @mousemove="videoMouseMove(d.serial)"
              @mouseup="videoMouseUp(d.serial, $event)"
              @mouseleave="videoMouseLeave(d.serial)"
              @touchstart="videoTouchStart(d.serial, $event)"
              @touchmove="videoTouchMove(d.serial)"
              @touchend="videoTouchEnd(d.serial, $event)" />
            <!-- MJPEG img -->
            <img v-else-if="multiStreaming[d.serial] && multiStreamMode[d.serial] === 'mjpeg' && mjpegUrls[d.serial]"
              :src="mjpegUrls[d.serial]"
              class="multi-stream-media"
              draggable="false"
              @mousedown="mjpegMouseDown(d.serial, $event)"
              @mousemove="videoMouseMove(d.serial)"
              @mouseup="mjpegMouseUp(d.serial, $event)"
              @mouseleave="videoMouseLeave(d.serial)"
              @dragstart.prevent />
            <div v-else class="multi-stream-placeholder">Press &#x26A1; or &#x25B6; to stream</div>
            <!-- Black screen warning -->
            <div v-if="blackWarning[d.serial]" class="black-warning black-warning--compact">
              FLAG_SECURE — switch to MJPEG
              <button @click="blackWarning[d.serial] = false; toggleMultiMode(d.serial)" class="black-warning-btn">Switch</button>
            </div>
            <!-- Frozen stream overlay -->
            <div v-if="streamFrozen[d.serial]" class="frozen-overlay" @click="reconnectStream(d.serial)">
              <div class="frozen-ghost">&#x1F47B;</div>
              <div class="frozen-text">Frozen</div>
              <div class="frozen-hint">Tap to reconnect</div>
            </div>
          </div>

          <!-- Per-device logs -->
          <div class="multi-logs-area">
            <div class="multi-logs-header">&#x25CF; Logs</div>
            <div class="multi-logs-scroll">
              <div v-for="(line, i) in (multiLogs[d.serial] || []).slice(-30)" :key="i"
                class="multi-log-line"
                :style="{
                  color: line.includes('[ERROR]') || line.includes('[CRITICAL]') ? '#f87171'
                    : line.includes('[WARN') ? '#fbbf24'
                    : line.includes('[INFO]') ? '#34d399'
                    : '#5b7a5e',
                  borderLeft: line.includes('[ERROR]') ? '2px solid #f87171'
                    : line.includes('[WARN') ? '2px solid #fbbf24'
                    : '2px solid transparent',
                  paddingLeft: '6px'
                }">{{ line }}</div>
              <div v-if="!(multiLogs[d.serial] || []).length" class="multi-log-empty">waiting for logs...</div>
            </div>
          </div>
        </div>
        <div v-if="!devices.length" class="multi-empty">
          No devices connected.
        </div>
      </div>
    </div>
    <!-- Wireless connect modal -->
    <div v-if="showWirelessModal" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showWirelessModal = false">
      <div class="card" style="width: 360px">
        <h3 class="font-bold text-sm mb-3" style="color: var(--text-1)">Connect WiFi Device</h3>
        <div class="mb-2">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Device IP</label>
          <input v-model="wirelessIp" placeholder="192.168.1.42" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
        </div>
        <div class="mb-2">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Port (default 5555)</label>
          <input v-model="wirelessPort" placeholder="5555" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
        </div>
        <div class="mb-3">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Pairing code (Android 11+ only, leave blank for reconnect)</label>
          <input v-model="wirelessCode" placeholder="123456" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
        </div>
        <div v-if="wirelessResult" class="mb-2 p-2 rounded text-xs" style="background: var(--bg-deep); color: var(--text-2)">{{ wirelessResult }}</div>
        <div class="flex gap-2">
          <button class="btn btn-primary" @click="wirelessConnect">Connect</button>
          <button class="btn" @click="showWirelessModal = false">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Agent markdown ──────────────────────────────────────────────── */
.agent-md :deep(h1), .agent-md :deep(h2), .agent-md :deep(h3) { font-size: 13px; font-weight: 700; margin: 8px 0 4px; color: var(--text-1); }
.agent-md :deep(p) { margin: 4px 0; }
.agent-md :deep(ul), .agent-md :deep(ol) { margin: 4px 0; padding-left: 18px; }
.agent-md :deep(li) { margin: 2px 0; }
.agent-md :deep(code) { background: #1e293b; padding: 1px 4px; border-radius: 3px; font-size: 11px; color: #a5b4fc; }
.agent-md :deep(pre) { background: #0a0e14; padding: 8px; border-radius: 6px; overflow-x: auto; font-size: 10px; margin: 6px 0; }
.agent-md :deep(pre code) { background: none; padding: 0; }
.agent-md :deep(table) { border-collapse: collapse; width: 100%; font-size: 11px; margin: 6px 0; }
.agent-md :deep(th), .agent-md :deep(td) { border: 1px solid #1e293b; padding: 4px 8px; text-align: left; }
.agent-md :deep(th) { background: #111827; font-weight: 600; }
.agent-md :deep(strong) { color: var(--text-1); }
.agent-md :deep(hr) { border: none; border-top: 1px solid #1e293b; margin: 8px 0; }

/* ── Animation ──────────────────────────────────────────────────── */
@keyframes fadeInOut {
  0% { opacity: 0; transform: translateX(-50%) translateY(-4px); }
  8% { opacity: 1; transform: translateX(-50%) translateY(0); }
  75% { opacity: 1; }
  100% { opacity: 0; }
}

/* ── Root ────────────────────────────────────────────────────────── */
.phone-admin {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 80px);
  overflow: hidden;
}

/* ── Tab Bar ─────────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
  flex-shrink: 0;
}

.tab-group {
  display: flex;
  gap: 2px;
  background: var(--bg-deep);
  border-radius: 8px;
  padding: 3px;
  border: 1px solid var(--border);
}

.tab-btn {
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  background: transparent;
  color: var(--text-4);
  transition: all 0.15s;
}
.tab-btn:hover { color: var(--text-2); }
.tab-btn.active {
  background: var(--accent);
  color: #fff;
}

.status-text {
  font-size: 11px;
  color: var(--text-4);
}

/* ── Single Device Layout ────────────────────────────────────────── */
.single-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Stream panel (left) */
.stream-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 0;
}

.stream-viewport {
  position: relative;
  width: 100%;
  height: 100%;
  max-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #070b10;
  border-radius: 6px;
  overflow: hidden;
}

.stream-media {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}

.stream-placeholder {
  color: var(--text-4);
  font-size: 13px;
  text-align: center;
  padding: 40px;
}

/* Sidebar (right) */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-section {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.sidebar-section:last-child { border-bottom: none; }

.sidebar-section--grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.section-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-4);
  margin-bottom: 8px;
  text-transform: uppercase;
}

/* Device selector */
.device-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.device-select {
  flex: 1;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  color: var(--text-1);
}

.nickname-row {
  margin-top: 6px;
}

.nickname-edit {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nickname-input {
  flex: 1;
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 12px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  color: var(--text-1);
}

/* Control buttons */
.ctrl-btn {
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-2);
  transition: all 0.12s;
  white-space: nowrap;
}
.ctrl-btn:hover { border-color: var(--accent); color: var(--text-1); }

.ctrl-btn--webrtc { background: #0ea5e9; color: #fff; border-color: #0ea5e9; }
.ctrl-btn--webrtc:hover { background: #0284c7; border-color: #0284c7; }
.ctrl-btn--mjpeg { background: var(--accent); color: #fff; border-color: var(--accent); }
.ctrl-btn--mjpeg:hover { background: #4f46e5; border-color: #4f46e5; }
.ctrl-btn--stop { border-color: #475569; color: var(--text-3); }
.ctrl-btn--confirm { color: #34d399; border-color: #34d399; }
.ctrl-btn--fix { background: #f59e0b; color: #000; border: none; font-size: 9px; padding: 2px 6px; }

.ctrl-btn--tiny { font-size: 9px; padding: 2px 6px; }

.btn-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.stream-status-line {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.stream-status-text {
  font-size: 10px;
  color: var(--text-4);
}

/* Hardware keys grid */
.hw-keys-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 3px;
}
.hw-keys-grid .ctrl-btn {
  padding: 4px 2px;
  font-size: 9px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Log filter row */
.log-filter-row {
  display: flex;
  gap: 3px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.log-filter-btn {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-deep);
  color: var(--text-3);
  border: 1px solid var(--border);
  transition: all 0.12s;
}
.log-filter-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 700;
}

.log-scroll {
  flex: 1;
  min-height: 60px;
  max-height: 180px;
  overflow-y: auto;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--bg-deep);
  font-family: 'Courier New', monospace;
  font-size: 10px;
  line-height: 1.6;
}
.log-scroll--bot { color: #10b981; }

.log-line {
  color: var(--text-4);
  word-break: break-all;
}

.log-empty {
  color: var(--text-4);
  font-style: italic;
}

/* Bot log select */
.bot-log-select {
  width: 100%;
  font-size: 11px;
  padding: 4px 8px;
  margin-bottom: 6px;
  background: var(--bg-deep);
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: 5px;
}

/* Black screen warning */
.black-warning {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  background: #f59e0bee;
  color: #000;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  z-index: 10;
  pointer-events: auto;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
  animation: fadeInOut 6s ease-in-out forwards;
}
.black-warning--compact {
  padding: 4px 10px;
  font-size: 9px;
  gap: 6px;
}

.black-warning-btn {
  background: #000;
  color: #f59e0b;
  border: none;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}

/* ── Frozen stream overlay ──────────────────────────────────────── */
.frozen-overlay {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: rgba(10, 15, 12, 0.85);
  backdrop-filter: blur(4px);
  cursor: pointer; z-index: 10;
  border-radius: inherit;
}
.frozen-ghost { font-size: 48px; margin-bottom: 8px; opacity: 0.9; }
.frozen-text { font-size: 14px; font-weight: 700; color: #f59e0b; letter-spacing: 0.5px; }
.frozen-hint { font-size: 11px; color: #8a9a8d; margin-top: 4px; }

/* ── Multi Device Layout ─────────────────────────────────────────── */
.multi-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.device-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-4);
}

.multi-grid {
  display: grid;
  gap: 8px;
  height: calc(100vh - 180px);
}

.multi-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-height: 0;
}

.multi-card-header {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.multi-device-name {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
}

.health-dots {
  display: flex;
  gap: 3px;
  align-items: center;
  margin-left: 4px;
}
.health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.multi-hw-keys {
  display: flex;
  gap: 2px;
  margin-left: 4px;
}

.hw-key-btn {
  padding: 2px 5px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-3);
  font-size: 10px;
  cursor: pointer;
  transition: border-color 0.12s;
}
.hw-key-btn:hover { border-color: var(--accent); }

.multi-stream-btns {
  margin-left: auto;
  display: flex;
  gap: 3px;
  align-items: center;
}

.multi-mode-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 3px;
}

/* Stream area */
.multi-stream-area {
  position: relative;
  flex: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #070b10;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.multi-stream-media {
  max-height: 100%;
  max-width: 100%;
  object-fit: contain;
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}

.multi-stream-placeholder {
  color: #334155;
  font-size: 11px;
}

/* Per-device logs */
.multi-logs-area {
  flex: 1;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  background: #050a0f;
  min-height: 0;
  overflow: hidden;
}

.multi-logs-header {
  padding: 3px 8px;
  font-size: 9px;
  font-weight: 600;
  color: #22c55e;
  border-bottom: 1px solid #0f1a12;
  flex-shrink: 0;
  background: #071209;
}

.multi-logs-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px 6px;
  font-family: 'Courier New', monospace;
  font-size: 9px;
  line-height: 1.5;
}

.multi-log-line {
  padding-left: 6px;
}

.multi-log-empty {
  color: #1a3020;
  font-style: italic;
}

.multi-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-4);
  font-size: 12px;
  padding: 40px 0;
}
</style>
