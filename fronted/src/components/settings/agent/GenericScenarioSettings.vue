<template>
  <section class="specific-card">
    <div class="card-heading">
      <div><span>通用场景面板</span><h3>{{ definition?.display_name || '自定义场景' }}</h3></div>
      <span class="policy-badge">无内置游戏规则</span>
    </div>
    <p class="intro">通用 Profile 只相信 MCP 工具描述和下列映射。可操作字段必须可靠，否则 Agent 会保持等待。</p>
    <div v-if="fields.length" class="field-grid">
      <label v-for="field in fields" :key="field.key" :class="{ wide: field.input_type === 'textarea' }">
        <span>{{ field.label }}<b v-if="field.required" aria-label="必填">*</b></span>
        <textarea v-if="field.input_type === 'textarea'" :value="stringValue(field.key)" rows="6" @input="setText(field.key, $event)" />
        <select v-else-if="field.input_type === 'select'" :value="stringValue(field.key)" @change="setText(field.key, $event)">
          <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <input v-else :type="field.input_type === 'number' ? 'number' : 'text'" :value="stringValue(field.key)" @input="setText(field.key, $event)" />
        <small v-if="field.description">{{ field.description }}</small>
      </label>
    </div>
    <p v-else class="empty-state">该适配器没有额外配置，直接使用上方通用参数。</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RegisteredScenarioDefinition } from '@/types/config'

const props = defineProps<{ definition: RegisteredScenarioDefinition | null }>()
const model = defineModel<Record<string, unknown>>({ required: true })
const fields = computed(() => props.definition?.config_fields || [])

function stringValue(key: string) { return String(model.value[key] ?? '') }
function setText(key: string, event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  model.value[key] = target.value
}
</script>

<style scoped>
.specific-card { padding: 16px; border: 1px solid rgba(167,139,250,.2); border-radius: 10px; background: rgba(76,29,149,.08); }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.card-heading span:first-child { color: #a78bfa; font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
h3 { margin: 4px 0 0; color: #ede9fe; font-size: 14px; }
.policy-badge { padding: 4px 8px; border-radius: 999px; color: #c4b5fd; background: rgba(139,92,246,.14); font-size: 10px; }
.intro { margin: 0 0 14px; color: #94a3b8; font-size: 11px; line-height: 1.6; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
label { display: flex; min-width: 0; flex-direction: column; gap: 6px; color: #cbd5e1; font-size: 12px; }
label.wide { grid-column: 1 / -1; }
label b { margin-left: 3px; color: #fca5a5; }
small { color: #94a3b8; font-size: 10px; line-height: 1.5; }
input, select, textarea { box-sizing: border-box; width: 100%; min-height: 44px; padding: 8px 10px; border: 1px solid rgba(255,255,255,.11); border-radius: 8px; color: #f1f5f9; background: #172033; font: inherit; }
textarea { resize: vertical; line-height: 1.5; }
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid #a78bfa; outline-offset: 2px; }
.empty-state { margin: 0; color: #64748b; text-align: center; }
@media (max-width: 720px) { .field-grid { grid-template-columns: 1fr; } label.wide { grid-column: auto; } }
</style>
