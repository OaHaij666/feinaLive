import { onUnmounted, ref } from 'vue'
import { useLLMStore } from '@/stores/llm'
import { useLiveStatsStore } from '@/stores/livestats'
import { useMusicStore } from '@/features/music/store'
import type { MusicState } from '@/features/music/types'
import { useNotification } from '@/utils/notification'

export interface LiveDanmakuMessage {
  id: string
  userId: string
  user: string
  content: string
  timestamp: Date
  type: 'normal' | 'highlight' | 'gift' | 'system' | 'welcome'
  color?: string
  badge?: string
  isAdmin: boolean
}

interface StandardLiveEvent {
  event_id: string
  type: string
  timestamp: number
  user?: {
    user_id: string
    display_name: string
    badges: string[]
    is_admin: boolean
  }
  content?: string
  gift?: {
    name: string
    count: number
    value: { value_minor: number }
  }
  stats?: Record<string, number | string>
  metadata?: Record<string, unknown>
}

export function useLiveEvents() {
  const danmakuList = ref<LiveDanmakuMessage[]>([])
  const isConnected = ref(false)
  const error = ref<string | null>(null)
  const llmStore = useLLMStore()
  const liveStatsStore = useLiveStatsStore()
  const musicStore = useMusicStore()
  const notification = useNotification()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let generation = 0
  let shouldReconnect = false

  function appendLiveEvent(event: StandardLiveEvent) {
    if (event.type === 'danmaku' && event.user) {
      danmakuList.value.push({
        id: event.event_id,
        userId: event.user.user_id,
        user: event.user.display_name || '未知用户',
        content: event.content || '',
        timestamp: new Date((event.timestamp || Date.now() / 1000) * 1000),
        type: 'normal',
        color: typeof event.metadata?.color === 'number'
          ? `#${Number(event.metadata.color).toString(16).padStart(6, '0')}`
          : undefined,
        badge: event.user.badges?.[0],
        isAdmin: !!event.user.is_admin,
      })
      danmakuList.value = danmakuList.value.slice(-50)
      liveStatsStore.incrementDanmaku()
    } else if (['gift', 'super_chat', 'membership'].includes(event.type) && event.gift) {
      const gift: LiveDanmakuMessage = {
        id: event.event_id,
        userId: event.user?.user_id || '',
        user: event.user?.display_name || '未知用户',
        content: `送出 ${event.gift.name} x${event.gift.count}${event.content ? `：${event.content}` : ''}`,
        timestamp: new Date((event.timestamp || Date.now() / 1000) * 1000),
        type: 'gift',
        isAdmin: !!event.user?.is_admin,
      }
      danmakuList.value.push(gift)
      danmakuList.value = danmakuList.value.slice(-50)
      liveStatsStore.addGift(event.gift.value.value_minor, event.gift.name, event.gift.count)
    } else if (event.type === 'room_stats') {
      const popularity = Number(event.stats?.popularity ?? event.stats?.viewer_count ?? 0)
      liveStatsStore.setPopularity(popularity)
    }
  }

  function connect() {
    shouldReconnect = true
    generation += 1
    const currentGeneration = generation
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) ws.close()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/live/ws`)
    ws = socket

    socket.onopen = () => {
      if (ws !== socket || currentGeneration !== generation) return
      isConnected.value = true
      error.value = null
    }
    socket.onmessage = (raw) => {
      if (ws !== socket || currentGeneration !== generation) return
      try {
        const msg = JSON.parse(raw.data)
        if (msg.type === 'live_event') appendLiveEvent(msg.data as StandardLiveEvent)
        else if (['start', 'text', 'audio', 'end'].includes(msg.type)) {
          if (!llmStore.isPlaybackOwner) llmStore.handleExternalChunk(msg)
        } else if (msg.type === 'reply' && !llmStore.isPlaybackOwner) {
          llmStore.handleExternalChunk({ type: 'start', data: {} })
          llmStore.handleExternalChunk({ type: 'end', data: { text: msg.data?.text || '' } })
        } else if (msg.type === 'music_added') {
          notification.success(`🎵 ${msg.data.user} 点歌成功: ${msg.data.title} - ${msg.data.artist}`)
        } else if (msg.type === 'music_error') notification.error(`❌ 点歌失败: ${msg.data.error}`)
        else if (msg.type === 'music_state') musicStore.applyExternalState(msg.data as MusicState)
      } catch (cause) {
        console.error('[LiveEvents] Parse error:', cause)
      }
    }
    socket.onerror = () => {
      if (ws !== socket) return
      error.value = '直播事件连接错误'
      isConnected.value = false
    }
    socket.onclose = (event) => {
      if (ws !== socket || currentGeneration !== generation) return
      ws = null
      isConnected.value = false
      if (event.code === 1008) {
        shouldReconnect = false
        error.value = event.reason || '直播平台尚未启动'
        return
      }
      if (shouldReconnect) reconnectTimer = setTimeout(connect, 5000)
    }
  }

  function disconnect() {
    shouldReconnect = false
    generation += 1
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    const socket = ws
    ws = null
    if (socket) socket.close()
    isConnected.value = false
  }

  onUnmounted(disconnect)
  return { danmakuList, isConnected, error, connect, disconnect }
}
