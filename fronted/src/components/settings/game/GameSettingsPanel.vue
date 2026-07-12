<template>
  <div class="game-settings">
    <section class="catalog-section" aria-labelledby="game-catalog-heading">
      <div class="section-heading">
        <div><span>游戏上下文</span><h2 id="game-catalog-heading">选择注册游戏</h2></div>
        <button class="refresh-btn" :disabled="loading" @click="loadCatalog">{{ loading ? '加载中…' : '刷新列表' }}</button>
      </div>
      <p class="section-desc">同一时间只运行一个游戏。选择决定 GameProfile、专属提示词、开局逻辑和配置面板；保存后停止并重新启动游戏集成生效。</p>

      <div v-if="games.length" class="game-grid" role="radiogroup" aria-label="注册游戏">
        <button
          v-for="game in games"
          :key="game.game_id"
          type="button"
          role="radio"
          :aria-checked="config.game_id === game.game_id"
          :class="['game-card', { selected: config.game_id === game.game_id }]"
          @click="selectGame(game)"
        >
          <span class="selection-mark" aria-hidden="true"></span>
          <b>{{ game.display_name }}</b>
          <small>{{ game.game_type }}</small>
          <p>{{ game.description }}</p>
        </button>
      </div>
      <div v-else-if="!loading" class="load-error" role="alert">
        <span>{{ loadError || '后端没有返回已注册游戏。' }}</span>
        <button @click="loadCatalog">重试</button>
      </div>
    </section>

    <CommonGameSettings v-model="config" />

    <section class="specific-section" aria-labelledby="specific-heading">
      <div class="section-heading compact-heading">
        <div><span>游戏专属配置</span><h2 id="specific-heading">{{ selectedDefinition?.display_name || config.game_id }}</h2></div>
      </div>
      <SlayTheSpireSettings v-if="config.game_id === 'slay_the_spire'" v-model="config.game_config" />
      <GenericGameSettings v-else v-model="config.game_config" :definition="selectedDefinition" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { GameCatalogPayload, GameConfig, RegisteredGameDefinition } from '@/types/config'
import CommonGameSettings from './CommonGameSettings.vue'
import GenericGameSettings from './GenericGameSettings.vue'
import SlayTheSpireSettings from './SlayTheSpireSettings.vue'

const config = defineModel<GameConfig>({ required: true })
const games = ref<RegisteredGameDefinition[]>([])
const loading = ref(false)
const loadError = ref('')
const drafts = new Map<string, Record<string, unknown>>()
const selectedDefinition = computed(() => games.value.find(item => item.game_id === config.value.game_id) || null)

onMounted(loadCatalog)

async function loadCatalog() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await fetch('/game/catalog')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json() as GameCatalogPayload
    games.value = data.games || []
    const selected = games.value.find(item => item.game_id === config.value.game_id)
    if (selected) initializeFields(selected, false)
  } catch (error) {
    loadError.value = `注册游戏目录加载失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

function selectGame(game: RegisteredGameDefinition) {
  if (game.game_id === config.value.game_id) return
  drafts.set(config.value.game_id, structuredClone(config.value.game_config || {}))
  config.value.game_id = game.game_id
  config.value.game_config = structuredClone(drafts.get(game.game_id) || {})
  initializeFields(game, true)
}

function initializeFields(game: RegisteredGameDefinition, replace: boolean) {
  const current = replace ? {} : (config.value.game_config || {})
  const values: Record<string, unknown> = { ...current }
  for (const field of game.config_fields) {
    if (values[field.key] === undefined || values[field.key] === null) values[field.key] = structuredClone(field.default)
  }
  config.value.game_config = values
}
</script>

<style scoped>
.game-settings { display: flex; flex-direction: column; gap: 14px; }
.catalog-section, .specific-section { padding: 16px; border: 1px solid rgba(255,255,255,.09); border-radius: 10px; background: rgba(15,23,42,.42); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading span { color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.section-heading h2 { margin: 4px 0 0; color: #dbeafe; font-size: 15px; }
.compact-heading { margin-bottom: 12px; }
.section-desc { margin: 8px 0 14px; color: #94a3b8; font-size: 11px; line-height: 1.6; }
.refresh-btn, .load-error button { min-height: 40px; padding: 7px 11px; border: 1px solid rgba(255,255,255,.11); border-radius: 8px; color: #bfdbfe; background: rgba(59,130,246,.1); cursor: pointer; }
.refresh-btn:disabled { opacity: .45; cursor: not-allowed; }
.game-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.game-card { position: relative; min-height: 132px; padding: 14px; border: 1px solid rgba(255,255,255,.1); border-radius: 10px; color: #cbd5e1; text-align: left; background: rgba(255,255,255,.035); cursor: pointer; transition: border-color .18s ease, background-color .18s ease; }
.game-card:hover { border-color: rgba(96,165,250,.38); background: rgba(59,130,246,.08); }
.game-card.selected { border-color: #60a5fa; background: rgba(37,99,235,.14); box-shadow: inset 0 0 0 1px rgba(96,165,250,.16); }
.selection-mark { position: absolute; top: 14px; right: 14px; width: 12px; height: 12px; border: 2px solid #64748b; border-radius: 50%; }
.selected .selection-mark { border-color: #93c5fd; background: #3b82f6; box-shadow: inset 0 0 0 3px #172033; }
.game-card b, .game-card small { display: block; padding-right: 24px; }
.game-card b { color: #f1f5f9; font-size: 13px; }
.game-card small { margin-top: 4px; color: #60a5fa; font: 10px ui-monospace, SFMono-Regular, Consolas, monospace; }
.game-card p { margin: 10px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.55; }
.game-card:focus-visible, .refresh-btn:focus-visible, .load-error button:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
.load-error { display: flex; min-height: 72px; padding: 12px; align-items: center; justify-content: space-between; gap: 12px; border-radius: 8px; color: #fca5a5; background: rgba(239,68,68,.08); font-size: 11px; }
@media (prefers-reduced-motion: reduce) { .game-card { transition: none; } }
</style>
