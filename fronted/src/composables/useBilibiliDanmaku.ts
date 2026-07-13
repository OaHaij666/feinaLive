import { ref, onUnmounted } from 'vue'
import { useLLMStore } from '@/stores/llm'
import { useLiveStatsStore } from '@/stores/livestats'
import { useMusicStore } from '@/features/music/store'
import type { MusicState } from '@/features/music/types'
import { useNotification } from '@/utils/notification'
import { useAdminCommands } from '@/composables/useAdminCommands'

export interface DanmakuMessage {
  id: string
  user: string
  content: string
  timestamp: Date
  type: 'normal' | 'highlight' | 'gift' | 'system' | 'welcome'
  color?: string
  badge?: string
  uid?: number
}

export function useBilibiliDanmaku() {
  const danmakuList = ref<DanmakuMessage[]>([])
  const isConnected = ref(false)
  const error = ref<string | null>(null)
  const llmStore = useLLMStore()
  const liveStatsStore = useLiveStatsStore()
  const musicStore = useMusicStore()
  const notification = useNotification()
  const { adminState } = useAdminCommands()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let desiredRoomId: number | null = null
  let connectionGeneration = 0
  let shouldReconnect = false

  function clearReconnectTimer() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function parseTimestamp(raw: unknown): Date {
    if (typeof raw === 'number') {
      return new Date(raw * 1000)
    }
    if (typeof raw === 'string') {
      const parsed = Date.parse(raw)
      if (!Number.isNaN(parsed)) {
        return new Date(parsed)
      }
      const n = Number(raw)
      if (!Number.isNaN(n)) {
        return new Date(n * 1000)
      }
    }
    return new Date()
  }

  function connect(roomId: number) {
    console.log('[BilibiliDanmaku] connect called with roomId:', roomId)
    desiredRoomId = roomId
    shouldReconnect = true
    connectionGeneration += 1
    const generation = connectionGeneration
    clearReconnectTimer()

    const previous = ws
    ws = null
    if (previous) {
      previous.onopen = null
      previous.onmessage = null
      previous.onerror = null
      previous.onclose = null
      previous.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/bilibili/ws/${roomId}`
    console.log('[BilibiliDanmaku] Connecting to', wsUrl)

    const socket = new WebSocket(wsUrl)
    ws = socket

    socket.onopen = () => {
      if (generation !== connectionGeneration || ws !== socket) return
      isConnected.value = true
      error.value = null
      console.log('[BilibiliDanmaku] Connected to room', roomId)
    }

    socket.onmessage = (event) => {
      if (generation !== connectionGeneration || ws !== socket) return
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'danmaku') {
          const data = msg.data
          const uname = data.uname || data.user || '未知用户'
          const content = data.msg || data.content || ''
          const danmaku: DanmakuMessage = {
            id: data.id || `danmaku-${data.uid || '0'}-${Date.now()}`,
            user: uname,
            content,
            timestamp: parseTimestamp(data.timestamp),
            type: 'normal',
            color: data.text_color ? `#${data.text_color}` : undefined,
            uid: data.uid,
          }
          danmakuList.value.push(danmaku)
          if (danmakuList.value.length > 50) {
            danmakuList.value = danmakuList.value.slice(-50)
          }
          liveStatsStore.incrementDanmaku()
        } else if (msg.type === 'gift') {
          const data = msg.data
          const gift: DanmakuMessage = {
            id: `gift-${data.uid}-${Date.now()}`,
            user: data.uname || '未知用户',
            content: `送出 ${data.gift_name} x${data.num}`,
            timestamp: new Date(),
            type: 'gift',
          }
          danmakuList.value.push(gift)
          liveStatsStore.addGift(Number(data.total_coin) || 0, data.gift_name || '未知礼物')
        } else if (msg.type === 'popularity') {
          const popularity = Number(msg.data?.popularity) || 0
          liveStatsStore.setPopularity(popularity)
        } else if (msg.type === 'start' || msg.type === 'text' || msg.type === 'audio' || msg.type === 'end') {
          if (!adminState.value.isTestRoomEnabled && !llmStore.isPlaybackOwner) {
            llmStore.handleExternalChunk(msg)
          }
        } else if (msg.type === 'reply') {
          if (llmStore.isPlaybackOwner) return
          llmStore.handleExternalChunk({
            type: 'start',
            data: {},
          })
          llmStore.handleExternalChunk({
            type: 'end',
            data: { text: msg.data?.text || '' },
          })
        } else if (msg.type === 'music_added') {
          const data = msg.data
          notification.success(`🎵 ${data.user} 点歌成功: ${data.title} - ${data.artist}`)
        } else if (msg.type === 'music_error') {
          const data = msg.data
          notification.error(`❌ 点歌失败: ${data.error}`)
        } else if (msg.type === 'music_state') {
          musicStore.applyExternalState(msg.data as MusicState)
        }
      } catch (e) {
        console.error('[BilibiliDanmaku] Parse error:', e)
      }
    }

    socket.onerror = () => {
      if (generation !== connectionGeneration || ws !== socket) return
      error.value = '连接错误'
      isConnected.value = false
    }

    socket.onclose = (event) => {
      if (generation !== connectionGeneration || ws !== socket) return
      ws = null
      isConnected.value = false
      console.log('[BilibiliDanmaku] Disconnected')
      if (event.code === 1008) {
        shouldReconnect = false
        error.value = event.reason || '当前直播间已变更'
        return
      }
      if (!shouldReconnect || desiredRoomId !== roomId) return
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (
          shouldReconnect &&
          desiredRoomId === roomId &&
          generation === connectionGeneration &&
          isConnected.value === false
        ) {
          connect(roomId)
        }
      }, 5000)
    }
  }

  function disconnect() {
    shouldReconnect = false
    desiredRoomId = null
    connectionGeneration += 1
    clearReconnectTimer()
    const socket = ws
    ws = null
    if (socket) {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close()
    }
    isConnected.value = false
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    danmakuList,
    isConnected,
    error,
    connect,
    disconnect,
  }
}
