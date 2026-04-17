import { ref, onUnmounted } from 'vue'
import { useLLMStore } from '@/stores/llm'
import { useMusicStore } from '@/stores/music'
import { useNotification } from '@/utils/notification'

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
  const musicStore = useMusicStore()
  const notification = useNotification()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

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
    if (ws) {
      ws.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/bilibili/ws/${roomId}`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      isConnected.value = true
      error.value = null
      console.log('[BilibiliDanmaku] Connected to room', roomId)
    }

    ws.onmessage = (event) => {
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
        } else if (msg.type === 'start' || msg.type === 'text' || msg.type === 'audio' || msg.type === 'end') {
          llmStore.handleExternalChunk(msg)
        } else if (msg.type === 'reply') {
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
        } else if (msg.type === 'music_control') {
          const action = msg.data?.action
          if (action === 'volume') {
            musicStore.setVolume(msg.data.volume)
          } else if (action === 'pause') {
            musicStore.setPaused(msg.data.is_paused)
          } else if (action === 'next' || action === 'rm') {
            musicStore.fetchQueue()
          }
        }
      } catch (e) {
        console.error('[BilibiliDanmaku] Parse error:', e)
      }
    }

    ws.onerror = () => {
      error.value = '连接错误'
      isConnected.value = false
    }

    ws.onclose = () => {
      isConnected.value = false
      console.log('[BilibiliDanmaku] Disconnected')
      reconnectTimer = setTimeout(() => {
        if (isConnected.value === false) {
          connect(roomId)
        }
      }, 5000)
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
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
