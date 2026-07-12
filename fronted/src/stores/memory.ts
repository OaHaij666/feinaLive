import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useNotification } from '@/utils/notification'
import type {
  AtomListResponse,
  GraphPayload,
  GameMemoryContextPayload,
  GameMemoryPolicy,
  GameMemoryScope,
  GameMemoryScopesPayload,
  GameSessionStatus,
  InjectPreviewPayload,
  MemoryAtom,
  MemoryBackup,
  MemoryStats,
  RecallResponse,
  SessionMemoryPayload,
} from '@/types/memory'

const API_BASE = '/ai/memory'
const GAME_MEMORY_BASE = '/agent/memory'

async function requestFrom<T>(base: string, path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    let message = body || `HTTP ${res.status}`
    try {
      const data = JSON.parse(body)
      message = data.detail || data.error || message
    } catch { /* 非 JSON 错误正文直接展示 */ }
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return await res.json() as T
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return requestFrom<T>(API_BASE, path, options)
}

async function gameRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return requestFrom<T>(GAME_MEMORY_BASE, path, options)
}

export const useMemoryStore = defineStore('memory', () => {
  const { error, success } = useNotification()
  const loadingCount = ref(0)
  const loading = computed(() => loadingCount.value > 0)
  const stats = ref<MemoryStats | null>(null)
  const atomList = ref<AtomListResponse>({ items: [], total: 0, page: 1, page_size: 20, has_more: false })
  const selectedAtom = ref<MemoryAtom | null>(null)
  const recall = ref<RecallResponse | null>(null)
  const graph = ref<GraphPayload | null>(null)
  const session = ref<SessionMemoryPayload | null>(null)
  const injectPreview = ref<InjectPreviewPayload | null>(null)
  const backups = ref<MemoryBackup[]>([])
  const gameScopes = ref<GameMemoryScope[]>([])
  const selectedGameId = ref('')
  const gameSessionStatus = ref<GameSessionStatus | null>(null)
  const gameContext = ref<GameMemoryContextPayload | null>(null)
  const gameAction = ref('')

  async function withLoading<T>(fn: () => Promise<T>, failMessage: string): Promise<T | null> {
    loadingCount.value += 1
    try {
      return await fn()
    } catch (e) {
      error(`${failMessage}: ${e instanceof Error ? e.message : String(e)}`)
      return null
    } finally {
      loadingCount.value = Math.max(0, loadingCount.value - 1)
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

  async function fetchSession(gameId = selectedGameId.value) {
    const suffix = gameId ? `?game_id=${encodeURIComponent(gameId)}` : ''
    const data = await withLoading(() => request<SessionMemoryPayload>(`/session${suffix}`), '获取单局记忆失败')
    if (data) session.value = data
  }

  async function withGameAction<T>(action: string, fn: () => Promise<T>, failMessage: string) {
    gameAction.value = action
    try {
      return await fn()
    } catch (e) {
      error(`${failMessage}: ${e instanceof Error ? e.message : String(e)}`)
      return null
    } finally {
      gameAction.value = ''
    }
  }

  async function fetchGameScopes() {
    const data = await withGameAction(
      'scopes',
      () => gameRequest<GameMemoryScopesPayload>('/scopes'),
      '获取游戏作用域失败',
    )
    if (!data) return
    gameScopes.value = data.games || []
    selectedGameId.value = data.selected_game_id || selectedGameId.value || data.games?.[0]?.game_id || ''
  }

  async function selectGameScope(gameId: string) {
    if (!gameId) return false
    const data = await withGameAction(
      'select',
      () => gameRequest<GameSessionStatus>('/select', {
        method: 'POST',
        body: JSON.stringify({ game_id: gameId }),
      }),
      '切换游戏作用域失败',
    )
    if (!data) return false
    selectedGameId.value = gameId
    gameSessionStatus.value = data
    await fetchGameScopes()
    success(`已切换到 ${gameId}`)
    return true
  }

  async function fetchGameStatus(gameId = selectedGameId.value) {
    if (!gameId) {
      gameSessionStatus.value = null
      return
    }
    const data = await withGameAction(
      'status',
      () => gameRequest<GameSessionStatus>(`/${encodeURIComponent(gameId)}/status`),
      '获取游戏会话状态失败',
    )
    if (data) gameSessionStatus.value = data
  }

  async function fetchGameContext(gameId = selectedGameId.value, query = '') {
    if (!gameId) return
    const qs = query ? `?query=${encodeURIComponent(query)}` : ''
    const data = await withGameAction(
      'context',
      () => gameRequest<GameMemoryContextPayload>(`/${encodeURIComponent(gameId)}/context${qs}`),
      '获取游戏记忆上下文失败',
    )
    if (data) gameContext.value = data
  }

  async function openGameSession(
    gameId: string,
    payload: { external_session_id?: string | null; policy?: Partial<GameMemoryPolicy> },
  ) {
    const data = await withGameAction(
      'open',
      () => gameRequest<GameSessionStatus>(`/${encodeURIComponent(gameId)}/sessions/open`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
      '打开游戏会话失败',
    )
    if (!data) return false
    gameSessionStatus.value = data
    success('游戏会话已打开')
    await fetchGameScopes()
    return true
  }

  async function checkpointGameSession(gameId = selectedGameId.value, force = false) {
    if (!gameId) return false
    const data = await withGameAction(
      force ? 'force-checkpoint' : 'checkpoint',
      () => gameRequest<{ success: boolean; summarized: boolean }>(`/${encodeURIComponent(gameId)}/checkpoint`, {
        method: 'POST',
        body: JSON.stringify({ force }),
      }),
      '执行记忆检查点失败',
    )
    if (!data) return false
    success(data.summarized ? '记忆总结已完成' : '当前没有达到总结条件的事件')
    await Promise.all([fetchGameStatus(gameId), fetchSession(gameId)])
    return true
  }

  async function closeGameSession(gameId = selectedGameId.value) {
    if (!gameId) return false
    const data = await withGameAction(
      'close',
      () => gameRequest<GameSessionStatus>(`/${encodeURIComponent(gameId)}/sessions/close`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'control_panel' }),
      }),
      '关闭游戏会话失败',
    )
    if (!data) return false
    gameSessionStatus.value = data
    success('游戏会话已关闭')
    await Promise.all([fetchGameScopes(), fetchSession(gameId)])
    return true
  }

  async function updateWorkingMemory(
    gameId: string,
    layer: 'core' | 'important' | 'recent',
    content: string,
  ) {
    const data = await withGameAction(
      `layer-${layer}`,
      () => gameRequest<{ success: boolean }>(`/${encodeURIComponent(gameId)}/working-memory`, {
        method: 'PUT',
        body: JSON.stringify({ layer, content, source: 'control_panel' }),
      }),
      '更新工作记忆失败',
    )
    if (!data?.success) return false
    success('工作记忆已更新')
    await Promise.all([fetchGameStatus(gameId), fetchSession(gameId)])
    return true
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
    gameScopes,
    selectedGameId,
    gameSessionStatus,
    gameContext,
    gameAction,
    fetchStats,
    fetchAtoms,
    fetchAtom,
    updateAtom,
    batchDelete,
    testRecall,
    fetchGraph,
    queryGraph,
    fetchSession,
    fetchGameScopes,
    selectGameScope,
    fetchGameStatus,
    fetchGameContext,
    openGameSession,
    checkpointGameSession,
    closeGameSession,
    updateWorkingMemory,
    previewInject,
    fetchBackups,
    createBackup,
  }
})
