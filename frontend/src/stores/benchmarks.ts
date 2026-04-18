import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'

export interface BenchmarkTask {
  id: string
  goal: string
  app: string
  category: string
  complexity: number
  max_steps: number
}

export interface BenchmarkSuite {
  id: string
  name: string
  description: string
}

export interface TaskResult {
  task_id: string
  goal: string
  model: string
  device: string
  score: number
  reason: string
  steps: number
  time_s: number
  error: string
  agent_log: Array<{ type: string; content?: string; name?: string; args?: any; result?: string }>
}

export interface BenchmarkRunSummary {
  id: string
  suite: string
  model: string
  provider: string
  device: string
  status: 'pending' | 'running' | 'completed' | 'stopped'
  success_rate: number
  total_tasks: number
  passed: number
  total_time_s: number
  started_at: number
  finished_at: number
  current_task: string
  results: TaskResult[]
}

export const useBenchmarkStore = defineStore('benchmarks', () => {
  const suites = ref<BenchmarkSuite[]>([])
  const tasks = ref<BenchmarkTask[]>([])
  const runs = ref<BenchmarkRunSummary[]>([])
  const error = ref<string | null>(null)

  async function fetchSuites() {
    try {
      suites.value = await api<BenchmarkSuite[]>('/api/benchmarks/suites')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function fetchTasks(suite = 'ghost_bench', category?: string) {
    try {
      const params = new URLSearchParams({ suite })
      if (category) params.set('category', category)
      tasks.value = await api<BenchmarkTask[]>(`/api/benchmarks/tasks?${params}`)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function fetchRuns() {
    try {
      runs.value = await api<BenchmarkRunSummary[]>('/api/benchmarks/runs')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function startRun(
    suite: string, taskIds: string[] | null, model: string, device: string, provider: string
  ) {
    error.value = null
    const result = await api<{ ok: boolean; run_id: string; message: string }>('/api/benchmarks/runs', {
      method: 'POST',
      body: JSON.stringify({ suite, tasks: taskIds, provider, model, device }),
    })
    await fetchRuns()
    return result
  }

  async function stopRun(runId: string) {
    await api(`/api/benchmarks/runs/${runId}/stop`, { method: 'POST' })
    await fetchRuns()
  }

  async function getRun(runId: string) {
    return api<BenchmarkRunSummary>(`/api/benchmarks/runs/${runId}`)
  }

  return { suites, tasks, runs, error, fetchSuites, fetchTasks, fetchRuns, startRun, stopRun, getRun }
})
