import { defineStore } from 'pinia'
import { computed, onUnmounted, ref } from 'vue'

export const useLiveStatsStore = defineStore('livestats', () => {
  const popularity = ref(0)
  const danmakuCount = ref(0)
  const giftCount = ref(0)
  const giftValueMinor = ref(0)
  const giftNameCounts = ref<Record<string, number>>({})

  const runtimeSeconds = ref(0)
  let timer: number | null = null

  const runtimeFormatted = computed(() => {
    const total = Math.max(0, Math.floor(runtimeSeconds.value))
    const h = Math.floor(total / 3600)
    const m = Math.floor((total % 3600) / 60)
    const s = total % 60
    const pad = (n: number) => n.toString().padStart(2, '0')
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
  })

  const topGifts = computed(() => {
    return Object.entries(giftNameCounts.value)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([name, count]) => ({ name, count }))
  })

  function setPopularity(pop: number) {
    popularity.value = pop
  }

  function incrementDanmaku() {
    danmakuCount.value++
  }

  function addGift(valueMinor: number, giftName: string, count = 1) {
    giftCount.value++
    giftValueMinor.value += valueMinor
    giftNameCounts.value[giftName] = (giftNameCounts.value[giftName] || 0) + count
  }

  function startTimer() {
    if (timer !== null) return
    timer = window.setInterval(() => {
      runtimeSeconds.value++
    }, 1000)
  }

  function stopTimer() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function reset() {
    popularity.value = 0
    danmakuCount.value = 0
    giftCount.value = 0
    giftValueMinor.value = 0
    giftNameCounts.value = {}
    runtimeSeconds.value = 0
  }

  onUnmounted(() => {
    stopTimer()
  })

  return {
    popularity,
    danmakuCount,
    giftCount,
    giftValueMinor,
    runtimeSeconds,
    runtimeFormatted,
    topGifts,
    setPopularity,
    incrementDanmaku,
    addGift,
    startTimer,
    stopTimer,
    reset,
  }
})
