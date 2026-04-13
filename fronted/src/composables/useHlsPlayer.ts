import { ref, onUnmounted } from 'vue'
import Hls from 'hls.js'

export function useHlsPlayer() {
  const isPlaying = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const quality = ref<'auto' | 'low' | 'medium' | 'high'>('auto')

  let hls: Hls | null = null

  function initPlayer(videoElement: HTMLVideoElement, streamUrl: string) {
    if (hls) {
      destroyPlayer()
    }

    error.value = null
    isLoading.value = true

    videoElement.onplaying = () => {
      isPlaying.value = true
      isLoading.value = false
      console.log('[HLS] Playing')
    }

    videoElement.onpause = () => {
      isPlaying.value = false
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
        fragLoadingMaxRetry: 8,
        levelLoadingTimeOut: 15000,
        levelLoadingMaxRetry: 6,
        maxBufferLength: 15,
        maxMaxBufferLength: 20,
        maxBufferSize: 40 * 1000 * 1000,
        maxBufferHole: 1.0,
        startLevel: -1,
      })

      hls.loadSource(streamUrl)
      hls.attachMedia(videoElement)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        console.log('[HLS] Manifest parsed')
        isLoading.value = false
        videoElement.play().catch(() => {})
      })

      hls.on(Hls.Events.ERROR, (_, data) => {
        console.warn('[HLS] Error:', data.type, data.details)
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              error.value = 'Network error'
              hls?.recoverMediaError()
              break
            case Hls.ErrorTypes.MEDIA_ERROR:
              error.value = 'Media error - recovering'
              hls?.recoverMediaError()
              break
            default:
              error.value = 'Fatal error'
              destroyPlayer()
              break
          }
        }
      })
    } else if (videoElement.canPlayType('application/vnd.apple.mpegurl')) {
      videoElement.src = streamUrl
      videoElement.addEventListener('loadedmetadata', () => {
        isLoading.value = false
        videoElement.play()
      })
    } else {
      error.value = 'HLS is not supported'
      isLoading.value = false
    }
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
    if (hls) {
      hls.destroy()
      hls = null
    }
    isPlaying.value = false
    isLoading.value = false
    error.value = null
  }

  onUnmounted(() => {
    destroyPlayer()
  })

  return {
    isPlaying,
    isLoading,
    error,
    quality,
    initPlayer,
    play,
    pause,
    setQuality,
    destroyPlayer,
  }
}
