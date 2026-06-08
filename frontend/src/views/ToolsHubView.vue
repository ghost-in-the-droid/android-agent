<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/composables/useApi'

interface ToolParam { name: string; type: string; required: boolean; default?: any; description?: string; items?: any }
interface ToolPlatformSupport { support: string; android: boolean; ios: boolean; notes?: string }
interface Tool { name: string; description: string; params: ToolParam[]; category: string; platform_support?: ToolPlatformSupport }
interface ToolGroup { category: string; tools: Tool[] }
interface ToolDevice {
  serial: string
  nickname?: string
  model?: string
  platform?: string
  status?: string
  status_message?: string
}

const groups = ref<ToolGroup[]>([])
const devices = ref<ToolDevice[]>([])
const loading = ref(false)
const search = ref('')
const selectedTool = ref<Tool | null>(null)
const testDevice = ref('')
const testArgs = ref<Record<string, any>>({})
const testResult = ref('')
const testRunning = ref(false)
const testDuration = ref(0)

const CATEGORY_EMOJI: Record<string, string> = {
  'Screen Reading': '👁', 'Input': '👆', 'App Management': '🚀',
  'Shell': '💻', 'Clipboard & Notifications': '📋', 'Skills': '🧩',
  'Web': '🌐', 'Marketing': '📣', 'Device': '📱', 'System': '⚙️',
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
const selectedDevicePlatform = computed(() => testDevice.value.startsWith('ios:') ? 'ios' : 'android')
const selectedToolNeedsDevice = computed(() =>
  !!selectedTool.value?.params.some(p => p.name === 'device')
)
const selectedToolSupportsDevice = computed(() => {
  if (!selectedTool.value || !selectedToolNeedsDevice.value) return true
  return toolSupportsPlatform(selectedTool.value, selectedDevicePlatform.value)
})
const selectedToolSupportMessage = computed(() => {
  if (!selectedTool.value || !selectedToolNeedsDevice.value || selectedToolSupportsDevice.value) return ''
  const platform = selectedDevicePlatform.value === 'ios' ? 'iOS' : 'Android'
  return `${selectedTool.value.name} does not support ${platform}. ${selectedTool.value.platform_support?.notes || ''}`.trim()
})

function isIosSerial(serial: string): boolean {
  return serial.startsWith('ios:')
}

function devicePlatform(device: ToolDevice): 'ios' | 'android' {
  const platform = String(device.platform || '').toLowerCase()
  if (platform === 'ios') return 'ios'
  return isIosSerial(device.serial) ? 'ios' : 'android'
}

function deviceLabel(device: ToolDevice): string {
  const platform = devicePlatform(device) === 'ios' ? 'iOS' : 'Android'
  const label = device.nickname || device.model || device.serial
  const status = device.status && device.status !== 'available' ? ` · ${device.status}` : ''
  return `${label} (${platform}${status})`
}

function toolSupportsPlatform(tool: Tool, platform: 'android' | 'ios'): boolean {
  const support = tool.platform_support
  if (!support) return true
  return platform === 'ios' ? !!support.ios : !!support.android
}

function supportLabel(tool: Tool): string {
  const support = tool.platform_support
  if (!support) return 'Unaudited'
  if (support.android && support.ios) return 'Android + iOS'
  if (support.ios) return 'iOS only'
  if (support.android) return support.support === 'ios_planned' ? 'Android, iOS planned' : 'Android only'
  return support.support || 'Unsupported'
}

function supportBadgeClass(tool: Tool, platform: 'android' | 'ios'): string {
  return toolSupportsPlatform(tool, platform) ? 'tool-platform-badge--on' : 'tool-platform-badge--off'
}

function defaultParamValue(param: ToolParam): any {
  if (param.name === 'device') return testDevice.value
  if (param.default !== undefined) {
    if (param.type === 'object' || param.type === 'array') {
      return JSON.stringify(param.default, null, 2)
    }
    return String(param.default)
  }
  if (param.type === 'object') return '{}'
  if (param.type === 'array') return '[]'
  if (param.type === 'boolean') return 'false'
  return ''
}

function parseParamValue(param: ToolParam, value: any): any {
  if (param.type === 'integer') return Number.parseInt(String(value || '0'), 10) || 0
  if (param.type === 'number') return Number(value) || 0
  if (param.type === 'boolean') return value === true || String(value).toLowerCase() === 'true'
  if (param.type === 'object' || param.type === 'array') {
    if (typeof value !== 'string') return value
    const raw = value.trim()
    if (!raw) return param.type === 'array' ? [] : {}
    try {
      const parsed = JSON.parse(raw)
      if (param.type === 'array' && !Array.isArray(parsed)) throw new Error('expected array')
      if (param.type === 'object' && (Array.isArray(parsed) || parsed === null || typeof parsed !== 'object')) {
        throw new Error('expected object')
      }
      return parsed
    } catch (error: any) {
      throw new Error(`${param.name} must be valid JSON ${param.type}: ${error?.message || error}`)
    }
  }
  return value
}

async function load() {
  loading.value = true
  try {
    groups.value = await api('/api/tools')
    const devResp = await api('/api/phone/devices')
    devices.value = devResp.devices || devResp || []
    const firstDevice = devices.value[0]
    if (firstDevice && !testDevice.value) testDevice.value = firstDevice.serial
  } finally { loading.value = false }
}

function selectTool(tool: Tool) {
  selectedTool.value = tool
  testResult.value = ''
  testArgs.value = {}
  for (const p of tool.params) {
    testArgs.value[p.name] = defaultParamValue(p)
  }
}

async function runTest() {
  if (!selectedTool.value) return
  if (!selectedToolSupportsDevice.value) {
    testDuration.value = 0
    testResult.value = `ERROR: ${selectedToolSupportMessage.value}`
    return
  }
  testRunning.value = true
  testResult.value = ''
  // Update device arg
  if ('device' in testArgs.value) testArgs.value.device = testDevice.value
  const args: Record<string, any> = {}
  try {
    for (const [k, v] of Object.entries(testArgs.value)) {
      const param = selectedTool.value.params.find(p => p.name === k)
      args[k] = param ? parseParamValue(param, v) : v
    }
  } catch (error: any) {
    testRunning.value = false
    testResult.value = `ERROR: ${error?.message || error}`
    return
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

watch(testDevice, (serial) => {
  if (selectedTool.value?.params.some(p => p.name === 'device')) {
    testArgs.value.device = serial
  }
})

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
            <div class="tool-platform-row">
              <span class="tool-platform-badge" :class="supportBadgeClass(t, 'android')">Android</span>
              <span class="tool-platform-badge" :class="supportBadgeClass(t, 'ios')">iOS</span>
              <span class="tool-platform-summary">{{ supportLabel(t) }}</span>
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
          <div class="tool-platform-row tool-platform-row--detail">
            <span class="tool-platform-badge" :class="supportBadgeClass(selectedTool, 'android')">Android</span>
            <span class="tool-platform-badge" :class="supportBadgeClass(selectedTool, 'ios')">iOS</span>
            <span class="tool-platform-summary">{{ supportLabel(selectedTool) }}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-2); line-height: 1.5">{{ selectedTool.description }}</div>
          <div v-if="selectedTool.platform_support?.notes" class="tool-platform-notes">{{ selectedTool.platform_support.notes }}</div>
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
            <select v-if="p.name === 'device' && devices.length" v-model="testDevice"
              style="width: 100%; padding: 6px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1)">
              <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ deviceLabel(d) }}</option>
            </select>
            <input v-else-if="p.name === 'device'"
              v-model="testDevice"
              style="width: 100%; padding: 6px 10px; font-size: 11px; background: var(--bg-deep); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1); outline: none; font-family: monospace" />
            <textarea v-else-if="p.type === 'object' || p.type === 'array'" v-model="testArgs[p.name]"
              :placeholder="p.type === 'array' ? '[]' : '{}'"
              class="tool-param-textarea"
              rows="5" />
            <select v-else-if="p.type === 'boolean'" v-model="testArgs[p.name]" class="tool-param-select">
              <option value="false">false</option>
              <option value="true">true</option>
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
              <option v-for="d in devices" :key="d.serial" :value="d.serial">{{ deviceLabel(d) }}</option>
            </select>
          </div>
          <div v-if="selectedToolSupportMessage" class="tool-platform-warning">
            {{ selectedToolSupportMessage }}
          </div>

          <button @click="runTest" :disabled="testRunning || !selectedToolSupportsDevice"
            style="width: 100%; padding: 8px; font-size: 12px; font-weight: 600; background: #6366f1; color: white; border: none; border-radius: 8px; cursor: pointer; margin-top: 4px"
            :style="{ opacity: testRunning || !selectedToolSupportsDevice ? 0.5 : 1 }">
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

<style scoped>
.tool-platform-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin: 4px 0 6px;
}

.tool-platform-row--detail {
  margin-bottom: 10px;
}

.tool-platform-badge {
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0;
  border: 1px solid transparent;
}

.tool-platform-badge--on {
  color: #bbf7d0;
  background: rgba(22, 101, 52, 0.32);
  border-color: rgba(34, 197, 94, 0.28);
}

.tool-platform-badge--off {
  color: #64748b;
  background: #0f172a;
  border-color: #1e293b;
}

.tool-platform-summary {
  color: var(--text-4);
  font-size: 9px;
}

.tool-platform-notes {
  margin-top: 8px;
  padding: 8px;
  color: #94a3b8;
  background: #0a0e14;
  border: 1px solid #1e2438;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.45;
}

.tool-platform-warning {
  margin-bottom: 8px;
  padding: 8px;
  color: #fca5a5;
  background: rgba(127, 29, 29, 0.22);
  border: 1px solid rgba(248, 113, 113, 0.28);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.45;
}

.tool-param-textarea,
.tool-param-select {
  width: 100%;
  padding: 6px 10px;
  font-size: 11px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-1);
  outline: none;
  font-family: 'JetBrains Mono', monospace;
}

.tool-param-textarea {
  resize: vertical;
  min-height: 70px;
  line-height: 1.45;
}
</style>
