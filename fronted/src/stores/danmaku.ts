import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { DanmakuMessage } from '@/types/danmaku'
import { DanmakuType } from '@/types/danmaku'
import { useLiveEvents } from '@/composables/useLiveEvents'
import { useAdminCommands } from '@/composables/useAdminCommands'

export const useDanmakuStore = defineStore('danmaku', () => {
  const danmakuList = ref<DanmakuMessage[]>([])
  const isConnected = ref(false)
  const maxCount = 9

  const { danmakuList: wsDanmakuList, isConnected: wsConnected, connect, disconnect } = useLiveEvents()
  const { shouldHideDanmaku, adminState } = useAdminCommands()

  const sortedList = computed(() => {
    return [...danmakuList.value].sort((a, b) =>
      b.timestamp.getTime() - a.timestamp.getTime()
    )
  })

  watch(() => wsDanmakuList.value.length, () => {
    const list = wsDanmakuList.value
    if (list.length > 0) {
      const latest = list[list.length - 1]
      if (shouldHideDanmaku(latest.isAdmin)) {
        return
      }
      const msg: DanmakuMessage = {
        id: latest.id,
        user: latest.user,
        content: latest.content,
        timestamp: latest.timestamp,
        type: latest.type as DanmakuType,
        color: latest.color,
        badge: latest.badge,
        userId: latest.userId,
        isAdmin: latest.isAdmin,
      }
      addDanmaku(msg)
    }
  })

  watch(wsConnected, (connected) => {
    isConnected.value = connected
  })

  function addDanmaku(message: DanmakuMessage) {
    if (shouldHideDanmaku(message.isAdmin || false)) {
      return
    }
    if (danmakuList.value.some((item) => item.id === message.id)) {
      return
    }
    danmakuList.value.push(message)
    if (danmakuList.value.length > maxCount) {
      danmakuList.value = danmakuList.value.slice(-maxCount)
    }
  }

  function clearDanmaku() {
    danmakuList.value = []
  }

  function connectToLive() {
    connect()
  }

  function disconnectFromLive() {
    disconnect()
  }

  return {
    danmakuList,
    sortedList,
    isConnected,
    adminState,
    addDanmaku,
    clearDanmaku,
    connectToLive,
    disconnectFromLive,
  }
})
