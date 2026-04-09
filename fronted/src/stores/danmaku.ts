import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DanmakuMessage } from '@/types/danmaku'
import { DanmakuType } from '@/types/danmaku'
import { mockDanmakuMessages, generateRandomDanmaku } from '@/mock/data'

function createSpecialMessages(): DanmakuMessage[] {
  return [
    {
      id: `special-1-${Date.now()}`,
      user: '✨月兔酱✨',
      content: '来了来了！打卡打卡！',
      timestamp: new Date(),
      type: DanmakuType.WELCOME,
      badge: '粉丝牌'
    },
    {
      id: `special-2-${Date.now()}`,
      user: '技术宅',
      content: '请问这个配置大概多少钱？想组装一台类似的',
      timestamp: new Date(),
      type: DanmakuType.HIGHLIGHT,
      color: '#6b8cce'
    },
    {
      id: `special-3-${Date.now()}`,
      user: '系统消息',
      content: '感谢「星辰大海」赠送的火箭 x1 🚀',
      timestamp: new Date(),
      type: DanmakuType.GIFT
    },
    {
      id: `special-4-${Date.now()}`,
      user: '音乐精灵',
      content: '666666 太秀了！',
      timestamp: new Date(),
      type: DanmakuType.NORMAL
    },
    {
      id: `special-5-${Date.now()}`,
      user: '星空漫步者',
      content: '主播声音好好听~',
      timestamp: new Date(),
      type: DanmakuType.NORMAL
    }
  ]
}

export const useDanmakuStore = defineStore('danmaku', () => {
  const danmakuList = ref<DanmakuMessage[]>([...mockDanmakuMessages])
  const isConnected = ref(false)
  const maxCount = 9

  const sortedList = computed(() => {
    return [...danmakuList.value].sort((a, b) => 
      b.timestamp.getTime() - a.timestamp.getTime()
    )
  })

  function addDanmaku(message: DanmakuMessage) {
    danmakuList.value.push(message)
    if (danmakuList.value.length > maxCount) {
      danmakuList.value = danmakuList.value.slice(-maxCount)
    }
  }

  function clearDanmaku() {
    danmakuList.value = []
  }

  function connect() {
    isConnected.value = true
  }

  function disconnect() {
    isConnected.value = false
  }

  function startMockGeneration() {
    const specialMessages = createSpecialMessages()
    let index = 0
    const showInitialMessages = () => {
      if (index < specialMessages.length) {
        addDanmaku(specialMessages[index])
        index++
        setTimeout(showInitialMessages, 800)
      } else {
        setInterval(() => {
          addDanmaku(generateRandomDanmaku())
        }, 3000)
      }
    }
    setTimeout(showInitialMessages, 500)
  }

  return {
    danmakuList,
    sortedList,
    isConnected,
    addDanmaku,
    clearDanmaku,
    connect,
    disconnect,
    startMockGeneration
  }
})
