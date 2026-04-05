<script setup lang="ts">
import { ref } from 'vue'
import type { Avd } from '@/stores/emulators'

const props = defineProps<{
  avds: Avd[]
  loading: boolean
}>()

const emit = defineEmits<{
  start: [name: string]
  stop: [name: string]
  delete: [name: string]
  setup: [name: string]
}>()

// Track which rows have an action in-flight to disable buttons
const busy = ref<Set<string>>(new Set())

async function act(name: string, event: 'start' | 'stop' | 'delete' | 'setup') {
  busy.value.add(name)
  try {
    emit(event, name)
  } finally {
    // Clear after a short delay so the poll can update status first
    setTimeout(() => busy.value.delete(name), 3000)
  }
}
</script>

<template>
  <div class="card" style="min-height: 120px">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-base font-semibold" style="color: var(--text-1)">Emulators</h2>
      <span class="text-xs" style="color: var(--text-4)">{{ avds.length }} AVDs</span>
    </div>

    <div v-if="loading && avds.length === 0" class="text-center py-8" style="color: var(--text-3)">
      Loading...
    </div>

    <div v-else-if="avds.length === 0" class="text-center py-8" style="color: var(--text-3)">
      No emulators found. Create one below.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm" style="table-layout: fixed">
        <colgroup>
          <col style="width: 28%" />
          <col style="width: 8%" />
          <col style="width: 14%" />
          <col style="width: 10%" />
          <col style="width: 12%" />
          <col style="width: 14%" />
          <col style="width: 14%" />
        </colgroup>
        <thead>
          <tr class="text-left text-xs uppercase" style="color: var(--text-4)">
            <th class="pb-2 pr-2">Name</th>
            <th class="pb-2 pr-2">API</th>
            <th class="pb-2 pr-2">Resolution</th>
            <th class="pb-2 pr-2">RAM</th>
            <th class="pb-2 pr-2">Status</th>
            <th class="pb-2 pr-2">Serial</th>
            <th class="pb-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="avd in avds"
            :key="avd.name"
            class="border-t"
            style="border-color: var(--border)"
          >
            <td class="py-2 pr-2 font-medium truncate" style="color: var(--text-1)" :title="avd.display_name || avd.name">
              {{ avd.display_name || avd.name }}
              <span v-if="avd.playstore" class="ml-1 text-xs opacity-50" title="Play Store">&#9654;</span>
            </td>
            <td class="py-2 pr-2" style="color: var(--text-2)">{{ avd.api_level }}</td>
            <td class="py-2 pr-2 truncate" style="color: var(--text-3)">{{ avd.resolution }}</td>
            <td class="py-2 pr-2" style="color: var(--text-3)">{{ avd.ram_mb ? `${avd.ram_mb}MB` : '—' }}</td>
            <td class="py-2 pr-2">
              <span
                class="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
                :class="{
                  'bg-green-500/15 text-green-400': avd.status === 'running',
                  'bg-yellow-500/15 text-yellow-400': avd.status === 'booting',
                  'bg-slate-500/15 text-slate-400': avd.status === 'stopped',
                }"
              >
                <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="{
                  'bg-green-400': avd.status === 'running',
                  'bg-yellow-400 animate-pulse': avd.status === 'booting',
                  'bg-slate-500': avd.status === 'stopped',
                }"></span>
                {{ avd.status }}
              </span>
            </td>
            <td class="py-2 pr-2 font-mono text-xs truncate" style="color: var(--text-3)">
              {{ avd.serial || '—' }}
            </td>
            <td class="py-2 text-right">
              <div class="flex gap-1 justify-end" style="min-height: 28px">
                <!-- Stopped actions -->
                <template v-if="avd.status === 'stopped'">
                  <button
                    class="btn btn-sm"
                    :disabled="busy.has(avd.name)"
                    @click="act(avd.name, 'start')"
                  >{{ busy.has(avd.name) ? '...' : 'Start' }}</button>
                  <button
                    class="btn btn-sm"
                    style="border-color: #ef4444; color: #ef4444"
                    :disabled="busy.has(avd.name)"
                    @click="act(avd.name, 'delete')"
                  >Del</button>
                </template>
                <!-- Booting actions -->
                <template v-else-if="avd.status === 'booting'">
                  <span class="text-xs py-1 px-2" style="color: var(--text-4)">booting...</span>
                  <button
                    class="btn btn-sm"
                    style="border-color: #f59e0b; color: #f59e0b"
                    @click="act(avd.name, 'stop')"
                  >Stop</button>
                </template>
                <!-- Running actions -->
                <template v-else>
                  <button
                    class="btn btn-sm"
                    :disabled="busy.has(avd.name)"
                    @click="act(avd.name, 'setup')"
                    title="Run automation setup"
                  >Setup</button>
                  <button
                    class="btn btn-sm"
                    style="border-color: #f59e0b; color: #f59e0b"
                    :disabled="busy.has(avd.name)"
                    @click="act(avd.name, 'stop')"
                  >{{ busy.has(avd.name) ? '...' : 'Stop' }}</button>
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
