import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { MusicState, QueueEntry } from './types'
import { useNotification } from '@/utils/notification'

const API_BASE = '/music'
const HEARTBEAT_INTERVAL_MS = 10_000

let audioElement: HTMLAudioElement | null = null

function getAudioElement(): HTMLAudioElement {
  if (!audioElement) {
    audioElement = new Audio()
    audioElement.preload = 'auto'
  }
  return audioElement
}

function getPlayerId(): string {
  const existing = sessionStorage.getItem('music_player_id')
  if (existing) return existing
  const value = crypto.randomUUID()
  sessionStorage.setItem('music_player_id', value)
  return value
}

export const useMusicStore = defineStore('music', () => {
  const notification = useNotification()
  const state = ref<MusicState>({
    revision: 0,
    current: null,
    queue: [],
    paused: false,
    volume: 1,
    ducking_factor: 1,
    effective_volume: 1,
    playback_owner_id: null,
  })
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const audioUnlocked = ref(false)
  const isPlaybackOwner = ref(false)
  const playerId = getPlayerId()
  const audio = getAudioElement()
  let heartbeatTimer: number | null = null
  let loadedEntryId: string | null = null
  let reportingFailure = false

  const current = computed(() => state.value.current)
  const queue = computed(() => state.value.queue)

  function applyState(next: MusicState) {
    if (next.revision < state.value.revision) return
    state.value = next
  }

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, init)
    if (!response.ok) {
      let detail = `HTTP ${response.status}`
      try {
        const payload = await response.json()
        detail = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || detail
      } catch {
        // Keep HTTP fallback.
      }
      throw new Error(detail)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  async function fetchState() {
    try {
      applyState(await request<MusicState>('/state'))
    } catch (cause) {
      notification.error(`无法获取音乐状态: ${String(cause)}`)
    }
  }

  async function claimPlayback(): Promise<boolean> {
    const result = await request<{ claimed: boolean }>('/player/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: playerId }),
    })
    isPlaybackOwner.value = result.claimed
    if (result.claimed && heartbeatTimer === null) {
      heartbeatTimer = window.setInterval(() => void heartbeat(), HEARTBEAT_INTERVAL_MS)
    }
    return result.claimed
  }

  async function heartbeat() {
    try {
      const result = await request<{ active: boolean }>('/player/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_id: playerId }),
      })
      isPlaybackOwner.value = result.active
      if (!result.active) stopAudio()
    } catch {
      isPlaybackOwner.value = false
      stopAudio()
    }
  }

  async function reportPlaybackEvent(
    entry: QueueEntry,
    event: 'started' | 'ended' | 'failed',
    reason = '',
  ) {
    if (!isPlaybackOwner.value) return
    try {
      const next = await request<MusicState>('/playback/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: playerId,
          entry_id: entry.id,
          event,
          reason,
        }),
      })
      applyState(next)
    } catch (cause) {
      if (event !== 'failed') notification.error(`音乐播放状态同步失败: ${String(cause)}`)
    }
  }

  function stopAudio() {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    loadedEntryId = null
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
  }

  async function synchronizePlayer(entry: QueueEntry | null) {
    if (!audioUnlocked.value || !isPlaybackOwner.value) return
    if (!entry) {
      stopAudio()
      return
    }
    if (loadedEntryId !== entry.id) {
      loadedEntryId = entry.id
      reportingFailure = false
      audio.src = `${API_BASE}/stream/${encodeURIComponent(entry.id)}?player_id=${encodeURIComponent(playerId)}`
      audio.load()
    }
    audio.volume = state.value.effective_volume
    if (state.value.paused) {
      audio.pause()
      return
    }
    try {
      await audio.play()
    } catch (cause) {
      if ((cause as DOMException)?.name !== 'AbortError') {
        notification.error(`音乐播放失败: ${String(cause)}`)
      }
    }
  }

  watch(
    () => [state.value.current?.id, state.value.paused, state.value.effective_volume] as const,
    () => void synchronizePlayer(state.value.current),
  )

  audio.addEventListener('timeupdate', () => {
    currentTime.value = audio.currentTime
  })
  audio.addEventListener('loadedmetadata', () => {
    duration.value = Number.isFinite(audio.duration) ? audio.duration : 0
  })
  audio.addEventListener('play', () => {
    isPlaying.value = true
    const entry = state.value.current
    if (entry) void reportPlaybackEvent(entry, 'started')
  })
  audio.addEventListener('pause', () => {
    isPlaying.value = false
  })
  audio.addEventListener('ended', () => {
    isPlaying.value = false
    const entry = state.value.current
    if (entry) void reportPlaybackEvent(entry, 'ended')
  })
  audio.addEventListener('error', () => {
    const entry = state.value.current
    if (!entry || reportingFailure || !audio.src) return
    reportingFailure = true
    isPlaying.value = false
    void reportPlaybackEvent(entry, 'failed', `HTMLAudioElement error ${audio.error?.code || 0}`)
  })

  async function unlockAndPlay() {
    try {
      const claimed = await claimPlayback()
      audioUnlocked.value = claimed
      if (!claimed) {
        notification.error('另一个页面正在负责音乐播放')
        return
      }
      await fetchState()
      await synchronizePlayer(state.value.current)
    } catch (cause) {
      notification.error(`无法启动音乐播放器: ${String(cause)}`)
    }
  }

  async function skipCurrent(removeFromLibrary = false) {
    applyState(await request<MusicState>(`/commands/skip?remove_from_library=${removeFromLibrary}`, { method: 'POST' }))
  }

  async function togglePlay() {
    applyState(await request<MusicState>('/commands/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paused: !state.value.paused }),
    }))
  }

  async function setVolume(volume: number) {
    applyState(await request<MusicState>('/commands/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume }),
    }))
  }

  function applyExternalState(next: MusicState) {
    applyState(next)
  }

  async function addSong(sourceId: string, requestedBy = 'admin') {
    try {
      const result = await request<{ accepted: boolean; error?: string }>('/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: sourceId,
          source_id: sourceId,
          provider: 'bilibili',
          requested_by: requestedBy,
        }),
      })
      if (!result.accepted) notification.error(result.error || '点歌未通过审核')
      await fetchState()
      return result.accepted
    } catch (cause) {
      notification.error(`点歌失败: ${String(cause)}`)
      return false
    }
  }

  async function removeFromQueue(entryId: string) {
    await request(`/queue/${encodeURIComponent(entryId)}`, { method: 'DELETE' })
    await fetchState()
  }

  function seekTo(percent: number) {
    if (Number.isFinite(audio.duration)) audio.currentTime = percent * audio.duration
  }

  window.addEventListener('beforeunload', () => {
    if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer)
    if (isPlaybackOwner.value) {
      navigator.sendBeacon(
        `${API_BASE}/player/release`,
        new Blob([JSON.stringify({ player_id: playerId })], { type: 'application/json' }),
      )
    }
  })

  return {
    state,
    current,
    queue,
    isPlaying,
    currentTime,
    duration,
    audioUnlocked,
    isPlaybackOwner,
    fetchState,
    applyExternalState,
    unlockAndPlay,
    togglePlay,
    skipCurrent,
    setVolume,
    addSong,
    removeFromQueue,
    seekTo,
  }
})
