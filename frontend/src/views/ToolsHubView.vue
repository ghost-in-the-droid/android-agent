<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/composables/useApi'

interface ToolParam { name: string; type: string; required: boolean; default?: any }
interface Tool { name: string; description: string; params: ToolParam[]; category: string }
interface ToolGroup { category: string; tools: Tool[] }

const groups = ref<ToolGroup[]>([])
const devices = ref<{serial: string; nickname?: string}[]>([])
const loading = ref(false)
const search = ref('')
const selectedTool = ref<Tool | null>(null)
const testDevice = ref('')
const testArgs = ref<Record<string, string>>({})
const testResult = ref('')
const testRunning = ref(false)
const testDuration = ref(0)

const CATEGORY_EMOJI: Record<string, string> = {
  'Screen Reading': '👁', 'Input': '👆', 'App Management': '🚀',
  'Shell': '💻', 'Clipboard & Notifications': '📋', 'Skills': '🧩',
  'Device': '📱', 'System': '⚙️',
}

const filteredGroups = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return groups.value
  return groups.value.map(g => ({
    ...g,
    tools: g.tools.filter(t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
  })).filter(g => g.tools.length > 0)
})

const totalTools = computed(() => groups.value.reduce((sum, g) => sum + g.tools.length, 0))

async function load() {
  loading.value = true
  try {
    groups.value = await api('/api/tools')
    const devResp = await api('/api/phone/devices')
    devices.value = devResp.devices || devResp || []
    if (devices.value.length && !testDevice.value) testDevice.value = devices.value[0].serial
  } finally { loading.value = false }
}

function selectTool(tool: Tool) {
  selectedTool.value = tool
  testResult.value = ''
  testArgs.value = {}
  for (const p of tool.params) {
    testArgs.value[p.name] = p.name === 'device' ? testDevice.value : (p.default != null ? String(p.default) : '')
  }
}

async function runTest() {
  if (!selectedTool.value) return
  testRunning.value = true
  testResult.value = ''
  // Update device arg
  if ('device' in testArgs.value) testArgs.value.device = testDevice.value
  // Parse numeric args
  const args: Record<string, any> = {}
  for (const [k, v] of Object.entries(testArgs.value)) {
    const param = selectedTool.value.params.find(p => p.name === k)
    if (param?.type === 'integer' || param?.type === 'number') args[k] = Number(v) || 0
    else if (param?.type === 'boolean') args[k] = v === 'true'
    else args[k] = v
  }
  try {
    const res = await api('/api/tools/test', {
      method: 'POST',
      body: JSON.stringify({ name: selectedTool.value.name, args })
    })
    testResult.value = res.ok ? res.result : `ERROR: ${res.error}`
    testDuration.value = res.duration_ms || 0
  } catch (e: any) {
    testResult.value = `Error: ${e.message}`
  }
  testRunning.value = false
}

onMounted(load)
</script>

<template>
  <div style="height: calc(100vh - 80px); display: flex; gap: 12px">
    <!-- LEFT: Tool list -->
    <div style="flex: 1; overflow-y: auto; min-width: 0">
      <!-- Header -->
      <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px">
        <h2 style="font-size: 20px; font-weight: 700; color: var(--text-1); margin: 0">🔧 Tools Hub</h2>
        <span style="font-size: 12px; color: var(--text-4)">{{ totalTools }} tools</span>
      </div>

      <!-- Search -->
      <input v-model="search" type="text" placeholder="Filter tools..."
        style="width: 100%; padding: 10px 14px; font-size: 13px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-deep); color: var(--text-1); outline: none; margin-bottom: 16px" />

      <!-- Tool groups -->
      <div v-for="g in filteredGroups" :key="g.category" style="margin-bottom: 16px">
        <div style="font-size: 13px; font-weight: 600; color: var(--text-2); margin-bottom: 8px; display: flex; align-items: center; gap: 6px">
          <span>{{ CATEGORY_EMOJI[g.category] || '🔧' }}</span>
          <span>{{ g.category }}</span>
          <span style="font-size: 10px; color: var(--text-4); font-weight: 400">({{ g.tools.length }})</span>
        </div>
        <div style="display: flex; flex-direction: column; gap: 4px">
          <div v-for="t in g.tools" :key="t.name"
            @click="selectTool(t)"
            style="padding: 10px 14px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; transition: all 0.12s"
            :style="{ borderColor: selectedTool?.name === t.name ? '#6366f1' : 'var(--border)', background: selectedTool?.name === t.name ? '#6366f108' : 'var(--bg-card)' }">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px">
              <span style="font-size: 13px; font-weight: 600; color: var(--text-1); font-family: 'JetBrains Mono', monospace">{{ t.name }}</span>
              <span v-if="t.params.length" style="font-size: 9px; color: var(--text-4); background: var(--bg-deep); padding: 1px 5px; border-radius: 4px">
                {{ t.params.filter(p => p.required).length }} req / {{ t.params.length }} params
              </span>
            </div>
            <div style="font-size: 11px; color: var(--text-3); line-height: 1.4">{{ t.description }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT: Tool detail + test panel -->
    <div style="width: 400px; flex-shrink: 0; overflow-y: auto">
      <div v-if="!selectedTool" style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-4); font-size: 13px">
        Select a tool to inspect and test
      </div>
      <div v-else style="display: flex; flex-direction: column; gap: 12px">
        <!-- Tool header -->
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 16px">
          <div style="font-size: 16px; font-weight: 700; color: var(--text-1); font-family: 'JetBrains Mono', monospace; margin-bottom: 4px">
            {{ selectedTool.name }}
          </div>
          <div style="font-size: 10px; color: #6366f1; margin-bottom: 8px">{{ selectedTool.category }}</div>
          <div style="font-size: 12px; color: var(--text-2); line-height: 1.5">{{ selectedTool.description }}</div>
        </div>

        <!-- Parameters -->
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 16px">
          <div style="font-size: 12px; font-weight: 600; color: var(--text-2); margin-bottom: 10px">Parameters</div>
          <div v-if="!selectedTool.params.length" style="font-size: 11px; color: var(--text-4)">No parameters</div>
          <div v-for="p in selectedTool.params" :key="p.name" style="margin-bottom: 8px">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px">
              <span style="font-size: 11px; font-weight: 600; color: var(--text-1); font-family: monospace">{{ p.name }}</span>
              <span style="font-size: 9px; color: var(--text-4); background: var(--bg-deep); padding: 1px 5px; border-radius: 3px">{{ p.type }}</span>
              <span v-if="p.required" style="font-size: 9px; color: #f59e0b">required</span>
            </div>
            <input v-if="p.name === 'device'"
              v-model="testDevice"
              style="width: 100%; padding: 6px 10px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1); outline: none; font-family: monospace" />
            <select v-else-if="p.name === 'device'" v-model="testDevice"
              style="width: 100%; padding: 6px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1)">
              <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ d.nickname || d.serial }}</option>
            </select>
            <input v-else v-model="testArgs[p.name]"
              :placeholder="p.default != null ? String(p.default) : ''"
              style="width: 100%; padding: 6px 10px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1); outline: none; font-family: monospace" />
          </div>

          <!-- Device selector for tools with device param -->
          <div v-if="selectedTool.params.some(p => p.name === 'device')" style="margin-bottom: 8px">
            <div style="font-size: 10px; color: var(--text-3); margin-bottom: 3px">Quick device select</div>
            <select v-model="testDevice"
              style="width: 100%; padding: 6px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1)"
              @change="testArgs.device = testDevice">
              <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ d.nickname || d.serial }}</option>
            </select>
          </div>

          <button @click="runTest" :disabled="testRunning"
            style="width: 100%; padding: 8px; font-size: 12px; font-weight: 600; background: #6366f1; color: white; border: none; border-radius: 8px; cursor: pointer; margin-top: 4px"
            :style="{ opacity: testRunning ? 0.5 : 1 }">
            {{ testRunning ? 'Running...' : '▶ Test Tool' }}
          </button>
        </div>

        <!-- Result -->
        <div v-if="testResult" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 16px">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
            <span style="font-size: 12px; font-weight: 600; color: var(--text-2)">Result</span>
            <span v-if="testDuration" style="font-size: 10px; color: var(--text-4); font-family: monospace">{{ testDuration.toFixed(0) }}ms</span>
          </div>
          <pre style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: var(--text-3); background: #0a0e14; padding: 12px; border-radius: 8px; overflow-x: auto; max-height: 400px; overflow-y: auto; white-space: pre-wrap; margin: 0; line-height: 1.5"
            :style="{ color: testResult.startsWith('ERROR') || testResult.startsWith('Error') ? '#f87171' : '#4ade80' }">{{ testResult }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
