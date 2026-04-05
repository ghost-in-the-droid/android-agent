<script setup lang="ts">
import { ref } from 'vue'
import type { PoolStatus } from '@/stores/emulators'

const props = defineProps<{
  pool: PoolStatus | null
}>()

const emit = defineEmits<{
  scaleUp: [count: number]
  scaleDown: [count: number | undefined]
  stopAll: []
  refresh: []
}>()

const scaleCount = ref(3)
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-base font-semibold" style="color: var(--text-1)">Emulator Pool</h2>
      <button class="btn btn-sm" @click="emit('refresh')">Refresh</button>
    </div>

    <!-- Status cards -->
    <div class="grid grid-cols-4 gap-3 mb-4">
      <div class="stat-card">
        <h3 style="color: var(--accent-lt)">{{ pool?.active ?? 0 }}</h3>
        <p>Active</p>
      </div>
      <div class="stat-card">
        <h3 style="color: #34d399">{{ pool?.idle ?? 0 }}</h3>
        <p>Idle</p>
      </div>
      <div class="stat-card">
        <h3 style="color: #f59e0b">{{ pool?.busy ?? 0 }}</h3>
        <p>Busy</p>
      </div>
      <div class="stat-card">
        <h3 style="color: var(--text-3)">{{ pool?.max_concurrent ?? 20 }}</h3>
        <p>Max</p>
      </div>
    </div>

    <!-- Resources -->
    <div v-if="pool?.resources" class="mb-4 p-3 rounded-lg" style="background: var(--bg-deep)">
      <div class="text-xs font-semibold mb-2" style="color: var(--text-3)">System Resources</div>
      <div class="grid grid-cols-3 gap-4 text-sm">
        <div>
          <span style="color: var(--text-4)">CPU:</span>
          <span class="ml-1 font-mono" style="color: var(--text-2)">{{ pool.resources.cpu_percent }}%</span>
          <span class="ml-1 text-xs" style="color: var(--text-4)">({{ pool.resources.cpu_count }} cores)</span>
        </div>
        <div>
          <span style="color: var(--text-4)">RAM:</span>
          <span class="ml-1 font-mono" style="color: var(--text-2)">
            {{ pool.resources.ram_used_gb }}/{{ pool.resources.ram_total_gb }} GB
          </span>
        </div>
        <div>
          <span style="color: var(--text-4)">Disk:</span>
          <span class="ml-1 font-mono" style="color: var(--text-2)">
            {{ pool.resources.disk_free_gb }} GB free
          </span>
        </div>
      </div>

      <!-- RAM bar -->
      <div class="mt-2 h-2 rounded-full overflow-hidden" style="background: var(--border)">
        <div
          class="h-full rounded-full transition-all"
          :style="{
            width: pool.resources.ram_total_gb
              ? `${(pool.resources.ram_used_gb / pool.resources.ram_total_gb * 100).toFixed(0)}%`
              : '0%',
            background: pool.resources.ram_used_gb / pool.resources.ram_total_gb > 0.85
              ? '#ef4444' : pool.resources.ram_used_gb / pool.resources.ram_total_gb > 0.7
                ? '#f59e0b' : '#34d399',
          }"
        ></div>
      </div>
    </div>

    <!-- Pool emulators table -->
    <div v-if="pool && pool.emulators.length > 0" class="mb-4">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs uppercase" style="color: var(--text-4)">
            <th class="pb-2 pr-4">Name</th>
            <th class="pb-2 pr-4">Serial</th>
            <th class="pb-2 pr-4">Status</th>
            <th class="pb-2">Job</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="emu in pool.emulators"
            :key="emu.serial"
            class="border-t"
            style="border-color: var(--border)"
          >
            <td class="py-1.5 pr-4" style="color: var(--text-2)">{{ emu.name }}</td>
            <td class="py-1.5 pr-4 font-mono text-xs" style="color: var(--text-3)">{{ emu.serial }}</td>
            <td class="py-1.5 pr-4">
              <span
                class="text-xs font-semibold"
                :style="{ color: emu.status === 'idle' ? '#34d399' : '#f59e0b' }"
              >{{ emu.status }}</span>
            </td>
            <td class="py-1.5 text-xs" style="color: var(--text-4)">{{ emu.current_job || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Controls -->
    <div class="flex items-center gap-3 flex-wrap">
      <div class="flex items-center gap-2">
        <label class="text-xs" style="color: var(--text-3)">Count:</label>
        <input
          v-model.number="scaleCount"
          type="number" min="1" max="20"
          class="w-16 px-2 py-1 rounded text-sm text-center"
          style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
        />
      </div>
      <button class="btn btn-primary btn-sm" @click="emit('scaleUp', scaleCount)">
        Scale Up
      </button>
      <button class="btn btn-sm" @click="emit('scaleDown', undefined)">
        Scale Down (idle)
      </button>
      <button
        v-if="pool && pool.active > 0"
        class="btn btn-sm"
        style="border-color: #ef4444; color: #ef4444"
        @click="emit('stopAll')"
      >
        Stop All
      </button>
    </div>
  </div>
</template>
