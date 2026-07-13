import { ref } from 'vue'

interface AvatarInputApi {
  sendAudioData: (level: number, speaking: boolean, replyId: string, audioTimeMs: number) => void
  setPlaybackReady: (ready: boolean) => void
  sendPlaybackAck: (replyId: string, status: 'started' | 'finished' | 'failed', error?: string) => void
  onPlaybackRole: (callback: (isOwner: boolean) => void) => () => void
  onHostChunk: (callback: (chunk: Record<string, unknown>) => void) => () => void
  isPlaybackOwner: () => boolean
  connect: () => void
  disconnect: () => void
}

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const isConnected = ref(false)
let mouseListenerAttached = false
let shouldReconnect = false
let playbackReady = false
let playbackOwner = false
let audioReplyId = ''
let audioSeq = 0
let lastMouseSentAt = 0
const playbackRoleListeners = new Set<(isOwner: boolean) => void>()
const hostChunkListeners = new Set<(chunk: Record<string, unknown>) => void>()

function notifyPlaybackRole(isOwner: boolean) {
  playbackOwner = isOwner
  playbackRoleListeners.forEach((callback) => callback(isOwner))
}

function sendJson(payload: Record<string, unknown>) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload))
  }
}

function sendMouseData(x: number, y: number) {
  if (playbackOwner && ws && ws.readyState === WebSocket.OPEN) {
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
  const now = performance.now()
  if (!playbackOwner || now - lastMouseSentAt < 33) return
  lastMouseSentAt = now
  const x = Math.max(0, Math.min(1, event.clientX / window.innerWidth))
  const y = Math.max(0, Math.min(1, event.clientY / window.innerHeight))
  sendMouseData(x, y)
}

function connect() {
  shouldReconnect = true
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/avatar/control`

  try {
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[AvatarInput] WebSocket connected')
      isConnected.value = true
      attachMouseListener()
      sendJson({ type: 'playback_ready', ready: playbackReady })
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'playback_role') {
          notifyPlaybackRole(Boolean(message.is_owner))
        } else if (['start', 'text', 'audio', 'end', 'error'].includes(message.type)) {
          hostChunkListeners.forEach((callback) => callback(message))
        }
      } catch (error) {
        console.error('[AvatarInput] Invalid server message:', error)
      }
    }

    ws.onclose = () => {
      console.log('[AvatarInput] WebSocket disconnected')
      isConnected.value = false
      detachMouseListener()
      ws = null
      notifyPlaybackRole(false)
      if (shouldReconnect) scheduleReconnect()
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
  if (reconnectTimer || !shouldReconnect) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (!shouldReconnect) return
    console.log('[AvatarInput] Attempting to reconnect...')
    connect()
  }, 3000)
}

function disconnect() {
  shouldReconnect = false
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    sendJson({ type: 'playback_ready', ready: false })
    ws.onclose = null
    ws.close()
    ws = null
  }
  detachMouseListener()
  isConnected.value = false
  notifyPlaybackRole(false)
}

function sendAudioData(
  level: number,
  speaking: boolean,
  replyId: string,
  audioTimeMs: number,
) {
  if (!playbackOwner) return
  if (replyId !== audioReplyId) {
    audioReplyId = replyId
    audioSeq = 0
  }
  sendJson({
    type: 'audio',
    level,
    speaking,
    reply_id: replyId,
    seq: audioSeq++,
    audio_time_ms: Math.max(0, audioTimeMs),
  })
}

function setPlaybackReady(ready: boolean) {
  playbackReady = ready
  sendJson({ type: 'playback_ready', ready })
}

function sendPlaybackAck(
  replyId: string,
  status: 'started' | 'finished' | 'failed',
  error = '',
) {
  if (!playbackOwner) return
  sendJson({ type: 'playback_ack', reply_id: replyId, status, error })
}

function onPlaybackRole(callback: (isOwner: boolean) => void) {
  playbackRoleListeners.add(callback)
  callback(playbackOwner)
  return () => playbackRoleListeners.delete(callback)
}

function onHostChunk(callback: (chunk: Record<string, unknown>) => void) {
  hostChunkListeners.add(callback)
  return () => hostChunkListeners.delete(callback)
}

function isPlaybackOwner() {
  return playbackOwner
}

export function useAvatarInput(): AvatarInputApi {
  return {
    sendAudioData,
    setPlaybackReady,
    sendPlaybackAck,
    onPlaybackRole,
    onHostChunk,
    isPlaybackOwner,
    connect,
    disconnect,
  }
}

export function getAvatarInputApi(): AvatarInputApi {
  return {
    sendAudioData,
    setPlaybackReady,
    sendPlaybackAck,
    onPlaybackRole,
    onHostChunk,
    isPlaybackOwner,
    connect,
    disconnect,
  }
}
