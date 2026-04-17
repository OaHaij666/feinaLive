import { ref } from 'vue'

interface AvatarInputApi {
  sendAudioData: (level: number, speaking: boolean) => void
  setSpeaking: (speaking: boolean) => void
  connect: () => void
  disconnect: () => void
}

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const isConnected = ref(false)
let mouseListenerAttached = false

function sendMouseData(x: number, y: number) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'mouse',
      x,
      y,
    }))
  }
}

function attachMouseListener() {
  if (mouseListenerAttached) return
  mouseListenerAttached = true
  window.addEventListener('mousemove', handleMouseMove)
}

function detachMouseListener() {
  if (!mouseListenerAttached) return
  mouseListenerAttached = false
  window.removeEventListener('mousemove', handleMouseMove)
}

function handleMouseMove(event: MouseEvent) {
  const x = Math.max(0, Math.min(1, event.clientX / window.innerWidth))
  const y = Math.max(0, Math.min(1, event.clientY / window.innerHeight))
  sendMouseData(x, y)
}

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/avatar/input`

  try {
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[AvatarInput] WebSocket connected')
      isConnected.value = true
      attachMouseListener()
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onclose = () => {
      console.log('[AvatarInput] WebSocket disconnected')
      isConnected.value = false
      detachMouseListener()
      ws = null
      scheduleReconnect()
    }

    ws.onerror = (error) => {
      console.error('[AvatarInput] WebSocket error:', error)
    }
  } catch (error) {
    console.error('[AvatarInput] Failed to create WebSocket:', error)
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    console.log('[AvatarInput] Attempting to reconnect...')
    connect()
  }, 3000)
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
  detachMouseListener()
  isConnected.value = false
}

function sendAudioData(level: number, speaking: boolean) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'audio',
      level,
      speaking,
    }))
  }
}

function setSpeaking(speaking: boolean) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'speaking',
      speaking,
    }))
  }
}

export function useAvatarInput(): AvatarInputApi {
  return {
    sendAudioData,
    setSpeaking,
    connect,
    disconnect,
  }
}

export function getAvatarInputApi(): AvatarInputApi {
  return {
    sendAudioData,
    setSpeaking,
    connect,
    disconnect,
  }
}
