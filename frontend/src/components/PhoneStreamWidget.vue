<script setup lang="ts">
/**
 * PhoneStreamWidget — reusable phone stream + controls component.
 *
 * Props:
 *   serial      — device serial (required)
 *   label       — display name (optional, falls back to serial)
 *   mode        — 'screenshot' | 'mjpeg' (default: 'screenshot')
 *   showKeys    — show hardware key buttons (default: true)
 *   showVolume  — show vol+/vol- buttons (default: false)
 *   showOverlay — show overlay toggle button (default: false)
 *   showRecording — show screen recording controls (default: true)
 *   compact     — smaller padding/fonts (default: false)
 *   autoStream  — start streaming on mount (default: false)
 *   fps         — screenshot poll interval in ms (default: 300)
 *
 * Emits:
 *   tap(x, y, streamW, streamH)  — user clicked/tapped on the stream
 */
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { api } from '@/composables/useApi'

const props = withDefaults(defineProps<{
  serial: string
  label?: string
  mode?: 'screenshot' | 'mjpeg'
  showKeys?: boolean
  showVolume?: boolean
  showOverlay?: boolean
  showRecording?: boolean
  compact?: boolean
  autoStream?: boolean
  fps?: number
}>(), {
  label: '',
  mode: 'screenshot',
  showKeys: true,
  showVolume: false,
  showOverlay: false,
  showRecording: true,
  compact: false,
  autoStream: false,
  fps: 300,
})

const emit = defineEmits<{
  tap: [x: number, y: number, streamW: number, streamH: number]
}>()

const streaming = ref(false)
const streamImg = ref('')
const mjpegUrl = ref('')
const overlayOn = ref(false)
const recording = ref(false)
const recordingBusy = ref(false)
const recordingStatusText = ref('')
const recordingFilename = ref('')
const recordingUrl = ref('')
const streamInfoStatus = ref('')
let timer: number | null = null

type RecordingResponse = {
  ok?: boolean
  running?: boolean
  filename?: string
  mode?: string
  url?: string
  error?: string
}

type StreamInfo = {
  ok?: boolean
  stream_url?: string
  effective_mode?: string
  fallback_mode?: string
  unsupported_actions?: string[]
}

const isIos = computed(() => props.serial?.startsWith('ios:') || false)
const platformLabel = computed(() => isIos.value ? 'iOS' : 'Android')
const streamMode = computed(() => isIos.value ? 'mjpeg' : props.mode)
const streamModeLabel = computed(() => {
  if (isIos.value && streamMode.value === 'mjpeg') return 'WDA MJPEG'
  return streamMode.value === 'mjpeg' ? 'MJPEG' : 'Screenshot'
})
const recordingButtonLabel = computed(() => {
  if (recordingBusy.value) return '...'
  return recording.value ? 'Stop Rec' : 'Record'
})
const recordingButtonTitle = computed(() => {
  if (recording.value) return 'Stop screen recording and save MP4'
  return isIos.value
    ? 'Record WDA MJPEG stream to MP4'
    : 'Record Android screen to MP4'
})
const keyButtons = computed(() => {
  if (isIos.value) {
    return [
      { label: 'Back', value: 'BACK', title: 'Back' },
      { label: 'Home', value: 'HOME', title: 'Home' },
      { label: 'Enter', value: 'ENTER', title: 'Enter' },
    ]
  }
  const keys: { label: string; value: number; title: string }[] = [
    { label: '\u25C0', value: 4, title: 'Back' },
    { label: '\u2302', value: 3, title: 'Home' },
    { label: '\u25A6', value: 187, title: 'Recents' },
    { label: '\u23FB', value: 26, title: 'Power' },
  ]
  if (props.showVolume) {
    keys.push({ label: 'Vol+', value: 24, title: 'Volume up' })
    keys.push({ label: 'Vol-', value: 25, title: 'Volume down' })
  }
  return keys
})

function defaultMjpegUrl(): string {
  const modeParam = isIos.value ? '&mode=wda-mjpeg' : ''
  return `/api/phone/stream?device=${encodeURIComponent(props.serial)}&fps=5${modeParam}`
}

async function resolveMjpegUrl(): Promise<string> {
  const fallback = defaultMjpegUrl()
  try {
    const mode = isIos.value ? 'mjpeg' : 'screencap'
    const info = await api<StreamInfo>(
      `/api/phone/stream-info?device=${encodeURIComponent(props.serial)}&fps=5&mode=${encodeURIComponent(mode)}`
    )
    streamInfoStatus.value = ''
    return info.stream_url || fallback
  } catch (error) {
    streamInfoStatus.value = error instanceof Error ? error.message.replace(/^API \d+:\s*/, '') : 'Stream metadata unavailable'
    return fallback
  }
}

async function startStream() {
  if (streaming.value) return
  streaming.value = true
  if (streamMode.value === 'mjpeg') {
    mjpegUrl.value = defaultMjpegUrl()
    mjpegUrl.value = await resolveMjpegUrl()
  } else {
    pollFrame()
    timer = window.setInterval(pollFrame, props.fps)
  }
}

function stopStream() {
  streaming.value = false
  if (timer) { clearInterval(timer); timer = null }
  streamImg.value = ''
  mjpegUrl.value = ''
  streamInfoStatus.value = ''
}

function toggleStream() {
  if (streaming.value) stopStream()
  else startStream()
}

async function pollFrame() {
  if (!props.serial) return
  try {
    const resp = await api(`/api/phone/screenshot/${props.serial}`)
    if (resp.ok && resp.image) streamImg.value = `data:image/jpeg;base64,${resp.image}`
  } catch {}
}

function sendKey(key: number | string) {
  if (!props.serial) return
  if (typeof key === 'string') {
    api('/api/phone/key', {
      method: 'POST',
      body: JSON.stringify({ device: props.serial, key })
    })
    return
  }
  api('/api/phone/input', {
    method: 'POST',
    body: JSON.stringify({ device: props.serial, action: 'keyevent', keycode: key })
  })
}

async function toggleOverlayFn() {
  if (isIos.value) return
  overlayOn.value = !overlayOn.value
  await api(`/api/phone/overlay/${props.serial}`, {
    method: 'POST', body: JSON.stringify({ visible: overlayOn.value })
  })
}

function handleClick(e: MouseEvent) {
  const el = e.target as HTMLImageElement
  const rect = el.getBoundingClientRect()
  // Screenshot polling is half-res; iOS WDA MJPEG already reports its own frame size.
  const sw = el.naturalWidth || 540
  const sh = el.naturalHeight || 1170
  const scale = isIos.value && streamMode.value === 'mjpeg' ? 1 : 2
  const streamW = sw * scale
  const streamH = sh * scale
  const x = Math.round((e.clientX - rect.left) / rect.width * streamW)
  const y = Math.round((e.clientY - rect.top) / rect.height * streamH)
  emit('tap', x, y, streamW, streamH)
  api('/api/phone/tap', {
    method: 'POST',
    body: JSON.stringify({ device: props.serial, x, y, stream_w: streamW, stream_h: streamH })
  })
}

function resetRecordingState() {
  recording.value = false
  recordingBusy.value = false
  recordingStatusText.value = ''
  recordingFilename.value = ''
  recordingUrl.value = ''
}

function applyRecordingStatus(result: RecordingResponse) {
  recording.value = !!result.running
  recordingFilename.value = result.filename || recordingFilename.value
  if (result.url) recordingUrl.value = result.url
  if (result.error) {
    recordingStatusText.value = result.error
  } else if (result.running) {
    recordingStatusText.value = result.mode ? `Recording: ${result.mode}` : 'Recording'
  } else if (result.url) {
    recordingStatusText.value = 'Saved recording'
  } else {
    recordingStatusText.value = ''
  }
}

function recordingErrorText(error: unknown) {
  if (error instanceof Error) return error.message.replace(/^API \d+:\s*/, '')
  return 'Recording request failed'
}

async function refreshRecordingStatus() {
  if (!props.serial) {
    resetRecordingState()
    return
  }
  try {
    const result = await api<RecordingResponse>(`/api/phone/recording/status/${encodeURIComponent(props.serial)}`)
    applyRecordingStatus(result)
  } catch (error) {
    recordingStatusText.value = recordingErrorText(error)
  }
}

async function toggleRecording() {
  if (!props.serial || recordingBusy.value) return
  recordingBusy.value = true
  recordingStatusText.value = ''
  try {
    const endpoint = recording.value ? '/api/phone/recording/stop' : '/api/phone/recording/start'
    const result = await api<RecordingResponse>(endpoint, {
      method: 'POST',
      body: JSON.stringify({ device: props.serial })
    })
    applyRecordingStatus(result)
  } catch (error) {
    recordingStatusText.value = recordingErrorText(error)
  } finally {
    recordingBusy.value = false
  }
}

// Auto-stream on mount if requested
onMounted(() => {
  if (props.autoStream && props.serial) startStream()
  void refreshRecordingStatus()
})
onUnmounted(() => stopStream())

// Restart stream if serial changes
watch(() => props.serial, (newVal, oldVal) => {
  if (newVal !== oldVal && streaming.value) {
    stopStream()
    if (newVal) startStream()
  }
  if (newVal !== oldVal) void refreshRecordingStatus()
})

defineExpose({ startStream, stopStream, streaming, refreshRecordingStatus, toggleRecording })
</script>

<template>
  <div class="psw" :class="{ 'psw--compact': compact }">
    <!-- Header -->
    <div class="psw-header">
      <span class="psw-status-dot" :style="{ background: streaming ? '#22c55e' : '#475569' }" :title="streaming ? 'Streaming' : 'Idle'"></span>
      <span class="psw-label">{{ label || serial?.slice(0, 10) || 'No device' }}</span>
      <span class="psw-platform">{{ platformLabel }}</span>
      <span class="psw-stream-mode">{{ streamModeLabel }}</span>
      <span v-if="recording" class="psw-recording-dot" title="Screen recording active"></span>
      <div class="psw-keys" v-if="showKeys">
        <button v-for="key in keyButtons" :key="String(key.value)" class="psw-key"
          @click="sendKey(key.value)" :title="key.title">{{ key.label }}</button>
        <button v-if="showOverlay && !isIos" class="psw-key"
          :style="{ background: overlayOn ? '#fbbf24' : '', color: overlayOn ? '#000' : '#fbbf24' }"
          @click="toggleOverlayFn" title="Toggle Overlay">&#x1F522;</button>
      </div>
      <button v-if="showRecording" class="psw-record-btn"
        :class="{ 'psw-record-btn--active': recording }"
        :disabled="!serial || recordingBusy"
        @click="toggleRecording"
        :title="recordingButtonTitle">
        {{ recordingButtonLabel }}
      </button>
      <a v-if="recordingUrl" class="psw-record-link" :href="recordingUrl" target="_blank" rel="noopener"
        :title="recordingFilename || 'Open recording'">MP4</a>
      <button class="psw-stream-btn" @click="toggleStream"
        :style="{ background: streaming ? '#ef444433' : '#22c55e33', color: streaming ? '#f87171' : '#4ade80' }">
        {{ streaming ? 'Stop' : 'Stream' }}
      </button>
    </div>
    <!-- Stream area -->
    <div class="psw-stream">
      <img v-if="streaming && streamMode === 'screenshot' && streamImg" :src="streamImg" class="psw-img"
        @click="handleClick" />
      <img v-else-if="streaming && streamMode === 'mjpeg' && mjpegUrl" :src="mjpegUrl" class="psw-img"
        draggable="false" @click="handleClick" @dragstart.prevent />
      <div v-else class="psw-placeholder">
        <slot name="placeholder">{{ streamInfoStatus || recordingStatusText || (isIos ? 'Start WDA stream' : 'Click Stream to watch') }}</slot>
      </div>
    </div>
    <div v-if="streamInfoStatus && streaming" class="psw-record-status" :title="streamInfoStatus">
      {{ streamInfoStatus }}
    </div>
    <div v-if="recordingStatusText && streaming" class="psw-record-status" :title="recordingStatusText">
      {{ recordingStatusText }}
    </div>
    <!-- Optional slot for extra content below stream (progress, logs, etc.) -->
    <slot name="footer"></slot>
  </div>
</template>

<style scoped>
.psw {
  display: flex;
  flex-direction: column;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e293b);
  border-radius: 10px;
  overflow: hidden;
  height: 100%;
}
.psw-header {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border, #1e293b);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.psw-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.psw-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-3, #94a3b8);
}
.psw-platform {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0;
  padding: 1px 5px;
  border-radius: 4px;
  background: #1f2937;
  color: #cbd5e1;
}
.psw-stream-mode {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0;
  padding: 1px 5px;
  border-radius: 4px;
  background: #0f172a;
  color: #38bdf8;
}
.psw-keys {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
}
.psw-key {
  padding: 2px 5px;
  background: #1a1f2e;
  border: 1px solid #2a3044;
  border-radius: 4px;
  color: #94a3b8;
  font-size: 10px;
  cursor: pointer;
  transition: background 0.12s;
}
.psw-key:hover { background: #252b3d; color: #e2e8f0; }
.psw-key:active { background: #6366f133; }
.psw-recording-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 0 2px #7f1d1d55;
  flex-shrink: 0;
}
.psw-record-btn {
  padding: 2px 7px;
  background: #1a1f2e;
  border: 1px solid #3f1d26;
  border-radius: 4px;
  color: #fca5a5;
  font-size: 9px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}
.psw-record-btn:hover:not(:disabled) {
  background: #3f1d26;
  color: #fecaca;
}
.psw-record-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.psw-record-btn--active {
  background: #ef444433;
  border-color: #ef444466;
  color: #fecaca;
}
.psw-record-link {
  padding: 2px 5px;
  border-radius: 4px;
  border: 1px solid #164e63;
  color: #67e8f9;
  font-size: 8px;
  font-weight: 700;
  text-decoration: none;
}
.psw-stream-btn {
  margin-left: auto;
  padding: 2px 8px;
  font-size: 9px;
  font-weight: 600;
  border-radius: 4px;
  border: none;
  cursor: pointer;
}
.psw-stream {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #070b10;
  min-height: 0;
  overflow: hidden;
}
.psw-img {
  max-height: 100%;
  max-width: 100%;
  object-fit: contain;
  cursor: crosshair;
}
.psw-placeholder {
  color: #334155;
  font-size: 11px;
  text-align: center;
  padding: 20px;
}
.psw-record-status {
  padding: 4px 8px;
  border-top: 1px solid #1e293b;
  color: #94a3b8;
  font-size: 9px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Compact mode */
.psw--compact .psw-header { padding: 4px 8px; }
.psw--compact .psw-label { font-size: 9px; }
.psw--compact .psw-platform { font-size: 8px; padding: 1px 4px; }
.psw--compact .psw-stream-mode { font-size: 8px; padding: 1px 4px; }
.psw--compact .psw-key { padding: 1px 4px; font-size: 9px; }
.psw--compact .psw-record-btn { font-size: 8px; padding: 1px 5px; }
.psw--compact .psw-record-link { font-size: 8px; padding: 1px 4px; }
.psw--compact .psw-stream-btn { font-size: 8px; padding: 1px 6px; }
</style>
