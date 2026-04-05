<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { SystemImage } from '@/stores/emulators'

const props = defineProps<{
  systemImages: SystemImage[]
  hasCmdlineTools: boolean
}>()

const emit = defineEmits<{
  create: [payload: Record<string, any>]
}>()

const form = reactive({
  name: '',
  api_level: 35,
  target: 'google_apis_playstore',
  device_profile: 'medium_phone',
  ram_mb: 2048,
  disk_mb: 6144,
  resolution: '1080x2400',
  dpi: 420,
  gpu: 'auto',
  cores: 2,
  headless: false,
})

const expanded = ref(false)

const deviceProfiles = [
  { value: 'medium_phone', label: 'Medium Phone' },
  { value: 'pixel_7', label: 'Pixel 7' },
  { value: 'pixel_8', label: 'Pixel 8' },
  { value: 'pixel_fold', label: 'Pixel Fold' },
  { value: 'pixel_tablet', label: 'Pixel Tablet' },
]

const gpuModes = [
  { value: 'auto', label: 'Auto' },
  { value: 'host', label: 'Host GPU' },
  { value: 'swiftshader_indirect', label: 'SwiftShader (software)' },
  { value: 'off', label: 'Off' },
]

function handleSubmit() {
  if (!form.name.trim()) return
  emit('create', { ...form })
  form.name = ''
}
</script>

<template>
  <div class="card">
    <button
      class="flex items-center justify-between w-full text-left"
      @click="expanded = !expanded"
    >
      <h2 class="text-base font-semibold" style="color: var(--text-1)">+ Create Emulator</h2>
      <span class="text-xs" style="color: var(--text-4)">{{ expanded ? '&#9660;' : '&#9654;' }}</span>
    </button>

    <div v-if="!props.hasCmdlineTools" class="mt-3 px-3 py-2 rounded-lg text-xs"
      style="background: #f59e0b15; border: 1px solid #f59e0b30; color: #f59e0b">
      cmdline-tools not installed. Creating new AVDs is disabled.
      Existing AVDs can still be started/stopped.
    </div>

    <form v-if="expanded && props.hasCmdlineTools" @submit.prevent="handleSubmit" class="mt-4 space-y-3">
      <!-- Row 1: Name + API -->
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">Name</label>
          <input
            v-model="form.name"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
            placeholder="my_emulator"
            required
          />
        </div>
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">API Level</label>
          <select
            v-model.number="form.api_level"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          >
            <option v-for="img in systemImages" :key="img.package" :value="Number(img.api_level)">
              Android {{ img.api_level }} ({{ img.target }})
            </option>
            <option v-if="systemImages.length === 0" :value="35">35 (not installed)</option>
          </select>
        </div>
      </div>

      <!-- Row 2: Device + RAM + Disk -->
      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">Device Profile</label>
          <select
            v-model="form.device_profile"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          >
            <option v-for="dp in deviceProfiles" :key="dp.value" :value="dp.value">{{ dp.label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">RAM (MB)</label>
          <input
            v-model.number="form.ram_mb"
            type="number" min="1024" step="512"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          />
        </div>
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">Disk (MB)</label>
          <input
            v-model.number="form.disk_mb"
            type="number" min="2048" step="1024"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          />
        </div>
      </div>

      <!-- Row 3: Resolution + GPU + Cores -->
      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">Resolution</label>
          <input
            v-model="form.resolution"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
            placeholder="1080x2400"
          />
        </div>
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">GPU</label>
          <select
            v-model="form.gpu"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          >
            <option v-for="g in gpuModes" :key="g.value" :value="g.value">{{ g.label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs mb-1" style="color: var(--text-3)">CPU Cores</label>
          <input
            v-model.number="form.cores"
            type="number" min="1" max="16"
            class="w-full px-3 py-1.5 rounded-md text-sm"
            style="background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-1)"
          />
        </div>
      </div>

      <!-- Row 4: Checkboxes + Submit -->
      <div class="flex items-center justify-between">
        <label class="flex items-center gap-2 text-sm" style="color: var(--text-2)">
          <input type="checkbox" v-model="form.headless" class="rounded" />
          Headless (no window)
        </label>
        <button type="submit" class="btn btn-primary" :disabled="!form.name.trim()">
          Create Emulator
        </button>
      </div>
    </form>
  </div>
</template>
