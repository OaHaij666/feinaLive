<template>
  <section class="agent-runtime" aria-labelledby="agent-runtime-heading">
    <div class="runtime-heading">
      <div><span>AGENT RUNTIME</span><h2 id="agent-runtime-heading">运行态与共享上下文</h2></div>
      <div class="heading-actions">
        <button :disabled="busy" @click="toggleQueue">{{ queue.muted ? '恢复消费队列' : '静音消费队列' }}</button>
        <button :disabled="busy" @click="refresh">刷新</button>
      </div>
    </div>

    <div class="runtime-metrics">
      <article><span :class="['dot', status.running ? 'ok' : 'idle']"></span><div><small>Agent</small><strong>{{ status.runtime_status || 'unknown' }}</strong></div></article>
      <article><span :class="['dot', health.healthy ? 'ok' : 'bad']"></span><div><small>场景能力</small><strong>{{ health.healthy ? '可用' : '不可用' }}</strong></div></article>
      <article><span :class="['dot', queue.muted ? 'bad' : 'ok']"></span><div><small>全局消费队列</small><strong>{{ queue.muted ? '已静音' : `${queue.size || 0} 条等待` }}</strong></div></article>
      <article><span :class="['dot', status.restart_required ? 'warn' : 'ok']"></span><div><small>配置状态</small><strong>{{ status.restart_required ? '需要重启' : '已装配' }}</strong></div></article>
    </div>

    <details class="context-view">
      <summary>HostRuntime ↔ AgentRuntime 轻量共享上下文 <span>{{ context.length }} 条</span></summary>
      <div v-if="context.length" class="context-list">
        <div v-for="(item, index) in context" :key="`${item.created_at}:${index}`">
          <span>{{ item.actor }} / {{ item.kind }}</span>
          <p>{{ item.summary }}</p>
        </div>
      </div>
      <p v-else class="context-empty">暂无最近十分钟的共享动态</p>
    </details>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useNotification } from '@/utils/notification'

interface MutualContextEntry { actor: string; kind: string; summary: string; created_at: number }

const notification = useNotification()
const busy = ref(false)
const status = reactive<Record<string, any>>({ running: false, runtime_status: 'unknown', restart_required: false })
const health = reactive<Record<string, any>>({ healthy: false })
const queue = reactive<Record<string, any>>({ size: 0, muted: false })
const context = ref<MutualContextEntry[]>([])

async function read<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

async function refresh() {
  busy.value = true
  try {
    const [statusData, healthData, contextData] = await Promise.all([
      read<Record<string, any>>('/agent/status'),
      read<Record<string, any>>('/agent/health'),
      read<{ mutual_context: MutualContextEntry[] }>('/agent/context'),
    ])
    Object.assign(status, statusData)
    Object.assign(health, healthData)
    Object.assign(queue, statusData.queue || {})
    context.value = contextData.mutual_context || []
  } catch (error) {
    notification.error(`Agent 运行态读取失败：${error instanceof Error ? error.message : String(error)}`)
  } finally {
    busy.value = false
  }
}

async function toggleQueue() {
  busy.value = true
  try {
    const response = await fetch(queue.muted ? '/agent/unmute' : '/agent/mute', { method: 'POST' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    queue.muted = !queue.muted
    notification.success(queue.muted ? '消费队列已静音' : '消费队列已恢复')
  } catch (error) {
    notification.error(`队列操作失败：${error instanceof Error ? error.message : String(error)}`)
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.agent-runtime { padding: 16px; border: 1px solid rgba(167,139,250,.2); border-radius: 12px; background: linear-gradient(135deg, rgba(76,29,149,.1), rgba(15,23,42,.55)); }
.runtime-heading, .heading-actions, .runtime-metrics article { display: flex; align-items: center; }
.runtime-heading { justify-content: space-between; gap: 12px; }
.runtime-heading span { color: #a78bfa; font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.runtime-heading h2 { margin: 4px 0 0; color: #f1f5f9; font-size: 15px; }
.heading-actions { gap: 8px; }
button { min-height: 40px; padding: 0 12px; border: 1px solid #3c4962; border-radius: 8px; color: #dbeafe; background: #192235; cursor: pointer; }
button:hover { border-color: #8b5cf6; }
button:focus-visible, summary:focus-visible { outline: 2px solid #a78bfa; outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .45; }
.runtime-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 14px; }
.runtime-metrics article { gap: 9px; min-width: 0; padding: 11px; border: 1px solid rgba(255,255,255,.07); border-radius: 9px; background: rgba(7,11,21,.5); }
.runtime-metrics article div { display: grid; min-width: 0; gap: 2px; }
.runtime-metrics small { color: #64748b; font-size: 10px; }
.runtime-metrics strong { overflow: hidden; color: #e2e8f0; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.dot { flex: 0 0 8px; height: 8px; border-radius: 50%; background: #64748b; box-shadow: 0 0 0 4px rgba(100,116,139,.1); }
.dot.ok { background: #22c55e; box-shadow: 0 0 0 4px rgba(34,197,94,.1); }
.dot.bad { background: #f43f5e; box-shadow: 0 0 0 4px rgba(244,63,94,.1); }
.dot.warn { background: #f59e0b; box-shadow: 0 0 0 4px rgba(245,158,11,.1); }
.context-view { margin-top: 12px; border-top: 1px solid rgba(255,255,255,.07); }
.context-view summary { padding: 12px 2px 0; color: #cbd5e1; font-size: 11px; cursor: pointer; }
.context-view summary span { color: #64748b; }
.context-list { display: grid; gap: 7px; margin-top: 10px; }
.context-list > div { padding: 9px 11px; border-left: 2px solid #7c3aed; background: rgba(15,23,42,.5); }
.context-list span { color: #a78bfa; font-size: 9px; text-transform: uppercase; }
.context-list p, .context-empty { margin: 4px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.55; }
@media (max-width: 800px) { .runtime-metrics { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .runtime-heading { align-items: stretch; flex-direction: column; } .heading-actions { display: grid; grid-template-columns: 1fr 1fr; } .runtime-metrics { grid-template-columns: 1fr; } }
</style>
