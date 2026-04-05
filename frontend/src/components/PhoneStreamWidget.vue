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
 *   compact     — smaller padding/fonts (default: false)
 *   autoStream  — start streaming on mount (default: false)
 *   fps         — screenshot poll interval in ms (default: 300)
 *
 * Emits:
 *   tap(x, y, streamW, streamH)  — user clicked/tapped on the stream
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { api } from '@/composables/useApi'

const props = withDefaults(defineProps<{
  serial: string
  label?: string
  mode?: 'screenshot' | 'mjpeg'
  showKeys?: boolean
  showVolume?: boolean
  showOverlay?: boolean
  compact?: boolean
  autoStream?: boolean
  fps?: number
}>(), {
  label: '',
  mode: 'screenshot',
  showKeys: true,
  showVolume: false,
  showOverlay: false,
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
let timer: number | null = null

function startStream() {
  if (streaming.value) return
  streaming.value = true
  if (props.mode === 'mjpeg') {
    mjpegUrl.value = `/api/phone/stream?device=${encodeURIComponent(props.serial)}&fps=5`
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

function sendKey(key: number) {
  if (!props.serial) return
  api('/api/phone/input', {
    method: 'POST',
    body: JSON.stringify({ device: props.serial, action: 'keyevent', keycode: key })
  })
}

async function toggleOverlayFn() {
  overlayOn.value = !overlayOn.value
  await api(`/api/phone/overlay/${props.serial}`, {
    method: 'POST', body: JSON.stringify({ visible: overlayOn.value })
  })
}

function handleClick(e: MouseEvent) {
  const el = e.target as HTMLImageElement
  const rect = el.getBoundingClientRect()
  // Scale from display coords to device coords (assume 1080x2400 or use naturalWidth)
  const sw = el.naturalWidth || 540
  const sh = el.naturalHeight || 1170
  const x = Math.round((e.clientX - rect.left) / rect.width * sw * 2)
  const y = Math.round((e.clientY - rect.top) / rect.height * sh * 2)
  emit('tap', x, y, sw * 2, sh * 2)
  // Also send tap directly
  api('/api/phone/tap', {
    method: 'POST',
    body: JSON.stringify({ device: props.serial, x, y, stream_w: sw * 2, stream_h: sh * 2 })
  })
}

// Auto-stream on mount if requested
onMounted(() => { if (props.autoStream && props.serial) startStream() })
onUnmounted(() => stopStream())

// Restart stream if serial changes
watch(() => props.serial, (newVal, oldVal) => {
  if (newVal !== oldVal && streaming.value) {
    stopStream()
    if (newVal) startStream()
  }
})

defineExpose({ startStream, stopStream, streaming })
</script>

<template>
  <div class="psw" :class="{ 'psw--compact': compact }">
    <!-- Header -->
    <div class="psw-header">
      <span class="psw-status-dot" :style="{ background: streaming ? '#22c55e' : '#475569' }" :title="streaming ? 'Streaming' : 'Idle'"></span>
      <span class="psw-label">{{ label || serial?.slice(0, 10) || 'No device' }}</span>
      <div class="psw-keys" v-if="showKeys">
        <button class="psw-key" @click="sendKey(4)" title="Back">&#x25C0;</button>
        <button class="psw-key" @click="sendKey(3)" title="Home">&#x2302;</button>
        <button class="psw-key" @click="sendKey(187)" title="Recents">&#x25A6;</button>
        <button class="psw-key" @click="sendKey(26)" title="Power">&#x23FB;</button>
        <button v-if="showVolume" class="psw-key" @click="sendKey(24)" title="Vol+">&#x1F50A;</button>
        <button v-if="showVolume" class="psw-key" @click="sendKey(25)" title="Vol-">&#x1F509;</button>
        <button v-if="showOverlay" class="psw-key"
          :style="{ background: overlayOn ? '#fbbf24' : '', color: overlayOn ? '#000' : '#fbbf24' }"
          @click="toggleOverlayFn" title="Toggle Overlay">&#x1F522;</button>
      </div>
      <button class="psw-stream-btn" @click="toggleStream"
        :style="{ background: streaming ? '#ef444433' : '#22c55e33', color: streaming ? '#f87171' : '#4ade80' }">
        {{ streaming ? 'Stop' : 'Stream' }}
      </button>
    </div>
    <!-- Stream area -->
    <div class="psw-stream">
      <img v-if="streaming && mode === 'screenshot' && streamImg" :src="streamImg" class="psw-img"
        @click="handleClick" />
      <img v-else-if="streaming && mode === 'mjpeg' && mjpegUrl" :src="mjpegUrl" class="psw-img"
        draggable="false" @click="handleClick" @dragstart.prevent />
      <div v-else class="psw-placeholder">
        <slot name="placeholder">Click Stream to watch</slot>
      </div>
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
.psw-keys {
  display: flex;
  gap: 2px;
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
/* Compact mode */
.psw--compact .psw-header { padding: 4px 8px; }
.psw--compact .psw-label { font-size: 9px; }
.psw--compact .psw-key { padding: 1px 4px; font-size: 9px; }
.psw--compact .psw-stream-btn { font-size: 8px; padding: 1px 6px; }
</style>
