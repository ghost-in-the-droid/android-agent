<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { useBenchmarkStore } from '@/stores/benchmarks'

const store = useBenchmarkStore()
const activeSubTab = ref<'tasks' | 'runs'>('tasks')
const toast = ref<{ msg: string; type: 'ok' | 'err' } | null>(null)
const expandedLog = ref<string | null>(null)
const liveLog = ref<Array<Record<string, any>>>([])
const liveRunId = ref<string | null>(null)
let liveEventSource: EventSource | null = null

const selectedTasks = ref<Set<string>>(new Set())
const runSuite = ref('ghost_bench')
const runProvider = ref('ollama')
const runModel = ref('gemma3:4b')
const runDevice = ref('emulator-5554')
const selectAll = ref(false)

type Provider = {
  id: string
  label: string
  models: string[]
}

const PROVIDERS: Provider[] = [
  { id: 'claude-code', label: 'Claude Code', models: ['sonnet', 'opus', 'haiku'] },
  { id: 'anthropic', label: 'Claude API', models: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514'] },
  { id: 'openrouter', label: 'OpenRouter', models: ['anthropic/claude-sonnet-4', 'google/gemini-2.5-pro'] },
  { id: 'ollama', label: 'Ollama (local)', models: ['llama3.2:3b', 'gemma3:4b', 'qwen3:4b', 'phi4-mini:3.8b', 'mistral:7b'] },
]

const currentModels = computed<string[]>(() => PROVIDERS.find(p => p.id === runProvider.value)?.models || [])
const runPlatform = computed<'android' | 'ios'>(() => runDevice.value.trim().startsWith('ios:') ? 'ios' : 'android')
const selectedTaskIds = computed(() => [...selectedTasks.value])
const tasksForRun = computed(() => {
  if (!selectedTasks.value.size) return store.tasks
  const selected = selectedTasks.value
  return store.tasks.filter(t => selected.has(t.id))
})
const unsupportedTasksForRun = computed(() => tasksForRun.value.filter(t => !taskSupportsPlatform(t, runPlatform.value)))
const canStartRun = computed(() => store.tasks.length > 0 && unsupportedTasksForRun.value.length === 0)
const runButtonTitle = computed(() => {
  if (!store.tasks.length) return 'No benchmark tasks loaded'
  if (!unsupportedTasksForRun.value.length) return ''
  const sample = unsupportedTasksForRun.value.slice(0, 3).map(t => t.id).join(', ')
  const suffix = unsupportedTasksForRun.value.length > 3 ? ` and ${unsupportedTasksForRun.value.length - 3} more` : ''
  return `${sample}${suffix} ${unsupportedTasksForRun.value.length === 1 ? 'does' : 'do'} not support ${runPlatform.value}`
})

function taskPlatforms(task: any): string[] {
  const platforms = Array.isArray(task.platforms) && task.platforms.length ? task.platforms : ['android']
  return platforms.map((p: string) => String(p).toLowerCase())
}

function taskSupportsPlatform(task: any, platform: 'android' | 'ios') {
  const platforms = taskPlatforms(task)
  return platforms.includes('all') || platforms.includes(platform)
}

function taskPlatformLabel(task: any) {
  const platforms = taskPlatforms(task)
  if (platforms.includes('all')) return 'All'
  return platforms.map((p: string) => p === 'ios' ? 'iOS' : 'Android').join(', ')
}

function onProviderChange() {
  const p = PROVIDERS.find(p => p.id === runProvider.value)
  const firstModel = p?.models[0]
  if (firstModel) runModel.value = firstModel
}

// Also try to fetch live Ollama models
async function fetchOllamaModels() {
  try {
    const resp = await fetch('/api/agent-chat/providers')
    if (resp.ok) {
      const providers = await resp.json()
      const ollama = providers.find((p: any) => p.id === 'ollama')
      if (ollama?.models?.length) {
        const idx = PROVIDERS.findIndex(p => p.id === 'ollama')
        const provider = idx >= 0 ? PROVIDERS[idx] : null
        if (provider) provider.models = ollama.models
      }
    }
  } catch {}
}

const streamUrl = computed(() =>
  runDevice.value ? `/api/phone/stream?device=${encodeURIComponent(runDevice.value)}&fps=3` : ''
)

let pollTimer: ReturnType<typeof setInterval> | null = null

function showToast(msg: string, type: 'ok' | 'err' = 'ok') {
  toast.value = { msg, type }
  setTimeout(() => { toast.value = null }, 4000)
}

function toggleSelectAll() {
  if (selectAll.value) {
    const compatible = store.tasks.filter(t => taskSupportsPlatform(t, runPlatform.value))
    selectedTasks.value = new Set(compatible.map(t => t.id))
    if (!compatible.length) {
      selectAll.value = false
      showToast(`No ${runPlatform.value} benchmark tasks are available`, 'err')
    }
  } else {
    selectedTasks.value = new Set()
  }
}

function toggleTask(id: string) {
  const task = store.tasks.find(t => t.id === id)
  if (task && !taskSupportsPlatform(task, runPlatform.value)) {
    showToast(`${id} does not support ${runPlatform.value}`, 'err')
    return
  }
  const next = new Set(selectedTasks.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedTasks.value = next
  const compatibleCount = store.tasks.filter(t => taskSupportsPlatform(t, runPlatform.value)).length
  selectAll.value = compatibleCount > 0 && next.size === compatibleCount
}

async function startRun() {
  if (!canStartRun.value) {
    showToast(runButtonTitle.value || `No compatible ${runPlatform.value} benchmark tasks selected`, 'err')
    return
  }
  const ids = selectedTasks.value.size > 0 ? [...selectedTasks.value] : null
  try {
    const result = await store.startRun(runSuite.value, ids, runModel.value, runDevice.value, runProvider.value)
    showToast(`Benchmark started: ${ids?.length || 'all'} tasks`)
    activeSubTab.value = 'runs'

    if (result.run_id) {
      liveLog.value = []
      liveRunId.value = result.run_id
      if (liveEventSource) liveEventSource.close()
      liveEventSource = new EventSource(`/api/benchmarks/runs/${result.run_id}/events`)
      liveEventSource.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data)
          liveLog.value.push(ev)
          if (liveLog.value.length > 200) liveLog.value = liveLog.value.slice(-200)
          if (ev.type === 'task_result' || ev.type === 'run_done') store.fetchRuns()
          if (ev.type === 'run_done') {
            liveEventSource?.close()
            liveEventSource = null
            liveRunId.value = null
          }
        } catch {}
      }
      liveEventSource.onerror = () => {
        liveEventSource?.close()
        liveEventSource = null
        liveRunId.value = null
      }
    }
  } catch (e: any) {
    showToast(e.message, 'err')
  }
}

async function handleStop(id: string) {
  try { await store.stopRun(id); showToast('Run stopped') }
  catch (e: any) { showToast(e.message, 'err') }
}

const activeRun = computed(() => store.runs.find(r => r.status === 'running'))

watch(runPlatform, () => {
  const allowed = new Set(store.tasks.filter(t => taskSupportsPlatform(t, runPlatform.value)).map(t => t.id))
  selectedTasks.value = new Set(selectedTaskIds.value.filter(id => allowed.has(id)))
  selectAll.value = selectedTasks.value.size > 0 && selectedTasks.value.size === allowed.size
})

onMounted(async () => {
  await Promise.all([store.fetchSuites(), store.fetchTasks(), store.fetchRuns()])
  fetchOllamaModels()
  pollTimer = setInterval(() => {
    if (activeSubTab.value === 'runs' || activeRun.value) store.fetchRuns()
  }, 5000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (liveEventSource) { liveEventSource.close(); liveEventSource = null }
})
</script>

<template>
  <div>
    <Transition name="fade">
      <div v-if="toast" class="fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium shadow-lg"
        :style="{ background: toast.type === 'ok' ? '#065f46' : '#7f1d1d', color: toast.type === 'ok' ? '#6ee7b7' : '#fca5a5', border: `1px solid ${toast.type === 'ok' ? '#059669' : '#dc2626'}` }">
        {{ toast.msg }}
      </div>
    </Transition>

    <div style="display: grid; grid-template-columns: 1fr 25%; gap: 16px; min-height: 600px">
      <!-- LEFT: Content -->
      <div>
        <div class="flex gap-2 mb-4 items-center">
          <button class="px-4 py-1.5 text-sm font-semibold rounded-lg transition-colors"
            :class="activeSubTab === 'tasks' ? 'text-indigo-400 bg-indigo-500/10' : 'text-slate-500 hover:text-slate-300'"
            @click="activeSubTab = 'tasks'">Tasks</button>
          <button class="px-4 py-1.5 text-sm font-semibold rounded-lg transition-colors"
            :class="activeSubTab === 'runs' ? 'text-indigo-400 bg-indigo-500/10' : 'text-slate-500 hover:text-slate-300'"
            @click="activeSubTab = 'runs'; store.fetchRuns()">Runs</button>
          <span v-if="activeRun" class="ml-auto text-xs px-3 py-1 rounded-full bg-yellow-500/15 text-yellow-400 animate-pulse">
            Running: {{ activeRun.current_task }} ({{ activeRun.results?.length || 0 }}/{{ activeRun.total_tasks }})
          </span>
        </div>

        <!-- Tasks -->
        <div v-show="activeSubTab === 'tasks'" class="space-y-4">
          <div class="card px-4 py-3 flex items-center gap-3 flex-wrap">
            <span class="text-xs font-semibold" style="color: var(--text-2)">Run Config</span>
            <select v-model="runProvider" @change="onProviderChange" class="text-xs px-2 py-1 rounded" style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-2)">
              <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
            </select>
            <select v-model="runModel" class="text-xs px-2 py-1 rounded" style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-2); max-width: 180px">
              <option v-for="m in currentModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <input v-model="runDevice" class="text-xs px-2 py-1 rounded" style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-2); width: 140px" placeholder="device serial" />
            <span class="text-xs px-2 py-1 rounded font-semibold" style="background: var(--bg-deep); color: var(--text-3); border: 1px solid var(--border)">
              {{ runPlatform === 'ios' ? 'iOS' : 'Android' }}
            </span>
            <button @click="startRun" :disabled="!canStartRun" :title="runButtonTitle"
              class="ml-auto px-4 py-1.5 text-sm font-semibold rounded-lg disabled:cursor-not-allowed disabled:opacity-50"
              style="background: #059669; color: white">
              Run {{ selectedTasks.size || 'All' }} Tasks
            </button>
          </div>
          <div v-if="unsupportedTasksForRun.length" class="card px-4 py-2 text-xs" style="border-color: #f59e0b55; color: #fbbf24; background: #f59e0b0d">
            {{ unsupportedTasksForRun.length }} {{ selectedTasks.size ? 'selected' : 'available' }} benchmark task{{ unsupportedTasksForRun.length === 1 ? '' : 's' }} cannot run on {{ runPlatform }}.
          </div>

          <div class="card" style="min-height: 200px">
            <div class="flex items-center justify-between mb-3">
              <h2 class="text-base font-semibold" style="color: var(--text-1)">Ghost Bench</h2>
              <span class="text-xs" style="color: var(--text-4)">{{ store.tasks.length }} tasks · {{ runPlatform }}</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-xs uppercase" style="color: var(--text-4)">
                    <th class="pb-2 pr-2 w-8"><input type="checkbox" v-model="selectAll" @change="toggleSelectAll" /></th>
                    <th class="pb-2 pr-2">Task</th>
                    <th class="pb-2 pr-2">Goal</th>
                    <th class="pb-2 pr-2">Category</th>
                    <th class="pb-2 pr-2">Platform</th>
                    <th class="pb-2 pr-2">Steps</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="task in store.tasks" :key="task.id" class="border-t" style="border-color: var(--border)"
                    :class="{ 'bg-indigo-500/5': selectedTasks.has(task.id), 'opacity-50': !taskSupportsPlatform(task, runPlatform) }">
                    <td class="py-2 pr-2"><input type="checkbox" :checked="selectedTasks.has(task.id)" :disabled="!taskSupportsPlatform(task, runPlatform)" @change="toggleTask(task.id)" /></td>
                    <td class="py-2 pr-2 font-mono text-xs" style="color: var(--text-2)">{{ task.id }}</td>
                    <td class="py-2 pr-2 truncate" style="color: var(--text-1); max-width: 280px" :title="task.goal">{{ task.goal }}</td>
                    <td class="py-2 pr-2 text-xs" style="color: var(--text-3)">{{ task.category }}</td>
                    <td class="py-2 pr-2 text-xs">
                      <span class="px-2 py-0.5 rounded-full font-semibold"
                        :style="{ background: taskSupportsPlatform(task, runPlatform) ? '#05966922' : '#64748b22', color: taskSupportsPlatform(task, runPlatform) ? '#34d399' : 'var(--text-4)' }">
                        {{ taskPlatformLabel(task) }}
                      </span>
                    </td>
                    <td class="py-2 pr-2 text-xs" style="color: var(--text-3)">{{ task.max_steps }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Runs -->
        <div v-show="activeSubTab === 'runs'" class="space-y-4">
          <div v-if="!store.runs.length" class="card px-4 py-8 text-center" style="color: var(--text-3)">
            No runs yet. Go to Tasks to start one.
          </div>

          <div v-for="run in store.runs" :key="run.id" class="card px-4 py-3">
            <div class="flex items-center gap-3 mb-3">
              <span class="font-mono text-xs px-2 py-0.5 rounded" style="background: var(--bg-deep); color: var(--text-3)">{{ run.id }}</span>
              <span class="text-sm font-semibold" style="color: var(--text-1)">{{ run.provider }}/{{ run.model }}</span>
              <span class="text-xs" style="color: var(--text-4)">{{ run.device }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full font-semibold"
                :class="{
                  'bg-green-500/15 text-green-400': run.status === 'completed',
                  'bg-yellow-500/15 text-yellow-400': run.status === 'running',
                  'bg-slate-500/15 text-slate-400': run.status === 'stopped',
                }">{{ run.status }}</span>
              <button v-if="run.status === 'running'" @click="handleStop(run.id)"
                class="ml-auto text-xs px-3 py-1 rounded" style="border: 1px solid #ef4444; color: #ef4444">Stop</button>
            </div>

            <div class="grid grid-cols-4 gap-3 mb-3">
              <div class="text-center">
                <div class="text-lg font-bold" :style="{ color: run.success_rate > 0.5 ? '#34d399' : run.success_rate > 0 ? '#fbbf24' : '#94a3b8' }">
                  {{ (run.success_rate * 100).toFixed(0) }}%
                </div>
                <div class="text-xs" style="color: var(--text-4)">Success</div>
              </div>
              <div class="text-center">
                <div class="text-lg font-bold" style="color: var(--text-2)">{{ run.passed }}/{{ run.total_tasks }}</div>
                <div class="text-xs" style="color: var(--text-4)">Passed</div>
              </div>
              <div class="text-center">
                <div class="text-lg font-bold" style="color: var(--text-2)">{{ run.total_time_s?.toFixed(0) || 0 }}s</div>
                <div class="text-xs" style="color: var(--text-4)">Total</div>
              </div>
              <div class="text-center">
                <div class="text-lg font-bold" style="color: var(--text-2)">{{ run.total_tasks > 0 ? (run.total_time_s / run.total_tasks).toFixed(0) : 0 }}s</div>
                <div class="text-xs" style="color: var(--text-4)">Avg/Task</div>
              </div>
            </div>

            <div v-if="run.results?.length">
              <div v-for="r in run.results" :key="r.task_id" class="border-t" style="border-color: var(--border)">
                <div class="flex items-center gap-3 py-2 cursor-pointer hover:bg-white/[0.02] px-1 rounded"
                  @click="expandedLog = expandedLog === r.task_id ? null : r.task_id">
                  <span class="text-xs" style="color: var(--text-4)">{{ expandedLog === r.task_id ? '▼' : '▶' }}</span>
                  <span class="font-mono text-xs" style="color: var(--text-2); min-width: 160px">{{ r.task_id }}</span>
                  <span class="text-xs font-semibold" :style="{ color: r.score > 0 ? '#34d399' : '#ef4444', minWidth: '36px' }">
                    {{ r.score > 0 ? 'PASS' : 'FAIL' }}
                  </span>
                  <span class="text-xs" style="color: var(--text-3)">{{ r.steps }} steps</span>
                  <span class="text-xs" style="color: var(--text-3)">{{ r.time_s?.toFixed(0) }}s</span>
                  <span class="text-xs truncate" style="color: var(--text-4); max-width: 200px">{{ r.reason }}</span>
                </div>
                <div v-if="expandedLog === r.task_id && r.agent_log?.length" class="mb-3 ml-4 p-3 rounded-lg"
                  style="background: var(--bg-deep); border: 1px solid var(--border); max-height: 400px; overflow-y: auto">
                  <div style="display: flex; flex-direction: column; gap: 4px">
                    <template v-for="(ev, j) in r.agent_log" :key="j">
                      <div v-if="ev.type === 'text'" style="background: #1a1f2e; color: var(--text-1); padding: 6px 10px; border-radius: 8px; font-size: 11px; line-height: 1.5; white-space: pre-wrap; word-break: break-word">{{ ev.content }}</div>
                      <div v-else-if="ev.type === 'tool_call'" style="font-size: 10px; color: #38bdf8; padding: 2px 8px; background: #0ea5e908; border-radius: 10px; border: 1px solid #0ea5e922; width: fit-content">🔧 {{ ev.name }}({{ JSON.stringify(ev.args || {}).slice(0, 100) }})</div>
                      <div v-else-if="ev.type === 'tool_result'" style="font-size: 9px; font-family: monospace; color: #64748b; padding: 3px 8px; max-height: 80px; overflow: hidden; border-left: 2px solid #1e293b; margin-left: 8px; white-space: pre-wrap; word-break: break-all">↳ {{ ev.result?.slice(0, 300) || ev.name }}</div>
                      <div v-else-if="ev.type === 'error'" style="font-size: 10px; color: #f87171; padding: 4px 8px; background: #ef444411; border-radius: 6px; border-left: 2px solid #ef4444">{{ ev.content }}</div>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="run.status === 'running' && run.total_tasks > 0" class="mt-2">
              <div class="w-full h-1.5 rounded-full" style="background: var(--bg-deep)">
                <div class="h-1.5 rounded-full transition-all" style="background: #059669"
                  :style="{ width: `${((run.results?.length || 0) / run.total_tasks) * 100}%` }"></div>
              </div>
              <div class="text-xs mt-1" style="color: var(--text-4)">{{ run.current_task }}...</div>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Device + Live Log -->
      <div style="position: sticky; top: 12px; height: fit-content; display: flex; flex-direction: column; gap: 8px; max-height: calc(100vh - 80px); overflow: hidden">
        <div class="card p-2" style="flex-shrink: 0">
          <div class="flex items-center justify-between mb-2 px-1">
            <span class="text-xs font-semibold" style="color: var(--text-2)">Device</span>
            <span class="text-xs" style="color: var(--text-4)">{{ runDevice }}</span>
          </div>
          <img v-if="streamUrl" :src="streamUrl" style="width: 100%; border-radius: 8px; background: #000; aspect-ratio: 9/16" alt="Device" />
          <div v-else class="flex items-center justify-center" style="aspect-ratio: 9/16; background: #0a0e17; border-radius: 8px">
            <span class="text-xs" style="color: var(--text-4)">No device</span>
          </div>
        </div>

        <div class="card p-2" style="flex: 1; min-height: 150px; overflow: hidden; display: flex; flex-direction: column">
          <div class="flex items-center justify-between mb-2 px-1">
            <span class="text-xs font-semibold" style="color: var(--text-2)">{{ liveRunId ? 'Live Log' : 'Agent Log' }}</span>
            <span v-if="liveRunId" class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          </div>
          <div style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 3px; padding-right: 4px">
            <div v-if="!liveLog.length" class="text-xs text-center py-4" style="color: var(--text-4)">
              Start a run to see live agent activity.
            </div>
            <template v-for="(ev, i) in liveLog" :key="i">
              <div v-if="ev.type === 'task_start'" style="font-size: 10px; font-weight: 600; color: #fbbf24; padding: 4px 6px; background: #fbbf2410; border-radius: 6px; border-left: 2px solid #fbbf24">Task: {{ ev.goal }}</div>
              <div v-else-if="ev.type === 'init'" style="font-size: 9px; color: #64748b; padding: 1px 6px">init: {{ ev.desc }}</div>
              <div v-else-if="ev.type === 'agent' && ev.content" style="font-size: 10px; color: var(--text-1); padding: 4px 6px; background: #1a1f2e; border-radius: 6px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow: hidden">{{ ev.content.slice(0, 300) }}</div>
              <div v-else-if="ev.type === 'agent' && ev.name && !ev.result" style="font-size: 9px; color: #38bdf8; padding: 2px 6px; background: #0ea5e908; border-radius: 8px; border: 1px solid #0ea5e922; width: fit-content">🔧 {{ ev.name }}</div>
              <div v-else-if="ev.type === 'agent' && ev.result" style="font-size: 8px; font-family: monospace; color: #475569; padding: 1px 6px; border-left: 2px solid #1e293b; margin-left: 6px; max-height: 40px; overflow: hidden; word-break: break-all">↳ {{ ev.result?.slice(0, 150) }}</div>
              <div v-else-if="ev.type === 'task_result'" style="font-size: 10px; font-weight: 600; padding: 3px 6px; border-radius: 6px"
                :style="{ color: ev.score > 0 ? '#34d399' : '#ef4444', background: ev.score > 0 ? '#34d39910' : '#ef444410', borderLeft: `2px solid ${ev.score > 0 ? '#34d399' : '#ef4444'}` }">
                {{ ev.score > 0 ? 'PASS' : 'FAIL' }} — {{ ev.reason }}
              </div>
              <div v-else-if="ev.type === 'run_done'" style="font-size: 10px; font-weight: 600; color: #a78bfa; padding: 4px 6px; background: #a78bfa10; border-radius: 6px; text-align: center">Benchmark complete</div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div v-if="store.error" class="mt-4 card px-4 py-3" style="border-color: #ef4444">
      <div class="text-xs" style="color: #ef4444">{{ store.error }}</div>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
