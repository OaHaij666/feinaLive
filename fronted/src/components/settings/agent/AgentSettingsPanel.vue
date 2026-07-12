<template>
  <div class="agent-settings">
    <section class="catalog-section" aria-labelledby="game-catalog-heading">
      <div class="section-heading">
        <div><span>运行场景</span><h2 id="game-catalog-heading">选择注册场景</h2></div>
        <button class="refresh-btn" :disabled="loading" @click="loadCatalog">{{ loading ? '加载中…' : '刷新列表' }}</button>
      </div>
      <p class="section-desc">同一进程只绑定一个场景。选择会决定场景指令、能力来源、记忆作用域与配置面板；保存后必须重启整个应用才会生效。</p>
      <p v-if="restartRequired" class="restart-notice" role="status">当前页面配置与进程启动时绑定的场景不同，需要重启整个应用后生效。停止再启动 Agent 不会热切换场景。</p>

      <div v-if="scenarios.length" class="scenario-grid" role="radiogroup" aria-label="注册场景">
        <button
          v-for="scenario in scenarios"
          :key="scenario.scenario_id"
          type="button"
          role="radio"
          :aria-checked="config.scenario_id === scenario.scenario_id"
          :class="['scenario-card', { selected: config.scenario_id === scenario.scenario_id }]"
          @click="selectScenario(scenario)"
        >
          <span class="selection-mark" aria-hidden="true"></span>
          <b>{{ scenario.display_name }}</b>
          <small>{{ scenario.category }}</small>
          <small>{{ scenario.capability_sources.join(' · ') }}</small>
          <p>{{ scenario.description }}</p>
        </button>
      </div>
      <div v-else-if="!loading" class="load-error" role="alert">
        <span>{{ loadError || '后端没有返回已注册游戏。' }}</span>
        <button @click="loadCatalog">重试</button>
      </div>
    </section>

    <CommonAgentSettings
      v-model="config"
      :uses-mcp="selectedDefinition?.capability_sources.includes('mcp') ?? false"
    />

    <section class="specific-section" aria-labelledby="specific-heading">
      <div class="section-heading compact-heading">
        <div><span>场景专属配置</span><h2 id="specific-heading">{{ selectedDefinition?.display_name || config.scenario_id }}</h2></div>
      </div>
      <SlayTheSpireSettings v-if="config.scenario_id === 'slay_the_spire'" v-model="config.scenario_config" />
      <GenericScenarioSettings v-else v-model="config.scenario_config" :definition="selectedDefinition" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { AgentConfig, RegisteredScenarioDefinition, ScenarioCatalogPayload } from '@/types/config'
import CommonAgentSettings from './CommonAgentSettings.vue'
import GenericScenarioSettings from './GenericScenarioSettings.vue'
import SlayTheSpireSettings from './SlayTheSpireSettings.vue'

const config = defineModel<AgentConfig>({ required: true })
const scenarios = ref<RegisteredScenarioDefinition[]>([])
const loading = ref(false)
const loadError = ref('')
const restartRequired = ref(false)
const drafts = new Map<string, Record<string, unknown>>()
const selectedDefinition = computed(() => scenarios.value.find(item => item.scenario_id === config.value.scenario_id) || null)

onMounted(loadCatalog)

async function loadCatalog() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await fetch('/agent/catalog')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json() as ScenarioCatalogPayload
    scenarios.value = data.scenarios || []
    restartRequired.value = Boolean(data.restart_required)
    const selected = scenarios.value.find(item => item.scenario_id === config.value.scenario_id)
    if (selected) initializeFields(selected, false)
  } catch (error) {
    loadError.value = `注册游戏目录加载失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

function selectScenario(scenario: RegisteredScenarioDefinition) {
  if (scenario.scenario_id === config.value.scenario_id) return
  drafts.set(config.value.scenario_id, structuredClone(config.value.scenario_config || {}))
  config.value.scenario_id = scenario.scenario_id
  config.value.scenario_config = structuredClone(drafts.get(scenario.scenario_id) || {})
  initializeFields(scenario, true)
}

function initializeFields(scenario: RegisteredScenarioDefinition, replace: boolean) {
  const current = replace ? {} : (config.value.scenario_config || {})
  const values: Record<string, unknown> = { ...current }
  for (const field of scenario.config_fields) {
    if (values[field.key] === undefined || values[field.key] === null) values[field.key] = structuredClone(field.default)
  }
  config.value.scenario_config = values
}
</script>

<style scoped>
.agent-settings { display: flex; flex-direction: column; gap: 14px; }
.catalog-section, .specific-section { padding: 16px; border: 1px solid rgba(255,255,255,.09); border-radius: 10px; background: rgba(15,23,42,.42); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading span { color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.section-heading h2 { margin: 4px 0 0; color: #dbeafe; font-size: 15px; }
.compact-heading { margin-bottom: 12px; }
.section-desc { margin: 8px 0 14px; color: #94a3b8; font-size: 11px; line-height: 1.6; }
.restart-notice { margin: -4px 0 14px; padding: 10px 12px; border: 1px solid rgba(251,191,36,.28); border-radius: 8px; color: #fde68a; background: rgba(245,158,11,.08); font-size: 11px; line-height: 1.55; }
.refresh-btn, .load-error button { min-height: 40px; padding: 7px 11px; border: 1px solid rgba(255,255,255,.11); border-radius: 8px; color: #bfdbfe; background: rgba(59,130,246,.1); cursor: pointer; }
.refresh-btn:disabled { opacity: .45; cursor: not-allowed; }
.scenario-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.scenario-card { position: relative; min-height: 132px; padding: 14px; border: 1px solid rgba(255,255,255,.1); border-radius: 10px; color: #cbd5e1; text-align: left; background: rgba(255,255,255,.035); cursor: pointer; transition: border-color .18s ease, background-color .18s ease; }
.scenario-card:hover { border-color: rgba(96,165,250,.38); background: rgba(59,130,246,.08); }
.scenario-card.selected { border-color: #60a5fa; background: rgba(37,99,235,.14); box-shadow: inset 0 0 0 1px rgba(96,165,250,.16); }
.selection-mark { position: absolute; top: 14px; right: 14px; width: 12px; height: 12px; border: 2px solid #64748b; border-radius: 50%; }
.selected .selection-mark { border-color: #93c5fd; background: #3b82f6; box-shadow: inset 0 0 0 3px #172033; }
.scenario-card b, .scenario-card small { display: block; padding-right: 24px; }
.scenario-card b { color: #f1f5f9; font-size: 13px; }
.scenario-card small { margin-top: 4px; color: #60a5fa; font: 10px ui-monospace, SFMono-Regular, Consolas, monospace; }
.scenario-card p { margin: 10px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.55; }
.scenario-card:focus-visible, .refresh-btn:focus-visible, .load-error button:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
.load-error { display: flex; min-height: 72px; padding: 12px; align-items: center; justify-content: space-between; gap: 12px; border-radius: 8px; color: #fca5a5; background: rgba(239,68,68,.08); font-size: 11px; }
@media (prefers-reduced-motion: reduce) { .scenario-card { transition: none; } }
</style>
