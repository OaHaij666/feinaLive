<template>
  <section class="music-console" aria-labelledby="music-runtime-title">
    <div class="music-heading">
      <div>
        <span class="eyebrow">MUSIC RUNTIME</span>
        <h3 id="music-runtime-title">曲库与播放队列</h3>
        <p>从已注册 Provider 搜索、点播并管理可信曲库。Bilibili 新内容入库时会经过审核。</p>
      </div>
      <button class="mini-btn" :disabled="loading" @click="refreshAll">刷新数据</button>
    </div>

    <div class="now-playing">
      <div class="cover-placeholder" aria-hidden="true">♪</div>
      <div class="track-copy">
        <span>{{ state.current ? '正在播放' : '当前空闲' }}</span>
        <strong>{{ state.current?.track.title || '等待下一首歌' }}</strong>
        <small v-if="state.current">{{ artistText(state.current.track) }} · {{ state.current.track.provider }}</small>
        <small v-else>队列中有 {{ state.queue.length }} 首待播歌曲</small>
      </div>
      <div class="runtime-actions">
        <button class="mini-btn" @click="musicStore.togglePlay">{{ state.paused ? '继续' : '暂停' }}</button>
        <button class="mini-btn danger" :disabled="!state.current" @click="musicStore.skipCurrent()">切歌</button>
      </div>
    </div>

    <div v-if="state.queue.length" class="queue-strip" aria-label="待播队列">
      <div v-for="(entry, index) in state.queue" :key="entry.id" class="queue-row">
        <span class="queue-index">{{ index + 1 }}</span>
        <div><strong>{{ entry.track.title }}</strong><small>{{ artistText(entry.track) }} · {{ entry.requested_by }}</small></div>
        <button class="icon-btn" :aria-label="`从队列移除 ${entry.track.title}`" @click="musicStore.removeFromQueue(entry.id)">×</button>
      </div>
    </div>

    <div class="workspace-tabs" role="tablist" aria-label="音乐管理视图">
      <button v-for="view in views" :key="view.key" :class="{ active: activeView === view.key }" role="tab" :aria-selected="activeView === view.key" @click="activeView = view.key">{{ view.label }}</button>
    </div>

    <div v-if="activeView === 'search'" class="music-workspace">
      <div class="search-bar">
        <select v-model="provider" aria-label="音乐 Provider">
          <option v-for="item in providers" :key="item" :value="item">{{ item }}</option>
        </select>
        <input v-model.trim="query" type="search" placeholder="搜索歌名、歌手或 BV 号" @keyup.enter="search" />
        <button class="primary-btn" :disabled="loading || !provider" @click="search">搜索</button>
      </div>
      <p v-if="provider === 'bilibili'" class="notice">Bilibili 是视频平台：未进入可信曲库的内容，在入库或点播时仍会走规则与 LLM 审核。</p>
      <div v-if="searchResults.length" class="result-list">
        <article v-for="item in searchResults" :key="`${provider}:${item.source_id}`" class="result-card">
          <img v-if="item.cover_url" :src="item.cover_url" alt="" loading="lazy" />
          <div><strong>{{ item.title }}</strong><small>{{ item.artist || '未知艺术家' }} · {{ durationText(item.duration_seconds) }}</small></div>
          <div class="result-actions">
            <button class="mini-btn" @click="requestTrack(item)">加入队列</button>
            <button class="mini-btn" @click="admitTrack(item)">加入可信曲库</button>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">{{ searched ? '没有找到匹配内容' : '输入关键词后从指定 Provider 搜索' }}</div>
    </div>

    <div v-else-if="activeView === 'library'" class="music-workspace">
      <div v-if="library.length" class="result-list">
        <article v-for="track in library" :key="track.id" class="result-card">
          <img v-if="track.cover_url" :src="track.cover_url" alt="" loading="lazy" />
          <div><strong>{{ track.title }}</strong><small>{{ artistText(track) }} · {{ track.provider }} · {{ durationText(track.duration_seconds) }}</small></div>
          <div class="result-actions">
            <button class="mini-btn" @click="requestLibraryTrack(track)">播放</button>
            <button class="mini-btn danger" @click="disableTrack(track)">移出曲库</button>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">可信曲库为空</div>
    </div>

    <div v-else class="music-workspace">
      <div v-if="history.length" class="history-list">
        <div v-for="entry in history" :key="entry.id" class="history-row">
          <span :class="['status-chip', entry.status]">{{ statusText(entry.status) }}</span>
          <div><strong>{{ entry.track.title }}</strong><small>{{ artistText(entry.track) }} · {{ formatTime(entry.finished_at || entry.requested_at) }}</small></div>
          <span>{{ entry.requested_by }}</span>
        </div>
      </div>
      <div v-else class="empty-state">暂无播放历史</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMusicStore } from '@/features/music/store'
import type { MusicRequestResult, ProviderSearchResult, QueueEntry, QueueEntryStatus, Track } from '@/features/music/types'
import { useNotification } from '@/utils/notification'

const views = [
  { key: 'search', label: 'Provider 搜索' },
  { key: 'library', label: '可信曲库' },
  { key: 'history', label: '播放历史' },
] as const

const musicStore = useMusicStore()
const { state } = storeToRefs(musicStore)
const notification = useNotification()
const activeView = ref<(typeof views)[number]['key']>('search')
const providers = ref<string[]>([])
const provider = ref('')
const query = ref('')
const searchResults = ref<ProviderSearchResult[]>([])
const library = ref<Track[]>([])
const history = ref<QueueEntry[]>([])
const loading = ref(false)
const searched = ref(false)

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/music${path}`, init)
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail?.message || payload?.detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function refreshAll() {
  loading.value = true
  try {
    const [providerData, libraryData, historyData] = await Promise.all([
      api<{ providers: string[] }>('/providers'),
      api<{ items: Track[] }>('/library'),
      api<{ items: QueueEntry[] }>('/history?limit=50'),
      musicStore.fetchState(),
    ])
    providers.value = providerData.providers
    if (!providers.value.includes(provider.value)) provider.value = providers.value[0] || ''
    library.value = libraryData.items
    history.value = historyData.items
  } catch (error) {
    notification.error(`音乐数据加载失败：${messageOf(error)}`)
  } finally {
    loading.value = false
  }
}

async function search() {
  if (!provider.value) return
  loading.value = true
  searched.value = true
  try {
    const data = await api<{ items: ProviderSearchResult[] }>(`/providers/${encodeURIComponent(provider.value)}/search?query=${encodeURIComponent(query.value)}&limit=20`)
    searchResults.value = data.items
  } catch (error) {
    notification.error(`搜索失败：${messageOf(error)}`)
  } finally {
    loading.value = false
  }
}

async function requestTrack(item: ProviderSearchResult) {
  await submitRequest(item.title, provider.value, item.source_id)
}

async function requestLibraryTrack(track: Track) {
  await submitRequest(track.title, track.provider, track.source_id)
}

async function submitRequest(requestQuery: string, requestProvider: string, sourceId: string) {
  try {
    const result = await api<MusicRequestResult>('/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: requestQuery, provider: requestProvider, source_id: sourceId, requested_by: 'console' }),
    })
    if (!result.accepted) throw new Error(result.error || result.classification?.reason || '点歌未通过')
    await musicStore.fetchState()
    notification.success(`已加入队列：${result.entry?.track.title || requestQuery}`)
  } catch (error) {
    notification.error(`点歌失败：${messageOf(error)}`)
  }
}

async function admitTrack(item: ProviderSearchResult) {
  try {
    const track = await api<Track>('/library', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider.value, source_id: item.source_id }),
    })
    notification.success(`已加入可信曲库：${track.title}`)
    await refreshAll()
  } catch (error) {
    notification.error(`入库失败：${messageOf(error)}`)
  }
}

async function disableTrack(track: Track) {
  try {
    await api(`/library/${encodeURIComponent(track.id)}?enabled=false`, { method: 'PATCH' })
    library.value = library.value.filter(item => item.id !== track.id)
    notification.success(`已移出可信曲库：${track.title}`)
  } catch (error) {
    notification.error(`移出失败：${messageOf(error)}`)
  }
}

function artistText(track: Track) {
  return track.artists.length ? track.artists.join(' / ') : '未知艺术家'
}

function durationText(seconds: number) {
  if (!seconds) return '时长未知'
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function statusText(status: QueueEntryStatus) {
  return ({ completed: '已播放', skipped: '已跳过', failed: '失败', rejected: '拒绝', cancelled: '取消', pending: '等待', playing: '播放中', paused: '暂停' } as Record<QueueEntryStatus, string>)[status]
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

onMounted(refreshAll)
</script>

<style scoped>
.music-console { margin-bottom: 30px; padding: 20px; border: 1px solid #283248; border-radius: 18px; background: linear-gradient(145deg, rgba(24,31,49,.95), rgba(13,18,31,.95)); }
.music-heading, .now-playing, .search-bar, .result-card, .history-row, .queue-row { display: flex; align-items: center; }
.music-heading { justify-content: space-between; gap: 20px; }
.music-heading h3 { margin: 3px 0 5px; font-size: 20px; color: #f8fafc; }
.music-heading p { margin: 0; color: #94a3b8; font-size: 13px; }
.eyebrow { color: #c4b5fd; font-size: 10px; font-weight: 800; letter-spacing: .16em; }
.now-playing { gap: 14px; margin-top: 18px; padding: 14px; border: 1px solid #343e57; border-radius: 14px; background: rgba(9,13,23,.68); }
.cover-placeholder { display: grid; flex: 0 0 48px; height: 48px; place-items: center; border-radius: 12px; color: #fff; font-size: 22px; background: linear-gradient(135deg, #7c3aed, #db2777); }
.track-copy, .result-card > div:nth-child(2), .history-row > div, .queue-row > div { display: grid; flex: 1; min-width: 0; gap: 3px; }
.track-copy span, small { color: #94a3b8; font-size: 11px; }
.track-copy strong, .result-card strong, .history-row strong, .queue-row strong { overflow: hidden; color: #f1f5f9; text-overflow: ellipsis; white-space: nowrap; }
.runtime-actions, .result-actions { display: flex; gap: 8px; }
.mini-btn, .primary-btn, .icon-btn, .workspace-tabs button { min-height: 40px; border: 1px solid #3b4761; border-radius: 10px; color: #dbe4f3; background: #1b2436; cursor: pointer; }
.mini-btn { padding: 0 13px; }
.mini-btn:hover, .workspace-tabs button:hover { border-color: #7c3aed; }
.mini-btn.danger { color: #fda4af; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid #a78bfa; outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .45; }
.queue-strip { display: grid; gap: 6px; margin-top: 10px; }
.queue-row { gap: 10px; padding: 8px 12px; border-radius: 10px; background: rgba(15,23,42,.6); }
.queue-index { color: #a78bfa; font-variant-numeric: tabular-nums; }
.icon-btn { width: 40px; padding: 0; font-size: 20px; background: transparent; }
.workspace-tabs { display: flex; gap: 8px; margin: 20px 0 12px; border-bottom: 1px solid #2b354a; }
.workspace-tabs button { padding: 0 14px; border-color: transparent; border-radius: 9px 9px 0 0; background: transparent; }
.workspace-tabs button.active { border-color: #4c3b78; color: #ddd6fe; background: rgba(124,58,237,.14); }
.music-workspace { min-height: 124px; }
.search-bar { gap: 8px; }
.search-bar select { flex: 0 0 150px; }
.search-bar input { flex: 1; }
.search-bar input, .search-bar select { min-height: 44px; border: 1px solid #364158; border-radius: 10px; padding: 0 12px; color: #eef2ff; background: #0d1320; }
.primary-btn { padding: 0 20px; border-color: #7c3aed; color: white; background: #7c3aed; }
.notice { margin: 10px 0; padding: 10px 12px; border-left: 3px solid #f59e0b; color: #cbd5e1; font-size: 12px; background: rgba(245,158,11,.07); }
.result-list, .history-list { display: grid; gap: 8px; margin-top: 12px; }
.result-card { gap: 12px; min-height: 64px; padding: 10px 12px; border: 1px solid #2d374d; border-radius: 12px; background: rgba(11,16,28,.7); }
.result-card img { width: 46px; height: 46px; border-radius: 9px; object-fit: cover; }
.history-row { gap: 12px; padding: 10px 4px; border-bottom: 1px solid #293247; }
.history-row > span:last-child { color: #94a3b8; font-size: 12px; }
.status-chip { min-width: 55px; border-radius: 999px; padding: 4px 8px; color: #cbd5e1; font-size: 10px; text-align: center; background: #273248; }
.status-chip.completed { color: #86efac; background: rgba(34,197,94,.12); }
.status-chip.failed, .status-chip.rejected { color: #fda4af; background: rgba(244,63,94,.12); }
.empty-state { display: grid; min-height: 120px; place-items: center; color: #64748b; font-size: 13px; }
@media (max-width: 700px) {
  .music-console { padding: 14px; }
  .music-heading, .now-playing, .search-bar, .result-card { align-items: stretch; flex-direction: column; }
  .runtime-actions, .result-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .search-bar select { flex-basis: auto; }
  .workspace-tabs { overflow-x: auto; }
  .workspace-tabs button { flex: 0 0 auto; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; transition: none !important; } }
</style>
