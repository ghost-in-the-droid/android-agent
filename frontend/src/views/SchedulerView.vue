<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '@/composables/useApi'

/* ── reactive state ─────────────────────────────────────────────────────── */
const schedules = ref<any[]>([])
const queue = ref<any[]>([])
const history = ref<any[]>([])
const timeline = ref<any>({ past: [], future: [], content_plan: [] })
const status = ref<any>({})
const devices = ref<any[]>([])
const accounts = ref<any[]>([])
let pollTimer: number | null = null

/* filters */
const schedPhoneFilter = ref('')
const historyPhoneFilter = ref('')
const historyTypeFilter = ref('')

/* ── log panel state ──────────────────────────────────────────────────── */
const logPanelOpen = ref(false)
const logPanelTitle = ref('')
const logPanelLines = ref<string[]>([])
const logPanelAutoScroll = ref(true)
const logPanelSource = ref<{ type: 'queue' | 'history'; id: number } | null>(null)
let logPollTimer: number | null = null

/* form state */
const showForm = ref(true)
const formTitle = ref('Add Schedule')
const sf = ref<any>({
  id: null, name: '', job_type: 'post', phone_serial: '', priority: 2,
  schedule_type: 'daily', daily_times: '', interval_minutes: 60,
  max_duration_s: 900, account: '', config_json: '{}',
})

/* timeline canvas */
const timelineCanvas = ref<HTMLCanvasElement | null>(null)
let timelineHits: any[] = []
let animFrameId: number | null = null

const TYPE_COLORS: Record<string, string> = {
  post: '#f59e0b', content_gen: '#22c55e', publish_draft: '#a855f7',
  skill_workflow: '#14b8a6', skill_action: '#a855f7', app_explore: '#f97316',
}

const TYPE_BADGE: Record<string, string> = {
  post: '\u{1F4F9}', content_gen: '\u{1F916}', publish_draft: '\u{1F4E4}',
}

/* ── data fetching ──────────────────────────────────────────────────────── */
async function load() {
  const [s, q, h, tl, st, d, acc] = await Promise.all([
    api('/api/schedules').catch(() => []),
    api('/api/scheduler/queue').catch(() => []),
    api('/api/scheduler/history?limit=100').catch(() => []),
    api('/api/scheduler/timeline').catch(() => ({ past: [], future: [], content_plan: [] })),
    api('/api/scheduler/status').catch(() => ({})),
    api('/api/phone/devices').catch(() => ({ devices: [] })),
    api('/api/accounts').catch(() => []),
  ])
  schedules.value = Array.isArray(s) ? s : s.schedules || []
  queue.value = Array.isArray(q) ? q : q.queue || []
  history.value = Array.isArray(h) ? h : h.runs || []
  timeline.value = tl || { past: [], future: [], content_plan: [] }
  status.value = st || {}
  devices.value = d.devices || d || []
  accounts.value = Array.isArray(acc) ? acc : []
  await nextTick()
  renderTimeline()
}

/* ── log panel ─────────────────────────────────────────────────────────── */
function openLogPanel(source: { type: 'queue' | 'history'; id: number }, title: string) {
  logPanelOpen.value = true
  logPanelTitle.value = title
  logPanelLines.value = []
  logPanelAutoScroll.value = true
  logPanelSource.value = source
  pollLogPanel()
  if (logPollTimer) clearInterval(logPollTimer)
  logPollTimer = window.setInterval(pollLogPanel, 1500)
}

function closeLogPanel() {
  logPanelOpen.value = false
  logPanelSource.value = null
  logPanelLines.value = []
  if (logPollTimer) { clearInterval(logPollTimer); logPollTimer = null }
}

async function pollLogPanel() {
  if (!logPanelSource.value) return
  const { type, id } = logPanelSource.value
  const url = type === 'queue'
    ? `/api/scheduler/queue/${id}/logs?since=0`
    : `/api/scheduler/history/${id}/logs?since=0`
  try {
    const resp = await api(url)
    logPanelLines.value = resp.lines || []
    await nextTick()
    if (logPanelAutoScroll.value) {
      const el = document.getElementById('sched-log-viewer')
      if (el) el.scrollTop = el.scrollHeight
    }
  } catch {}
}

function onRunRowClick(r: any) {
  if (r._active) {
    openLogPanel({ type: 'queue', id: r.id }, r.schedule_name || r.job_type)
  } else {
    openLogPanel({ type: 'history', id: r.id }, r.schedule_name || r.job_type)
  }
}

/* ── phone helpers ──────────────────────────────────────────────────────── */
function phoneName(serial: string | null): string {
  if (!serial) return '?'
  const ph = devices.value.find((p: any) => p.serial === serial)
  if (ph) return ph.nickname || ph.model || serial.slice(0, 5)
  return serial.slice(0, 5)
}

const phoneList = computed(() => {
  // Build phone list from devices + any serials found in data
  const serials = new Set<string>()
  devices.value.forEach((d: any) => serials.add(d.serial))
  schedules.value.forEach((s: any) => { if (s.phone_serial) serials.add(s.phone_serial) })
  history.value.forEach((r: any) => { if (r.phone_serial) serials.add(r.phone_serial) })
  queue.value.forEach((j: any) => { if (j.phone_serial) serials.add(j.phone_serial) })
  ;(timeline.value.past || []).forEach((r: any) => { if (r.phone_serial) serials.add(r.phone_serial) })
  ;(timeline.value.future || []).forEach((r: any) => { if (r.phone_serial) serials.add(r.phone_serial) })
  return Array.from(serials).map(s => ({
    serial: s,
    label: phoneName(s),
  }))
})

/* ── computed: filtered schedules ───────────────────────────────────────── */
const filteredSchedules = computed(() => {
  const all = schedules.value
  if (!schedPhoneFilter.value) return all
  return all.filter((s: any) => s.phone_serial === schedPhoneFilter.value)
})

/* ── computed: filtered history ─────────────────────────────────────────── */
const activeJobs = computed(() =>
  queue.value.filter((j: any) => j.status === 'running').map((j: any) => ({ ...j, _active: true }))
)

const allRuns = computed(() => [...activeJobs.value, ...history.value])

const filteredRuns = computed(() => {
  let runs = allRuns.value
  if (historyPhoneFilter.value) runs = runs.filter((r: any) => r.phone_serial === historyPhoneFilter.value)
  if (historyTypeFilter.value) runs = runs.filter((r: any) => r.job_type === historyTypeFilter.value)
  return runs.slice(0, 50)
})

/* ── formatting helpers ─────────────────────────────────────────────────── */
function fmtDuration(s: number | null | undefined, active?: boolean): string {
  if (s == null) return '\u2014'
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
}

function fmtElapsed(startedAt: string): string {
  try {
    const startStr = startedAt.replace(' ', 'T')
    const secs = Math.max(0, Math.floor((Date.now() - new Date(startStr).getTime()) / 1000))
    if (secs < 60) return `${secs}s`
    return `${Math.floor(secs / 60)}m${String(secs % 60).padStart(2, '0')}s`
  } catch { return '' }
}

function parseTimes(s: any): string {
  try {
    const arr = JSON.parse(s || '[]')
    return Array.isArray(arr) ? arr.join(', ') : String(s)
  } catch { return String(s || '') }
}

function parseConfig(json: string): any {
  try { return JSON.parse(json || '{}') } catch { return {} }
}

function configDetail(r: any): string {
  const cfg = parseConfig(r.config_json)
  const jt = r.job_type
  let detail = ''
  if (jt === 'post') detail = cfg.action || 'draft'
  if (cfg.account) detail += ` @${cfg.account}`
  return detail
}

function schedDesc(s: any): string {
  if (s.schedule_type === 'daily') {
    return parseTimes(s.daily_times)
  }
  return `every ${s.interval_minutes}m`
}

function lastRunStr(s: any): string {
  if (!s.last_run) return '\u2014'
  const time = (s.last_run.started_at || '').slice(11, 16)
  const ok = s.last_run.status === 'completed'
  return `${time} ${ok ? '\u2705' : '\u274C'}`
}

function schedConfigDetail(s: any): string {
  const cfg = parseConfig(s.config_json)
  const jt = s.job_type
  if (jt === 'post') return cfg.action || 'draft'
  return ''
}

function schedAccount(s: any): string {
  const cfg = parseConfig(s.config_json)
  return cfg.account ? `@${cfg.account}` : ''
}

/* ── phone queue helpers ────────────────────────────────────────────────── */
function phoneStatus(serial: string): any {
  return status.value[serial] || {}
}

function phonePending(serial: string): any[] {
  return queue.value.filter((j: any) => j.phone_serial === serial && j.status === 'pending')
}

function phoneSchedCount(serial: string): number {
  return schedules.value.filter((s: any) => s.phone_serial === serial && s.is_enabled).length
}

function phoneNextSched(serial: string): any | null {
  return schedules.value.find(
    (s: any) => s.phone_serial === serial && s.is_enabled && s.next_run
  ) || null
}

/* ── queue panel helpers ────────────────────────────────────────────────── */
const runningPhones = computed(() => {
  return Object.entries(status.value)
    .filter(([, v]: [string, any]) => v.running)
    .map(([serial, info]: [string, any]) => ({ serial, info }))
})

const pendingJobs = computed(() =>
  queue.value.filter((j: any) => j.status === 'pending')
)

/* ── schedule CRUD ──────────────────────────────────────────────────────── */
async function toggleSchedule(id: number) {
  await api(`/api/schedules/${id}/toggle`, { method: 'POST' })
  await load()
}

async function runNow(id: number) {
  await api(`/api/schedules/${id}/run-now`, { method: 'POST' })
  await load()
}

async function deleteSchedule(id: number) {
  if (!confirm('Delete this schedule?')) return
  await api(`/api/schedules/${id}`, { method: 'DELETE' })
  await load()
}

async function killJob(qid: number) {
  if (!confirm('Kill this running job?')) return
  await api(`/api/scheduler/queue/${qid}/kill`, { method: 'POST' })
  await load()
}

/* ── form actions ───────────────────────────────────────────────────────── */
function sfEdit(id: number) {
  const s = schedules.value.find((x: any) => x.id === id)
  if (!s) return
  sf.value = {
    id: s.id, name: s.name, job_type: s.job_type,
    phone_serial: s.phone_serial || '', priority: s.priority,
    schedule_type: s.schedule_type,
    daily_times: parseTimes(s.daily_times),
    interval_minutes: s.interval_minutes || 60,
    max_duration_s: s.max_duration_s || 900,
    account: parseConfig(s.config_json).account || '',
    config_json: s.config_json || '{}',
  }
  formTitle.value = 'Edit Schedule'
}

function sfReset() {
  sf.value = {
    id: null, name: '', job_type: 'post', phone_serial: '', priority: 2,
    schedule_type: 'daily', daily_times: '', interval_minutes: 60,
    max_duration_s: 900, account: '', config_json: '{}',
  }
  formTitle.value = 'Add Schedule'
}

async function sfSave() {
  const f = sf.value
  // Inject account into config if set
  if (f.account) {
    try {
      const cfg = JSON.parse(f.config_json || '{}')
      cfg.account = f.account
      f.config_json = JSON.stringify(cfg)
    } catch {}
  }
  const body: any = {
    name: f.name,
    job_type: f.job_type,
    phone_serial: f.phone_serial || null,
    priority: parseInt(f.priority),
    schedule_type: f.schedule_type,
    config_json: f.config_json,
    max_duration_s: parseInt(f.max_duration_s) || 900,
  }
  if (f.schedule_type === 'daily') {
    body.daily_times = JSON.stringify(f.daily_times.split(',').map((t: string) => t.trim()).filter(Boolean))
  } else {
    body.interval_minutes = parseInt(f.interval_minutes) || 60
  }
  try {
    if (f.id) {
      await api(`/api/schedules/${f.id}`, { method: 'PUT', body: JSON.stringify(body) })
    } else {
      await api('/api/schedules', { method: 'POST', body: JSON.stringify(body) })
    }
    sfReset()
    await load()
  } catch (e: any) {
    alert('Save failed: ' + e.message)
  }
}

/* ── 24-Hour Timeline (canvas) ──────────────────────────────────────────── */
function renderTimeline() {
  const canvas = timelineCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const phones = phoneList.value
  const phoneCount = Math.max(phones.length, 1)
  const H = Math.max(80, 20 + phoneCount * 22 + 10)
  canvas.width = rect.width * dpr
  canvas.height = H * dpr
  canvas.style.height = H + 'px'
  ctx.scale(dpr, dpr)
  const W = rect.width

  ctx.clearRect(0, 0, W, H)
  timelineHits = []

  const now = new Date()
  const startH = 0
  const totalH = 24
  const trackL = 54
  const trackW = W - 58

  // Background
  ctx.fillStyle = '#0d1018'
  ctx.fillRect(0, 0, W, H)

  // Hour gridlines + labels
  for (let h = startH; h <= startH + totalH; h++) {
    const x = trackL + (h - startH) * (trackW / totalH)
    ctx.fillStyle = '#1e2438'
    ctx.fillRect(x, 0, 1, H)
    if (h < startH + totalH) {
      ctx.fillStyle = '#475569'
      ctx.font = '10px monospace'
      ctx.textAlign = 'left'
      ctx.fillText(String(h % 24).padStart(2, '0'), x + 2, 12)
    }
  }

  // Now marker
  const nowH = now.getHours() + now.getMinutes() / 60
  if (nowH >= startH && nowH <= startH + totalH) {
    const nowX = trackL + (nowH - startH) * (trackW / totalH)
    ctx.strokeStyle = '#ef4444'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(nowX, 0)
    ctx.lineTo(nowX, H)
    ctx.stroke()
    ctx.fillStyle = '#ef4444'
    ctx.font = '9px monospace'
    ctx.textAlign = 'center'
    ctx.fillText('NOW', nowX, 22)
  }

  // Phone rows
  const phoneRows = phones.map((p, i) => ({
    serial: p.serial,
    label: p.label,
    y: 28 + i * 22,
  }))

  // Phone labels + track bg
  ctx.textAlign = 'left'
  ctx.font = '10px monospace'
  for (const ph of phoneRows) {
    ctx.fillStyle = '#64748b'
    ctx.fillText(ph.label.slice(0, 10), 4, ph.y + 4)
    ctx.fillStyle = '#111827'
    ctx.fillRect(trackL, ph.y - 6, trackW, 16)
  }

  const tl = timeline.value || {}

  function parseTimeH(dtStr: string): number {
    try {
      const t = dtStr.split(' ')[1] || dtStr
      const p = t.split(':')
      return parseInt(p[0] || '0') + parseInt(p[1] || '0') / 60
    } catch { return 0 }
  }

  // Past runs - filled blocks
  for (const run of (tl.past || [])) {
    if (!run.started_at) continue
    const ph = phoneRows.find(p => p.serial === run.phone_serial)
    if (!ph) continue
    const sH = parseTimeH(run.started_at)
    const dur = (run.duration_s || 300) / 3600
    if (sH < startH || sH > startH + totalH) continue
    const x = trackL + (sH - startH) * (trackW / totalH)
    const w = Math.max(3, dur * (trackW / totalH))
    ctx.fillStyle = run.status === 'completed' ? (TYPE_COLORS[run.job_type] || '#6366f1')
      : run.status === 'timeout' ? '#fb923c'
      : run.status === 'failed' ? '#ef4444' : '#f59e0b'
    ctx.globalAlpha = 0.8
    ctx.fillRect(x, ph.y - 5, w, 14)
    ctx.globalAlpha = 1
  }

  // Currently running - glowing block
  const activeQ = queue.value.filter((j: any) => j.status === 'running' && j.started_at)
  for (const job of activeQ) {
    const ph = phoneRows.find(p => p.serial === job.phone_serial)
    if (!ph) continue
    const sH = parseTimeH(job.started_at)
    if (sH < startH || sH > startH + totalH) continue
    const x = trackL + (sH - startH) * (trackW / totalH)
    const nowPos = trackL + (nowH - startH) * (trackW / totalH)
    const w = Math.max(6, nowPos - x)
    const pulse = 0.5 + 0.3 * Math.sin(Date.now() / 400)
    const jName = (job.schedule_name || '').toLowerCase()
    const activeCol = jName.includes('cat') ? '#f59e0b'
      : jName.includes('dog') ? '#22c55e'
      : jName.includes('general') ? '#a78bfa'
      : (TYPE_COLORS[job.job_type] || '#6366f1')
    ctx.shadowColor = activeCol
    ctx.shadowBlur = 8
    ctx.fillStyle = activeCol
    ctx.globalAlpha = pulse
    ctx.fillRect(x, ph.y - 6, w, 16)
    ctx.shadowBlur = 0
    ctx.globalAlpha = 1
    ctx.strokeStyle = activeCol
    ctx.lineWidth = 2
    ctx.strokeRect(x, ph.y - 6, w, 16)
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 9px monospace'
    ctx.textAlign = 'left'
    const elapsed = Math.max(0, Math.floor((Date.now() - new Date(job.started_at.replace(' ', 'T')).getTime()) / 1000))
    const elStr = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m`
    ctx.fillText(`\u25B6 ${elStr}`, x + 2, ph.y + 5)
  }

  // Future - outlined blocks
  for (const fut of (tl.future || [])) {
    const ph = phoneRows.find(p => p.serial === fut.phone_serial)
    if (!ph) continue
    const parts = fut.time.split(':')
    const fH = parseInt(parts[0]) + parseInt(parts[1]) / 60
    if (fH < startH || fH > startH + totalH) continue
    const x = trackL + (fH - startH) * (trackW / totalH)
    const w = Math.max(6, (15 / 60) * (trackW / totalH))
    const futName = (fut.schedule_name || '').toLowerCase()
    const futCol = futName.includes('cat') ? '#f59e0b'
      : futName.includes('dog') ? '#22c55e'
      : futName.includes('general') ? '#a78bfa'
      : (TYPE_COLORS[fut.job_type] || '#6366f1')
    const isPast = !!fut.is_past
    ctx.globalAlpha = isPast ? 0.3 : 1
    if (isPast) ctx.setLineDash([3, 3]); else ctx.setLineDash([])
    ctx.strokeStyle = futCol
    ctx.lineWidth = 1.5
    ctx.strokeRect(x, ph.y - 5, w, 14)
    ctx.setLineDash([])
    // Short label
    ctx.fillStyle = futCol
    ctx.globalAlpha = isPast ? 0.3 : 0.9
    ctx.font = 'bold 10px monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const shortLabel = futName.includes('cat') ? 'C' : futName.includes('dog') ? 'D' : futName.includes('general') ? 'G' : ''
    if (shortLabel) ctx.fillText(shortLabel, x + w / 2, ph.y + 2)
    ctx.globalAlpha = 1
    ctx.textBaseline = 'alphabetic'
  }

  // Legend
  ctx.font = '9px monospace'
  ctx.textAlign = 'left'
  let lx = 40
  for (const [type, col] of Object.entries(TYPE_COLORS).slice(0, 6)) {
    ctx.fillStyle = col
    ctx.fillRect(lx, H - 10, 8, 8)
    ctx.fillStyle = '#64748b'
    ctx.fillText(type, lx + 11, H - 3)
    lx += ctx.measureText(type).width + 22
  }

  // Animate if active jobs
  if (activeQ.length) {
    animFrameId = requestAnimationFrame(() => renderTimeline())
  }
}

// Rerender timeline when data or window changes
function handleResize() {
  renderTimeline()
}

watch([timeline, queue, devices], () => {
  nextTick(() => renderTimeline())
})

onMounted(() => {
  load()
  pollTimer = window.setInterval(load, 3000)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (logPollTimer) clearInterval(logPollTimer)
  if (animFrameId) cancelAnimationFrame(animFrameId)
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div class="scheduler-root">

    <!-- ══════════════════════════════════════════════════════════════════════
         TOP ROW: Status Bar — compact single-line phone status
         ══════════════════════════════════════════════════════════════════════ -->
    <div class="status-bar">
      <div v-for="ph in phoneList" :key="ph.serial" class="status-bar-phone">
        <!-- Status dot -->
        <span class="status-dot" :class="{ 'dot-active': phoneStatus(ph.serial).running }" />
        <!-- Phone name -->
        <span class="status-phone-name">{{ ph.label }}</span>

        <!-- Running info -->
        <template v-if="phoneStatus(ph.serial).running && phoneStatus(ph.serial).job">
          <span class="status-job-name">{{ phoneStatus(ph.serial).job.schedule_name || phoneStatus(ph.serial).job.job_type }}</span>
          <span class="status-elapsed">{{ phoneStatus(ph.serial).job.started_at ? fmtElapsed(phoneStatus(ph.serial).job.started_at) : '' }}</span>
          <button class="status-kill-btn" @click="killJob(phoneStatus(ph.serial).job.id)">Kill</button>
        </template>
        <!-- Idle info -->
        <template v-else>
          <span class="status-idle">idle</span>
          <span v-if="phoneNextSched(ph.serial)" class="status-next">next: {{ phoneNextSched(ph.serial)?.name }}</span>
        </template>

        <!-- Queue badge -->
        <span v-if="phonePending(ph.serial).length" class="status-queue-badge">{{ phonePending(ph.serial).length }} queued</span>
        <span v-if="phoneSchedCount(ph.serial)" class="status-sched-count">{{ phoneSchedCount(ph.serial) }} sched</span>
      </div>

      <!-- Global queue summary -->
      <div v-if="pendingJobs.length" class="status-bar-queue">
        <span class="status-queue-label">Queue:</span>
        <span v-for="pj in pendingJobs" :key="pj.id" class="status-queue-item">
          {{ pj.schedule_name || pj.job_type }}
          <button class="status-queue-x" @click="killJob(pj.id)">&times;</button>
        </span>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         SECTION 1: 24-Hour Timeline (full width, taller)
         ══════════════════════════════════════════════════════════════════════ -->
    <div class="timeline-section">
      <div class="section-header">
        <h2 class="section-title">24-Hour Timeline</h2>
        <span class="section-subtitle">{{ phoneList.length }} device{{ phoneList.length !== 1 ? 's' : '' }}</span>
      </div>
      <div class="timeline-canvas-wrap">
        <canvas ref="timelineCanvas" height="160" style="width: 100%; cursor: default" />
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         SECTION 2: Schedules (left 60%) + Form (right 40%)
         ══════════════════════════════════════════════════════════════════════ -->
    <div class="sched-form-grid">

      <!-- ── LEFT: Schedule List ── -->
      <div class="sched-list-panel">
        <div class="sched-list-header">
          <h2 class="section-title">Schedules</h2>
          <span class="count-badge">
            {{ schedPhoneFilter ? `${filteredSchedules.length}/${schedules.length}` : schedules.length }}
          </span>
          <select v-model="schedPhoneFilter" class="filter-select">
            <option value="">All Phones</option>
            <option v-for="ph in phoneList" :key="ph.serial" :value="ph.serial">{{ ph.label }}</option>
          </select>
        </div>

        <div v-if="!filteredSchedules.length" class="empty-msg">No schedules yet</div>

        <!-- Compact schedule rows -->
        <div class="sched-rows">
          <div v-for="s in filteredSchedules" :key="s.id" class="sched-row">
            <!-- Left: status + info -->
            <div class="sched-row-main">
              <span class="sched-enabled-dot" :class="{ enabled: s.is_enabled }" />
              <span class="sched-name">{{ s.name }}</span>
              <span class="type-badge" :style="{ background: TYPE_COLORS[s.job_type] || '#6366f1' }">{{ s.job_type }}</span>
              <span class="sched-phone">{{ s.phone_serial ? phoneName(s.phone_serial) : '---' }}</span>
              <span class="sched-separator">&middot;</span>
              <span class="sched-timing">{{ schedDesc(s) }}</span>
              <template v-if="schedAccount(s)">
                <span class="sched-separator">&middot;</span>
                <span class="sched-account">{{ schedAccount(s) }}</span>
              </template>
              <span v-if="schedConfigDetail(s)" class="sched-separator">&middot;</span>
              <span v-if="schedConfigDetail(s)" class="sched-detail" v-html="schedConfigDetail(s)" />
            </div>
            <!-- Right: metadata + actions -->
            <div class="sched-row-meta">
              <span class="sched-last-next">Last {{ lastRunStr(s) }}</span>
              <span class="sched-separator">&middot;</span>
              <span class="sched-last-next">Next {{ s.next_run || '\u2014' }}</span>
            </div>
            <div class="sched-row-actions">
              <button class="act-btn" @click="sfEdit(s.id)">Edit</button>
              <button class="act-btn act-primary" @click="runNow(s.id)">Run</button>
              <button class="act-btn" :class="{ 'act-enable': !s.is_enabled }" @click="toggleSchedule(s.id)">{{ s.is_enabled ? 'Off' : 'On' }}</button>
              <button class="act-btn act-danger" @click="deleteSchedule(s.id)">Del</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── RIGHT: Add / Edit Form ── -->
      <div class="form-panel">
        <h2 class="section-title form-title">{{ formTitle }}</h2>

        <!-- Name -->
        <div class="form-field">
          <label class="form-label">Name</label>
          <input v-model="sf.name" type="text" placeholder="Morning Post" class="form-input" />
        </div>
        <!-- Type + Phone -->
        <div class="form-row-2">
          <div class="form-field">
            <label class="form-label">Type</label>
            <select v-model="sf.job_type" class="form-input">
              <option value="post">Post</option>
              <option value="publish_draft">Publish Draft</option>
              <option value="skill_workflow">Skill</option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">Phone</label>
            <select v-model="sf.phone_serial" class="form-input">
              <option value="">None</option>
              <option v-for="ph in phoneList" :key="ph.serial" :value="ph.serial">{{ ph.label }}</option>
            </select>
          </div>
        </div>
        <!-- Priority + Schedule -->
        <div class="form-row-2">
          <div class="form-field">
            <label class="form-label">Priority</label>
            <select v-model="sf.priority" class="form-input">
              <option :value="1">1 (highest)</option>
              <option :value="2">2 (normal)</option>
              <option :value="3">3 (low)</option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">Schedule</label>
            <select v-model="sf.schedule_type" class="form-input">
              <option value="daily">Daily</option>
              <option value="interval">Interval</option>
            </select>
          </div>
        </div>
        <!-- Times (daily) -->
        <div v-if="sf.schedule_type === 'daily'" class="form-field">
          <label class="form-label">Times (comma-sep, HH:MM)</label>
          <input v-model="sf.daily_times" type="text" placeholder="09:00, 14:00, 20:00" class="form-input" />
        </div>
        <!-- Interval (interval) -->
        <div v-if="sf.schedule_type === 'interval'" class="form-field">
          <label class="form-label">Interval (minutes)</label>
          <input v-model.number="sf.interval_minutes" type="number" min="5" class="form-input" />
        </div>
        <!-- Timeout + Account -->
        <div class="form-row-2">
          <div class="form-field">
            <label class="form-label">Timeout (sec)</label>
            <input v-model.number="sf.max_duration_s" type="number" min="60" class="form-input" />
          </div>
          <div class="form-field">
            <label class="form-label">Account</label>
            <select v-model="sf.account" class="form-input">
              <option value="">auto-detect</option>
              <option v-for="a in accounts" :key="a.handle || a.username || a" :value="a.handle || a.username || a">
                @{{ a.handle || a.username || a }}
              </option>
            </select>
          </div>
        </div>
        <!-- Config JSON -->
        <div class="form-field">
          <label class="form-label">
            Config JSON
          </label>
          <textarea v-model="sf.config_json" rows="3" class="form-input form-textarea" />
        </div>
        <!-- Buttons -->
        <div class="form-actions">
          <button class="act-btn act-primary" @click="sfSave">Save</button>
          <button class="act-btn" @click="sfReset">Cancel</button>
        </div>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         SECTION 3: Recent Runs (full width, reduced columns)
         ══════════════════════════════════════════════════════════════════════ -->
    <div class="runs-section">
      <div class="runs-header">
        <h2 class="section-title">Recent Runs</h2>
        <span class="count-badge">
          {{ (historyPhoneFilter || historyTypeFilter) ? `${filteredRuns.length}/${allRuns.length}` : allRuns.length }}
        </span>
        <div class="runs-filters">
          <select v-model="historyPhoneFilter" class="filter-select">
            <option value="">All Phones</option>
            <option v-for="ph in phoneList" :key="ph.serial" :value="ph.serial">{{ ph.label }}</option>
          </select>
          <select v-model="historyTypeFilter" class="filter-select">
            <option value="">All Types</option>
            <option value="post">&#x1f4f9; post</option>
            <option value="publish_draft">&#x1f4e4; publish_draft</option>
            <option value="content_gen">&#x1f916; content_gen</option>
          </select>
        </div>
      </div>

      <div class="runs-table-wrap">
        <div v-if="!filteredRuns.length" class="empty-msg">No runs yet</div>
        <table v-else class="runs-table">
          <thead>
            <tr>
              <th class="th-left">Type / Name</th>
              <th class="th-left">Phone</th>
              <th class="th-left">Started</th>
              <th class="th-left">Duration</th>
              <th class="th-left">Status</th>
              <th class="th-left">Stats</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filteredRuns" :key="r.id" class="history-row" @click="onRunRowClick(r)">
              <!-- Type / Name combined -->
              <td class="td-name">
                <span class="run-type-icon">{{ TYPE_BADGE[r.job_type] || '' }}</span>
                <span class="run-name">{{ r.schedule_name || r.job_type }}</span>
              </td>
              <!-- Phone -->
              <td class="td-dim">{{ phoneName(r.phone_serial) }}</td>
              <!-- Started -->
              <td class="td-mono">{{ (r.started_at || r.created_at || '').slice(5, 16).replace('T', ' ') }}</td>
              <!-- Duration -->
              <td>
                <template v-if="r._active && r.started_at">
                  <span class="td-running">{{ fmtElapsed(r.started_at) }}&hellip;</span>
                </template>
                <template v-else>
                  <span class="td-dim">{{ r.duration_s != null ? fmtDuration(r.duration_s) : '\u2014' }}</span>
                </template>
              </td>
              <!-- Status -->
              <td>
                <span v-if="r._active" class="status-chip chip-running">running</span>
                <span v-else-if="r.status === 'completed'" class="status-chip chip-ok">completed</span>
                <span v-else-if="r.status === 'failed'" class="status-chip chip-fail">failed</span>
                <span v-else-if="r.status === 'timeout'" class="status-chip chip-warn">timeout</span>
                <span v-else-if="r.status === 'killed'" class="status-chip chip-killed">killed</span>
                <span v-else-if="r.status === 'preempted'" class="status-chip chip-preempt">preempted</span>
                <span v-else class="status-chip">{{ r.status }}</span>
              </td>
              <!-- Stats -->
              <td class="td-stats">
                <template v-if="r._active">
                  <span class="td-running" style="font-style:italic">in progress&hellip;</span>
                </template>
                <template v-else-if="r.error_msg && r.error_msg.trim()">
                  <span :style="{ color: r.status === 'timeout' ? '#fb923c' : r.status === 'failed' ? '#f87171' : '#34d399' }">
                    {{ r.error_msg.trim() }}
                  </span>
                </template>
                <template v-else>
                  <span class="td-dim"></span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         LOG PANEL (unchanged functionality)
         ══════════════════════════════════════════════════════════════════════ -->
    <div v-if="logPanelOpen" class="card p-4 mb-6" style="border-color: #334155">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <span class="text-sm font-semibold" style="color: #cbd5e1">Logs: {{ logPanelTitle }}</span>
          <span class="text-xs" style="color: #64748b">{{ logPanelLines.length }} lines</span>
        </div>
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-1.5 text-xs cursor-pointer" style="color: #64748b">
            <input type="checkbox" v-model="logPanelAutoScroll" style="width: 11px; height: 11px; accent-color: var(--accent)" />
            auto-scroll
          </label>
          <button class="rounded px-2 py-0.5 text-xs" style="background: #1e293b; border: 1px solid #334155; color: #94a3b8; cursor: pointer" @click="closeLogPanel">Close</button>
        </div>
      </div>
      <div id="sched-log-viewer"
        style="height: 320px; overflow-y: auto; background: #070b10; border: 1px solid #1e2438; border-radius: 8px; padding: 10px 12px; font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 11px; line-height: 1.55; color: #94a3b8; white-space: pre-wrap; word-break: break-all">
        <div v-if="!logPanelLines.length" style="color: #475569">-- no log output --</div>
        <div v-for="(line, i) in logPanelLines" :key="i"
          :style="{
            color: line.includes('ERROR') || line.includes('FAIL') ? '#f87171' :
              line.includes('WARN') ? '#fbbf24' :
              line.includes('PASS') || line.includes('completed') ? '#4ade80' : '#94a3b8'
          }">{{ line }}</div>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* ── Layout Shell ─────────────────────────────────────────────────────── */
.scheduler-root {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Status Bar (top row, compact) ────────────────────────────────────── */
.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 14px;
}

.status-bar-phone {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px 3px 6px;
  border-right: 1px solid var(--border);
}
.status-bar-phone:last-of-type {
  border-right: none;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-4);
  flex-shrink: 0;
}
.status-dot.dot-active {
  background: #22c55e;
  box-shadow: 0 0 6px #22c55e88;
}

.status-phone-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
}

.status-job-name {
  font-size: 11px;
  font-weight: 600;
  color: #a5b4fc;
  white-space: nowrap;
}

.status-elapsed {
  font-size: 10px;
  font-family: monospace;
  color: #22c55e;
}

.status-kill-btn {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #7f1d1d;
  border: 1px solid #991b1b;
  color: #fca5a5;
  cursor: pointer;
  line-height: 1.3;
}
.status-kill-btn:hover { background: #991b1b; }

.status-idle {
  font-size: 10px;
  color: var(--text-4);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-next {
  font-size: 10px;
  color: var(--text-3);
}

.status-queue-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  background: #78350f;
  color: #fbbf24;
  font-weight: 600;
}

.status-sched-count {
  font-size: 9px;
  color: var(--text-4);
}

.status-bar-queue {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.status-queue-label {
  font-size: 10px;
  color: var(--text-4);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.status-queue-item {
  font-size: 10px;
  color: var(--text-3);
  padding: 1px 6px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.status-queue-x {
  background: none;
  border: none;
  color: var(--text-4);
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
  line-height: 1;
}
.status-queue-x:hover { color: #f87171; }

/* ── Section Headers ──────────────────────────────────────────────────── */
.section-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  margin: 0;
  letter-spacing: 0.01em;
}

.section-subtitle {
  font-size: 11px;
  color: var(--text-4);
}

.count-badge {
  font-size: 11px;
  color: var(--text-4);
  padding: 0 6px;
  background: var(--bg-deep);
  border-radius: 8px;
  line-height: 1.6;
}

/* ── Timeline ─────────────────────────────────────────────────────────── */
.timeline-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}

.timeline-canvas-wrap {
  min-height: 150px;
}

/* ── Schedule + Form Grid ─────────────────────────────────────────────── */
.sched-form-grid {
  display: grid;
  grid-template-columns: 4fr 1.5fr;
  gap: 16px;
  align-items: stretch;
}

/* ── Schedule List ────────────────────────────────────────────────────── */
.sched-list-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}

.sched-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.sched-list-header .filter-select {
  margin-left: auto;
}

.empty-msg {
  font-size: 12px;
  color: var(--text-4);
  padding: 8px 0;
}

.sched-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 480px;
  overflow-y: auto;
}

.sched-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  padding: 6px 10px;
  background: var(--bg-deep);
  border: 1px solid transparent;
  border-radius: 6px;
  transition: border-color 0.15s;
}
.sched-row:hover {
  border-color: var(--border);
}

.sched-row-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
}

.sched-enabled-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-4);
  flex-shrink: 0;
}
.sched-enabled-dot.enabled {
  background: #22c55e;
}

.sched-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

.type-badge {
  font-size: 9px;
  font-weight: 600;
  color: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1.5;
  flex-shrink: 0;
}

.sched-phone {
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}

.sched-separator {
  font-size: 11px;
  color: var(--text-4);
}

.sched-timing {
  font-size: 11px;
  color: var(--text-3);
  font-family: monospace;
  white-space: nowrap;
}

.sched-account {
  font-size: 11px;
  color: #a78bfa;
  white-space: nowrap;
}

.sched-detail {
  font-size: 10px;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.sched-row-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.sched-last-next {
  font-size: 10px;
  color: var(--text-4);
  white-space: nowrap;
}

.sched-row-actions {
  display: flex;
  gap: 3px;
  flex-shrink: 0;
}

/* ── Action Buttons ───────────────────────────────────────────────────── */
.act-btn {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-2);
  cursor: pointer;
  transition: all 0.12s;
  line-height: 1.4;
}
.act-btn:hover { border-color: var(--accent-lt); color: var(--text-1); }
.act-btn.act-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.act-btn.act-primary:hover { opacity: 0.85; }
.act-btn.act-danger { background: #7f1d1d; border-color: #991b1b; color: #fca5a5; }
.act-btn.act-danger:hover { background: #991b1b; }
.act-btn.act-enable { background: #166534; border-color: #22c55e; color: #bbf7d0; }

/* ── Filter Select ────────────────────────────────────────────────────── */
.filter-select {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--bg-deep);
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: 4px;
}

/* ── Form Panel ───────────────────────────────────────────────────────── */
.form-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}

.form-title {
  margin-bottom: 10px;
}

.form-field {
  margin-bottom: 8px;
}

.form-label {
  display: block;
  font-size: 11px;
  color: var(--text-3);
  margin-bottom: 2px;
}

.form-hint {
  color: var(--text-4);
}

.form-input {
  width: 100%;
  padding: 4px 8px;
  font-size: 12px;
  background: var(--bg-deep);
  color: var(--text-1);
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.form-input:focus { border-color: var(--accent); }

.form-textarea {
  font-family: monospace;
  resize: vertical;
}

.form-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.form-actions .act-btn {
  font-size: 12px;
  padding: 4px 14px;
}

/* ── Recent Runs Section ──────────────────────────────────────────────── */
.runs-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}

.runs-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.runs-filters {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.runs-table-wrap {
  max-height: 380px;
  overflow-y: auto;
}

/* ── Runs Table ───────────────────────────────────────────────────────── */
.runs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.runs-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-card);
}

.th-left {
  padding: 4px 8px;
  font-size: 10px;
  color: var(--text-4);
  text-align: left;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}

.runs-table td {
  padding: 4px 8px;
  border-bottom: 1px solid #1e243844;
  vertical-align: middle;
}

.runs-table tbody tr {
  cursor: pointer;
}

.history-row:hover {
  background: #0f1523;
}

.runs-table tbody tr:nth-child(even) {
  background: #0d101822;
}
.runs-table tbody tr:nth-child(even):hover {
  background: #0f1523;
}

.td-name {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.run-type-icon {
  font-size: 12px;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}

.run-name {
  color: #a5b4fc;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.td-dim { color: var(--text-4); }
.td-mono { font-family: monospace; color: var(--text-4); font-size: 10px; }
.td-running { color: #22c55e; }
.td-stats { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Status Chips ─────────────────────────────────────────────────────── */
.status-chip {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--text-3);
}
.chip-running { background: #052e1633; color: #22c55e; border: 1px solid #22c55e44; }
.chip-ok      { color: #34d399; }
.chip-fail    { background: #450a0a33; color: #f87171; border: 1px solid #f8717144; }
.chip-warn    { color: #fb923c; }
.chip-killed  { color: #fbbf24; }
.chip-preempt { color: #a78bfa; }

/* ── Scrollbar polish ─────────────────────────────────────────────────── */
.sched-rows::-webkit-scrollbar,
.runs-table-wrap::-webkit-scrollbar {
  width: 5px;
}
.sched-rows::-webkit-scrollbar-track,
.runs-table-wrap::-webkit-scrollbar-track {
  background: transparent;
}
.sched-rows::-webkit-scrollbar-thumb,
.runs-table-wrap::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}
</style>
