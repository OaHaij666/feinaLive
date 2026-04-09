import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StreamStatus } from '@/types/stream'
import { mockStreamStatus, mockAnnouncement } from '@/mock/data'

export const useStreamStore = defineStore('stream', () => {
  const currentTime = ref('')
  const isStreaming = ref(mockStreamStatus.isLive)
  const streamTitle = ref(mockStreamStatus.title)
  const announcement = ref(mockAnnouncement)
  const viewerCount = ref(mockStreamStatus.viewerCount)
  const currentTopic = ref(mockStreamStatus.currentTopic)

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
    updateClock,
    updateAnnouncement,
    setStreaming,
    startClock,
    stopClock
  }
})
