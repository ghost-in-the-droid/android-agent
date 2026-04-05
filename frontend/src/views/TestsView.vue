<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '@/composables/useApi'

interface TestFile {
  file: string
  tests: string[]
}

interface Recording {
  name: string
  device: string
  date: string
  size_mb: string
  result?: { passed: number; failed: number; skipped: number; errors: number }
}

const testCatalog = ref<TestFile[]>([])
const selectedTest = ref('')
const retryEnabled = ref(false)
const devices = ref<any[]>([])
const phoneStates = ref<Record<string, any>>({})
const recordings = ref<Recording[]>([])
const viewingRec = ref<any>(null)
let pollTimer: number | null = null

/* ── per-device live logs ─────────────────────────────────────────────── */
const phoneLogs = ref<Record<string, string[]>>({})
const phoneLogSeq = ref<Record<string, number>>({})
const phoneAutoScroll = ref<Record<string, boolean>>({})

/* ── recording log sync ───────────────────────────────────────────────── */
const viewingRecLogs = ref<string[]>([])
const recVideoRef = ref<HTMLVideoElement | null>(null)
const recLogAutoScroll = ref(true)
const highlightedLogIdx = ref(-1)

const cmdPreview = computed(() => {
  const val = selectedTest.value
  if (!val) return 'pytest -v --tb=short -s tests/'
  const [file, test] = val.split('|')
  const node = file ? ('tests/' + file + (test ? '::' + test : '')) : '\u2014'
  const retry = retryEnabled.value ? ' --reruns 2 --reruns-delay 5' : ''
  return `pytest -v --tb=short -s${retry} ${node}`
})

function phoneName(serial: string): string {
  const d = devices.value.find((x: any) => x.serial === serial)
  return d ? (d.nickname || d.model || d.label || d.serial) : serial.slice(0, 6)
}

function recTestName(name: string): string {
  return name.replace(/^[^_]+_\d{8}_\d{6}_/, '').replace('.mp4', '')
}

function recTime(date: string): string {
  return (date || '').slice(5, 16).replace('T', ' ')
}

function recStatus(r: Recording): { text: string; color: string } {
  if (!r.result) return { text: '', color: '' }
  const { passed, failed, skipped, errors } = r.result
  if (failed > 0 || errors > 0) return { text: `${failed + errors} failed`, color: '#f87171' }
  if (passed > 0) return { text: `${passed} passed`, color: '#34d399' }
  if (skipped > 0) return { text: `${skipped} skipped`, color: '#fbbf24' }
  return { text: '', color: '' }
}

function recStats(r: Recording): string {
  if (!r.result) return ''
  const parts: string[] = []
  if (r.result.passed) parts.push(`${r.result.passed}P`)
  if (r.result.failed) parts.push(`${r.result.failed}F`)
  if (r.result.skipped) parts.push(`${r.result.skipped}S`)
  return parts.join('/')
}

async function load() {
  const [t, d, r] = await Promise.all([
    api('/api/tests').catch(() => []),
    api('/api/phone/devices').catch(() => ({ devices: [] })),
    api('/api/test-runner/recordings').catch(() => [])
  ])
  testCatalog.value = Array.isArray(t) ? t : t.tests || []
  devices.value = d.devices || d || []
  recordings.value = Array.isArray(r) ? r : r.recordings || []
  if (!selectedTest.value && testCatalog.value.length) {
    selectedTest.value = testCatalog.value[0].file + '|'
  }
}

async function startTest(serial: string) {
  const val = selectedTest.value
  if (!val) { alert('Select a test first'); return }
  const [file, test] = val.split('|')
  phoneStates.value[serial] = { running: true, returncode: null }
  phoneLogs.value[serial] = []
  phoneLogSeq.value[serial] = 0
  phoneAutoScroll.value[serial] = true
  await api('/api/test-runner/start', {
    method: 'POST',
    body: JSON.stringify({ file, test: test || '', device: serial, retry: retryEnabled.value })
  })
  if (!pollTimer) pollTimer = window.setInterval(pollStatus, 1500)
}

async function stopTest(serial: string) {
  await api('/api/test-runner/stop', { method: 'POST', body: JSON.stringify({ device: serial }) })
}

async function pollStatus() {
  try {
    const s = await api('/api/test-runner/status')
    phoneStates.value = s.devices || s || {}
    // Poll logs for every device that has an entry
    for (const serial of Object.keys(phoneStates.value)) {
      await pollDeviceLogs(serial)
    }
    const anyRunning = Object.values(phoneStates.value).some((d: any) => d.running)
    if (!anyRunning && pollTimer) {
      clearInterval(pollTimer); pollTimer = null
      await load()
    }
  } catch {}
}

async function pollDeviceLogs(serial: string) {
  try {
    const since = phoneLogSeq.value[serial] || 0
    const resp = await api(`/api/test-runner/logs?device=${serial}&since=${since}`)
    if (resp.lines?.length) {
      if (!phoneLogs.value[serial]) phoneLogs.value[serial] = []
      phoneLogs.value[serial].push(...resp.lines)
      phoneLogSeq.value[serial] = resp.total
      if (phoneLogs.value[serial].length > 500) {
        phoneLogs.value[serial] = phoneLogs.value[serial].slice(-300)
      }
      await nextTick()
      if (phoneAutoScroll.value[serial]) {
        const el = document.getElementById(`log-${serial}`)
        if (el) el.scrollTop = el.scrollHeight
      }
    }
  } catch {}
}

async function deleteRecording(name: string) {
  if (!confirm(`Delete recording "${name}"?`)) return
  await api(`/api/test-runner/recording/${encodeURIComponent(name)}`, { method: 'DELETE' })
  await load()
}

async function viewRecording(rec: Recording) {
  viewingRec.value = rec
  viewingRecLogs.value = []
  highlightedLogIdx.value = -1
  recLogAutoScroll.value = true
  // Load logs for the recording's device
  try {
    const resp = await api(`/api/test-runner/logs?device=${rec.device}&since=0`)
    viewingRecLogs.value = resp.lines || []
  } catch {}
}

/* ── recording video / log sync ───────────────────────────────────────── */
function parseLogTimestamp(line: string): number | null {
  // Matches patterns like "2026-04-01 12:34:56" or "12:34:56" at the start of a log line
  const m = line.match(/(?:^\d{4}-\d{2}-\d{2}\s+)?(\d{2}):(\d{2}):(\d{2})/)
  if (!m) return null
  return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3])
}

function onVideoTimeUpdate() {
  if (!recVideoRef.value || !viewingRecLogs.value.length) return
  const currentTime = recVideoRef.value.currentTime
  const duration = recVideoRef.value.duration
  if (!duration || duration <= 0) return

  // Map video position to log lines proportionally
  const ratio = currentTime / duration
  const targetIdx = Math.min(
    Math.floor(ratio * viewingRecLogs.value.length),
    viewingRecLogs.value.length - 1
  )
  highlightedLogIdx.value = targetIdx

  if (recLogAutoScroll.value) {
    const container = document.getElementById('rec-log-viewer')
    if (container) {
      const lineEl = container.children[targetIdx] as HTMLElement
      if (lineEl) {
        lineEl.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
    }
  }
}

onMounted(load)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div>
    <!-- Test selector -->
    <div class="card p-4 mb-4">
      <div class="text-xs font-semibold uppercase tracking-widest mb-3" style="color: var(--text-3)">Select test</div>
      <div class="flex items-center gap-3 mb-2">
        <select v-model="selectedTest" style="flex: 1; padding: 7px 10px; font-size: 13px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 8px; color: var(--text-1)">
          <optgroup v-for="f in testCatalog" :key="f.file" :label="f.file.replace(/\.py$/, '')">
            <option :value="f.file + '|'">&mdash; run all in {{ f.file.replace(/\.py$/, '') }} &mdash;</option>
            <option v-for="t in f.tests" :key="t" :value="f.file + '|' + t">{{ t }}</option>
          </optgroup>
        </select>
        <label class="flex items-center gap-1.5 text-xs cursor-pointer" style="color: var(--text-3); white-space: nowrap">
          <input type="checkbox" v-model="retryEnabled" style="width: 12px; height: 12px; accent-color: var(--accent)">
          Retry (2x)
        </label>
      </div>
      <div style="padding: 7px 10px; background: var(--bg-deep); border-radius: 6px; font-family: monospace; font-size: 11px; color: var(--text-4); word-break: break-all">
        {{ cmdPreview }}
      </div>
    </div>

    <!-- Phone cards -->
    <div class="grid grid-cols-1 gap-4 mb-4">
      <div v-for="d in devices" :key="d.serial" class="card p-4 flex flex-col gap-3">
        <div class="flex items-center gap-3">
          <div style="width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; transition: background 0.3s"
            :style="{
              background: phoneStates[d.serial]?.running ? '#38bdf8' :
                phoneStates[d.serial]?.returncode === 0 ? '#22c55e' :
                phoneStates[d.serial]?.returncode != null ? '#f87171' : '#374151',
              boxShadow: phoneStates[d.serial]?.running ? '0 0 8px #38bdf8' : 'none'
            }" />
          <div class="flex-1" style="min-width: 0">
            <div class="text-sm font-semibold" style="color: var(--text-1)">{{ d.nickname || d.model || d.label || d.serial }}</div>
            <div class="text-xs" style="color: var(--text-5)">{{ (d.serial || '').slice(0, 6) }}</div>
          </div>
          <div v-if="phoneStates[d.serial]?.returncode === 0"
            style="display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; background: #14532d; color: #4ade80">PASSED</div>
          <div v-else-if="phoneStates[d.serial]?.returncode != null && phoneStates[d.serial]?.returncode !== undefined"
            style="display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; background: #450a0a; color: #f87171">FAILED</div>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary flex-1" style="justify-content: center; display: flex; align-items: center; gap: 5px; font-size: 12px; padding: 5px 0"
            @click="startTest(d.serial)" :disabled="phoneStates[d.serial]?.running">
            &#9654; Run
          </button>
          <button v-show="phoneStates[d.serial]?.running" class="btn flex-1"
            style="justify-content: center; display: flex; align-items: center; gap: 5px; font-size: 12px; padding: 5px 0; background: #7f1d1d; color: #fca5a5; border: none"
            @click="stopTest(d.serial)">
            &#9632; Stop
          </button>
        </div>

        <!-- Inline video player (during test execution) -->
        <div v-if="phoneStates[d.serial]?.running && phoneStates[d.serial]?.recording" style="border-radius: 8px; overflow: hidden; background: #000">
          <video :src="`/api/test-runner/recording/${phoneStates[d.serial].recording}`"
            autoplay muted loop
            style="width: 100%; max-height: 200px; object-fit: contain; display: block" />
        </div>

        <!-- Live log viewer -->
        <div v-if="phoneLogs[d.serial]?.length || phoneStates[d.serial]?.running" style="position: relative">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-semibold" style="color: var(--text-4)">Live Logs</span>
            <label class="flex items-center gap-1 text-xs cursor-pointer" style="color: var(--text-4)">
              <input type="checkbox" :checked="phoneAutoScroll[d.serial] !== false"
                @change="phoneAutoScroll[d.serial] = ($event.target as HTMLInputElement).checked"
                style="width: 10px; height: 10px; accent-color: var(--accent)" />
              auto-scroll
            </label>
          </div>
          <div :id="`log-${d.serial}`"
            style="height: 200px; overflow-y: auto; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 11px; line-height: 1.55; color: var(--text-3); white-space: pre-wrap; word-break: break-all">
            <div v-for="(line, i) in (phoneLogs[d.serial] || []).slice(-200)" :key="i"
              :style="{
                color: line.includes('PASSED') ? '#4ade80' :
                  line.includes('FAILED') || line.includes('ERROR') ? '#f87171' :
                  line.includes('WARNING') ? '#fbbf24' :
                  line.includes('SKIP') ? '#94a3b8' : 'var(--text-3)'
              }">{{ line }}</div>
            <div v-if="phoneStates[d.serial]?.running && !(phoneLogs[d.serial] || []).length" style="color: var(--text-4)">Waiting for output...</div>
          </div>
        </div>
      </div>
      <div v-if="!devices.length" class="card p-4 text-sm" style="color: var(--text-5)">No phones connected</div>
    </div>

    <!-- Recording viewer -->
    <div v-if="viewingRec" class="mt-4 mb-4">
      <div class="grid grid-cols-2 gap-4" style="max-height: 520px">
        <div class="card p-3 flex flex-col" style="max-height: 520px">
          <div class="text-xs font-semibold uppercase tracking-widest mb-2" style="color: var(--text-3)">{{ viewingRec.name }}</div>
          <video ref="recVideoRef" controls :src="`/api/test-runner/recording/${viewingRec.name}`"
            @timeupdate="onVideoTimeUpdate"
            style="width: 100%; max-height: 480px; object-fit: contain; border-radius: 6px; background: #000; display: block"></video>
        </div>
        <div class="card p-3 flex flex-col" style="max-height: 520px">
          <div class="flex items-center justify-between mb-2">
            <div class="text-xs font-semibold uppercase tracking-widest" style="color: var(--text-3)">Logs</div>
            <div class="flex items-center gap-3">
              <label class="flex items-center gap-1 text-xs cursor-pointer" style="color: var(--text-4)">
                <input type="checkbox" v-model="recLogAutoScroll"
                  style="width: 10px; height: 10px; accent-color: var(--accent)" />
                auto-scroll
              </label>
              <button class="text-xs" style="color: var(--text-5); cursor: pointer" @click="viewingRec = null; viewingRecLogs = []">&#10005; close</button>
            </div>
          </div>
          <div id="rec-log-viewer"
            style="font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 11px; line-height: 1.55; color: var(--text-3); background: var(--bg-deep); border-radius: 6px; padding: 10px 12px; flex: 1; overflow-y: auto; white-space: pre-wrap; word-break: break-all">
            <div v-if="!viewingRecLogs.length" style="color: var(--text-5)">-- no logs available --</div>
            <div v-for="(line, i) in viewingRecLogs" :key="i"
              :style="{
                background: i === highlightedLogIdx ? 'rgba(99, 102, 241, 0.18)' : 'transparent',
                borderLeft: i === highlightedLogIdx ? '2px solid #6366f1' : '2px solid transparent',
                paddingLeft: '6px',
                transition: 'background 0.15s, border-color 0.15s',
                color: line.includes('PASSED') ? '#4ade80' :
                  line.includes('FAILED') || line.includes('ERROR') ? '#f87171' :
                  line.includes('WARNING') ? '#fbbf24' : 'var(--text-3)'
              }">{{ line }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recordings table -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="text-xs font-semibold uppercase tracking-widest" style="color: var(--text-3)">Test Recordings</div>
        <button class="text-xs" style="color: var(--text-5); cursor: pointer" @click="load">Refresh</button>
      </div>
      <div v-if="recordings.length" style="overflow-x: auto">
        <table style="width: 100%; border-collapse: collapse; font-size: 11px">
          <thead>
            <tr style="border-bottom: 1px solid var(--border-lg)">
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: center; font-weight: 600; text-transform: uppercase"></th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Test</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Phone</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Date</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Size</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Status</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: left; font-weight: 600; text-transform: uppercase">Stats</th>
              <th style="padding: 4px 8px; font-size: 10px; color: var(--text-5); text-align: center; font-weight: 600; text-transform: uppercase"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recordings" :key="r.name"
              style="border-bottom: 1px solid var(--border-lg); cursor: pointer"
              @click="viewRecording(r)"
              @mouseenter="($event.currentTarget as HTMLElement).style.background = '#0f1523'"
              @mouseleave="($event.currentTarget as HTMLElement).style.background = 'transparent'">
              <td style="padding: 5px 8px; text-align: center">&#127916;</td>
              <td style="padding: 5px 8px; color: #a5b4fc">{{ recTestName(r.name) }}</td>
              <td style="padding: 5px 8px; color: var(--text-3)">{{ phoneName(r.device || '') }}</td>
              <td style="padding: 5px 8px; color: var(--text-4); font-family: monospace">{{ recTime(r.date) }}</td>
              <td style="padding: 5px 8px; color: var(--text-4)">{{ r.size_mb ? r.size_mb + ' MB' : '' }}</td>
              <td style="padding: 5px 8px">
                <span v-if="recStatus(r).text" :style="{ color: recStatus(r).color }">{{ recStatus(r).text }}</span>
              </td>
              <td style="padding: 5px 8px; color: var(--text-3)">{{ recStats(r) }}</td>
              <td style="padding: 5px 8px; text-align: center" @click.stop="deleteRecording(r.name)">
                <span style="color: var(--text-5); cursor: pointer"
                  @mouseenter="($event.target as HTMLElement).style.color = '#f87171'"
                  @mouseleave="($event.target as HTMLElement).style.color = 'var(--text-5)'"
                  title="Delete">&times;</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-xs" style="color: var(--text-5)">-- none --</div>
    </div>
  </div>
</template>
