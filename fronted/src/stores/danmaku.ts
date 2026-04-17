import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { DanmakuMessage } from '@/types/danmaku'
import { DanmakuType } from '@/types/danmaku'
import { useBilibiliDanmaku, type DanmakuMessage as WsDanmaku } from '@/composables/useBilibiliDanmaku'
import { useAdminCommands } from '@/composables/useAdminCommands'

const ADMIN_UID = 378810242
const ADMIN_USERNAME = 'RongR0Ng'

export const useDanmakuStore = defineStore('danmaku', () => {
  const danmakuList = ref<DanmakuMessage[]>([])
  const isConnected = ref(false)
  const maxCount = 9

  const { danmakuList: wsDanmakuList, isConnected: wsConnected, connect, disconnect } = useBilibiliDanmaku()
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
      if (shouldHideDanmaku(latest.uid || 0, latest.user)) {
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
        uid: latest.uid,
      }
      addDanmaku(msg)
    }
  })

  watch(wsConnected, (connected) => {
    isConnected.value = connected
  })

  function addDanmaku(message: DanmakuMessage) {
    if (shouldHideDanmaku(message.uid || 0, message.user)) {
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

  function connectToRoom(roomId: number) {
    if (roomId && roomId > 0) {
      connect(roomId)
    }
  }

  function disconnectFromRoom() {
    disconnect()
  }

  function startMockGeneration() {
  }

  return {
    danmakuList,
    sortedList,
    isConnected,
    adminState,
    addDanmaku,
    clearDanmaku,
    connectToRoom,
    disconnectFromRoom,
    startMockGeneration
  }
})
