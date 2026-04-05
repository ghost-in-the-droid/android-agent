<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '@/composables/useApi'
import PhoneStreamWidget from '@/components/PhoneStreamWidget.vue'

interface SkillAction { name: string; description: string }
interface SkillWorkflow { name: string; description: string }
interface PopupDetector { detect: string; button: string; label: string; method?: string; notes?: string }
interface SkillInfo {
  dir: string; name: string; version: string; app_package: string | null
  description: string; actions: string[] | SkillAction[]; workflows: string[] | SkillWorkflow[]
  elements_count: number; popup_count?: number; popup_detectors?: PopupDetector[]
  metadata: any; default_params?: Record<string, Record<string, any>>
}
interface SkillDetail extends SkillInfo {
  elements: Record<string, any>[]
}

const skills = ref<SkillInfo[]>([])
const selected = ref<SkillDetail | null>(null)
const loading = ref(false)
const searchQuery = ref('')
const filteredSkills = computed(() => {
  const q = searchQuery.value.toLowerCase()
  if (!q) return skills.value
  return skills.value.filter(s =>
    (s.name || s.dir || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.app_package || '').toLowerCase().includes(q)
  )
})
const devices = ref<{serial: string; nickname?: string}[]>([])
const runModal = ref(false)
const runTarget = ref({ type: '', name: '' })
const runDevice = ref('')
const runParams = ref('{}')
const runResult = ref('')

const ICONS: Record<string, string> = {
  tiktok: '🎵', instagram: '📸', _base: '🧩', send_gmail_email: '🧩'
}

/* ── compat tracking ─────────────────────────────────────────────────── */
interface CompatEntry {
  device_serial: string; skill_name: string; target_type: string; target_name: string
  app_version: string | null; status: string; last_run_at: string | null; last_error: string | null
  run_count: number; ok_count: number; fail_count: number
}
const compat = ref<CompatEntry[]>([])
const verifying = ref(false)
const verifyLog = ref('')

function compatFor(skill: string, device?: string): CompatEntry[] {
  return compat.value.filter(c => c.skill_name === skill && (!device || c.device_serial === device))
}
function compatStatus(skill: string, device: string): string {
  const entries = compatFor(skill, device)
  if (!entries.length) return 'untested'
  if (entries.every(c => c.status === 'ok')) return 'ok'
  if (entries.some(c => c.status === 'ok')) return 'partial'
  return 'fail'
}
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  ok: { bg: '#22c55e22', text: '#4ade80' },
  fail: { bg: '#ef444422', text: '#f87171' },
  partial: { bg: '#f59e0b22', text: '#fbbf24' },
  untested: { bg: '#64748b22', text: '#94a3b8' },
}

async function verifySkill(skillName: string, device: string) {
  if (!device) return
  verifying.value = true
  verifyLog.value = ''
  runDevice.value = device
  // Auto-start stream so user can watch the verification
  if (phoneWidget.value && !phoneWidget.value.streaming) phoneWidget.value.startStream()
  const sk = selected.value
  const workflows = sk?.workflows || []
  for (const w of workflows) {
    const wName = typeof w === 'string' ? w : w.name
    verifyLog.value += `Testing ${wName}...\n`
    try {
      const res = await api(`/api/skills/${skillName}/verify`, {
        method: 'POST', body: JSON.stringify({ workflow: wName, device, params: {} })
      })
      verifyLog.value += res.ok ? `  ✅ ${wName} passed\n` : `  ❌ ${wName} failed: ${res.output?.slice(0, 200)}\n`
    } catch (e: any) {
      verifyLog.value += `  ❌ ${wName} error: ${e.message}\n`
    }
  }
  verifying.value = false
  await loadCompat()
}

async function resetCompat(skill: string, device: string) {
  await api(`/api/skills/compat/${device}/${skill}`, { method: 'DELETE' })
  await loadCompat()
}

async function loadCompat() {
  try { compat.value = await api('/api/skills/compat') } catch { compat.value = [] }
}

async function load() {
  loading.value = true
  try {
    skills.value = await api('/api/skills')
    const devResp = await api('/api/phone/devices')
    devices.value = devResp.devices || devResp || []
    await loadCompat()
  } finally { loading.value = false }
}

const phoneWidget = ref<InstanceType<typeof PhoneStreamWidget> | null>(null)

async function showDetail(name: string) {
  const detail = await api<SkillDetail>(`/api/skills/${name}`)
  selected.value = detail
  // Push browser history so Back button works
  history.pushState({ skill: name }, '', `#skill/${name}`)
}

function back() {
  selected.value = null
  history.pushState(null, '', location.pathname)
}

function onPopState() {
  // Browser back button pressed
  if (selected.value) {
    selected.value = null
  }
}

function actionCount(s: SkillInfo) {
  return Array.isArray(s.actions) ? s.actions.length : 0
}
function workflowCount(s: SkillInfo) {
  return Array.isArray(s.workflows) ? s.workflows.length : 0
}

function openRun(type: 'workflow' | 'action', name: string) {
  runTarget.value = { type, name }
  runDevice.value = devices.value[0]?.serial || ''
  runResult.value = ''
  // Pre-fill default params from skill metadata
  const dp = (selected.value as any)?.default_params as Record<string, any> | undefined
  const typeKey = type === 'workflow' ? 'workflows' : 'actions'
  const defaults = dp?.[typeKey]?.[name]
  runParams.value = defaults ? JSON.stringify(defaults, null, 2) : '{}'
  runModal.value = true
}

async function executeRun() {
  const skill = selected.value?.dir || selected.value?.name
  const endpoint = runTarget.value.type === 'workflow'
    ? `/api/skills/${skill}/run`
    : `/api/skills/${skill}/run-action`
  const body: any = { device: runDevice.value }
  body[runTarget.value.type] = runTarget.value.name
  try { body.params = JSON.parse(runParams.value) } catch { body.params = {} }
  // Auto-start stream on the selected device
  if (phoneWidget.value && !phoneWidget.value.streaming) phoneWidget.value.startStream()
  try {
    const res = await api(endpoint, { method: 'POST', body: JSON.stringify(body) })
    runResult.value = `✅ Enqueued — job_id: ${res.job_id || res.ok || JSON.stringify(res)}`
  } catch (e: any) {
    runResult.value = `❌ ${e.message}`
  }
}

async function deleteSkill(name: string) {
  if (!confirm(`Delete skill "${name}"? This cannot be undone.`)) return
  try {
    await api(`/api/skills/${name}`, { method: 'DELETE' })
    selected.value = null
    await load()
  } catch (e: any) {
    alert('Failed to delete: ' + e.message)
  }
}

function exportSkill(name: string) {
  window.open(`/api/skills/export/${name}`, '_blank')
}

/* ── Hub / Browse tab ─────────────────────────────────────────────── */
const hubTab = ref<'installed' | 'browse'>('installed')
const registry = ref<any[]>([])
const installing = ref<Record<string, boolean>>({})
const hubSearch = ref('')

async function loadRegistry() {
  try { registry.value = await api('/api/skills/registry') } catch { registry.value = [] }
}

async function installFromHub(name: string) {
  installing.value[name] = true
  try {
    await api('/api/skills/install', { method: 'POST', body: JSON.stringify({ name }) })
    await load() // refresh installed skills
  } catch (e: any) {
    alert('Install failed: ' + e.message)
  } finally {
    installing.value[name] = false
  }
}

const installedNames = computed(() => new Set(skills.value.map(s => s.dir || s.name)))

const filteredRegistry = computed(() => {
  const q = hubSearch.value.toLowerCase()
  if (!q) return registry.value
  return registry.value.filter((s: any) =>
    (s.name || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.app_package || '').toLowerCase().includes(q)
  )
})

function switchTab(tab: 'installed' | 'browse') {
  hubTab.value = tab
  if (tab === 'browse' && registry.value.length === 0) {
    loadRegistry()
  }
}

onMounted(() => {
  load()
  window.addEventListener('popstate', onPopState)
})
onUnmounted(() => {
  window.removeEventListener('popstate', onPopState)
})
</script>

<template>
  <div class="sh-root">

    <!-- ============================================================ -->
    <!-- DETAIL VIEW                                                   -->
    <!-- ============================================================ -->
    <div v-if="selected" style="display: flex; gap: 12px; height: calc(100vh - 80px)">
      <!-- LEFT: Skill detail (75%) -->
      <div class="sh-detail" style="flex: 3; overflow-y: auto; min-width: 0">

      <!-- Detail header -->
      <div class="sh-detail-header">
        <button class="sh-back-btn" @click="back">
          <span class="sh-back-arrow">&#8592;</span> Skills
        </button>
        <div class="sh-detail-title-row">
          <span class="sh-detail-icon">{{ ICONS[selected.dir] || '&#x1f9e9;' }}</span>
          <div class="sh-detail-title-block">
            <h2 class="sh-detail-name">{{ selected.name }}</h2>
            <div class="sh-detail-meta">
              <span class="sh-version-badge">v{{ selected.version || '1.0.0' }}</span>
              <span class="sh-pkg">{{ selected.app_package || 'universal' }}</span>
            </div>
          </div>
        </div>
        <p class="sh-detail-desc">{{ selected.description }}</p>
      </div>

      <!-- Two-column body -->
      <div class="sh-detail-columns">

        <!-- LEFT column (60%) — Actions + Workflows -->
        <div class="sh-col-left">

          <!-- Actions -->
          <div class="sh-section" v-if="actionCount(selected)">
            <h3 class="sh-section-title">Actions <span class="sh-count-badge">{{ actionCount(selected) }}</span></h3>
            <div class="sh-list">
              <div v-for="a in selected.actions" :key="typeof a === 'string' ? a : a.name"
                class="sh-list-row sh-list-row--compact">
                <div class="sh-list-row-text">
                  <span class="sh-list-row-name">{{ typeof a === 'string' ? a : a.name }}</span>
                  <span v-if="typeof a !== 'string' && a.description" class="sh-list-row-desc">{{ a.description }}</span>
                </div>
                <button class="sh-run-btn sh-run-btn--small" @click="openRun('action', typeof a === 'string' ? a : a.name)">&#9654;</button>
              </div>
            </div>
          </div>

          <!-- Workflows -->
          <div class="sh-section" v-if="workflowCount(selected)">
            <h3 class="sh-section-title">Workflows <span class="sh-count-badge">{{ workflowCount(selected) }}</span></h3>
            <div class="sh-list">
              <div v-for="w in selected.workflows" :key="typeof w === 'string' ? w : w.name"
                class="sh-list-row sh-list-row--workflow">
                <div class="sh-list-row-text">
                  <span class="sh-list-row-name">{{ typeof w === 'string' ? w : w.name }}</span>
                  <span v-if="typeof w !== 'string' && w.description" class="sh-list-row-desc">{{ w.description }}</span>
                </div>
                <button class="sh-run-btn" @click="openRun('workflow', typeof w === 'string' ? w : w.name)">&#9654; Run</button>
              </div>
            </div>
          </div>
        </div>

        <!-- RIGHT column (40%) — Compat, Elements, Export/Delete -->
        <div class="sh-col-right">

          <!-- Device compatibility -->
          <div class="sh-section" v-if="devices.length">
            <h3 class="sh-section-title">Device Compatibility</h3>
            <div class="sh-compat-list">
              <div v-for="d in devices" :key="d.serial" class="sh-compat-row">
                <div class="sh-compat-row-top">
                  <span class="sh-compat-device">{{ d.nickname || d.serial?.slice(0, 10) }}</span>
                  <span class="sh-compat-status"
                    :style="{ background: STATUS_COLORS[compatStatus(selected.dir, d.serial)]?.bg,
                              color: STATUS_COLORS[compatStatus(selected.dir, d.serial)]?.text }">
                    {{ compatStatus(selected.dir, d.serial).toUpperCase() }}
                  </span>
                  <div class="sh-compat-actions">
                    <button class="sh-verify-btn" :disabled="verifying"
                      @click="verifySkill(selected.dir, d.serial)"
                      title="Run all workflows on this device to test if they work. Results are saved per-device.">
                      {{ verifying ? 'Testing...' : 'Verify' }}
                    </button>
                    <button v-if="compatFor(selected.dir, d.serial).length"
                      class="sh-reset-btn"
                      @click="resetCompat(selected.dir, d.serial)" title="Reset status">&#8634;</button>
                  </div>
                </div>
                <div v-if="compatFor(selected.dir, d.serial).length" class="sh-compat-targets">
                  <span v-for="c in compatFor(selected.dir, d.serial)" :key="c.target_name"
                    class="sh-compat-target-badge"
                    :style="{ background: c.status === 'ok' ? '#22c55e11' : '#ef444411', color: c.status === 'ok' ? '#4ade80' : '#f87171' }">
                    {{ c.target_name }} ({{ c.ok_count }}/{{ c.run_count }})
                  </span>
                </div>
              </div>
            </div>
            <pre v-if="verifyLog" class="sh-verify-log">{{ verifyLog }}</pre>
          </div>

          <!-- Elements -->
          <div class="sh-section" v-if="selected.elements_count">
            <h3 class="sh-section-title">Elements <span class="sh-count-badge">{{ selected.elements_count }}</span></h3>
            <p class="sh-elements-note">UI element definitions with fallback locator chains.</p>
          </div>

          <!-- Popup Detectors -->
          <div class="sh-section" v-if="selected.popup_detectors?.length">
            <h3 class="sh-section-title">Popup Detectors <span class="sh-count-badge">{{ selected.popup_detectors.length }}</span></h3>
            <div class="sh-popup-list">
              <div v-for="p in selected.popup_detectors" :key="p.detect" class="sh-popup-row">
                <div class="sh-popup-label">{{ p.label }}</div>
                <div class="sh-popup-meta">
                  <span class="sh-popup-detect">detect: "{{ p.detect }}"</span>
                  <span class="sh-popup-action">{{ p.method === 'back' ? 'press Back' : 'tap "' + p.button + '"' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Export / Delete -->
          <div class="sh-section sh-section--actions">
            <button class="sh-export-btn" @click="exportSkill(selected.dir)">Export ZIP</button>
            <button class="sh-delete-btn" @click="deleteSkill(selected.dir)">Delete Skill</button>
          </div>
        </div>
      </div>
      </div><!-- end left column -->

      <!-- RIGHT: Phone stream (25%) -->
      <div style="flex: 1; min-width: 220px; max-width: 320px">
        <PhoneStreamWidget
          ref="phoneWidget"
          :serial="runDevice || devices[0]?.serial || ''"
          :label="devices.find(d => d.serial === (runDevice || devices[0]?.serial))?.nickname || ''"
          :show-keys="true"
          :show-volume="true"
          :compact="true"
          :auto-stream="false">
          <template #placeholder>Run a skill to auto-start stream</template>
        </PhoneStreamWidget>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- TAB TOGGLE + BROWSE / HUB VIEWS                              -->
    <!-- ============================================================ -->
    <div v-else class="sh-browse">

      <!-- Tab toggle -->
      <div class="sh-tab-bar">
        <button class="sh-tab-btn" :class="{ 'sh-tab-btn--active': hubTab === 'installed' }"
          @click="switchTab('installed')">
          Installed
          <span class="sh-tab-count">{{ skills.length }}</span>
        </button>
        <button class="sh-tab-btn" :class="{ 'sh-tab-btn--active': hubTab === 'browse' }"
          @click="switchTab('browse')">
          Browse Hub
          <span v-if="registry.length" class="sh-tab-count">{{ registry.length }}</span>
        </button>
      </div>

      <!-- ── INSTALLED TAB ─────────────────────────────────────────── -->
      <div v-if="hubTab === 'installed'">

        <!-- Browse header -->
        <div class="sh-browse-header">
          <div class="sh-browse-title-row">
            <h2 class="sh-browse-title">Skill Hub</h2>
            <span class="sh-skill-count">{{ skills.length }} skills</span>
          </div>
          <div class="sh-browse-toolbar">
            <input
              v-model="searchQuery"
              type="text"
              class="sh-search"
              placeholder="Filter by name or description..."
            />
            <button class="sh-refresh-btn" @click="load" :disabled="loading">
              {{ loading ? 'Loading...' : 'Refresh' }}
            </button>
          </div>
        </div>

        <!-- Skill cards -->
        <div class="sh-card-grid">
          <div v-if="!filteredSkills.length && !loading" class="sh-empty">
            No skills found{{ searchQuery ? ' matching "' + searchQuery + '"' : '' }}.
          </div>
          <div v-for="s in filteredSkills" :key="s.dir"
            class="sh-card"
            @click="showDetail(s.dir)">

            <!-- Header: icon + name + version -->
            <div class="sh-card-header">
              <span class="sh-card-icon">{{ ICONS[s.dir] || '&#x1f9e9;' }}</span>
              <div class="sh-card-title-block">
                <span class="sh-card-name">{{ s.name || s.dir }}</span>
                <span class="sh-version-badge">v{{ s.metadata?.version || '1.0.0' }}</span>
              </div>
            </div>

            <!-- Package -->
            <div class="sh-card-pkg">{{ s.app_package || 'universal' }}</div>

            <!-- Description -->
            <div class="sh-card-desc">{{ s.description }}</div>

            <!-- Stats -->
            <div class="sh-card-stats">
              <span class="sh-stat-pill">{{ actionCount(s) }} actions</span>
              <span class="sh-stat-pill">{{ workflowCount(s) }} workflows</span>
              <span class="sh-stat-pill">{{ s.elements_count || 0 }} elements</span>
              <span v-if="s.popup_count" class="sh-stat-pill">{{ s.popup_count }} popups</span>
            </div>

            <!-- Compat badges -->
            <div v-if="compatFor(s.dir).length" class="sh-card-compat">
              <span v-for="d in devices" :key="d.serial"
                class="sh-compat-inline-badge"
                :style="{ background: STATUS_COLORS[compatStatus(s.dir, d.serial)]?.bg,
                          color: STATUS_COLORS[compatStatus(s.dir, d.serial)]?.text }"
                :title="d.nickname || d.serial">
                {{ (d.nickname || d.serial?.slice(0, 6)) }}: {{ compatStatus(s.dir, d.serial) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── BROWSE HUB TAB ────────────────────────────────────────── -->
      <div v-if="hubTab === 'browse'">

        <div class="sh-browse-header">
          <div class="sh-browse-title-row">
            <h2 class="sh-browse-title">Browse Skill Hub</h2>
            <span class="sh-skill-count">{{ registry.length }} available</span>
          </div>
          <div class="sh-browse-toolbar">
            <input
              v-model="hubSearch"
              type="text"
              class="sh-search"
              placeholder="Search available skills..."
            />
            <button class="sh-refresh-btn" @click="loadRegistry">
              Refresh
            </button>
          </div>
        </div>

        <!-- Registry cards -->
        <div class="sh-card-grid">
          <div v-if="!filteredRegistry.length && registry.length === 0" class="sh-empty">
            Loading registry...
          </div>
          <div v-if="!filteredRegistry.length && registry.length > 0" class="sh-empty">
            No skills found matching "{{ hubSearch }}".
          </div>
          <div v-for="s in filteredRegistry" :key="s.name"
            class="sh-card sh-card--hub">

            <!-- Header: icon + name + version + official badge -->
            <div class="sh-card-header">
              <span class="sh-card-icon">{{ ICONS[s.name] || '&#x1f9e9;' }}</span>
              <div class="sh-card-title-block">
                <span class="sh-card-name">{{ s.display_name || s.name }}</span>
                <span class="sh-version-badge">v{{ s.version || '0.0.0' }}</span>
                <span v-if="s.source === 'official' || !s.source" class="sh-official-badge">Official</span>
                <span v-else class="sh-community-badge">Community</span>
              </div>
            </div>

            <!-- Package -->
            <div class="sh-card-pkg">{{ s.app_package || 'universal' }}</div>

            <!-- Description -->
            <div class="sh-card-desc">{{ s.description }}</div>

            <!-- Stats -->
            <div class="sh-card-stats">
              <span class="sh-stat-pill" v-if="s.actions">{{ Array.isArray(s.actions) ? s.actions.length : 0 }} actions</span>
              <span class="sh-stat-pill" v-if="s.workflows">{{ Array.isArray(s.workflows) ? s.workflows.length : 0 }} workflows</span>
              <span class="sh-stat-pill" v-if="s.elements_count">{{ s.elements_count }} elements</span>
              <span v-if="s.author" class="sh-stat-pill">by {{ s.author }}</span>
            </div>

            <!-- Install button -->
            <div class="sh-card-install-row">
              <button
                v-if="installedNames.has(s.name)"
                class="sh-installed-badge-btn"
                disabled>
                Installed
              </button>
              <button
                v-else
                class="sh-install-btn"
                :disabled="installing[s.name]"
                @click.stop="installFromHub(s.name)">
                {{ installing[s.name] ? 'Installing...' : 'Install' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- RUN MODAL (unchanged)                                         -->
    <!-- ============================================================ -->
    <div v-if="runModal" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="runModal = false">
      <div class="card w-96">
        <h3 class="font-bold text-sm mb-3" style="color: var(--text-1)">
          Run {{ runTarget.type }}: {{ runTarget.name }}
        </h3>
        <div class="mb-3">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Device</label>
          <select v-model="runDevice" class="w-full px-3 py-2 rounded-lg text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)">
            <option v-for="d in devices" :key="d.serial" :value="d.serial">
              {{ d.nickname || d.serial }}
            </option>
          </select>
        </div>
        <div class="mb-3">
          <label class="block text-xs mb-1" style="color: var(--text-3)">Params (JSON)</label>
          <textarea v-model="runParams" rows="3" class="w-full px-3 py-2 rounded-lg text-sm font-mono"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)" />
        </div>
        <div v-if="runResult" class="mb-3 p-2 rounded text-xs" style="background: var(--bg-deep); color: var(--text-2)">
          {{ runResult }}
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary" @click="executeRun">Execute</button>
          <button class="btn" @click="runModal = false">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── CSS Variables (consumed from parent, defined as fallbacks) ──── */
.sh-root {
  --_bg-base: var(--bg-base, #0d1117);
  --_bg-card: var(--bg-card, #161b22);
  --_bg-deep: var(--bg-deep, #0d1117);
  --_text-1: var(--text-1, #e6edf3);
  --_text-2: var(--text-2, #b1bac4);
  --_text-3: var(--text-3, #8b949e);
  --_text-4: var(--text-4, #6e7681);
  --_accent: var(--accent, #6366f1);
  --_border: var(--border, #30363d);
  color: var(--_text-1);
}

/* ── Browse view ──────────────────────────────────────────────────── */
.sh-browse-header {
  margin-bottom: 16px;
}
.sh-browse-title-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.sh-browse-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--_text-1);
  margin: 0;
}
.sh-skill-count {
  font-size: 12px;
  color: var(--_text-4);
  font-weight: 500;
}
.sh-browse-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}
.sh-search {
  flex: 1;
  padding: 10px 14px;
  font-size: 13px;
  border-radius: 8px;
  border: 1px solid var(--_border);
  background: var(--_bg-deep);
  color: var(--_text-1);
  outline: none;
  transition: border-color 0.15s;
}
.sh-search::placeholder {
  color: var(--_text-4);
}
.sh-search:focus {
  border-color: var(--_accent);
}
.sh-refresh-btn {
  padding: 9px 16px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  border: 1px solid var(--_border);
  background: var(--_bg-card);
  color: var(--_text-2);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.sh-refresh-btn:hover:not(:disabled) {
  background: var(--_bg-deep);
  color: var(--_text-1);
}
.sh-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Skill card grid ──────────────────────────────────────────────── */
.sh-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  padding-bottom: 8px;
}
.sh-empty {
  grid-column: 1 / -1;
  padding: 60px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--_text-4);
}
.sh-card {
  background: var(--_bg-card);
  border: 1px solid color-mix(in srgb, var(--_border) 60%, transparent);
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.sh-card:hover {
  border-color: color-mix(in srgb, var(--_accent) 40%, var(--_border));
  box-shadow: 0 8px 24px color-mix(in srgb, var(--_accent) 8%, transparent);
  transform: translateY(-2px);
}

.sh-card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 4px;
}
.sh-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--_accent) 12%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
  flex-shrink: 0;
}
.sh-card-title-block {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}
.sh-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--_text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.15s;
}
.sh-card:hover .sh-card-name {
  color: var(--_accent);
}
.sh-card-pkg {
  font-size: 10px;
  color: var(--_text-4);
  font-family: monospace;
  margin-bottom: 6px;
  padding-left: 48px;
}
.sh-card-desc {
  font-size: 12px;
  color: var(--_text-3);
  line-height: 1.5;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sh-card-stats {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: auto;
}
.sh-stat-pill {
  font-size: 10px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--_text-4) 12%, transparent);
  color: var(--_text-3);
}
.sh-card-compat {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.sh-compat-inline-badge {
  font-size: 9px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
}

/* ── Version badge (shared) ───────────────────────────────────────── */
.sh-version-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--_text-4) 18%, transparent);
  color: var(--_text-3);
  line-height: 1.6;
}

/* ── Detail view ──────────────────────────────────────────────────── */
.sh-detail-header {
  margin-bottom: 24px;
}
.sh-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--_text-3);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  margin-bottom: 16px;
  transition: color 0.15s;
}
.sh-back-btn:hover {
  color: var(--_text-1);
}
.sh-back-arrow {
  font-size: 14px;
}
.sh-detail-title-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 8px;
}
.sh-detail-icon {
  font-size: 32px;
  line-height: 1;
}
.sh-detail-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sh-detail-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--_text-1);
  margin: 0;
}
.sh-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sh-pkg {
  font-size: 11px;
  color: var(--_text-4);
  font-family: monospace;
}
.sh-detail-desc {
  font-size: 13px;
  color: var(--_text-2);
  margin-top: 8px;
  line-height: 1.5;
}

/* ── Two-column layout ────────────────────────────────────────────── */
.sh-detail-columns {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 20px;
  align-items: start;
}
@media (max-width: 800px) {
  .sh-detail-columns {
    grid-template-columns: 1fr;
  }
}

/* ── Sections ─────────────────────────────────────────────────────── */
.sh-section {
  background: var(--_bg-card);
  border: 1px solid var(--_border);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
}
.sh-section--actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sh-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--_text-1);
  margin: 0 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sh-count-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--_accent) 16%, transparent);
  color: var(--_accent);
}

/* ── List rows (actions / workflows) ──────────────────────────────── */
.sh-list {
  display: flex;
  flex-direction: column;
}
.sh-list-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--_border);
  transition: background 0.12s;
}
.sh-list-row:last-child {
  border-bottom: none;
}
.sh-list-row:hover {
  background: color-mix(in srgb, var(--_accent) 5%, transparent);
}
.sh-list-row--compact {
  padding: 8px 12px;
}
.sh-list-row--workflow {
  padding: 12px 12px;
}
.sh-list-row-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.sh-list-row-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--_text-1);
}
.sh-list-row-desc {
  font-size: 11px;
  color: var(--_text-4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Run buttons ──────────────────────────────────────────────────── */
.sh-run-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
  border: none;
  background: var(--_accent);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.sh-run-btn:hover {
  opacity: 0.85;
}
.sh-run-btn--small {
  padding: 4px 10px;
  font-size: 10px;
}

/* ── Compat section ───────────────────────────────────────────────── */
.sh-compat-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sh-compat-row {
  background: var(--_bg-deep);
  border: 1px solid var(--_border);
  border-radius: 8px;
  padding: 10px 12px;
}
.sh-compat-row-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sh-compat-device {
  font-size: 12px;
  font-weight: 600;
  color: var(--_text-2);
  min-width: 80px;
}
.sh-compat-status {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.sh-compat-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.sh-verify-btn {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 5px;
  border: none;
  background: var(--_accent);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.sh-verify-btn:hover:not(:disabled) {
  opacity: 0.85;
}
.sh-verify-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sh-reset-btn {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 5px;
  border: 1px solid var(--_border);
  background: var(--_bg-card);
  color: var(--_text-3);
  cursor: pointer;
  transition: background 0.15s;
}
.sh-reset-btn:hover {
  background: var(--_bg-deep);
}
.sh-compat-targets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.sh-compat-target-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 4px;
}
.sh-verify-log {
  margin-top: 12px;
  padding: 10px;
  border-radius: 6px;
  font-size: 10px;
  font-family: monospace;
  background: #0a0e14;
  color: #94a3b8;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
}

/* ── Elements note ────────────────────────────────────────────────── */
.sh-elements-note {
  font-size: 11px;
  color: var(--_text-4);
  margin: 0;
}

/* ── Popup detectors ─────────────────────────────────────────────── */
.sh-popup-list {
  display: flex;
  flex-direction: column;
}
.sh-popup-row {
  padding: 8px 10px;
  border-bottom: 1px solid var(--_border);
}
.sh-popup-row:last-child {
  border-bottom: none;
}
.sh-popup-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--_text-1);
  margin-bottom: 2px;
}
.sh-popup-meta {
  display: flex;
  gap: 12px;
  font-size: 10px;
  font-family: monospace;
}
.sh-popup-detect {
  color: var(--_text-4);
}
.sh-popup-action {
  color: #f59e0b;
}

/* ── Export / Delete buttons ──────────────────────────────────────── */
.sh-export-btn {
  flex: 1;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid var(--_border);
  background: var(--_bg-deep);
  color: var(--_text-2);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sh-export-btn:hover {
  background: var(--_bg-card);
  color: var(--_text-1);
}
.sh-delete-btn {
  flex: 1;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid #ef444444;
  background: #ef444416;
  color: #f87171;
  cursor: pointer;
  transition: background 0.15s;
}
.sh-delete-btn:hover {
  background: #ef444433;
}

/* ── Tab bar ─────────────────────────────────────────────────────── */
.sh-tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: var(--_bg-deep);
  border: 1px solid var(--_border);
  border-radius: 10px;
  padding: 4px;
  width: fit-content;
}
.sh-tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--_text-3);
  cursor: pointer;
  transition: all 0.15s;
}
.sh-tab-btn:hover:not(.sh-tab-btn--active) {
  color: var(--_text-2);
  background: color-mix(in srgb, var(--_text-4) 8%, transparent);
}
.sh-tab-btn--active {
  background: var(--_bg-card);
  color: var(--_text-1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.sh-tab-count {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--_text-4) 18%, transparent);
  color: var(--_text-3);
  line-height: 1.6;
}
.sh-tab-btn--active .sh-tab-count {
  background: color-mix(in srgb, var(--_accent) 16%, transparent);
  color: var(--_accent);
}

/* ── Hub card tweaks ─────────────────────────────────────────────── */
.sh-card--hub {
  cursor: default;
}
.sh-card--hub:hover {
  transform: none;
}

/* ── Official / Community badges ─────────────────────────────────── */
.sh-official-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 9999px;
  background: #22c55e18;
  color: #4ade80;
  letter-spacing: 0.02em;
}
.sh-community-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 9999px;
  background: #3b82f618;
  color: #60a5fa;
  letter-spacing: 0.02em;
}

/* ── Install button row ──────────────────────────────────────────── */
.sh-card-install-row {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
.sh-install-btn {
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: none;
  background: var(--_accent);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.sh-install-btn:hover:not(:disabled) {
  opacity: 0.85;
}
.sh-install-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sh-installed-badge-btn {
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid #22c55e44;
  background: #22c55e12;
  color: #4ade80;
  cursor: default;
}
</style>
