<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/composables/useApi'
import PhoneStreamWidget from '@/components/PhoneStreamWidget.vue'

interface ExplorerRun {
  name: string; states: number; transitions: number; max_depth: number; device: string; date: string
}
interface AppState {
  state_id: string; screenshot_path: string; elements: any[]; depth: number; activity: string
  transitions: Record<string, string>
}

const devices = ref<{serial: string; nickname?: string}[]>([])
const runs = ref<ExplorerRun[]>([])
const pkg = ref('')
const device = ref('')
const installedPackages = ref<string[]>([])
const filteredPackages = ref<string[]>([])
const showPkgDropdown = ref(false)
const maxDepth = ref(3)
const maxStates = ref(20)
const settle = ref(1.5)
const running = ref(false)
const jobId = ref<number | null>(null)
const progress = ref({ states_found: 0, transitions: 0, current_depth: 0, log_tail: [] as string[] })

const cleanLogs = computed(() => {
  return progress.value.log_tail.map(line => {
    // Strip timestamp prefix like "[03:22:14] " or "2026-04-03 03:22:14,448 [__main__] "
    let clean = line.replace(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+\[[\w.]+\]\s*/, '')
    clean = clean.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, '')
    return clean
  })
})
let pollTimer: number | null = null

// Current run detail
const currentRun = ref<{ package: string; states: Record<string, AppState>; total_states: number; total_transitions: number } | null>(null)
const selectedState = ref<string | null>(null)

async function loadDevices() {
  try {
    const resp = await api('/api/phone/devices')
    devices.value = resp.devices || resp || []
    if (devices.value.length && !device.value) device.value = devices.value[0].serial
  } catch {}
}

async function loadRuns() {
  try { runs.value = await api('/api/explorer/runs') } catch { runs.value = [] }
}

async function loadPackages() {
  if (!device.value) return
  try {
    const resp = await api(`/api/phone/packages/${device.value}`)
    installedPackages.value = resp.packages || resp || []
  } catch { installedPackages.value = [] }
}

function onPkgInput() {
  const q = pkg.value.toLowerCase()
  if (!q) {
    filteredPackages.value = installedPackages.value.slice(0, 20)
  } else {
    filteredPackages.value = installedPackages.value.filter(p => p.toLowerCase().includes(q)).slice(0, 20)
  }
  showPkgDropdown.value = filteredPackages.value.length > 0
}

function selectPkg(p: string) {
  pkg.value = p
  showPkgDropdown.value = false
}

function hidePkgDropdown() {
  setTimeout(() => { showPkgDropdown.value = false }, 200)
}

const phoneWidget = ref<InstanceType<typeof PhoneStreamWidget> | null>(null)

async function startExploration() {
  if (!pkg.value.trim() || !device.value) return
  running.value = true
  progress.value = { states_found: 0, transitions: 0, current_depth: 0, log_tail: [] }
  // Auto-start stream so user can watch
  if (phoneWidget.value && !phoneWidget.value.streaming) phoneWidget.value.startStream()
  try {
    await api('/api/explorer/start', {
      method: 'POST',
      body: JSON.stringify({
        package: pkg.value.trim(), device: device.value,
        max_depth: maxDepth.value, max_states: maxStates.value, settle: settle.value
      })
    })
    pollTimer = window.setInterval(pollStatus, 1500)
  } catch (e: any) {
    running.value = false
    alert('Failed: ' + e.message)
  }
}

async function stopExploration() {
  await api('/api/explorer/stop', { method: 'POST', body: JSON.stringify({}) })
  running.value = false
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  await loadRuns()
}

async function pollStatus() {
  try {
    const s = await api('/api/explorer/status')
    progress.value = s
    if (!s.running) {
      running.value = false
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
      await loadRuns()
    }
  } catch {}
}

async function viewRun(name: string) {
  currentRun.value = await api(`/api/explorer/run/${name}`)
  selectedState.value = null
}

async function deleteRun(name: string) {
  if (!confirm(`Delete exploration "${name}"?`)) return
  await api(`/api/explorer/delete/${name}`, { method: 'DELETE' })
  await loadRuns()
  if (currentRun.value?.package === name) currentRun.value = null
}

function selectState(id: string) { selectedState.value = id }

function stateDetail(id: string): AppState | null {
  return currentRun.value?.states?.[id] || null
}

onMounted(async () => {
  await Promise.all([loadDevices(), loadRuns()])
  await loadPackages()
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div style="display: flex; gap: 12px; height: calc(100vh - 80px)">
    <!-- LEFT: Explorer (75%) -->
    <div style="flex: 3; overflow-y: auto; min-width: 0">
    <div class="flex items-center gap-2 mb-4">
      <h2 class="text-lg font-bold" style="color: var(--text-1)">⛏️ Skill-Miner</h2>
      <span v-if="installedPackages.length" class="text-xs px-2 py-0.5 rounded-full" style="background: var(--bg-deep); color: var(--text-4); border: 1px solid var(--border)">{{ installedPackages.length }} packages</span>
      <span class="text-xs ml-auto flex items-center gap-1.5" :style="{ color: running ? '#f59e0b' : 'var(--text-4)' }">
        <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%" :style="{ background: running ? '#f59e0b' : '#64748b' }"></span>
        {{ running ? 'exploring...' : 'idle' }}
      </span>
    </div>

    <!-- Launch panel -->
    <div class="card mb-4">
      <div class="flex gap-3 mb-3 items-end flex-wrap">
        <div style="position: relative; min-width: 200px; max-width: 260px; flex: 1">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Package</label>
          <input v-model="pkg" @input="onPkgInput" @focus="onPkgInput" @blur="hidePkgDropdown" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
            placeholder="com.zhiliaoapp.musically" />
          <div v-if="showPkgDropdown" class="absolute left-0 right-0 mt-1 rounded-lg overflow-auto z-10"
            style="background: var(--bg-card); border: 1px solid var(--border); max-height: 200px; box-shadow: 0 4px 12px rgba(0,0,0,0.3)">
            <div v-for="p in filteredPackages" :key="p" @mousedown="selectPkg(p)"
              class="px-3 py-1.5 text-xs cursor-pointer hover:bg-white/5" style="color: var(--text-2)">
              {{ p }}
            </div>
          </div>
        </div>
        <div style="min-width: 140px; max-width: 200px">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Device</label>
          <select v-model="device" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)">
            <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ d.nickname || d.serial }}</option>
          </select>
        </div>
        <div class="flex gap-2">
          <div>
            <label class="block text-xs mb-1" style="color: var(--text-3)">Depth</label>
            <input v-model.number="maxDepth" type="number" min="1" max="10" class="w-16 px-2 py-2 rounded-lg text-sm"
              style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
          </div>
          <div>
            <label class="block text-xs mb-1" style="color: var(--text-3)">States</label>
            <input v-model.number="maxStates" type="number" min="1" max="200" class="w-16 px-2 py-2 rounded-lg text-sm"
              style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
          </div>
          <div>
            <label class="block text-xs mb-1" style="color: var(--text-3)">Settle (s)</label>
            <input v-model.number="settle" type="number" min="0.5" max="10" step="0.5" class="w-16 px-2 py-2 rounded-lg text-sm"
              style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
          </div>
          <div class="flex items-end gap-2">
            <button v-if="!running" class="btn" style="background: #22c55e; color: white; border: none" @click="startExploration">▶ Start</button>
            <button class="btn" :disabled="!running" :style="{ borderColor: '#ef4444', color: running ? '#ef4444' : '#64748b', opacity: running ? 1 : 0.4, cursor: running ? 'pointer' : 'not-allowed' }" @click="stopExploration">⏹ Stop</button>
          </div>
        </div>
      </div>

      <!-- Progress -->
      <div v-if="running" class="mt-3">
        <div class="flex gap-4 text-xs mb-2" style="color: var(--text-3)">
          <span>States: {{ progress.states_found }}/{{ maxStates }}</span>
          <span>Transitions: {{ progress.transitions }}</span>
          <span>Depth: {{ progress.current_depth }}</span>
        </div>
        <div class="w-full rounded-full h-2" style="background: var(--bg-deep)">
          <div class="h-2 rounded-full transition-all" style="background: var(--accent)"
            :style="{ width: Math.min(100, (progress.states_found / maxStates) * 100) + '%' }" />
        </div>
        <div class="mt-2 p-2 rounded-lg max-h-32 overflow-auto"
          style="background: #0a0e14; border: 1px solid #1a1f2e; border-radius: 8px">
          <div v-for="(line, i) in cleanLogs" :key="i"
            style="font-size: 11px; line-height: 1.6; font-family: 'JetBrains Mono', 'Fira Code', monospace; padding: 0 4px"
            :style="{
              color: line.includes('New state') || line.includes('State') ? '#4ade80'
                : line.includes('Tapping') ? '#38bdf8'
                : line.includes('Back') || line.includes('lost') ? '#fbbf24'
                : line.includes('Done') ? '#a78bfa'
                : line.includes('Error') || line.includes('error') ? '#f87171'
                : '#64748b'
            }">{{ line }}</div>
        </div>
      </div>
    </div>

    <!-- Run detail -->
    <div v-if="currentRun" class="card mb-4">
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="font-semibold text-sm" style="color: var(--text-1)">{{ currentRun.package }}</div>
          <div class="text-xs" style="color: var(--text-3)">
            {{ currentRun.total_states }} states · {{ currentRun.total_transitions }} transitions
          </div>
        </div>
        <button class="btn btn-sm" @click="currentRun = null">Close</button>
      </div>

      <!-- State tabs -->
      <div class="flex gap-1 mb-3 flex-wrap">
        <button v-for="(state, id) in currentRun.states" :key="id"
          class="px-2 py-1 rounded text-xs" @click="selectState(String(id))"
          :class="selectedState === String(id) ? 'bg-indigo-500 text-white' : ''"
          :style="selectedState !== String(id) ? { background: 'var(--bg-deep)', color: 'var(--text-3)', border: '1px solid var(--border)' } : {}">
          {{ String(id).slice(0, 8) }}
        </button>
      </div>

      <!-- State detail -->
      <div v-if="selectedState && stateDetail(selectedState)" class="grid grid-cols-2 gap-4">
        <div>
          <img :src="`/api/explorer/screenshot/${currentRun.package}/${selectedState}`"
            class="rounded-lg w-full" style="max-width: 300px; border: 1px solid var(--border)" />
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--text-3)">
            Activity: {{ stateDetail(selectedState)?.activity || '—' }}
          </div>
          <div class="text-xs mb-1" style="color: var(--text-3)">
            Elements: {{ stateDetail(selectedState)?.elements?.length || 0 }}
          </div>
          <div class="text-xs mb-1" style="color: var(--text-3)">
            Depth: {{ stateDetail(selectedState)?.depth }}
          </div>
          <div class="mt-2 text-[10px] font-mono max-h-48 overflow-auto p-2 rounded"
            style="background: var(--bg-deep); color: var(--text-4)">
            <div v-for="(el, i) in (stateDetail(selectedState)?.elements || []).slice(0, 20)" :key="i">
              #{{ el.idx }} {{ el.class?.split('.')?.pop() }} "{{ el.text || el.content_desc || el.resource_id || '—' }}"
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Previous runs -->
    <div class="card">
      <div class="flex items-center justify-between mb-2">
        <div class="text-xs font-semibold" style="color: var(--text-3)">Previous Explorations</div>
        <button class="btn btn-sm" @click="loadRuns" title="Refresh">&#8635; Refresh</button>
      </div>
      <table class="w-full text-xs" style="color: var(--text-2)">
        <thead>
          <tr style="border-bottom: 1px solid var(--border)">
            <th class="text-left py-2 px-2">Package</th>
            <th class="text-right py-2 px-2">States</th>
            <th class="text-right py-2 px-2">Transitions</th>
            <th class="text-right py-2 px-2">Depth</th>
            <th class="text-left py-2 px-2">Date</th>
            <th class="text-right py-2 px-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.name" style="border-bottom: 1px solid var(--border)">
            <td class="py-1.5 px-2 font-mono">{{ (r as any).package || r.name }}</td>
            <td class="py-1.5 px-2 text-right">{{ r.states }}</td>
            <td class="py-1.5 px-2 text-right">{{ r.transitions }}</td>
            <td class="py-1.5 px-2 text-right">{{ r.max_depth }}</td>
            <td class="py-1.5 px-2">{{ r.date }}</td>
            <td class="py-1.5 px-2 text-right flex gap-1 justify-end">
              <button class="btn btn-sm" @click="viewRun(r.name)">👁</button>
              <button class="btn btn-sm" style="color: #ef4444" @click="deleteRun(r.name)">🗑</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!runs.length" class="text-center py-6" style="color: var(--text-4)">No explorations yet.</div>
    </div>
    </div><!-- end left column -->

    <!-- RIGHT: Phone stream (25%) -->
    <div style="flex: 1; min-width: 220px; max-width: 320px">
      <PhoneStreamWidget
        ref="phoneWidget"
        :serial="device"
        :label="devices.find(d => d.serial === device)?.nickname || ''"
        :show-keys="true"
        :compact="true"
        :auto-stream="false">
        <template #placeholder>Click Stream to watch<br/>the exploration live</template>
        <template #footer>
          <div v-if="running" style="padding: 8px 10px; border-top: 1px solid #1a2e1a; flex-shrink: 0; background: #060d06">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px">
              <span style="width: 5px; height: 5px; border-radius: 50%; background: #22c55e; animation: pulse 1.5s infinite"></span>
              <span style="font-size: 9px; color: #4ade80; font-weight: 600">Mining...</span>
              <span style="font-size: 9px; color: #3a5a3e; font-family: monospace; margin-left: auto">
                {{ progress.states_found }}/{{ maxStates }}
              </span>
            </div>
            <div v-for="(line, i) in cleanLogs.slice(-3)" :key="i"
              style="font-size: 9px; font-family: 'JetBrains Mono', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.5"
              :style="{
                color: line.includes('State') ? '#4ade80' : line.includes('Tapping') ? '#38bdf8' : '#3a5a3e'
              }">{{ line }}</div>
          </div>
        </template>
      </PhoneStreamWidget>
    </div>
  </div>
</template>
