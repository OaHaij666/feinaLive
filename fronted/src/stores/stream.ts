import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StreamStatus } from '@/types/stream'
import { mockStreamStatus } from '@/mock/data'

export const useStreamStore = defineStore('stream', () => {
  const currentTime = ref('')
  const isStreaming = ref(mockStreamStatus.isLive)
  const streamTitle = ref(mockStreamStatus.title)
  const announcement = ref('')
  const viewerCount = ref(mockStreamStatus.viewerCount)
  const currentTopic = ref(mockStreamStatus.currentTopic)
  const llmModel = ref('')
  const ttsVoice = ref('')

  const formattedTime = computed(() => currentTime.value)

  function updateClock() {
    const now = new Date()
    const hours = String(now.getHours()).padStart(2, '0')
    const minutes = String(now.getMinutes()).padStart(2, '0')
    const seconds = String(now.getSeconds()).padStart(2, '0')
    currentTime.value = `${hours}:${minutes}.${seconds}`
  }

  function updateAnnouncement(text: string) {
    announcement.value = text
  }

  async function fetchConfig() {
    try {
      const res = await fetch('/config')
      const data = await res.json()
      llmModel.value = data.host?.model || ''
      ttsVoice.value = data.tts?.voice || ''
      announcement.value = data.announcement || '直播间24小时随机刷新开播。AI主播是小笨蛋不要欺负她喵。白天基本上是无人直播间喵，夜间可能会真人代播。直播间指令：输入 点歌 歌名 或者 点歌 BVid进行点歌，推荐使用BV号点歌。输入/clear 清除AI对你的记忆。'
    } catch (e) {
      console.error('Failed to fetch config:', e)
      announcement.value = '直播间24小时随机刷新开播。AI主播是小笨蛋不要欺负她喵。白天基本上是无人直播间喵，夜间可能会真人代播。直播间指令：输入 点歌 歌名 或者 点歌 BVid进行点歌，推荐使用BV号点歌。输入/clear 清除AI对你的记忆。'
    }
  }

  function setStreaming(status: boolean) {
    isStreaming.value = status
  }

  let clockInterval: number | null = null

  function startClock() {
    updateClock()
    clockInterval = window.setInterval(updateClock, 100)
  }

  function stopClock() {
    if (clockInterval) {
      clearInterval(clockInterval)
      clockInterval = null
    }
  }

  return {
    currentTime,
    formattedTime,
    isStreaming,
    streamTitle,
    announcement,
    viewerCount,
    currentTopic,
    llmModel,
    ttsVoice,
    updateClock,
    updateAnnouncement,
    fetchConfig,
    setStreaming,
    startClock,
    stopClock
  }
})
