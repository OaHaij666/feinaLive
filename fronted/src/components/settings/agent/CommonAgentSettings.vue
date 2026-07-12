<template>
  <div class="common-settings">
    <section class="settings-card connection-card">
      <div class="card-heading">
        <div><span>通用配置</span><h3>运行与能力连接</h3></div>
        <label class="switch-label">
          <input v-model="config.enabled" type="checkbox" />
          <span>{{ config.enabled ? '允许启动' : '保持停用' }}</span>
        </label>
      </div>
      <template v-if="usesMcp">
        <label class="field-label" for="agent-mcp-url">MCP 服务地址</label>
        <input id="agent-mcp-url" v-model.trim="config.mcp_url" type="url" placeholder="http://127.0.0.1:8080" />
        <p class="field-help">MCP Capability 通过该地址发现工具、读取状态并执行动作。</p>
      </template>
      <p v-else class="field-help">当前场景由事件驱动，不装配 MCP Capability。</p>
    </section>

    <section class="settings-card">
      <div class="card-heading"><div><span>通用配置</span><h3>决策时序</h3></div></div>
      <div class="field-grid">
        <label>状态轮询间隔 <small>秒</small><input v-model.number="config.poll_interval" type="number" min="0.2" max="10" step="0.1" /></label>
        <label>最小操作间隔 <small>秒</small><input v-model.number="config.min_step_interval" type="number" min="1" max="30" step="0.5" /></label>
        <label>操作间隔抖动 <small>秒</small><input v-model.number="config.step_jitter" type="number" min="0" max="5" step="0.1" /></label>
        <label>解说建议间隔 <small>秒</small><input v-model.number="config.commentary_interval" type="number" min="5" max="300" /></label>
        <label>解说硬间隔 <small>秒</small><input v-model.number="config.min_commentary_interval" type="number" min="5" max="120" /></label>
        <label>解说消费超时 <small>秒</small><input v-model.number="config.commentary_hold_timeout" type="number" min="5" max="60" /></label>
      </div>
    </section>

    <section class="settings-card wide-card">
      <div class="card-heading"><div><span>通用配置</span><h3>记忆与上下文预算</h3></div></div>
      <div class="field-grid four-columns">
        <label>总结阈值 <small>事件条数</small><input v-model.number="config.memory_threshold" type="number" min="1" max="200" /></label>
        <label>空闲总结 <small>秒</small><input v-model.number="config.memory_idle_seconds" type="number" min="10" max="3600" /></label>
        <label>空闲扫描 <small>秒</small><input v-model.number="config.memory_scan_interval_seconds" type="number" min="5" max="600" /></label>
        <label>事件上下文预算 <small>字符</small><input v-model.number="config.memory_context_max_chars" type="number" min="1000" max="50000" step="1000" /></label>
        <label>长期知识积极度 <small>1 保守—5 积极</small><input v-model.number="config.memory_eagerness" type="number" min="1" max="5" /></label>
        <label>队列最大长度 <small>条</small><input v-model.number="config.queue_max_size" type="number" min="5" max="100" /></label>
        <label>主播历史 <small>条</small><input v-model.number="config.host_history_maxlen" type="number" min="10" max="200" /></label>
        <label>动作历史 <small>条</small><input v-model.number="config.action_history_maxlen" type="number" min="10" max="200" /></label>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { AgentConfig } from '@/types/config'
defineProps<{ usesMcp: boolean }>()
const config = defineModel<AgentConfig>({ required: true })
</script>

<style scoped>
.common-settings { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.settings-card { min-width: 0; padding: 16px; border: 1px solid rgba(255,255,255,.09); border-radius: 10px; background: rgba(15,23,42,.52); }
.connection-card, .wide-card { grid-column: 1 / -1; }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.card-heading span { color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.card-heading h3 { margin: 4px 0 0; color: #dbeafe; font-size: 14px; }
.switch-label { display: flex; min-height: 44px; align-items: center; gap: 8px; color: #cbd5e1; font-size: 12px; cursor: pointer; }
.switch-label input { width: 17px; height: 17px; accent-color: #3b82f6; }
.field-label { display: block; margin-bottom: 6px; color: #cbd5e1; font-size: 12px; }
.field-help { margin: 6px 0 0; color: #94a3b8; font-size: 11px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.field-grid.four-columns { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.field-grid label { display: flex; min-width: 0; flex-direction: column; gap: 6px; color: #cbd5e1; font-size: 12px; }
.field-grid small { color: #94a3b8; font-size: 10px; font-weight: 400; }
input[type='url'], input[type='number'] { box-sizing: border-box; width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid rgba(255,255,255,.11); border-radius: 8px; color: #f1f5f9; background: rgba(255,255,255,.055); }
input:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
@media (max-width: 900px) { .common-settings, .field-grid, .field-grid.four-columns { grid-template-columns: 1fr; } }
</style>
