<template>
  <div class="memory-debug">
    <div class="memory-toolbar">
      <div class="toolbar-main">
        <div class="game-scope-control">
          <label for="memory-game-scope">游戏作用域</label>
          <select
            id="memory-game-scope"
            :value="selectedGameId"
            :disabled="!gameScopes.length || !!gameAction"
            aria-label="选择游戏记忆作用域"
            @change="changeGameScope"
          >
            <option v-if="!gameScopes.length" value="">暂无游戏</option>
            <option v-for="scope in gameScopes" :key="scope.game_id" :value="scope.game_id">
              {{ scope.game_id }} · {{ scope.atom_count }} 原子
            </option>
          </select>
          <span :class="['scope-status', gameSessionStatus?.active ? 'active' : 'inactive']">
            {{ gameSessionStatus?.active ? '会话运行中' : '无活动会话' }}
          </span>
        </div>
        <div class="memory-tabs" role="tablist" aria-label="记忆控制台页面">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            :class="{ active: activeView === tab.key }"
            role="tab"
            :aria-selected="activeView === tab.key"
            @click="switchView(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>
      <button class="small-btn" :disabled="loading || !!gameAction" aria-label="刷新当前记忆页面" @click="refreshCurrent">
        {{ loading || gameAction === 'scopes' ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div v-if="activeView === 'overview'" class="memory-view">
      <div class="stat-grid">
        <div class="stat-card"><span>长期记忆</span><strong>{{ stats?.total_atoms || 0 }}</strong></div>
        <div class="stat-card"><span>图谱节点</span><strong>{{ stats?.graph_nodes || 0 }}</strong></div>
        <div class="stat-card"><span>图谱边</span><strong>{{ stats?.graph_edges || 0 }}</strong></div>
        <div class="stat-card"><span>待总结事件</span><strong>{{ stats?.session.pending_count || 0 }}</strong></div>
      </div>
      <div class="overview-grid">
        <section class="memory-section">
          <h3>状态分布</h3>
          <div v-for="[key, count] in entries(stats?.status_breakdown)" :key="key" class="bar-row">
            <span>{{ key }}</span><div><i :style="{ width: barWidth(count, stats?.total_atoms || 0) }"></i></div><b>{{ count }}</b>
          </div>
          <p v-if="!entries(stats?.status_breakdown).length" class="empty">暂无状态数据</p>
        </section>
        <section class="memory-section">
          <h3>类型分布</h3>
          <div v-for="[key, count] in entries(stats?.atom_type_breakdown)" :key="key" class="bar-row">
            <span>{{ typeLabel(key) }}</span><div><i :style="{ width: barWidth(count, stats?.total_atoms || 0) }"></i></div><b>{{ count }}</b>
          </div>
          <p v-if="!entries(stats?.atom_type_breakdown).length" class="empty">暂无类型数据</p>
        </section>
        <section class="memory-section wide">
          <h3>重要性分布</h3>
          <div class="histogram">
            <div v-for="[key, count] in entries(stats?.importance_distribution)" :key="key" class="hist-bar">
              <i :style="{ height: barWidth(count, maxImportanceCount, true) }"></i>
              <span>{{ key }}</span>
              <b>{{ count }}</b>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div v-else-if="activeView === 'atoms'" class="memory-view atoms-layout">
      <section class="memory-section">
        <div class="filter-row">
          <input v-model="atomFilters.keyword" placeholder="关键词 / ID" @keyup.enter="loadAtoms(1)" />
          <select v-model="atomFilters.status"><option value="all">全部状态</option><option value="active">active</option><option value="dormant">dormant</option><option value="archived">archived</option><option value="forgotten">forgotten</option></select>
          <select v-model="atomFilters.atom_type"><option value="">全部类型</option><option v-for="item in atomTypes" :key="item" :value="item">{{ typeLabel(item) }}</option></select>
          <input v-model="atomFilters.game_id" placeholder="game_id" />
          <input v-model="atomFilters.user_id" placeholder="user_id" />
          <select v-model="atomFilters.sort"><option value="created_desc">新到旧</option><option value="importance_desc">重要性高</option><option value="accessed_desc">最近访问</option><option value="expires_asc">快过期</option></select>
          <button class="small-btn" @click="loadAtoms(1)">查询</button>
        </div>
        <div class="batch-row">
          <span>已选 {{ selectedAtomIds.length }} 条</span>
          <button class="small-btn danger" :disabled="!selectedAtomIds.length" @click="softDeleteSelected">软删除</button>
        </div>
        <div class="table-scroll">
          <table>
            <thead><tr><th></th><th>ID</th><th>内容</th><th>类型</th><th>重要性</th><th>状态</th><th>Scope</th><th>创建时间</th></tr></thead>
            <tbody>
              <tr v-for="atom in atomList.items" :key="atom.id" :class="{ selected: selectedAtom?.id === atom.id }" @click="selectAtom(atom.id)">
                <td><input type="checkbox" :checked="selectedAtomIds.includes(atom.id)" @click.stop="toggleAtomSelection(atom.id)" /></td>
                <td class="mono">{{ atom.id }}</td>
                <td><div class="content-cell">{{ atom.content }}</div></td>
                <td>{{ typeLabel(atom.atom_type) }}</td>
                <td>{{ score(atom.importance) }}</td>
                <td><span :class="['pill', atom.status]">{{ atom.status }}</span></td>
                <td class="scope-cell">{{ atom.game_id || atom.user_id || atom.session_id || '-' }}</td>
                <td>{{ formatTime(atom.created_at) }}</td>
              </tr>
              <tr v-if="!atomList.items.length"><td colspan="8" class="empty">暂无记忆</td></tr>
            </tbody>
          </table>
        </div>
        <div class="pager">
          <button class="small-btn" :disabled="atomList.page <= 1" @click="loadAtoms(atomList.page - 1)">上一页</button>
          <span>第 {{ atomList.page }} 页 / 共 {{ atomList.total }} 条</span>
          <button class="small-btn" :disabled="!atomList.has_more" @click="loadAtoms(atomList.page + 1)">下一页</button>
        </div>
      </section>

      <section class="memory-section detail-panel">
        <h3>记忆详情</h3>
        <div v-if="selectedAtom" class="detail-form">
          <label>内容<textarea v-model="editAtom.content" rows="5"></textarea></label>
          <label>实体<input v-model="editEntities" placeholder="用逗号分隔" /></label>
          <div class="form-grid">
            <label>类型<select v-model="editAtom.atom_type"><option v-for="item in atomTypes" :key="item" :value="item">{{ typeLabel(item) }}</option></select></label>
            <label>状态<select v-model="editAtom.status"><option value="active">active</option><option value="dormant">dormant</option><option value="archived">archived</option><option value="forgotten">forgotten</option></select></label>
            <label>重要性<input v-model.number="editAtom.importance" type="number" min="0" max="1" step="0.05" /></label>
            <label>置信度<input v-model.number="editAtom.confidence" type="number" min="0" max="1" step="0.05" /></label>
            <label>game_id<input v-model="editAtom.game_id" /></label>
            <label>user_id<input v-model="editAtom.user_id" /></label>
          </div>
          <div class="action-row">
            <button class="small-btn" @click="saveSelectedAtom">保存</button>
            <button class="small-btn danger" @click="softDeleteOne(selectedAtom.id)">软删除</button>
          </div>
        </div>
        <p v-else class="empty">选择一条记忆查看详情</p>
      </section>
    </div>

    <div v-else-if="activeView === 'recall'" class="memory-view recall-layout">
      <section class="memory-section">
        <h3>召回测试</h3>
        <textarea v-model="recallForm.query" rows="4" placeholder="输入查询内容，测试实际召回排序"></textarea>
        <div class="filter-row">
          <label>K <input v-model.number="recallForm.k" type="number" min="1" max="50" /></label>
          <input v-model="recallForm.game_id" placeholder="game_id" />
          <input v-model="recallForm.user_id" placeholder="user_id" />
          <select v-model="recallForm.atom_type"><option value="">全部类型</option><option v-for="item in atomTypes" :key="item" :value="item">{{ typeLabel(item) }}</option></select>
          <button class="small-btn" @click="runRecall">测试召回</button>
        </div>
      </section>
      <section class="memory-section">
        <h3>结果 <span v-if="recall">({{ recall.total }} 条 / {{ recall.elapsed_time_ms }}ms)</span></h3>
        <div v-for="(item, index) in recall?.results || []" :key="item.id" class="result-item" @click="selectAtom(item.id)">
          <div><b>#{{ index + 1 }}</b><span class="mono">ID {{ item.id }}</span><span>{{ typeLabel(item.atom_type) }}</span></div>
          <p>{{ item.content }}</p>
          <small>final {{ item.final_score }} / bm25 {{ item.bm25_score }} / temporal {{ item.temporal_score }}</small>
        </div>
        <p v-if="recall && !recall.results.length" class="empty">没有召回结果</p>
      </section>
    </div>

    <div v-else-if="activeView === 'graph'" class="memory-view graph-layout">
      <section class="memory-section graph-main">
        <div class="filter-row">
          <input v-model="graphForm.query" placeholder="查询图谱 / 高亮记忆" @keyup.enter="runGraphQuery" />
          <input v-model.number="graphForm.memory_id" type="number" min="1" placeholder="memory_id" />
          <input v-model="graphForm.game_id" placeholder="game_id" />
          <input v-model="graphForm.user_id" placeholder="user_id" />
          <button class="small-btn" @click="runGraphQuery">查询</button>
          <button class="small-btn" @click="loadGraphOverview">概览</button>
        </div>
        <div ref="canvasWrap" class="graph-canvas-wrap">
          <canvas ref="graphCanvas" @mousedown="onGraphMouseDown" @mousemove="onGraphMouseMove" @mouseup="onGraphMouseUp" @mouseleave="onGraphMouseUp" @wheel.prevent="onGraphWheel"></canvas>
        </div>
      </section>
      <section class="memory-section graph-side">
        <h3>图谱概览</h3>
        <div class="mini-stats">
          <span>节点 {{ graph?.summary.visible_node_count || 0 }}</span>
          <span>边 {{ graph?.summary.visible_edge_count || 0 }}</span>
          <span>记忆 {{ graph?.summary.visible_memory_count || 0 }}</span>
        </div>
        <h3>选中节点</h3>
        <pre>{{ selectedGraphNode ? JSON.stringify(selectedGraphNode.metadata, null, 2) : '未选中' }}</pre>
      </section>
    </div>

    <div v-else-if="activeView === 'session'" class="memory-view">
      <GameMemoryControl :game-id="selectedGameId" />
      <section class="memory-section inject-section">
        <h3>注入预览</h3>
        <div class="filter-row">
          <select v-model="injectForm.target"><option value="game">GameGraph</option><option value="host">HostGraph</option></select>
          <input v-model="injectForm.game_id" placeholder="game_id" />
          <input v-model="injectForm.user_id" placeholder="user_id" />
          <button class="small-btn" @click="runInjectPreview">生成</button>
        </div>
        <textarea :value="injectPreview?.content || ''" readonly rows="14"></textarea>
      </section>
    </div>

    <div v-else class="memory-view">
      <section class="memory-section">
        <div class="section-head">
          <h3>数据库备份</h3>
          <button class="small-btn" @click="store.createBackup">创建备份</button>
        </div>
        <div v-for="backup in backups" :key="backup.name" class="backup-item">
          <b>{{ backup.name }}</b>
          <span>{{ formatSize(backup.size_bytes) }} / {{ backup.file_count }} 文件 / {{ formatTime(backup.created_at) }}</span>
        </div>
        <p v-if="!backups.length" class="empty">暂无备份</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMemoryStore } from '@/stores/memory'
import type { GraphNode, MemoryAtom } from '@/types/memory'
import GameMemoryControl from '@/components/memory/GameMemoryControl.vue'

const store = useMemoryStore()
const {
  loading,
  stats,
  atomList,
  selectedAtom,
  recall,
  graph,
  injectPreview,
  backups,
  gameScopes,
  selectedGameId,
  gameSessionStatus,
  gameAction,
} = storeToRefs(store)

const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'atoms', label: '记忆管理' },
  { key: 'recall', label: '召回测试' },
  { key: 'graph', label: '知识图谱' },
  { key: 'session', label: '游戏会话' },
  { key: 'backups', label: '备份' },
]
const activeView = ref('overview')
const atomTypes = ['game_mechanic', 'game_lore', 'viewer_preference', 'viewer_fact', 'viewer_relation', 'host_personality', 'episodic', 'factual', 'unknown']
const selectedAtomIds = ref<number[]>([])
const editEntities = ref('')
const editAtom = reactive<Partial<MemoryAtom>>({})
const atomFilters = reactive({ keyword: '', status: 'all', atom_type: '', game_id: '', user_id: '', sort: 'created_desc' })
const recallForm = reactive({ query: '', k: 5, game_id: '', user_id: '', atom_type: '' })
const graphForm = reactive({ query: '', memory_id: null as number | null, game_id: '', user_id: '' })
const injectForm = reactive({ target: 'game', game_id: '', user_id: '' })

const graphCanvas = ref<HTMLCanvasElement | null>(null)
const canvasWrap = ref<HTMLElement | null>(null)
const selectedGraphNode = ref<GraphNode | null>(null)
const graphView = reactive({ scale: 1, offsetX: 0, offsetY: 0, dragging: false, dragNode: null as GraphNode | null, lastX: 0, lastY: 0 })

const maxImportanceCount = computed(() => Math.max(1, ...entries(stats.value?.importance_distribution).map(([, count]) => count)))

watch(selectedAtom, atom => {
  Object.assign(editAtom, atom || {})
  editEntities.value = (atom?.entities || []).join(', ')
})

watch(graph, async () => {
  if (activeView.value === 'graph') {
    await nextTick()
    layoutGraph()
    drawGraph()
  }
})

onMounted(async () => {
  await Promise.all([
    store.fetchStats(),
    store.fetchAtoms({ page: 1, page_size: 20 }),
    store.fetchGameScopes(),
  ])
  syncGameScope(selectedGameId.value)
  if (selectedGameId.value) {
    await Promise.all([
      store.fetchGameStatus(selectedGameId.value),
      store.fetchSession(selectedGameId.value),
    ])
  }
})

async function changeGameScope(event: Event) {
  const gameId = (event.target as HTMLSelectElement).value
  if (!gameId || gameId === selectedGameId.value) return
  const changed = await store.selectGameScope(gameId)
  if (!changed) return
  syncGameScope(gameId)
  await Promise.all([store.fetchGameStatus(gameId), store.fetchSession(gameId)])
  await refreshCurrent()
}

function syncGameScope(gameId: string) {
  atomFilters.game_id = gameId
  recallForm.game_id = gameId
  graphForm.game_id = gameId
  injectForm.game_id = gameId
}

async function switchView(key: string) {
  activeView.value = key
  await refreshCurrent()
}

async function refreshCurrent() {
  if (activeView.value === 'overview') await store.fetchStats()
  else if (activeView.value === 'atoms') await loadAtoms(atomList.value.page || 1)
  else if (activeView.value === 'graph') await loadGraphOverview()
  else if (activeView.value === 'session' && selectedGameId.value) {
    await Promise.all([
      store.fetchGameStatus(selectedGameId.value),
      store.fetchSession(selectedGameId.value),
    ])
  }
  else if (activeView.value === 'backups') await store.fetchBackups()
}

async function loadAtoms(page: number) {
  await store.fetchAtoms({ ...atomFilters, page, page_size: atomList.value.page_size || 20 })
}

async function selectAtom(id: number) {
  await store.fetchAtom(id)
  activeView.value = activeView.value === 'recall' ? 'atoms' : activeView.value
}

function toggleAtomSelection(id: number) {
  selectedAtomIds.value = selectedAtomIds.value.includes(id)
    ? selectedAtomIds.value.filter(item => item !== id)
    : [...selectedAtomIds.value, id]
}

async function saveSelectedAtom() {
  if (!selectedAtom.value) return
  const ok = await store.updateAtom(selectedAtom.value.id, {
    ...editAtom,
    entities: editEntities.value.split(',').map(item => item.trim()).filter(Boolean),
  })
  if (ok) await loadAtoms(atomList.value.page)
}

async function softDeleteSelected() {
  if (!selectedAtomIds.value.length || !window.confirm('确认将选中的记忆标记为 forgotten？')) return
  const ok = await store.batchDelete(selectedAtomIds.value)
  if (ok) {
    selectedAtomIds.value = []
    await loadAtoms(atomList.value.page)
  }
}

async function softDeleteOne(id: number) {
  if (!window.confirm(`确认软删除记忆 #${id}？`)) return
  const ok = await store.batchDelete([id])
  if (ok) await loadAtoms(atomList.value.page)
}

async function runRecall() {
  await store.testRecall({ ...recallForm, atom_type: recallForm.atom_type || null })
}

async function loadGraphOverview() {
  await store.fetchGraph({ game_id: graphForm.game_id, user_id: graphForm.user_id })
}

async function runGraphQuery() {
  await store.queryGraph({ ...graphForm, memory_id: graphForm.memory_id || null })
}

async function runInjectPreview() {
  await store.previewInject({ ...injectForm, user_id: injectForm.user_id || null })
}

function entries(value?: Record<string, number> | null): Array<[string, number]> {
  return Object.entries(value || {}).filter(([, count]) => count > 0)
}

function barWidth(value: number, total: number, vertical = false) {
  const pct = total <= 0 ? 0 : Math.max(4, Math.round((value / total) * 100))
  return `${Math.min(100, pct)}${vertical ? '%' : '%'}`
}

function typeLabel(value: string) {
  const labels: Record<string, string> = {
    game_mechanic: '游戏机制',
    game_lore: '游戏背景',
    viewer_preference: '观众偏好',
    viewer_fact: '观众事实',
    viewer_relation: '观众关系',
    host_personality: '主播人设',
    episodic: '互动事件',
    factual: '事实',
    unknown: '未知',
  }
  return labels[value] || value
}

function score(value: number) {
  return (Number(value || 0) * 10).toFixed(1)
}

function formatTime(ts?: number | null) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function layoutGraph() {
  const nodes = graph.value?.snapshot.nodes || []
  const edges = graph.value?.snapshot.edges || []
  if (!nodes.length) return
  const rect = canvasWrap.value?.getBoundingClientRect()
  const radius = Math.min(rect?.width || 800, rect?.height || 420) * 0.28
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / nodes.length
    node.x = Math.cos(angle) * radius
    node.y = Math.sin(angle) * radius
    node.vx = 0
    node.vy = 0
  })
  const nodeMap = new Map(nodes.map(node => [node.id, node]))
  for (let step = 0; step < 180; step++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        const dx = (a.x || 0) - (b.x || 0)
        const dy = (a.y || 0) - (b.y || 0)
        const dist2 = Math.max(80, dx * dx + dy * dy)
        const force = 900 / dist2
        const dist = Math.sqrt(dist2)
        a.vx = (a.vx || 0) + (dx / dist) * force
        a.vy = (a.vy || 0) + (dy / dist) * force
        b.vx = (b.vx || 0) - (dx / dist) * force
        b.vy = (b.vy || 0) - (dy / dist) * force
      }
    }
    for (const edge of edges) {
      const a = nodeMap.get(edge.source)
      const b = nodeMap.get(edge.target)
      if (!a || !b) continue
      const dx = (b.x || 0) - (a.x || 0)
      const dy = (b.y || 0) - (a.y || 0)
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy))
      const force = (dist - 130) * 0.015
      a.vx = (a.vx || 0) + (dx / dist) * force
      a.vy = (a.vy || 0) + (dy / dist) * force
      b.vx = (b.vx || 0) - (dx / dist) * force
      b.vy = (b.vy || 0) - (dy / dist) * force
    }
    for (const node of nodes) {
      node.vx = ((node.vx || 0) - (node.x || 0) * 0.002) * 0.82
      node.vy = ((node.vy || 0) - (node.y || 0) * 0.002) * 0.82
      node.x = (node.x || 0) + node.vx
      node.y = (node.y || 0) + node.vy
    }
  }
  graphView.scale = 1
  graphView.offsetX = 0
  graphView.offsetY = 0
}

function drawGraph() {
  const canvas = graphCanvas.value
  const rect = canvasWrap.value?.getBoundingClientRect()
  if (!canvas || !rect) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.floor(rect.width * dpr)
  canvas.height = Math.floor(rect.height * dpr)
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)
  ctx.fillStyle = 'rgba(15, 23, 42, 0.72)'
  ctx.fillRect(0, 0, rect.width, rect.height)
  const nodes = graph.value?.snapshot.nodes || []
  const edges = graph.value?.snapshot.edges || []
  const nodeMap = new Map(nodes.map(node => [node.id, node]))
  ctx.save()
  ctx.translate(rect.width / 2 + graphView.offsetX, rect.height / 2 + graphView.offsetY)
  ctx.scale(graphView.scale, graphView.scale)
  for (const edge of edges) {
    const a = nodeMap.get(edge.source)
    const b = nodeMap.get(edge.target)
    if (!a || !b) continue
    ctx.beginPath()
    ctx.moveTo(a.x || 0, a.y || 0)
    ctx.lineTo(b.x || 0, b.y || 0)
    ctx.strokeStyle = edge.relation_type === 'matches' ? 'rgba(45, 212, 191, 0.7)' : 'rgba(148, 163, 184, 0.35)'
    ctx.lineWidth = Math.max(1, edge.weight || 1)
    ctx.stroke()
  }
  for (const node of nodes) {
    const r = nodeRadius(node)
    ctx.beginPath()
    ctx.arc(node.x || 0, node.y || 0, r, 0, Math.PI * 2)
    ctx.fillStyle = nodeColor(node.type)
    ctx.fill()
    if (selectedGraphNode.value?.id === node.id) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 3
      ctx.stroke()
    }
    ctx.fillStyle = '#e2e8f0'
    ctx.font = '12px sans-serif'
    ctx.fillText(node.label.slice(0, 24), (node.x || 0) + r + 4, (node.y || 0) + 4)
  }
  ctx.restore()
}

function nodeRadius(node: GraphNode) {
  return Math.max(6, Math.min(16, 7 + Math.sqrt(Number(node.weight || 1)) * 2))
}

function nodeColor(type: string) {
  if (type === 'atom') return '#60a5fa'
  if (type === 'entity') return '#34d399'
  if (type.startsWith('game_')) return '#f59e0b'
  return '#94a3b8'
}

function hitGraphNode(clientX: number, clientY: number) {
  const canvas = graphCanvas.value
  const rect = canvas?.getBoundingClientRect()
  if (!rect) return null
  const x = (clientX - rect.left - rect.width / 2 - graphView.offsetX) / graphView.scale
  const y = (clientY - rect.top - rect.height / 2 - graphView.offsetY) / graphView.scale
  for (const node of graph.value?.snapshot.nodes || []) {
    const dx = x - (node.x || 0)
    const dy = y - (node.y || 0)
    if (Math.sqrt(dx * dx + dy * dy) <= nodeRadius(node) + 4) return node
  }
  return null
}

function onGraphMouseDown(event: MouseEvent) {
  graphView.lastX = event.clientX
  graphView.lastY = event.clientY
  graphView.dragNode = hitGraphNode(event.clientX, event.clientY)
  graphView.dragging = true
  if (graphView.dragNode) selectedGraphNode.value = graphView.dragNode
  drawGraph()
}

function onGraphMouseMove(event: MouseEvent) {
  if (!graphView.dragging) return
  const dx = event.clientX - graphView.lastX
  const dy = event.clientY - graphView.lastY
  graphView.lastX = event.clientX
  graphView.lastY = event.clientY
  if (graphView.dragNode) {
    graphView.dragNode.x = (graphView.dragNode.x || 0) + dx / graphView.scale
    graphView.dragNode.y = (graphView.dragNode.y || 0) + dy / graphView.scale
  } else {
    graphView.offsetX += dx
    graphView.offsetY += dy
  }
  drawGraph()
}

function onGraphMouseUp() {
  graphView.dragging = false
  graphView.dragNode = null
}

function onGraphWheel(event: WheelEvent) {
  graphView.scale = Math.max(0.35, Math.min(2.6, graphView.scale + (event.deltaY > 0 ? -0.08 : 0.08)))
  drawGraph()
}
</script>

<style scoped>
.memory-debug { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.memory-toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.toolbar-main { display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 10px; }
.game-scope-control { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #94a3b8; font-size: 11px; }
.game-scope-control select {
  min-width: 220px;
  min-height: 38px;
  padding: 7px 10px;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  color: #e2e8f0;
  background: #182235;
}
.scope-status { padding: 4px 8px; border-radius: 999px; font-weight: 700; }
.scope-status.active { color: #86efac; background: rgba(34,197,94,0.14); }
.scope-status.inactive { color: #94a3b8; background: rgba(148,163,184,0.12); }
.memory-tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.memory-tabs button, .small-btn {
  background: rgba(255,255,255,0.06);
  color: #cbd5e1;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 7px;
  padding: 7px 11px;
  cursor: pointer;
  font-size: 12px;
}
.memory-tabs button.active, .small-btn:hover { background: rgba(59,130,246,0.22); color: #93c5fd; }
.memory-tabs button:focus-visible, .small-btn:focus-visible, .game-scope-control select:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
.small-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.small-btn.danger { color: #fecaca; background: rgba(239,68,68,0.16); }
.memory-view { min-height: 0; }
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.stat-card, .memory-section {
  background: rgba(15,23,42,0.62);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 8px;
}
.stat-card { padding: 14px; display: flex; justify-content: space-between; align-items: center; }
.stat-card span { color: #94a3b8; font-size: 12px; }
.stat-card strong { color: #f8fafc; font-size: 24px; }
.overview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.memory-section { padding: 14px; min-width: 0; }
.memory-section.wide { grid-column: 1 / -1; }
.memory-section h3 { margin: 0 0 12px; color: #bfdbfe; font-size: 13px; }
.bar-row { display: grid; grid-template-columns: 110px 1fr 44px; align-items: center; gap: 8px; margin: 7px 0; font-size: 12px; color: #cbd5e1; }
.bar-row div { height: 8px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; }
.bar-row i { display: block; height: 100%; background: #38bdf8; }
.histogram { display: grid; grid-template-columns: repeat(10, 1fr); gap: 8px; height: 130px; align-items: end; }
.hist-bar { display: grid; grid-template-rows: 1fr auto auto; gap: 4px; text-align: center; font-size: 11px; color: #94a3b8; height: 100%; }
.hist-bar i { align-self: end; background: #22c55e; border-radius: 4px 4px 0 0; min-height: 4px; }
.atoms-layout { display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 12px; }
.filter-row, .batch-row, .action-row, .section-head, .pager { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.filter-row { margin-bottom: 10px; }
.filter-row input, .filter-row select, .detail-form input, .detail-form select, textarea {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  color: #e2e8f0;
  border-radius: 7px;
  padding: 7px 9px;
  font-size: 12px;
}
textarea { width: 100%; resize: vertical; font-family: inherit; box-sizing: border-box; }
.filter-row input { width: 130px; }
.table-scroll { max-height: 455px; overflow: auto; margin-top: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border-bottom: 1px solid rgba(255,255,255,0.07); padding: 8px; text-align: left; color: #cbd5e1; }
th { color: #93c5fd; font-weight: 600; position: sticky; top: 0; background: #172033; }
tr.selected { background: rgba(59,130,246,0.12); }
.content-cell { max-width: 440px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.scope-cell { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; color: #93c5fd; }
.pill { border-radius: 999px; padding: 2px 7px; background: rgba(148,163,184,0.18); }
.pill.active { color: #86efac; }
.pill.expired { color: #fbbf24; }
.pill.dormant { color: #fbbf24; }
.pill.archived { color: #c4b5fd; }
.pill.forgotten { color: #fca5a5; }
.detail-form { display: flex; flex-direction: column; gap: 10px; }
.detail-form label { display: flex; flex-direction: column; gap: 5px; color: #94a3b8; font-size: 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.recall-layout, .session-layout { display: grid; grid-template-columns: 0.8fr 1.2fr; gap: 12px; }
.inject-section { margin-top: 12px; }
.result-item, .event-item, .backup-item {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  background: rgba(255,255,255,0.035);
  cursor: pointer;
}
.result-item div { display: flex; gap: 10px; color: #93c5fd; font-size: 12px; }
.result-item p, .event-item p { margin: 6px 0; color: #e2e8f0; }
.result-item small, .backup-item span { color: #94a3b8; }
.graph-layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 12px; min-height: 590px; }
.graph-main { display: flex; flex-direction: column; }
.graph-canvas-wrap { flex: 1; min-height: 500px; border-radius: 8px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
canvas { display: block; width: 100%; height: 100%; cursor: grab; }
.mini-stats { display: grid; grid-template-columns: 1fr; gap: 8px; color: #cbd5e1; font-size: 12px; margin-bottom: 16px; }
pre { max-height: 420px; overflow: auto; white-space: pre-wrap; color: #cbd5e1; background: rgba(0,0,0,0.25); padding: 10px; border-radius: 8px; font-size: 11px; }
.empty { color: #64748b; text-align: center; padding: 20px; }
.pager { justify-content: flex-end; margin-top: 10px; color: #94a3b8; font-size: 12px; }
@media (max-width: 1100px) {
  .stat-grid, .overview-grid, .atoms-layout, .recall-layout, .session-layout, .graph-layout { grid-template-columns: 1fr; }
}
</style>
