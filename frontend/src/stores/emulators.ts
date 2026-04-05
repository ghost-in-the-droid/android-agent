import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'

export interface Avd {
  name: string
  display_name?: string
  api_level: string
  target_flavor?: string
  abi?: string
  resolution?: string
  dpi?: number
  ram_mb?: number
  disk?: string
  gpu_mode?: string
  cores?: number
  playstore?: boolean
  status: 'running' | 'stopped' | 'booting'
  serial: string | null
  pid: number | null
}

export interface Prerequisites {
  sdk_root: string
  sdk_exists: boolean
  emulator_binary: boolean
  adb_binary: boolean
  cmdline_tools: boolean
  kvm: boolean
  avd_home: string
}

export interface SystemImage {
  api_level: string
  target: string
  arch: string
  package: string
  path: string
}

export interface PoolStatus {
  active: number
  idle: number
  busy: number
  max_concurrent: number
  emulators: Array<{
    serial: string
    name: string
    status: 'idle' | 'busy'
    current_job: string | null
    pid: number | null
  }>
  resources: ResourceUsage
}

export interface ResourceUsage {
  cpu_count: number
  cpu_percent: number
  ram_total_gb: number
  ram_used_gb: number
  ram_available_gb: number
  disk_total_gb: number
  disk_free_gb: number
}

export interface CreateAvdPayload {
  name: string
  api_level?: number
  target?: string
  device_profile?: string
  ram_mb?: number
  disk_mb?: number
  resolution?: string
  dpi?: number
  gpu?: string
  cores?: number
  headless?: boolean
}

export const useEmulatorStore = defineStore('emulators', () => {
  const avds = ref<Avd[]>([])
  const prerequisites = ref<Prerequisites | null>(null)
  const systemImages = ref<SystemImage[]>([])
  const poolStatus = ref<PoolStatus | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const runningCount = computed(() => avds.value.filter(a => a.status === 'running').length)
  const stoppedCount = computed(() => avds.value.filter(a => a.status === 'stopped').length)

  async function fetchPrerequisites() {
    try {
      prerequisites.value = await api<Prerequisites>('/api/emulators/prerequisites')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function fetchAvds(showLoading = false) {
    if (showLoading) loading.value = true
    error.value = null
    try {
      avds.value = await api<Avd[]>('/api/emulators')
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchSystemImages() {
    try {
      systemImages.value = await api<SystemImage[]>('/api/emulators/system-images')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function createAvd(payload: CreateAvdPayload) {
    error.value = null
    const result = await api<{ ok: boolean; error?: string }>('/api/emulators', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (!result.ok) throw new Error(result.error || 'Create failed')
    await fetchAvds()
    return result
  }

  async function deleteAvd(name: string) {
    error.value = null
    const result = await api<{ ok: boolean; error?: string }>(`/api/emulators/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
    if (!result.ok) throw new Error(result.error || 'Delete failed')
    await fetchAvds()
    return result
  }

  async function startAvd(name: string, headless = false) {
    error.value = null
    const result = await api<{ ok: boolean; serial?: string; error?: string }>(
      `/api/emulators/${encodeURIComponent(name)}/start`,
      { method: 'POST', body: JSON.stringify({ headless }) },
    )
    if (!result.ok) throw new Error(result.error || 'Start failed')
    await fetchAvds()
    return result
  }

  async function stopAvd(name: string) {
    error.value = null
    const result = await api<{ ok: boolean; error?: string }>(
      `/api/emulators/${encodeURIComponent(name)}/stop`,
      { method: 'POST' },
    )
    if (!result.ok) throw new Error(result.error || 'Stop failed')
    await fetchAvds()
    return result
  }

  async function setupAvd(name: string) {
    const result = await api<{ ok: boolean }>(
      `/api/emulators/${encodeURIComponent(name)}/setup`,
      { method: 'POST' },
    )
    return result
  }

  async function installApk(name: string, apkPath: string) {
    const result = await api<{ ok: boolean; error?: string }>(
      `/api/emulators/${encodeURIComponent(name)}/install-apk`,
      { method: 'POST', body: JSON.stringify({ apk_path: apkPath }) },
    )
    if (!result.ok) throw new Error(result.error || 'Install failed')
    return result
  }

  async function snapshotSave(name: string, snapshotName = 'automation_ready') {
    return api(`/api/emulators/${encodeURIComponent(name)}/snapshot/save`, {
      method: 'POST',
      body: JSON.stringify({ snapshot_name: snapshotName }),
    })
  }

  async function snapshotLoad(name: string, snapshotName = 'automation_ready') {
    return api(`/api/emulators/${encodeURIComponent(name)}/snapshot/load`, {
      method: 'POST',
      body: JSON.stringify({ snapshot_name: snapshotName }),
    })
  }

  // ── Pool ──────────────────────────────────────────────────────────────

  async function fetchPoolStatus() {
    try {
      poolStatus.value = await api<PoolStatus>('/api/emulator-pool/status')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function poolScaleUp(count: number, config: Partial<CreateAvdPayload> = {}) {
    const result = await api<{ ok: boolean; error?: string }>('/api/emulator-pool/scale-up', {
      method: 'POST',
      body: JSON.stringify({ count, config }),
    })
    if (!result.ok) throw new Error(result.error || 'Scale up failed')
    await fetchPoolStatus()
    return result
  }

  async function poolScaleDown(count?: number) {
    const result = await api<{ ok: boolean }>('/api/emulator-pool/scale-down', {
      method: 'POST',
      body: JSON.stringify({ count }),
    })
    await fetchPoolStatus()
    return result
  }

  async function poolStopAll() {
    const result = await api<{ ok: boolean }>('/api/emulator-pool/stop-all', {
      method: 'POST',
    })
    await fetchPoolStatus()
    return result
  }

  return {
    avds, prerequisites, systemImages, poolStatus,
    loading, error, runningCount, stoppedCount,
    fetchPrerequisites, fetchAvds, fetchSystemImages,
    createAvd, deleteAvd, startAvd, stopAvd, setupAvd,
    installApk, snapshotSave, snapshotLoad,
    fetchPoolStatus, poolScaleUp, poolScaleDown, poolStopAll,
  }
})
