import { ref, onUnmounted } from 'vue'
import Hls from 'hls.js'

const POLLING_INTERVAL = 3000
const MAX_RECONNECT_ATTEMPTS = 20
const RECONNECT_INTERVAL = 5000

export function useHlsPlayer() {
  const isPlaying = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const quality = ref<'auto' | 'low' | 'medium' | 'high'>('auto')
  const isReconnecting = ref(false)

  let hls: Hls | null = null
  let streamUrl: string = ''
  let videoElement: HTMLVideoElement | null = null
  let reconnectAttempts = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pollingTimer: ReturnType<typeof setInterval> | null = null

  function startPolling() {
    if (pollingTimer) return
    pollingTimer = setInterval(async () => {
      try {
        const response = await fetch('/stream/status')
        const data = await response.json()
        if (data.nginx_running && data.urls) {
          const fullUrl = data.urls.hls_url
          const url = new URL(fullUrl)
          const newPath = url.pathname
          if (newPath !== streamUrl) {
            streamUrl = newPath
            reconnectAttempts = 0
            stopPolling()
            if (videoElement) {
              isReconnecting.value = true
              error.value = null
              destroyPlayer()
              setTimeout(() => {
                initPlayerInternal(videoElement!, streamUrl)
                isReconnecting.value = false
              }, 1000)
            }
          }
        }
      } catch {
      }
    }, POLLING_INTERVAL)
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  function scheduleReconnect() {
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      error.value = '连接失败，请检查服务状态'
      startPolling()
      return
    }
    reconnectAttempts++
    const delay = Math.min(RECONNECT_INTERVAL * reconnectAttempts, 30000)
    reconnectTimer = setTimeout(() => {
      if (streamUrl && videoElement) {
        initPlayerInternal(videoElement, streamUrl)
      }
    }, delay)
  }

  function initPlayerInternal(videoEl: HTMLVideoElement, url: string) {
    if (hls) {
      destroyPlayer()
    }

    error.value = null
    isLoading.value = true

    videoEl.onplaying = () => {
      isPlaying.value = true
      isLoading.value = false
      isReconnecting.value = false
      reconnectAttempts = 0
      console.log('[HLS] Playing')
    }

    videoEl.onpause = () => {
      isPlaying.value = false
      console.log('[HLS] Pause')
    }

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        liveSyncDurationCount: 3,
        liveMaxLatencyDurationCount: 5,
        liveDurationInfinity: true,
        highBufferWatchdogPeriod: 5,
        fragLoadingTimeOut: 20000,
        fragLoadingMaxRetry: 6,
        levelLoadingTimeOut: 15000,
        levelLoadingMaxRetry: 4,
        maxBufferLength: 15,
        maxMaxBufferLength: 20,
        maxBufferSize: 40 * 1000 * 1000,
        maxBufferHole: 1.0,
        startLevel: -1,
      })

      hls.loadSource(url)
      hls.attachMedia(videoEl)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        console.log('[HLS] Manifest parsed')
        isLoading.value = false
        videoEl.play().catch(() => {})
      })

      hls.on(Hls.Events.ERROR, (_, data) => {
        console.warn('[HLS] Error:', data.type, data.details)
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              console.log('[HLS] Network error, attempting recovery...')
              error.value = '网络断开，正在尝试恢复...'
              hls?.recoverMediaError()
              scheduleReconnect()
              break
            case Hls.ErrorTypes.MEDIA_ERROR:
              console.log('[HLS] Media error, attempting recovery...')
              error.value = '媒体错误，正在尝试恢复...'
              hls?.recoverMediaError()
              break
            default:
              console.log('[HLS] Fatal error, will reconnect...')
              error.value = '连接断开，正在尝试恢复...'
              destroyPlayer()
              scheduleReconnect()
              break
          }
        }
      })
    } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      videoEl.src = url
      videoEl.addEventListener('loadedmetadata', () => {
        isLoading.value = false
        videoEl.play()
      })
      videoEl.addEventListener('error', () => {
        console.log('[HLS] Apple HLS error, will reconnect...')
        error.value = '连接断开，正在尝试恢复...'
        scheduleReconnect()
      })
    } else {
      error.value = 'HLS is not supported'
      isLoading.value = false
      startPolling()
    }
  }

  function initPlayer(videoEl: HTMLVideoElement, url: string) {
    videoElement = videoEl
    streamUrl = url
    reconnectAttempts = 0
    initPlayerInternal(videoEl, url)
  }

  function play() {}

  function pause() {}

  function setQuality(level: 'auto' | 'low' | 'medium' | 'high') {
    if (!hls) return
    if (level === 'auto') {
      hls.currentLevel = -1
      quality.value = 'auto'
    }
  }

  function destroyPlayer() {
    stopPolling()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (hls) {
      hls.destroy()
      hls = null
    }
    isPlaying.value = false
    isLoading.value = false
  }

  function manualRetry() {
    stopPolling()
    reconnectAttempts = 0
    if (streamUrl && videoElement) {
      destroyPlayer()
      initPlayerInternal(videoElement, streamUrl)
    }
  }

  onUnmounted(() => {
    destroyPlayer()
  })

  return {
    isPlaying,
    isLoading,
    error,
    quality,
    isReconnecting,
    initPlayer,
    play,
    pause,
    setQuality,
    destroyPlayer,
    manualRetry,
  }
}
