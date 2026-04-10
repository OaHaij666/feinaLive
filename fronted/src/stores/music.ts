import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { MusicItem, QueueResponse } from '@/types/music'
import { MusicStatus } from '@/types/music'
import { useNotification } from '@/utils/notification'

const API_BASE = '/music'

let audioElement: HTMLAudioElement | null = null

function getAudioElement(): HTMLAudioElement {
  if (!audioElement) {
    audioElement = new Audio()
    audioElement.crossOrigin = 'anonymous'
  }
  return audioElement
}

function toProxyUrl(url: string): string {
  if (!url) return ''
  if (url.includes('bilivideo.com') || url.includes('biliplus')) {
    return `${API_BASE}/proxy/audio?url=${encodeURIComponent(url)}`
  }
  return url
}

export const useMusicStore = defineStore('music', () => {
  const { error } = useNotification()
  const current = ref<MusicItem | null>(null)
  const queue = ref<MusicItem[]>([])
  const history = ref<MusicItem[]>([])
  const totalPlayed = ref(0)
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const audioUnlocked = ref(false)

  const audio = getAudioElement()

  audio.addEventListener('timeupdate', () => {
    currentTime.value = audio.currentTime
  })

  audio.addEventListener('loadedmetadata', () => {
    duration.value = audio.duration || 0
  })

  audio.addEventListener('ended', async () => {
    await playNext()
  })

  audio.addEventListener('error', (e) => {
    console.error('Audio error:', e)
    error('音频播放失败')
    isPlaying.value = false
  })

  audio.addEventListener('play', () => {
    isPlaying.value = true
  })

  audio.addEventListener('pause', () => {
    isPlaying.value = false
  })

  watch(current, async (newCurrent) => {
    if (newCurrent?.audioUrl) {
      audio.src = toProxyUrl(newCurrent.audioUrl)
      if (audioUnlocked.value) {
        audio.play().catch(() => {
          error('播放失败')
        })
        isPlaying.value = true
      } else {
        isPlaying.value = false
      }
    } else {
      audio.src = ''
      isPlaying.value = false
      currentTime.value = 0
      duration.value = 0
    }
  })

  const hasNext = computed(() => queue.value.length > 0)

  async function fetchQueue() {
    try {
      const res = await fetch(`${API_BASE}/queue`)
      if (!res.ok) {
        const err = await res.json()
        error(err.error || '获取播放队列失败')
        return
      }
      const data: QueueResponse = await res.json()
      current.value = data.current
      queue.value = data.queue
    } catch (e) {
      error('网络错误，无法获取播放队列')
    }
  }

  async function fetchHistory() {
    try {
      const res = await fetch(`${API_BASE}/history`)
      history.value = await res.json()
    } catch (e) {
      console.error('Failed to fetch history:', e)
    }
  }

  async function playNext() {
    try {
      const res = await fetch(`${API_BASE}/next`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json()
        error(err.error || '播放下一首失败')
        return
      }
      const data = await res.json()
      if (data) {
        current.value = data
      } else {
        current.value = null
      }
      await fetchQueue()
    } catch (e) {
      error('网络错误，无法播放下一首')
    }
  }

  async function skipCurrent() {
    try {
      await fetch(`${API_BASE}/skip`, { method: 'POST' })
      await playNext()
    } catch (e) {
      console.error('Failed to skip:', e)
    }
  }

  async function addSong(bvid: string, requestedBy: string = 'user') {
    try {
      const res = await fetch(`${API_BASE}/add/${bvid}?requestedBy=${requestedBy}`, {
        method: 'POST'
      })
      if (!res.ok) {
        const err = await res.json()
        error(err.error || '添加歌曲失败')
        return false
      }
      await fetchQueue()
      return true
    } catch (e) {
      error('网络错误，无法添加歌曲')
    }
    return false
  }

  async function removeFromQueue(itemId: string) {
    try {
      await fetch(`${API_BASE}/queue/${itemId}`, { method: 'DELETE' })
      await fetchQueue()
    } catch (e) {
      console.error('Failed to remove from queue:', e)
    }
  }

  async function clearQueue() {
    try {
      await fetch(`${API_BASE}/queue`, { method: 'DELETE' })
      queue.value = []
    } catch (e) {
      console.error('Failed to clear queue:', e)
    }
  }

  function unlockAndPlay() {
    audioUnlocked.value = true
    if (current.value?.audioUrl && !isPlaying.value) {
      audio.play().catch(() => {
        error('播放失败')
      })
    } else if (!current.value) {
      playNext()
    }
  }

  function togglePlay() {
    if (!audioUnlocked.value) {
      audioUnlocked.value = true
    }
    if (current.value?.audioUrl) {
      if (isPlaying.value) {
        audio.pause()
      } else {
        audio.play().catch(() => {
          error('播放失败')
        })
      }
    }
  }

  function seekTo(percent: number) {
    if (audio.duration && current.value) {
      audio.currentTime = percent * audio.duration
    }
  }

  return {
    current,
    queue,
    history,
    totalPlayed,
    isPlaying,
    currentTime,
    duration,
    audioUnlocked,
    hasNext,
    fetchQueue,
    fetchHistory,
    playNext,
    skipCurrent,
    addSong,
    removeFromQueue,
    clearQueue,
    unlockAndPlay,
    togglePlay,
    seekTo,
  }
})
