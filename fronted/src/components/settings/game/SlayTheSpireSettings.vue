<template>
  <section class="specific-card">
    <div class="card-heading">
      <div><span>杀戮尖塔专属</span><h3>开局与记忆边界</h3></div>
      <span class="policy-badge">每局清空三层记忆</span>
    </div>
    <label for="spire-character">默认角色</label>
    <select id="spire-character" v-model="defaultCharacter">
      <option value="IRONCLAD">铁甲战士</option>
      <option value="SILENT">猎手</option>
      <option value="DEFECT">机器人</option>
      <option value="WATCHER">观者</option>
    </select>
    <p>用于自动重开或 MCP 未明确指定角色的开局。杀戮尖塔 Profile 会在开局后采集初始牌组和遗物，并写入重要工作记忆。</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const model = defineModel<Record<string, unknown>>({ required: true })
const defaultCharacter = computed({
  get: () => String(model.value.default_character || 'IRONCLAD'),
  set: value => { model.value.default_character = value },
})
</script>

<style scoped>
.specific-card { padding: 16px; border: 1px solid rgba(96,165,250,.22); border-radius: 10px; background: rgba(30,64,175,.08); }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.card-heading span:first-child { color: #60a5fa; font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
h3 { margin: 4px 0 0; color: #dbeafe; font-size: 14px; }
.policy-badge { padding: 4px 8px; border-radius: 999px; color: #93c5fd; background: rgba(59,130,246,.14); font-size: 10px; }
label { display: block; margin-bottom: 6px; color: #cbd5e1; font-size: 12px; }
select { width: 100%; min-height: 44px; padding: 8px 10px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; color: #f1f5f9; background: #172033; }
select:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
p { margin: 8px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.6; }
</style>
