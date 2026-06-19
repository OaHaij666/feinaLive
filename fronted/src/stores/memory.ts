import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useNotification } from '@/utils/notification'
import type {
  AtomListResponse,
  GraphPayload,
  InjectPreviewPayload,
  MemoryAtom,
  MemoryBackup,
  MemoryStats,
  RecallResponse,
  SessionMemoryPayload,
} from '@/types/memory'

const API_BASE = '/ai/memory'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const data = await res.json()
      message = data.detail || data.error || message
    } catch {
      message = await res.text()
    }
    throw new Error(message)
  }
  return await res.json()
}

export const useMemoryStore = defineStore('memory', () => {
  const { error, success } = useNotification()
  const loading = ref(false)
  const stats = ref<MemoryStats | null>(null)
  const atomList = ref<AtomListResponse>({ items: [], total: 0, page: 1, page_size: 20, has_more: false })
  const selectedAtom = ref<MemoryAtom | null>(null)
  const recall = ref<RecallResponse | null>(null)
  const graph = ref<GraphPayload | null>(null)
  const session = ref<SessionMemoryPayload | null>(null)
  const injectPreview = ref<InjectPreviewPayload | null>(null)
  const backups = ref<MemoryBackup[]>([])

  async function withLoading<T>(fn: () => Promise<T>, failMessage: string): Promise<T | null> {
    loading.value = true
    try {
      return await fn()
    } catch (e) {
      error(`${failMessage}: ${e instanceof Error ? e.message : String(e)}`)
      return null
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    const data = await withLoading(() => request<MemoryStats>('/stats'), '获取记忆统计失败')
    if (data) stats.value = data
  }

  async function fetchAtoms(params: Record<string, string | number | undefined | null> = {}) {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') qs.set(key, String(value))
    }
    const data = await withLoading(
      () => request<AtomListResponse>(`/atoms${qs.toString() ? `?${qs}` : ''}`),
      '获取记忆列表失败',
    )
    if (data) atomList.value = data
  }

  async function fetchAtom(id: number) {
    const data = await withLoading(() => request<MemoryAtom>(`/atoms/${id}`), '获取记忆详情失败')
    if (data) selectedAtom.value = data
  }

  async function updateAtom(id: number, payload: Partial<MemoryAtom>) {
    const data = await withLoading(
      () => request<{ success: boolean; atom: MemoryAtom }>(`/atoms/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
      '更新记忆失败',
    )
    if (data?.success) {
      selectedAtom.value = data.atom
      success('记忆已更新')
    }
    return data?.success || false
  }

  async function batchUpdate(atomIds: number[], fields: Record<string, unknown>) {
    const data = await withLoading(
      () => request<{ success: boolean; updated_count: number }>('/atoms/batch-update', {
        method: 'POST',
        body: JSON.stringify({ atom_ids: atomIds, fields }),
      }),
      '批量更新失败',
    )
    if (data?.success) success(`已更新 ${data.updated_count} 条记忆`)
    return data?.success || false
  }

  async function batchDelete(atomIds: number[]) {
    const data = await withLoading(
      () => request<{ success: boolean; deleted_count: number }>('/atoms/batch-delete', {
        method: 'POST',
        body: JSON.stringify({ atom_ids: atomIds }),
      }),
      '删除记忆失败',
    )
    if (data?.success) success(`已软删除 ${data.deleted_count} 条记忆`)
    return data?.success || false
  }

  async function testRecall(payload: Record<string, unknown>) {
    const data = await withLoading(
      () => request<RecallResponse>('/recall/test', { method: 'POST', body: JSON.stringify(payload) }),
      '召回测试失败',
    )
    if (data) recall.value = data
  }

  async function fetchGraph(params: Record<string, string | number | undefined | null> = {}) {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') qs.set(key, String(value))
    }
    const data = await withLoading(
      () => request<GraphPayload>(`/graph/overview${qs.toString() ? `?${qs}` : ''}`),
      '获取图谱失败',
    )
    if (data) graph.value = data
  }

  async function queryGraph(payload: Record<string, unknown>) {
    const data = await withLoading(
      () => request<GraphPayload>('/graph/query', { method: 'POST', body: JSON.stringify(payload) }),
      '查询图谱失败',
    )
    if (data) graph.value = data
  }

  async function fetchSession() {
    const data = await withLoading(() => request<SessionMemoryPayload>('/session'), '获取单局记忆失败')
    if (data) session.value = data
  }

  async function previewInject(payload: Record<string, unknown>) {
    const data = await withLoading(
      () => request<InjectPreviewPayload>('/inject/preview', { method: 'POST', body: JSON.stringify(payload) }),
      '生成注入预览失败',
    )
    if (data) injectPreview.value = data
  }

  async function fetchBackups() {
    const data = await withLoading(() => request<{ backups: MemoryBackup[] }>('/backups'), '获取备份列表失败')
    if (data) backups.value = data.backups || []
  }

  async function createBackup() {
    const data = await withLoading(
      () => request<{ success: boolean }>('/backups', { method: 'POST', body: JSON.stringify({}) }),
      '创建备份失败',
    )
    if (data?.success) {
      success('记忆数据库备份已创建')
      await fetchBackups()
    }
  }

  return {
    loading,
    stats,
    atomList,
    selectedAtom,
    recall,
    graph,
    session,
    injectPreview,
    backups,
    fetchStats,
    fetchAtoms,
    fetchAtom,
    updateAtom,
    batchUpdate,
    batchDelete,
    testRecall,
    fetchGraph,
    queryGraph,
    fetchSession,
    previewInject,
    fetchBackups,
    createBackup,
  }
})
