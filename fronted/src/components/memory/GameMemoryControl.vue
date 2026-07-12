<template>
  <div class="game-memory-control">
    <section class="control-card status-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">当前会话</p>
          <h3>{{ gameId || '未选择游戏' }}</h3>
        </div>
        <span :class="['status-pill', status?.active ? 'active' : 'inactive']">
          {{ status?.active ? '运行中' : '未运行' }}
        </span>
      </div>

      <div v-if="gameId" class="status-grid">
        <div><span>会话 ID</span><b class="mono">{{ status?.session_id || '—' }}</b></div>
        <div><span>待总结事件</span><b>{{ status?.pending_count ?? 0 }}</b></div>
        <div><span>会话模式</span><b>{{ sessionModeLabel(policy.session_mode) }}</b></div>
        <div><span>总结阈值</span><b>{{ policy.summary_threshold }} 条</b></div>
      </div>
      <p v-else class="empty-state">先从顶部选择一个游戏作用域。</p>

      <div class="action-row">
        <button class="control-btn" :disabled="!canOperate" @click="checkpoint(false)">
          {{ busy('checkpoint') ? '检查中…' : '按策略检查点' }}
        </button>
        <button class="control-btn emphasized" :disabled="!canOperate" @click="checkpoint(true)">
          {{ busy('force-checkpoint') ? '总结中…' : '立即总结' }}
        </button>
        <button class="control-btn" :disabled="!gameId || !!gameAction" @click="loadContext">
          {{ busy('context') ? '加载中…' : '预览上下文' }}
        </button>
      </div>
    </section>

    <section class="control-card working-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">三层工作记忆</p>
          <h3>当前 Agent 上下文</h3>
        </div>
        <span class="subtle">保存只修改选中的游戏</span>
      </div>
      <div class="layer-grid">
        <label v-for="layer in layers" :key="layer.key" class="layer-editor">
          <span>
            <b>{{ layer.label }}</b>
            <small>{{ retentionLabel(policy.layer_retention[layer.key]) }}</small>
          </span>
          <textarea v-model="layerDrafts[layer.key]" :aria-label="`${layer.label}内容`" rows="7" :disabled="!status?.active"></textarea>
          <button
            class="control-btn layer-save"
            :disabled="!status?.active || !!gameAction || !layerChanged(layer.key)"
            @click="saveLayer(layer.key)"
          >
            {{ busy(`layer-${layer.key}`) ? '保存中…' : `保存${layer.label}` }}
          </button>
        </label>
      </div>
    </section>

    <section class="control-card policy-card">
      <button class="disclosure" :aria-expanded="showSessionForm" @click="showSessionForm = !showSessionForm">
        <span><b>新建游戏会话</b><small>可覆盖当前游戏的记忆策略</small></span>
        <span aria-hidden="true">{{ showSessionForm ? '收起' : '展开' }}</span>
      </button>
      <div v-if="showSessionForm" class="session-form">
        <div class="form-grid">
          <label>外部会话 ID<input v-model.trim="openForm.external_session_id" placeholder="external 模式必填" /></label>
          <label>会话模式
            <select v-model="openForm.policy.session_mode">
              <option value="per_run">每局独立</option>
              <option value="continuous">连续会话</option>
              <option value="external">由 MCP 管理边界</option>
            </select>
          </label>
          <label v-for="layer in layers" :key="`retention-${layer.key}`">{{ layer.label }}跨局策略
            <select v-model="openForm.policy.layer_retention[layer.key]">
              <option value="reset">新局清空</option>
              <option value="carry">跨局保留</option>
            </select>
          </label>
        </div>

        <details>
          <summary>高级策略</summary>
          <div class="form-grid advanced-grid">
            <label>事件总结阈值<input v-model.number="openForm.policy.summary_threshold" type="number" min="1" /></label>
            <label>空闲总结秒数<input v-model.number="openForm.policy.idle_summary_seconds" type="number" min="1" /></label>
            <label>上下文字符预算<input v-model.number="openForm.policy.context_max_chars" type="number" min="1000" step="500" /></label>
            <label class="check-label"><input v-model="openForm.policy.flush_on_session_end" type="checkbox" />结束会话时强制总结</label>
            <label class="check-label"><input v-model="openForm.policy.capture_action_results" type="checkbox" />记录 MCP 动作结果</label>
            <label class="check-label"><input v-model="openForm.policy.capture_query_results" type="checkbox" />记录 MCP 查询结果</label>
            <label class="check-label"><input v-model="openForm.policy.durable_memory_enabled" type="checkbox" />允许提炼长期知识</label>
          </div>
        </details>

        <p v-if="openForm.policy.session_mode === 'external' && !openForm.external_session_id" class="form-warning">
          external 模式需要 MCP 提供稳定的外部会话 ID。
        </p>
        <button class="control-btn emphasized" :disabled="!canOpen" @click="openSession">
          {{ busy('open') ? '创建中…' : '创建并切换会话' }}
        </button>
      </div>
    </section>

    <section v-if="session?.pending_events.length" class="control-card events-card">
      <div class="section-head">
        <div><p class="eyebrow">未总结事件</p><h3>当前批次 MCP 事件</h3></div>
        <span class="subtle">{{ session.pending_events.length }} 条</span>
      </div>
      <div class="event-list">
        <article v-for="event in session.pending_events" :key="event.event_id">
          <div><b>#{{ event.event_id }} · {{ event.event_type }}</b><time>{{ formatTime(event.created_at) }}</time></div>
          <p>{{ event.content }}</p>
        </article>
      </div>
    </section>

    <section v-if="gameContext" class="control-card context-card">
      <div class="section-head">
        <div><p class="eyebrow">上下文预览</p><h3>实际可注入内容</h3></div>
        <button class="text-btn" @click="store.gameContext = null">关闭</button>
      </div>
      <div class="context-grid">
        <div><span>召回原子</span><b>{{ gameContext.recalled_atoms.length }}</b></div>
        <div><span>图谱事实</span><b>{{ gameContext.graph_facts.length }}</b></div>
        <div><span>待处理事件</span><b>{{ gameContext.pending_events.length }}</b></div>
      </div>
      <pre>{{ JSON.stringify(gameContext, null, 2) }}</pre>
    </section>

    <section v-if="status?.active" class="control-card danger-zone">
      <div>
        <h3>结束当前会话</h3>
        <p>按策略总结剩余事件并关闭会话；此操作不会删除已有记忆。</p>
      </div>
      <button class="control-btn danger" :disabled="!!gameAction" @click="closeSession">
        {{ busy('close') ? '关闭中…' : '结束会话' }}
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMemoryStore } from '@/stores/memory'
import type { GameLayerName, GameMemoryPolicy } from '@/types/memory'

const props = defineProps<{ gameId: string }>()
const store = useMemoryStore()
const { gameSessionStatus: status, gameContext, gameAction, session } = storeToRefs(store)
const showSessionForm = ref(false)

const layers: Array<{ key: GameLayerName; label: string }> = [
  { key: 'core', label: '核心记忆' },
  { key: 'important', label: '重要记忆' },
  { key: 'recent', label: '最近记忆' },
]
const fallbackPolicy: GameMemoryPolicy = {
  session_mode: 'per_run',
  layer_retention: { core: 'reset', important: 'reset', recent: 'reset' },
  flush_on_session_end: true,
  summary_threshold: 30,
  idle_summary_seconds: 120,
  context_max_chars: 12000,
  capture_action_results: true,
  capture_query_results: true,
  durable_memory_enabled: true,
}
const policy = computed(() => status.value?.policy || fallbackPolicy)
const layerDrafts = reactive<Record<GameLayerName, string>>({ core: '', important: '', recent: '' })
const openForm = reactive<{ external_session_id: string; policy: GameMemoryPolicy }>({
  external_session_id: '',
  policy: structuredClone(fallbackPolicy),
})
const canOperate = computed(() => !!props.gameId && !!status.value?.active && !gameAction.value)
const canOpen = computed(() => {
  if (!props.gameId || !!gameAction.value) return false
  return openForm.policy.session_mode !== 'external' || !!openForm.external_session_id
})

watch(status, value => {
  layerDrafts.core = value?.core || ''
  layerDrafts.important = value?.important || ''
  layerDrafts.recent = value?.recent || ''
  if (value?.policy) Object.assign(openForm.policy, structuredClone(value.policy))
}, { immediate: true })

watch(() => props.gameId, () => {
  store.gameContext = null
})

function busy(action: string) {
  return gameAction.value === action
}

function layerChanged(layer: GameLayerName) {
  return layerDrafts[layer] !== (status.value?.[layer] || '')
}

async function saveLayer(layer: GameLayerName) {
  await store.updateWorkingMemory(props.gameId, layer, layerDrafts[layer])
}

async function checkpoint(force: boolean) {
  await store.checkpointGameSession(props.gameId, force)
}

async function loadContext() {
  await store.fetchGameContext(props.gameId)
}

async function openSession() {
  if (status.value?.active && !window.confirm(`当前 ${props.gameId} 会话仍在运行。确认按策略结束它并创建新会话？`)) return
  const opened = await store.openGameSession(props.gameId, {
    external_session_id: openForm.external_session_id || null,
    policy: structuredClone(openForm.policy),
  })
  if (opened) {
    showSessionForm.value = false
    await store.fetchSession(props.gameId)
  }
}

async function closeSession() {
  if (!window.confirm(`确认结束 ${props.gameId} 的当前记忆会话？剩余事件会按策略处理。`)) return
  await store.closeGameSession(props.gameId)
}

function sessionModeLabel(mode: GameMemoryPolicy['session_mode']) {
  return { per_run: '每局独立', continuous: '连续', external: 'MCP 外部控制' }[mode]
}

function retentionLabel(value: 'reset' | 'carry') {
  return value === 'carry' ? '跨局保留' : '新局清空'
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleString()
}
</script>

<style scoped>
.game-memory-control { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.control-card { min-width: 0; padding: 16px; border: 1px solid rgba(255,255,255,.09); border-radius: 10px; background: rgba(15,23,42,.62); }
.status-card, .working-card, .events-card, .context-card, .danger-zone { grid-column: 1 / -1; }
.section-head, .action-row, .danger-zone { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { margin: 0; color: #dbeafe; font-size: 14px; }
.eyebrow { margin: 0 0 5px; color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.subtle, small { color: #64748b; font-size: 11px; }
.status-pill { padding: 4px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.status-pill.active { color: #86efac; background: rgba(34,197,94,.14); }
.status-pill.inactive { color: #94a3b8; background: rgba(148,163,184,.12); }
.status-grid, .context-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 14px 0; }
.status-grid div, .context-grid div { display: flex; flex-direction: column; gap: 5px; min-width: 0; padding: 10px; border-radius: 8px; background: rgba(255,255,255,.035); }
.status-grid span, .context-grid span { color: #64748b; font-size: 11px; }
.status-grid b, .context-grid b { overflow: hidden; color: #e2e8f0; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.action-row { justify-content: flex-start; flex-wrap: wrap; }
.control-btn, .text-btn, .disclosure { min-height: 40px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; color: #cbd5e1; background: rgba(255,255,255,.055); cursor: pointer; }
.control-btn { padding: 8px 12px; font-size: 12px; }
.control-btn:hover:not(:disabled) { color: #bfdbfe; border-color: rgba(96,165,250,.45); background: rgba(59,130,246,.16); }
.control-btn.emphasized { color: #dbeafe; background: rgba(37,99,235,.32); }
.control-btn.danger { color: #fecaca; border-color: rgba(239,68,68,.3); background: rgba(239,68,68,.14); }
.control-btn:disabled { opacity: .42; cursor: not-allowed; }
.control-btn:focus-visible, .text-btn:focus-visible, .disclosure:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
.layer-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.layer-editor { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.layer-editor > span { display: flex; align-items: center; justify-content: space-between; color: #cbd5e1; font-size: 12px; }
textarea, input, select { box-sizing: border-box; width: 100%; border: 1px solid rgba(255,255,255,.1); border-radius: 7px; color: #e2e8f0; background: rgba(255,255,255,.055); font: inherit; }
textarea { padding: 9px; resize: vertical; line-height: 1.5; }
input, select { min-height: 38px; padding: 7px 9px; }
.layer-save { align-self: flex-end; }
.disclosure { display: flex; width: 100%; padding: 4px 0; border: 0; align-items: center; justify-content: space-between; text-align: left; background: none; }
.disclosure span:first-child { display: flex; flex-direction: column; gap: 4px; }
.session-form { display: flex; flex-direction: column; gap: 14px; margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.form-grid label { display: flex; flex-direction: column; gap: 6px; color: #94a3b8; font-size: 11px; }
details { color: #94a3b8; font-size: 12px; }
summary { padding: 8px 0; cursor: pointer; }
.advanced-grid { margin-top: 8px; }
.form-grid .check-label { min-height: 38px; flex-direction: row; align-items: center; }
.check-label input { width: 16px; min-height: 16px; }
.form-warning { margin: 0; color: #fbbf24; font-size: 11px; }
.event-list { max-height: 360px; margin-top: 12px; overflow: auto; }
.event-list article { padding: 10px 0; border-top: 1px solid rgba(255,255,255,.07); }
.event-list article div { display: flex; justify-content: space-between; gap: 10px; color: #93c5fd; font-size: 11px; }
.event-list time { color: #64748b; }
.event-list p { margin: 7px 0 0; color: #cbd5e1; font-size: 12px; white-space: pre-wrap; }
.context-grid { grid-template-columns: repeat(3, 1fr); }
pre { max-height: 420px; padding: 12px; overflow: auto; border-radius: 8px; color: #cbd5e1; background: rgba(0,0,0,.25); font-size: 11px; white-space: pre-wrap; }
.text-btn { min-height: 32px; padding: 4px 8px; border: 0; color: #93c5fd; background: none; }
.danger-zone p { margin: 6px 0 0; color: #64748b; font-size: 11px; }
.empty-state { margin: 16px 0; color: #64748b; text-align: center; }
@media (max-width: 900px) {
  .game-memory-control, .layer-grid, .form-grid { grid-template-columns: 1fr; }
  .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .policy-card { grid-column: 1 / -1; }
}
</style>
