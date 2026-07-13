<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '@/composables/useApi'

interface TestFile { file: string; tests: string[] }

const testCatalog = ref<TestFile[]>([])
const devices = ref<any[]>([])
const selectedTest = ref('')
const phoneStates = ref<Record<string, any>>({})
const phoneLogs = ref<Record<string, string[]>>({})
const phoneLogSeq = ref<Record<string, number>>({})
const phoneAutoScroll = ref<Record<string, boolean>>({})
const loading = ref(false)
let pollTimer: number | null = null

/* Curate the catalog down to health/smoke-relevant tests. */
const HEALTH_RE = /health|smoke|news/i
const healthTests = computed(() =>
  testCatalog.value.filter(f => HEALTH_RE.test(f.file))
)

function healthColor(status: string): string {
  const s = (status || '').toLowerCase()
  if (['available', 'ready', 'connected', 'online'].includes(s)) return '#22c55e'
  if (!s) return '#6b7280'
  return '#f87171'
}
function healthLabel(status: string): string {
  const s = (status || '').toLowerCase()
  if (['available', 'ready', 'connected', 'online'].includes(s)) return 'HEALTHY'
  if (!s) return 'UNKNOWN'
  return 'DEGRADED'
}
function checks(d: any): { label: string; ok: boolean; detail: string }[] {
  const c = d?.details?.checks || {}
  const out: { label: string; ok: boolean; detail: string }[] = []
  if ('appium_status_code' in c)
    out.push({ label: 'Appium', ok: c.appium_status_code === 200, detail: String(c.appium_status_code ?? '') })
  if (c.remote_xpc_tunnel)
    out.push({ label: 'Tunnel', ok: !!c.remote_xpc_tunnel.ok, detail: c.remote_xpc_tunnel.state || '' })
  if (c.host_device)
    out.push({ label: 'USB', ok: (c.host_device.state || '') === 'connected', detail: c.host_device.state || '' })
  return out
}
function phoneName(d: any): string {
  return d.nickname || d.model || d.device_name || d.label || d.serial
}

async function load() {
  loading.value = true
  try {
    const [t, d] = await Promise.all([
      api('/api/tests').catch(() => []),
      api('/api/phone/devices').catch(() => ({ devices: [] })),
    ])
    testCatalog.value = Array.isArray(t) ? t : t.tests || []
    devices.value = d.devices || d || []
    if (!selectedTest.value) {
      const smoke = healthTests.value.find(f => /chrome_news_smoke_device/.test(f.file))
      if (smoke) {
        const t2 = smoke.tests.find(x => /on_device/.test(x)) || ''
        selectedTest.value = smoke.file + '|' + t2
      } else if (healthTests.value[0]) {
        selectedTest.value = healthTests.value[0].file + '|'
      }
    }
  } finally {
    loading.value = false
  }
}

async function runCheck(serial: string) {
  if (!selectedTest.value) { alert('Select a health check first'); return }
  const [file, test] = selectedTest.value.split('|')
  phoneStates.value[serial] = { running: true, returncode: null }
  phoneLogs.value[serial] = []
  phoneLogSeq.value[serial] = 0
  phoneAutoScroll.value[serial] = true
  await api('/api/test-runner/start', {
    method: 'POST',
    body: JSON.stringify({ file, test: test || '', device: serial, retry: false }),
  })
  if (!pollTimer) pollTimer = window.setInterval(pollStatus, 1500)
}

async function stopCheck(serial: string) {
  await api('/api/test-runner/stop', { method: 'POST', body: JSON.stringify({ device: serial }) })
}

async function pollStatus() {
  try {
    const s = await api('/api/test-runner/status')
    phoneStates.value = s.devices || s || {}
    for (const serial of Object.keys(phoneStates.value)) await pollDeviceLogs(serial)
    const anyRunning = Object.values(phoneStates.value).some((d: any) => d.running)
    if (!anyRunning && pollTimer) { clearInterval(pollTimer); pollTimer = null; await load() }
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
      if (phoneLogs.value[serial].length > 400) phoneLogs.value[serial] = phoneLogs.value[serial].slice(-250)
      await nextTick()
      if (phoneAutoScroll.value[serial]) {
        const el = document.getElementById(`hlog-${serial}`)
        if (el) el.scrollTop = el.scrollHeight
      }
    }
  } catch {}
}

onMounted(load)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div>
    <!-- Intro -->
    <div class="card p-4 mb-4">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-sm font-semibold" style="color: var(--text-1)">🩺 Device Health</div>
          <div class="text-xs mt-1" style="color: var(--text-4)">
            Live device status + on-demand health/smoke checks. Runs real end-to-end tests through the device backend.
          </div>
        </div>
        <button class="text-xs" style="color: var(--text-5); cursor: pointer" @click="load">
          {{ loading ? '…' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Health check selector -->
    <div class="card p-4 mb-4">
      <div class="text-xs font-semibold uppercase tracking-widest mb-3" style="color: var(--text-3)">Health check</div>
      <select v-model="selectedTest"
        style="width: 100%; padding: 7px 10px; font-size: 13px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 8px; color: var(--text-1)">
        <optgroup v-for="f in healthTests" :key="f.file" :label="f.file.replace(/\.py$/, '')">
          <option :value="f.file + '|'">&mdash; all in {{ f.file.replace(/\.py$/, '') }} &mdash;</option>
          <option v-for="t in f.tests" :key="t" :value="f.file + '|' + t">{{ t }}</option>
        </optgroup>
      </select>
      <div v-if="!healthTests.length" class="text-xs mt-2" style="color: var(--text-5)">
        No health/smoke tests found. (Looking for files matching health / smoke / news.)
      </div>
    </div>

    <!-- Device cards -->
    <div class="grid grid-cols-1 gap-4">
      <div v-for="d in devices" :key="d.serial" class="card p-4 flex flex-col gap-3">
        <!-- status header -->
        <div class="flex items-center gap-3">
          <div :style="{ width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0, background: healthColor(d.status), boxShadow: `0 0 8px ${healthColor(d.status)}` }" />
          <div class="flex-1" style="min-width: 0">
            <div class="text-sm font-semibold" style="color: var(--text-1)">
              {{ phoneName(d) }}
              <span style="color: var(--text-5); font-weight: 400">· {{ (d.platform || '').toUpperCase() }} {{ d.platform_version || '' }}</span>
            </div>
            <div class="text-xs" style="color: var(--text-5)">{{ d.serial }}</div>
          </div>
          <span :style="{ padding: '2px 8px', borderRadius: '10px', fontSize: '10px', fontWeight: 700, background: healthColor(d.status) + '22', color: healthColor(d.status) }">
            {{ healthLabel(d.status) }}
          </span>
        </div>

        <!-- status message -->
        <div v-if="d.status_message && healthLabel(d.status) !== 'HEALTHY'"
          class="text-xs" style="color: #fbbf24; background: #2a220a; border-radius: 6px; padding: 6px 9px">
          {{ d.status_message }}
        </div>

        <!-- sub-checks -->
        <div v-if="checks(d).length" class="flex flex-wrap gap-2">
          <span v-for="c in checks(d)" :key="c.label"
            :style="{ fontSize: '11px', padding: '2px 8px', borderRadius: '6px', background: 'var(--bg-deep)', border: '1px solid var(--border)', color: c.ok ? '#4ade80' : '#f87171' }">
            {{ c.ok ? '✓' : '✕' }} {{ c.label }}<span v-if="c.detail" style="opacity:0.6"> · {{ c.detail }}</span>
          </span>
        </div>

        <!-- run controls -->
        <div class="flex gap-2 items-center">
          <button class="btn btn-primary" style="justify-content: center; display: flex; align-items: center; gap: 5px; font-size: 12px; padding: 5px 14px"
            @click="runCheck(d.serial)" :disabled="phoneStates[d.serial]?.running">
            &#9654; Run health check
          </button>
          <button v-show="phoneStates[d.serial]?.running" class="btn"
            style="font-size: 12px; padding: 5px 14px; background: #7f1d1d; color: #fca5a5; border: none"
            @click="stopCheck(d.serial)">&#9632; Stop</button>
          <span v-if="phoneStates[d.serial]?.returncode === 0"
            style="padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; background: #14532d; color: #4ade80">PASSED</span>
          <span v-else-if="phoneStates[d.serial]?.returncode != null"
            style="padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; background: #450a0a; color: #f87171">FAILED</span>
        </div>

        <!-- live logs -->
        <div v-if="phoneLogs[d.serial]?.length || phoneStates[d.serial]?.running">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-semibold" style="color: var(--text-4)">Live logs</span>
            <label class="flex items-center gap-1 text-xs cursor-pointer" style="color: var(--text-4)">
              <input type="checkbox" :checked="phoneAutoScroll[d.serial] !== false"
                @change="phoneAutoScroll[d.serial] = ($event.target as HTMLInputElement).checked"
                style="width: 10px; height: 10px; accent-color: var(--accent)" /> auto-scroll
            </label>
          </div>
          <div :id="`hlog-${d.serial}`"
            style="height: 200px; overflow-y: auto; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; line-height: 1.55; white-space: pre-wrap; word-break: break-all">
            <div v-for="(line, i) in (phoneLogs[d.serial] || []).slice(-200)" :key="i"
              :style="{ color: line.includes('PASSED') ? '#4ade80' : (line.includes('FAILED') || line.includes('ERROR')) ? '#f87171' : line.includes('SKIP') ? '#94a3b8' : 'var(--text-3)' }">{{ line }}</div>
            <div v-if="phoneStates[d.serial]?.running && !(phoneLogs[d.serial] || []).length" style="color: var(--text-4)">Waiting for output…</div>
          </div>
        </div>
      </div>

      <div v-if="!devices.length" class="card p-4 text-sm" style="color: var(--text-5)">
        No devices connected. Start the stack with <code>ghost-ios up</code>.
      </div>
    </div>

    <div class="text-xs mt-4" style="color: var(--text-5)">
      Full test catalog + recordings live in the 🧪 Tests tab.
    </div>
  </div>
</template>
