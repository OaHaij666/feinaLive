import { ref, onMounted, onUnmounted } from 'vue'

const AVATAR_INPUT_WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/avatar/input`

let globalWs: WebSocket | null = null
let globalSendAudioData: ((level: number, speaking: boolean) => void) | null = null
let globalSetSpeaking: ((speaking: boolean) => void) | null = null

export function getAvatarInputApi() {
  return {
    sendAudioData: globalSendAudioData,
    setSpeaking: globalSetSpeaking
  }
}

export function useAvatarInput() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const isSpeaking = ref(false)
  const audioLevel = ref(0)

  let lastMouseX = 0.5
  let lastMouseY = 0.5
  let mouseThrottleTimer: number | null = null

  function connect() {
    if (ws.value) {
      ws.value.close()
    }

    ws.value = new WebSocket(AVATAR_INPUT_WS_URL)
    globalWs = ws.value

    ws.value.onopen = () => {
      console.log('Avatar input WebSocket 连接成功')
      connected.value = true
    }

    ws.value.onclose = () => {
      console.log('Avatar input WebSocket 断开')
      connected.value = false
      setTimeout(() => {
        if (!ws.value || ws.value.readyState === WebSocket.CLOSED) {
          connect()
        }
      }, 3000)
    }

    ws.value.onerror = (error) => {
      console.error('Avatar input WebSocket 错误:', error)
      connected.value = false
    }
  }

  function sendMousePosition(x: number, y: number) {
    lastMouseX = x
    lastMouseY = y
    
    if (mouseThrottleTimer) return
    
    mouseThrottleTimer = window.setTimeout(() => {
      mouseThrottleTimer = null
      if (ws.value && ws.value.readyState === WebSocket.OPEN) {
        ws.value.send(JSON.stringify({
          type: 'mouse',
          x: lastMouseX,
          y: lastMouseY
        }))
      }
    }, 16)
  }

  function sendAudioData(level: number, speaking: boolean) {
    audioLevel.value = level
    isSpeaking.value = speaking
    
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({
        type: 'audio',
        level,
        speaking
      }))
    }
  }

  function setSpeaking(speaking: boolean) {
    isSpeaking.value = speaking
    
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({
        type: 'speaking',
        speaking
      }))
    }
  }

  function handleMouseMove(event: MouseEvent) {
    const x = event.clientX / window.innerWidth
    const y = event.clientY / window.innerHeight
    sendMousePosition(x, y)
  }

  globalSendAudioData = sendAudioData
  globalSetSpeaking = setSpeaking

  onMounted(() => {
    connect()
    window.addEventListener('mousemove', handleMouseMove)
  })

  onUnmounted(() => {
    window.removeEventListener('mousemove', handleMouseMove)
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    if (mouseThrottleTimer) {
      clearTimeout(mouseThrottleTimer)
    }
    globalSendAudioData = null
    globalSetSpeaking = null
  })

  return {
    connected,
    isSpeaking,
    audioLevel,
    sendMousePosition,
    sendAudioData,
    setSpeaking
  }
}
