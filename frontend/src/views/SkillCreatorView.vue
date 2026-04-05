<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '@/composables/useApi'
import { renderMermaid } from '@/composables/useMermaid'
import PhoneStreamWidget from '@/components/PhoneStreamWidget.vue'

const devices = ref<any[]>([])
const selectedDevice = ref('')
const backend = ref(localStorage.getItem('creator_backend') || 'claude-code')
const model = ref(localStorage.getItem('creator_model') || 'anthropic/claude-sonnet-4')
const messages = ref<{role: string; content: string; actions?: any[]}[]>([])
const input = ref('')
const sending = ref(false)
const streaming = ref(false)
const streamImg = ref('')
const overlayOn = ref(false)
const elements = ref<any[]>([])
const actionHistory = ref<any[]>([])
const autopilot = ref(false)
const recording = ref(false)
const recordedActions = ref<any[]>([])
const showContextModal = ref(false)
const overlayCanvas = ref<HTMLCanvasElement | null>(null)
let streamTimer: number | null = null

const BACKENDS = [
  { id: 'claude-code', label: 'Claude Code (free)' },
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'claude', label: 'Claude API' },
  { id: 'ollama', label: 'Ollama (local)' },
]

const MODELS: Record<string, string[]> = {
  openrouter: ['anthropic/claude-sonnet-4', 'anthropic/claude-opus-4', 'google/gemini-2.5-pro', 'meta-llama/llama-3-70b'],
  claude: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514', 'claude-haiku-4-20251001'],
  ollama: [],
  'claude-code': ['sonnet', 'opus', 'haiku'],
}
const ollamaModels = ref<string[]>([])

async function loadDevices() {
  try {
    const resp = await api('/api/phone/devices')
    devices.value = resp.devices || resp || []
    if (devices.value.length && !selectedDevice.value) selectedDevice.value = devices.value[0].serial
  } catch {}
}

async function loadOllamaModels() {
  try {
    const resp = await api('/api/creator/ollama-models')
    ollamaModels.value = resp.models || resp || []
  } catch {}
}

function onBackendChange() {
  localStorage.setItem('creator_backend', backend.value)
  if (backend.value === 'ollama' && ollamaModels.value.length) {
    model.value = ollamaModels.value[0]
  } else if (MODELS[backend.value]?.length) {
    model.value = MODELS[backend.value][0]
  }
}

function onModelChange() {
  localStorage.setItem('creator_model', model.value)
}

function availableModels() {
  if (backend.value === 'ollama') return ollamaModels.value
  return MODELS[backend.value] || []
}

function toggleStream() {
  if (streaming.value) {
    streaming.value = false
    if (streamTimer) { clearInterval(streamTimer); streamTimer = null }
  } else {
    streaming.value = true
    pollFrame()
    streamTimer = window.setInterval(pollFrame, 200)
  }
}

async function pollFrame() {
  if (!selectedDevice.value) return
  try {
    const resp = await api(`/api/phone/screenshot/${selectedDevice.value}`)
    if (resp.ok && resp.image) {
      streamImg.value = `data:image/jpeg;base64,${resp.image}`
    }
  } catch {}
}

async function refreshElements() {
  if (!selectedDevice.value) return
  try {
    const resp = await api(`/api/phone/elements/${selectedDevice.value}`)
    elements.value = resp.elements || resp || []
  } catch {}
}

async function tapElement(idx: number) {
  const el = elements.value[idx]
  if (!el) return
  const cx = el.center?.x || (el.bounds.x1 + el.bounds.x2) / 2
  const cy = el.center?.y || (el.bounds.y1 + el.bounds.y2) / 2
  await api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, x: cx, y: cy }) })
  const step = { action: 'tap', x: cx, y: cy, element: el.text || el.content_desc || `#${idx}`, description: `Tap ${el.text || el.content_desc || `element #${idx}`}` }
  actionHistory.value.push(step)
  if (recording.value) recordedActions.value.push(step)
  await refreshElements()
}

async function send() {
  if (!input.value.trim() || sending.value) return
  // Auto-start stream on first interaction
  if (!streaming.value && selectedDevice.value) toggleStream()
  const msg = input.value.trim()
  input.value = ''
  messages.value.push({ role: 'user', content: msg })
  sending.value = true

  try {
    const context: any = {
      elements: elements.value.slice(0, 40),
      action_history: actionHistory.value.slice(-15),
      device: selectedDevice.value,
    }
    const resp = await api('/api/creator/chat', {
      method: 'POST',
      body: JSON.stringify({ backend: backend.value, model: model.value, message: msg, context })
    })
    const reply = resp.reply || resp.content || JSON.stringify(resp)
    // Parse action plans from reply
    let actions: any[] = []
    const jsonMatch = reply.match(/```json\s*(\[[\s\S]*?\])\s*```/)
    if (jsonMatch) {
      try { actions = JSON.parse(jsonMatch[1]) } catch {}
    }
    messages.value.push({ role: 'assistant', content: reply, actions })
  } catch (e: any) {
    messages.value.push({ role: 'error', content: e.message })
  } finally {
    sending.value = false
    await nextTick()
    const el = document.getElementById('creator-messages')
    if (el) el.scrollTop = el.scrollHeight
  }
}

async function executeActions(actions: any[]) {
  for (const step of actions) {
    if (step.action === 'tap' && step.element_idx !== undefined) {
      await tapElement(step.element_idx)
    } else if (step.action === 'tap' && step.x !== undefined) {
      await api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, x: step.x, y: step.y }) })
    } else if (step.action === 'type') {
      await api('/api/phone/type', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, text: step.text }) })
    } else if (step.action === 'back') {
      await api('/api/phone/back', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value }) })
    } else if (step.action === 'launch') {
      await api('/api/phone/launch', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, package: step.package }) })
    } else if (step.action === 'swipe') {
      await api('/api/phone/swipe', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, ...step }) })
    } else if (step.action === 'wait') {
      await new Promise(r => setTimeout(r, (step.seconds || 1) * 1000))
    }
    actionHistory.value.push(step)
    await new Promise(r => setTimeout(r, 500))
  }
  await refreshElements()
}

function sendKey(key: number | string) {
  if (!selectedDevice.value) return
  const keyName = typeof key === 'number' ? { 3: 'HOME', 4: 'BACK', 24: 'VOLUME_UP', 25: 'VOLUME_DOWN', 26: 'POWER', 187: 'APP_SWITCH' }[key] || String(key) : key
  if (typeof key === 'string') {
    api('/api/phone/key', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, key }) })
  } else {
    api('/api/phone/input', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, action: 'keyevent', keycode: key }) })
  }
  const step = { action: key === 4 ? 'back' : key === 3 ? 'home' : 'key', key: keyName, description: `Press ${keyName}` }
  actionHistory.value.push(step)
  if (recording.value) recordedActions.value.push(step)
}

function handleStreamClick(e: MouseEvent) {
  if (!selectedDevice.value) return
  const el = e.target as HTMLImageElement
  const rect = el.getBoundingClientRect()
  const x = Math.round((e.clientX - rect.left) / rect.width * 1080)
  const y = Math.round((e.clientY - rect.top) / rect.height * 2400)
  api('/api/phone/tap', { method: 'POST', body: JSON.stringify({ device: selectedDevice.value, x, y }) })
  const step = { action: 'tap', x, y }
  actionHistory.value.push(step)
  if (recording.value) recordedActions.value.push(step)
}

function toggleRecord() {
  recording.value = !recording.value
  if (recording.value) {
    recordedActions.value = []
    messages.value.push({ role: 'system', content: 'Recording started. Tap elements, press hardware keys — all actions are captured.' })
  } else {
    const n = recordedActions.value.length
    messages.value.push({ role: 'system', content: `Recording stopped. ${n} actions captured.${n > 0 ? ' Click "Save as Skill" to save.' : ''}` })
  }
}

const saveSkillName = ref('')
const saveSkillModal = ref(false)

function openSaveSkill() {
  if (!recordedActions.value.length) return
  saveSkillName.value = ''
  saveSkillModal.value = true
}

async function saveRecordedSkill() {
  const name = saveSkillName.value.trim().toLowerCase().replace(/\s+/g, '_')
  if (!name || !recordedActions.value.length) return
  try {
    const res = await api('/api/skills/create-from-recording', {
      method: 'POST',
      body: JSON.stringify({ name, steps: recordedActions.value, app_package: '' })
    })
    messages.value.push({ role: 'system', content: `Skill "${name}" saved with ${recordedActions.value.length} steps.` })
    saveSkillModal.value = false
    recordedActions.value = []
  } catch (e: any) {
    messages.value.push({ role: 'system', content: `Failed to save: ${e.message}` })
  }
}

function drawOverlay() {
  const canvas = overlayCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!overlayOn.value || !elements.value.length) return
  // Scale from device coords (1080x2400) to canvas size
  const scaleX = canvas.width / 1080
  const scaleY = canvas.height / 2400
  elements.value.forEach((el, i) => {
    if (!el.bounds) return
    const x = el.bounds.x1 * scaleX
    const y = el.bounds.y1 * scaleY
    const w = (el.bounds.x2 - el.bounds.x1) * scaleX
    const h = (el.bounds.y2 - el.bounds.y1) * scaleY
    ctx.strokeStyle = '#6366f1'
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, w, h)
    ctx.fillStyle = '#6366f1cc'
    ctx.font = 'bold 11px sans-serif'
    ctx.fillText(String(i), x + 2, y + 12)
  })
}

watch([overlayOn, elements], () => { nextTick(drawOverlay) })
watch(messages, () => {
  nextTick(() => {
    const el = document.getElementById('creator-messages')
    if (el) renderMermaid(el)
  })
}, { deep: true })

onMounted(async () => {
  await Promise.all([loadDevices(), loadOllamaModels()])
  onBackendChange()
  // Retry device loading if initial call failed (server might have been restarting)
  if (!devices.value.length) {
    setTimeout(async () => { await loadDevices() }, 3000)
  }
})
onUnmounted(() => { if (streamTimer) clearInterval(streamTimer) })
</script>

<template>
  <div class="sc-layout">
    <!-- LEFT: Chat Panel -->
    <div class="sc-card sc-chat-panel">
      <!-- Header -->
      <div class="sc-chat-header">
        <span class="sc-title">Skill Creator</span>
        <div class="sc-header-controls">
          <select v-model="backend" @change="onBackendChange" class="sc-select sc-select--pill">
            <option v-for="b in BACKENDS" :key="b.id" :value="b.id">{{ b.label }}</option>
          </select>
          <select v-model="model" @change="onModelChange" class="sc-select sc-select--pill sc-select--model">
            <option v-for="m in availableModels()" :key="m" :value="m">{{ m }}</option>
          </select>
          <label class="sc-autopilot" title="Auto-approve all steps without confirmation">
            <input type="checkbox" v-model="autopilot" class="sc-autopilot-check" />
            <span class="sc-autopilot-label">Autopilot</span>
          </label>
          <button class="sc-btn sc-btn--ghost" @click="showContextModal = true" title="Show what the agent sees">
            Context
          </button>
        </div>
        <span v-if="sending || streaming" class="sc-status-badge">{{ sending ? 'Sending...' : 'Streaming' }}</span>
      </div>

      <!-- Messages -->
      <div id="creator-messages" class="sc-messages">
        <div v-if="!messages.length" class="sc-welcome">
          Welcome to Skill Creator. Describe what you want to automate, or click elements on the device screen to build actions.
        </div>
        <div v-for="(msg, i) in messages" :key="i"
          :class="['sc-msg', 'sc-msg--' + msg.role]">
          <div class="sc-msg-role" v-if="msg.role !== 'user'">{{ msg.role }}</div>
          <div class="sc-msg-body">{{ msg.content }}</div>
          <div v-if="msg.actions?.length" class="sc-msg-actions">
            <button class="sc-btn sc-btn--accent sc-btn--sm" @click="executeActions(msg.actions)">
              Execute {{ msg.actions.length }} actions
            </button>
          </div>
        </div>
      </div>

      <!-- Thinking indicator -->
      <div v-if="sending" class="sc-thinking">
        <div class="sc-thinking-dots">
          <span class="sc-dot"></span>
          <span class="sc-dot sc-dot--2"></span>
          <span class="sc-dot sc-dot--3"></span>
        </div>
        <span class="sc-thinking-text">Thinking...</span>
      </div>

      <!-- Input bar -->
      <div class="sc-input-bar">
        <input v-model="input" @keyup.enter="send" placeholder="Describe an action..."
          class="sc-input" />
        <button @click="send" :disabled="sending" class="sc-btn sc-btn--accent sc-send-btn">Send</button>
      </div>
    </div>

    <!-- RIGHT: Device Panel -->
    <div class="sc-card sc-device-panel">
      <!-- Device header -->
      <div class="sc-device-header">
        <span class="sc-status-dot" :style="{ background: streaming ? '#22c55e' : '#475569' }"></span>
        <select v-model="selectedDevice" class="sc-select sc-select--device">
          <option value="">{{ devices.length ? 'Select device' : 'No devices — click ↻' }}</option>
          <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ d.nickname || d.model || d.serial }}</option>
        </select>
        <button class="sc-pill-btn" @click="loadDevices" title="Refresh devices" style="padding: 4px 8px; font-size: 11px">↻</button>
        <div class="sc-device-actions">
          <button :class="['sc-pill-btn', streaming && 'sc-pill-btn--active']" @click="toggleStream">
            {{ streaming ? 'Stop' : 'Stream' }}
          </button>
          <button :class="['sc-pill-btn', overlayOn && 'sc-pill-btn--active', !overlayOn && 'sc-pill-btn--warn']"
            @click="overlayOn = !overlayOn; refreshElements()">
            Overlay
          </button>
          <button :class="['sc-pill-btn', recording ? 'sc-pill-btn--danger' : 'sc-pill-btn--danger-ghost']"
            @click="toggleRecord">
            {{ recording ? 'Stop Rec' : 'Record' }}
          </button>
          <button v-if="!recording && recordedActions.length" class="sc-pill-btn sc-pill-btn--active"
            @click="openSaveSkill">
            Save ({{ recordedActions.length }})
          </button>
        </div>
        <span v-if="elements.length" class="sc-el-badge">{{ elements.length }}</span>
      </div>

      <!-- Hardware keys -->
      <div class="sc-hw-keys">
        <button class="sc-hw-btn" @click="sendKey(4)" title="Back">&#x25C0;</button>
        <button class="sc-hw-btn" @click="sendKey(3)" title="Home">&#x2302;</button>
        <button class="sc-hw-btn" @click="sendKey(187)" title="Recents">&#x25A6;</button>
        <button class="sc-hw-btn" @click="sendKey(26)" title="Power">&#x23FB;</button>
        <button class="sc-hw-btn" @click="sendKey(24)" title="Vol+">&#x1F50A;</button>
        <button class="sc-hw-btn" @click="sendKey(25)" title="Vol-">&#x1F509;</button>
      </div>

      <!-- Stream area -->
      <div class="sc-stream-area">
        <img v-if="streamImg" :src="streamImg" class="sc-stream-img"
          @click="handleStreamClick" />
        <canvas ref="overlayCanvas" width="360" height="800" class="sc-overlay-canvas"></canvas>
        <div v-if="!streamImg" class="sc-stream-empty">
          Select a device and press Stream
        </div>
      </div>

      <!-- Element list -->
      <div v-if="overlayOn && elements.length" class="sc-elements">
        <div class="sc-elements-header">Clickable elements</div>
        <div class="sc-elements-list">
          <div v-for="(el, i) in elements.slice(0, 30)" :key="i"
            class="sc-el-row" @click="tapElement(i)">
            <span class="sc-el-idx">{{ i }}</span>
            <span class="sc-el-text">
              {{ el.class?.split('.')?.pop() }} "{{ el.text || el.content_desc || '\u2014' }}"
            </span>
            <span class="sc-el-tap">tap</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Context Modal -->
    <div v-if="showContextModal" class="sc-modal-backdrop" @click.self="showContextModal = false">
      <div class="sc-modal">
        <div class="sc-modal-header">
          <span class="sc-modal-title">Agent Context</span>
          <button class="sc-btn sc-btn--ghost" @click="showContextModal = false">Close</button>
        </div>
        <div class="sc-modal-section">
          <div class="sc-modal-meta">Device: {{ selectedDevice || 'none' }}</div>
          <div class="sc-modal-meta">Backend: {{ backend }} / {{ model }}</div>
          <div class="sc-modal-meta">Elements: {{ elements.length }}</div>
        </div>
        <div v-if="streamImg" class="sc-modal-section">
          <div class="sc-modal-section-title">Current Screen</div>
          <img :src="streamImg" class="sc-modal-screenshot" />
        </div>
        <div v-if="elements.length" class="sc-modal-section">
          <div class="sc-modal-section-title">Elements ({{ elements.length }})</div>
          <table class="sc-table">
            <thead>
              <tr>
                <th class="sc-th sc-th--accent">#</th>
                <th class="sc-th">Text</th>
                <th class="sc-th sc-th--muted">Class</th>
                <th class="sc-th sc-th--dim">Bounds</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(el, i) in elements.slice(0, 20)" :key="i" class="sc-tr">
                <td class="sc-td sc-td--accent">{{ i }}</td>
                <td class="sc-td sc-td--text">{{ el.text || el.content_desc || el.resource_id || '---' }}</td>
                <td class="sc-td sc-td--class">{{ (el.class || '').split('.').pop() }}</td>
                <td class="sc-td sc-td--bounds">{{ el.bounds ? `[${el.bounds.x1},${el.bounds.y1}][${el.bounds.x2},${el.bounds.y2}]` : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Save as Skill modal -->
    <div v-if="saveSkillModal" class="sc-modal-backdrop" @click.self="saveSkillModal = false">
      <div class="sc-modal" style="max-width: 400px">
        <div class="sc-modal-header">
          <span class="sc-modal-title">Save as Skill</span>
          <button class="sc-btn sc-btn--ghost" @click="saveSkillModal = false">Close</button>
        </div>
        <div class="sc-modal-section">
          <div class="sc-modal-meta">{{ recordedActions.length }} recorded actions</div>
          <div style="margin-top: 12px">
            <label style="font-size: 11px; color: var(--text-3); display: block; margin-bottom: 4px">Skill name</label>
            <input v-model="saveSkillName" placeholder="my_automation"
              style="width: 100%; padding: 8px 12px; font-size: 13px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1); outline: none"
              @keyup.enter="saveRecordedSkill" />
          </div>
          <div style="margin-top: 8px; max-height: 200px; overflow-y: auto; font-size: 10px; font-family: monospace; color: var(--text-4)">
            <div v-for="(a, i) in recordedActions" :key="i">
              {{ i + 1 }}. {{ a.description || a.action }} {{ a.x !== undefined ? `(${a.x}, ${a.y})` : '' }}
            </div>
          </div>
          <button class="sc-btn sc-btn--accent" style="margin-top: 12px; width: 100%" @click="saveRecordedSkill"
            :disabled="!saveSkillName.trim()">Save Skill</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── CSS Variables (scoped aliases) ──────────────────────────────── */
/* Leverages global vars from main.css:
   --bg-base, --bg-card, --bg-deep, --border,
   --text-1 .. --text-4, --accent, --accent-lt               */

/* ── Layout ──────────────────────────────────────────────────────── */
.sc-layout {
  display: flex;
  height: calc(100vh - 80px);
  gap: 12px;
  padding: 4px 0;
}

/* ── Shared Card ─────────────────────────────────────────────────── */
.sc-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 4px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
.sc-btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-2);
  transition: all 0.15s ease;
  white-space: nowrap;
}
.sc-btn:hover {
  border-color: var(--accent);
  color: var(--text-1);
}
.sc-btn--accent {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.sc-btn--accent:hover {
  opacity: 0.88;
  border-color: var(--accent);
}
.sc-btn--accent:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sc-btn--ghost {
  background: transparent;
  border-color: var(--border);
  color: var(--text-4);
  font-size: 11px;
  padding: 4px 10px;
}
.sc-btn--ghost:hover {
  border-color: var(--accent);
  color: var(--text-2);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.sc-btn--sm {
  padding: 5px 12px;
  font-size: 11px;
}

/* ── Select (pill style) ─────────────────────────────────────────── */
.sc-select {
  background: var(--bg-deep);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 500;
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='8' height='5' viewBox='0 0 8 5' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l3 3 3-3' stroke='%2364748b' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 6px center;
  padding-right: 20px;
}
.sc-select:focus {
  border-color: var(--accent);
}
.sc-select option {
  background: var(--bg-deep);
  color: var(--text-2);
}
.sc-select--pill {
  border-radius: 9999px;
  padding: 3px 20px 3px 10px;
  font-size: 10px;
}
.sc-select--model {
  max-width: 160px;
}
.sc-select--device {
  flex: 1;
  min-width: 0;
}

/* ═══════════════════════════════════════════════════════════════════
   LEFT: Chat Panel
   ═══════════════════════════════════════════════════════════════════ */
.sc-chat-panel {
  flex: 1;
  min-width: 300px;
}

.sc-chat-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sc-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.01em;
}

.sc-header-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.sc-autopilot {
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}
.sc-autopilot-check {
  width: 13px;
  height: 13px;
  accent-color: var(--accent);
  cursor: pointer;
}
.sc-autopilot-label {
  font-size: 10px;
  color: var(--accent-lt);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sc-status-badge {
  font-size: 10px;
  font-weight: 500;
  color: var(--accent-lt);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  padding: 2px 8px;
  border-radius: 9999px;
}

/* ── Messages ────────────────────────────────────────────────────── */
.sc-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sc-messages::-webkit-scrollbar {
  width: 5px;
}
.sc-messages::-webkit-scrollbar-track {
  background: transparent;
}
.sc-messages::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.sc-welcome {
  background: var(--bg-deep);
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  font-size: 13px;
  color: var(--text-3);
  line-height: 1.55;
  text-align: center;
}

/* ── Message Bubbles ─────────────────────────────────────────────── */
.sc-msg {
  border-radius: 10px;
  padding: 12px 14px;
  max-width: 85%;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.sc-msg--user {
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  color: var(--text-1);
  margin-left: auto;
  border-bottom-right-radius: 3px;
}
.sc-msg--assistant {
  background: var(--bg-deep);
  color: var(--text-2);
  margin-right: auto;
  border-bottom-left-radius: 3px;
  border: 1px solid var(--border);
}
.sc-msg--system {
  background: transparent;
  color: var(--text-4);
  font-size: 11px;
  font-style: italic;
  text-align: center;
  max-width: 100%;
  padding: 8px 14px;
}
.sc-msg--error {
  background: color-mix(in srgb, #ef4444 10%, transparent);
  color: #f87171;
  border-left: 3px solid #ef4444;
  margin-right: auto;
  max-width: 100%;
}

.sc-msg-role {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
  opacity: 0.6;
}
.sc-msg--assistant .sc-msg-role {
  color: var(--accent-lt);
}
.sc-msg--system .sc-msg-role {
  color: var(--text-4);
}
.sc-msg--error .sc-msg-role {
  color: #f87171;
}

.sc-msg-body {
  white-space: pre-wrap;
}

.sc-msg-actions {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
}

/* ── Thinking indicator ──────────────────────────────────────────── */
.sc-thinking {
  padding: 8px 16px;
  border-top: 1px solid color-mix(in srgb, var(--accent) 15%, transparent);
  background: var(--bg-deep);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.sc-thinking-dots {
  display: flex;
  gap: 4px;
}
.sc-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: sc-pulse 1.2s ease-in-out infinite;
}
.sc-dot--2 { animation-delay: 0.2s; }
.sc-dot--3 { animation-delay: 0.4s; }

@keyframes sc-pulse {
  0%, 100% { opacity: 0.25; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.15); }
}

.sc-thinking-text {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-lt);
}

/* ── Input bar ───────────────────────────────────────────────────── */
.sc-input-bar {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  background: var(--bg-deep);
  display: flex;
  gap: 8px;
}
.sc-input {
  flex: 1;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  color: var(--text-1);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.sc-input::placeholder {
  color: var(--text-4);
}
.sc-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 15%, transparent);
}
.sc-send-btn {
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 13px;
}

/* ═══════════════════════════════════════════════════════════════════
   RIGHT: Device Panel
   ═══════════════════════════════════════════════════════════════════ */
.sc-device-panel {
  width: 400px;
  flex-shrink: 0;
}

.sc-device-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}
.sc-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sc-device-actions {
  display: flex;
  gap: 5px;
}

/* ── Pill Buttons (Stream, Overlay, Record) ──────────────────────── */
.sc-pill-btn {
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-deep);
  color: var(--text-3);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.sc-pill-btn:hover {
  border-color: var(--accent);
  color: var(--text-1);
}
.sc-pill-btn--active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.sc-pill-btn--active:hover {
  opacity: 0.88;
}
.sc-pill-btn--warn {
  color: #fbbf24;
}
.sc-pill-btn--warn:hover {
  border-color: #fbbf24;
}
.sc-pill-btn--danger-ghost {
  color: #f87171;
}
.sc-pill-btn--danger-ghost:hover {
  border-color: #f87171;
}
.sc-pill-btn--danger {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
.sc-pill-btn--danger:hover {
  opacity: 0.88;
}

.sc-el-badge {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  color: var(--accent-lt);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  padding: 2px 8px;
  border-radius: 9999px;
  min-width: 20px;
  text-align: center;
}

/* ── Hardware keys ───────────────────────────────────────────────── */
.sc-hw-keys {
  display: flex;
  justify-content: center;
  gap: 4px;
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sc-hw-btn {
  padding: 3px 8px;
  background: #1a1f2e;
  border: 1px solid #2a3044;
  border-radius: 4px;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.12s;
}
.sc-hw-btn:hover {
  background: #252b3d;
  color: #e2e8f0;
}
.sc-hw-btn:active {
  background: #6366f133;
}

/* ── Stream area ─────────────────────────────────────────────────── */
.sc-stream-area {
  flex: 1;
  position: relative;
  background: #050508;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sc-stream-img {
  max-height: 100%;
  max-width: 100%;
  object-fit: contain;
  cursor: crosshair;
}
.sc-overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.sc-stream-empty {
  color: var(--text-4);
  font-size: 13px;
  text-align: center;
  padding: 48px 24px;
  line-height: 1.6;
}

/* ── Element list ────────────────────────────────────────────────── */
.sc-elements {
  border-top: 1px solid var(--border);
  max-height: 170px;
  display: flex;
  flex-direction: column;
}
.sc-elements-header {
  padding: 8px 14px 4px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-4);
}
.sc-elements-list {
  overflow-y: auto;
  padding: 0 8px 8px;
}
.sc-elements-list::-webkit-scrollbar {
  width: 4px;
}
.sc-elements-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}
.sc-el-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.12s;
}
.sc-el-row:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.sc-el-idx {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  color: var(--accent-lt);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-radius: 5px;
}
.sc-el-text {
  flex: 1;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.sc-el-tap {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-4);
  opacity: 0;
  transition: opacity 0.12s;
}
.sc-el-row:hover .sc-el-tap {
  opacity: 1;
  color: var(--accent-lt);
}

/* ═══════════════════════════════════════════════════════════════════
   Context Modal
   ═══════════════════════════════════════════════════════════════════ */
.sc-modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sc-modal {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  padding: 24px;
  max-width: 700px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}
.sc-modal::-webkit-scrollbar {
  width: 5px;
}
.sc-modal::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
.sc-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.sc-modal-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
}

.sc-modal-section {
  margin-bottom: 16px;
}
.sc-modal-section:last-child {
  margin-bottom: 0;
}
.sc-modal-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 8px;
}
.sc-modal-meta {
  font-size: 12px;
  color: var(--text-4);
  margin-bottom: 4px;
  line-height: 1.5;
}
.sc-modal-screenshot {
  max-height: 200px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

/* ── Context Table ───────────────────────────────────────────────── */
.sc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.sc-th {
  text-align: left;
  padding: 6px 8px;
  color: var(--text-1);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
}
.sc-th--accent { color: var(--accent); }
.sc-th--muted { color: var(--text-4); }
.sc-th--dim { color: var(--text-4); opacity: 0.7; }

.sc-tr {
  border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
  transition: background 0.1s;
}
.sc-tr:hover {
  background: color-mix(in srgb, var(--accent) 4%, transparent);
}
.sc-td {
  padding: 5px 8px;
}
.sc-td--accent {
  color: var(--accent);
  font-weight: 700;
}
.sc-td--text {
  color: var(--text-1);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sc-td--class {
  color: var(--text-4);
  font-size: 10px;
}
.sc-td--bounds {
  color: var(--text-4);
  font-size: 10px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  opacity: 0.7;
}
</style>
