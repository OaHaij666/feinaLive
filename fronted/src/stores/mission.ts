import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface MissionData {
  id: number
  server: string
  missions: string[][]
  createdAt: string
}

export const useMissionStore = defineStore('mission', () => {
  const missionData = ref<MissionData | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastFetchTime = ref<Date | null>(null)

  const characterMissions = computed(() => missionData.value?.missions[0] || [])
  const weaponMissions = computed(() => missionData.value?.missions[1] || [])
  const modMissions = computed(() => missionData.value?.missions[2] || [])

  const refreshCountdown = computed(() => {
    const now = new Date()
    const nextHour = new Date(now)
    nextHour.setHours(nextHour.getHours() + 1, 0, 0, 0)
    const diff = nextHour.getTime() - now.getTime()
    const minutes = Math.floor(diff / 60000)
    const seconds = Math.floor((diff % 60000) / 1000)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  })

  async function fetchMissions() {
    isLoading.value = true
    error.value = null
    
    try {
      const response = await fetch('https://api.dna-builder.cn/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `{ missionsIngame(server: "cn") { id server missions createdAt } }`
        })
      })
      
      const data = await response.json()
      
      if (data.errors) {
        throw new Error(data.errors[0].message)
      }
      
      missionData.value = data.data.missionsIngame
      lastFetchTime.value = new Date()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '获取数据失败'
      console.error('Failed to fetch missions:', e)
    } finally {
      isLoading.value = false
    }
  }

  return {
    missionData,
    isLoading,
    error,
    lastFetchTime,
    characterMissions,
    weaponMissions,
    modMissions,
    refreshCountdown,
    fetchMissions
  }
})
