<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BotView from '@/views/BotView.vue'
import TestsView from '@/views/TestsView.vue'
import SchedulerView from '@/views/SchedulerView.vue'
import PhoneAdminView from '@/views/PhoneAdminView.vue'
import SkillHubView from '@/views/SkillHubView.vue'
import SkillCreatorView from '@/views/SkillCreatorView.vue'
import ExplorerView from '@/views/ExplorerView.vue'
import ToolsHubView from '@/views/ToolsHubView.vue'
import EmulatorTab from '@/components/emulator/EmulatorTab.vue'
import BenchmarkTab from '@/components/benchmark/BenchmarkTab.vue'

const coreTabs = [
  { id: 'phone', label: '👻 Phone Agent' },
  { id: 'scheduler', label: '⏰ Scheduler' },
  { id: 'skills', label: '🧩 Skill Hub' },
  { id: 'creator', label: '🛠️ Skill Creator' },
  { id: 'explorer', label: '⛏️ Skill-Miner' },
  { id: 'tools', label: '🔧 Tools' },
  { id: 'bot', label: '▶️ Manual Run' },
  { id: 'tests', label: '🧪 Tests' },
  { id: 'emulators', label: '🖥️ Emulators' },
  { id: 'benchmarks', label: '📊 Benchmarks' },
]

const premiumTabs = ref<{id: string, label: string, component?: string}[]>([])
const tabs = computed(() => [...coreTabs, ...premiumTabs.value])

const activeTab = ref('phone')
const restarting = ref(false)

// Status ghost — polls device state for header mascot
const ghostState = ref<'disconnected' | 'idle' | 'working' | 'error'>('disconnected')
const GHOST_IMAGES: Record<string, string> = {
  disconnected: '/mascot/47-sleeping.png',
  idle: '/mascot/01-front-view.png',
  working: '/mascot/05-focused.png',
  error: '/mascot/49-dead.png',
}
let ghostTimer: number | null = null
async function pollGhostState() {
  try {
    const resp = await fetch('/api/phone/devices')
    if (!resp.ok) { ghostState.value = 'error'; return }
    const data = await resp.json()
    const devs = data.devices || data || []
    if (!devs.length) { ghostState.value = 'disconnected'; return }
    try {
      const qr = await fetch('/api/scheduler/queue')
      if (qr.ok) {
        const qd = await qr.json()
        const running = (qd.queue || []).some((j: any) => j.status === 'running')
        ghostState.value = running ? 'working' : 'idle'
        return
      }
    } catch {}
    ghostState.value = 'idle'
  } catch { ghostState.value = 'disconnected' }
}
async function fetchFeatures() {
  try {
    const resp = await fetch('/api/features')
    if (resp.ok) {
      const data = await resp.json()
      premiumTabs.value = data.premium_tabs || []
    }
  } catch {}
}

onMounted(() => {
  pollGhostState()
  fetchFeatures()
  ghostTimer = window.setInterval(pollGhostState, 10000)
})
onUnmounted(() => { if (ghostTimer) clearInterval(ghostTimer) })

async function restartServer() {
  if (!confirm('Restart the backend server?')) return
  restarting.value = true
  try {
    await fetch('/api/server/restart', { method: 'POST' })
  } catch {}
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 1000))
    try {
      const resp = await fetch('/api/stats')
      if (resp.ok) { restarting.value = false; return }
    } catch {}
  }
  restarting.value = false
}
</script>

<template>
  <div class="min-h-screen" style="background: var(--bg-base)">
    <div class="px-6 pt-4 pb-0">
      <div class="flex items-center justify-between mb-4">
        <div style="display:flex;align-items:center;gap:0.6rem">
          <div style="display:flex;flex-direction:column;align-items:center;min-width:48px">
            <img :src="GHOST_IMAGES[ghostState]" alt="" style="width:44px;height:44px;object-fit:contain;transition:all 0.3s;filter:drop-shadow(0 0 6px rgba(52,211,153,0.4))" />
            <span style="font-size:8px;letter-spacing:0.5px;margin-top:-2px;opacity:0.45;text-transform:uppercase;color:var(--text-1);line-height:1">{{ ghostState }}</span>
          </div>
          <h1 class="text-xl font-bold" style="color: var(--text-1)">
            Ghost in the Droid
          </h1>
        </div>
        <div class="flex items-center gap-3">
          <a href="http://localhost:4321" target="_blank"
            style="padding: 4px 12px; font-size: 11px; border-radius: 5px; border: 1px solid #1e2e22; background: #141e17; color: #8a9a8d; text-decoration: none; transition: color 0.2s"
            onmouseover="this.style.color='#e8ede9'" onmouseout="this.style.color='#8a9a8d'">
            📖 Docs
          </a>
          <button @click="restartServer" :disabled="restarting"
            style="padding: 4px 12px; font-size: 11px; border-radius: 5px; cursor: pointer; border: 1px solid #1e2e22; background: #141e17; color: #8a9a8d"
            :style="restarting ? { opacity: 0.5, cursor: 'wait' } : {}">
            {{ restarting ? '⟳ Restarting...' : '⟳ Restart Server' }}
          </button>
        </div>
      </div>
      <div class="flex gap-1 border-b pb-0 flex-wrap" style="border-color: var(--border)">
        <button
          v-for="tab in tabs" :key="tab.id" @click="activeTab = tab.id"
          class="px-5 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 transition-colors whitespace-nowrap"
          :class="activeTab === tab.id
            ? 'border-emerald-500/70 text-emerald-500/80 bg-emerald-500/8'
            : 'border-transparent text-slate-500 hover:text-slate-300'">
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div class="px-6 py-4">
      <PhoneAdminView v-if="activeTab === 'phone'" />
      <SchedulerView v-else-if="activeTab === 'scheduler'" />
      <SkillHubView v-else-if="activeTab === 'skills'" />
      <SkillCreatorView v-else-if="activeTab === 'creator'" />
      <ExplorerView v-else-if="activeTab === 'explorer'" />
      <ToolsHubView v-else-if="activeTab === 'tools'" />
      <BotView v-else-if="activeTab === 'bot'" />
      <TestsView v-else-if="activeTab === 'tests'" />
      <EmulatorTab v-else-if="activeTab === 'emulators'" />
      <BenchmarkTab v-else-if="activeTab === 'benchmarks'" />
      <!-- Premium tabs: rendered as iframes from premium frontend server -->
      <iframe
        v-else-if="premiumTabs.some(t => t.id === activeTab)"
        :src="`http://localhost:6176/#/${activeTab}`"
        style="width:100%;border:none;min-height:calc(100vh - 120px)"
      />
    </div>
  </div>
</template>
