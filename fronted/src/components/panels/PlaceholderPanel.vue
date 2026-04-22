<template>
  <div class="placeholder-panel">
    <div class="panel-glow"></div>

    <div class="panel-content">
      <div class="content-upper">
        <div class="music-section">
          <div class="music-main">
            <div class="track-info">
              <div class="track-info-header">
                <div class="track-title" :title="current?.title ? `${current.title} - ${current.upName}` : '等待播放'">
                  {{ current?.title ? `${current.title} - ${current.upName}` : '等待播放' }}
                </div>
              </div>

              <div class="progress-section" v-if="hasCurrent">
                <div class="progress-bar" @click.stop="handleSeek">
                  <div class="progress-track">
                    <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
                    <div class="progress-handle" :style="{ left: progressPercent + '%' }"></div>
                  </div>
                </div>
                <div class="time-display">
                  <span>{{ formatTime(currentTime) }}</span>
                  <span>{{ formatTime(duration) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="queue-section">
            <div class="queue-header">
              <span class="queue-label">播放列表</span>
              <span class="queue-count">{{ displayQueue.length }}首</span>
            </div>
            <div class="queue-list" ref="queueListRef" v-if="displayQueue.length > 0">
              <div
                v-for="(item, index) in displayQueue"
                :key="item.id"
                class="queue-item"
                :class="{ next: index === 0 }"
              >
                <div class="item-index">{{ index + 1 }}</div>
                <div class="item-info">
                  <div class="item-title">{{ item.title }} - {{ item.upName }}</div>
                </div>
                <div class="item-duration">{{ formatTime(item.duration) }}</div>
              </div>
            </div>
            <div class="queue-empty" v-else>
              <span>歌单为空</span>
            </div>
          </div>
        </div>
      </div>

      <div class="content-lower">
        <Transition name="fade">
          <div class="llm-content" v-if="isVisible" ref="llmContentRef">
            <div class="marquee-wrapper" ref="marqueeWrapperRef">
              <div class="marquee-content" :key="scrollKey">
                <span class="text-content" ref="textContentRef">{{ displayContent }}</span>
                <span class="typing-cursor" v-if="isGenerating"></span>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useMusicStore } from '@/stores/music'
import { useLLMStore } from '@/stores/llm'

const musicStore = useMusicStore()
const llmStore = useLLMStore()
const { current, queue, isPlaying, currentTime, duration } = storeToRefs(musicStore)
const { isGenerating, displayText, latestAssistantMessage } = storeToRefs(llmStore)

const hasCurrent = computed(() => !!current.value)

const displayQueue = computed(() => queue.value.slice(0, 3))

const progressPercent = computed(() => {
  if (!duration.value) return 0
  return (currentTime.value / duration.value) * 100
})

const latestMessage = computed(() => latestAssistantMessage.value)

const marqueeWrapperRef = ref<HTMLElement | null>(null)
const textContentRef = ref<HTMLElement | null>(null)
const queueListRef = ref<HTMLElement | null>(null)

const isVisible = ref(false)
const displayContent = ref('')
let hideTimer: ReturnType<typeof setTimeout> | null = null
let scrollTimer: ReturnType<typeof setInterval> | null = null
let scrollKey = ref(0)
let renderedLength = 0
let queueScrollTimer: ReturnType<typeof setInterval> | null = null
let queueScrollDirection = 1
let queueScrollPaused = false

const clearScrollTimer = () => {
  if (scrollTimer) {
    clearInterval(scrollTimer)
    scrollTimer = null
  }
}

const clearQueueScrollTimer = () => {
  if (queueScrollTimer) {
    clearInterval(queueScrollTimer)
    queueScrollTimer = null
  }
}

const startQueueAutoScroll = () => {
  clearQueueScrollTimer()
  nextTick(() => {
    if (!queueListRef.value) return
    const el = queueListRef.value
    const hasOverflow = el.scrollHeight > el.clientHeight
    if (!hasOverflow) return
    
    queueScrollTimer = setInterval(() => {
      if (!queueListRef.value || queueScrollPaused) return
      const el = queueListRef.value
      const maxScroll = el.scrollHeight - el.clientHeight
      
      if (queueScrollDirection === 1) {
        el.scrollTop += 1
        if (el.scrollTop >= maxScroll) {
          queueScrollDirection = -1
          setTimeout(() => { queueScrollPaused = false }, 2000)
          queueScrollPaused = true
        }
      } else {
        el.scrollTop -= 1
        if (el.scrollTop <= 0) {
          queueScrollDirection = 1
          setTimeout(() => { queueScrollPaused = false }, 2000)
          queueScrollPaused = true
        }
      }
    }, 50)
  })
}

const checkOverflowAndScroll = () => {
  nextTick(() => {
    if (textContentRef.value && marqueeWrapperRef.value) {
      const textWidth = textContentRef.value.scrollWidth
      const wrapperWidth = marqueeWrapperRef.value.clientWidth
      
      if (textWidth > wrapperWidth && displayContent.value.length > 0) {
        clearScrollTimer()
        
        const currentDisplayLength = displayContent.value.length
        renderedLength += currentDisplayLength
        scrollKey.value++
        
        const remaining = displayText.value.slice(renderedLength)
        
        if (remaining.length > 0) {
          displayContent.value = remaining
          
          scrollTimer = setInterval(() => {
            if (!isVisible.value || !displayText.value) {
              clearScrollTimer()
              return
            }
            
            const len = displayContent.value.length
            renderedLength += len
            scrollKey.value++
            
            const next = displayText.value.slice(renderedLength)
            
            if (next.length === 0) {
              clearScrollTimer()
              return
            }
            
            displayContent.value = next
            
            nextTick(() => {
              if (textContentRef.value && marqueeWrapperRef.value) {
                const tw = textContentRef.value.scrollWidth
                const ww = marqueeWrapperRef.value.clientWidth
                if (tw <= ww) {
                  clearScrollTimer()
                }
              }
            })
          }, 3000)
        }
      }
    }
  })
}

const startHideTimer = () => {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    isVisible.value = false
    displayContent.value = ''
    scrollKey.value++
    renderedLength = 0
    clearScrollTimer()
  }, 30000)
}

watch(displayText, (newText, oldText) => {
  if (newText && newText.length > 0) {
    const isNewSentence = !oldText || 
                          newText.length < oldText.length || 
                          !newText.startsWith(oldText)
    
    if (!isVisible.value || isNewSentence) {
      renderedLength = 0
      scrollKey.value++
      clearScrollTimer()
    }
    displayContent.value = newText.slice(renderedLength)
    isVisible.value = true
    startHideTimer()
    checkOverflowAndScroll()
  }
}, { immediate: true })

watch(queue, () => {
  startQueueAutoScroll()
})

function handleSeek(event: MouseEvent) {
  const bar = event.currentTarget as HTMLElement
  const rect = bar.getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  musicStore.seekTo(percent)
}

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(() => {
  musicStore.fetchQueue()
  startQueueAutoScroll()
})

onUnmounted(() => {
  clearQueueScrollTimer()
})
</script>

<style scoped>
.placeholder-panel {
  width: 680px;
  height: 160px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.45) 0%, rgba(240, 249, 255, 0.38) 100%);
  backdrop-filter: blur(2.4px);
  -webkit-backdrop-filter: blur(2.4px);
  border: 1.5px solid rgba(255, 255, 255, 0.35);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  box-shadow:
    0 8px 32px rgba(59, 130, 246, 0.15),
    inset 0 1px 2px rgba(255, 255, 255, 0.8),
    inset 0 -1px 2px rgba(147, 197, 253, 0.2);
  transition: all 0.3s ease;
}

.placeholder-panel:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.52) 0%, rgba(240, 249, 255, 0.45) 100%);
  box-shadow:
    0 12px 40px rgba(59, 130, 246, 0.22),
    inset 0 1px 2px rgba(255, 255, 255, 0.9),
    inset 0 -1px 2px rgba(147, 197, 253, 0.25);
  transform: translateY(-2px);
}

.panel-glow {
  position: absolute;
  top: -50%;
  right: -20%;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.12), transparent 70%);
  pointer-events: none;
}

.panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-upper {
  flex: 1;
  min-height: 0;
}

.content-lower {
  flex: 1;
  border-top: 1px dashed rgba(147, 197, 253, 0.2);
  padding: 6px 14px;
}

.music-section {
  display: flex;
  height: 100%;
  padding: 6px 14px;
  gap: 12px;
}

.music-main {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.track-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.track-info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.track-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(30, 58, 95, 0.9);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-section {
  margin-top: 6px;
}

.progress-bar {
  height: 16px;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.progress-track {
  width: 100%;
  height: 4px;
  background: rgba(147, 197, 253, 0.4);
  border-radius: 2px;
  position: relative;
  overflow: visible;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa, #3b82f6);
  border-radius: 2px;
  transition: width 0.1s linear;
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
}

.progress-handle {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  background: white;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
  opacity: 0;
  transition: opacity 0.2s;
}

.progress-bar:hover .progress-handle {
  opacity: 1;
}

.time-display {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 10px;
  color: rgba(30, 58, 95, 0.5);
  font-variant-numeric: tabular-nums;
}

.queue-section {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid rgba(147, 197, 253, 0.2);
  padding-left: 12px;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.queue-label {
  font-size: 10px;
  font-weight: 600;
  color: rgba(30, 58, 95, 0.7);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.queue-count {
  font-size: 9px;
  color: rgba(30, 58, 95, 0.5);
  background: rgba(147, 197, 253, 0.2);
  padding: 1px 5px;
  border-radius: 6px;
}

.queue-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(147, 197, 253, 0.3) transparent;
}

.queue-list::-webkit-scrollbar {
  width: 3px;
}

.queue-list::-webkit-scrollbar-track {
  background: transparent;
}

.queue-list::-webkit-scrollbar-thumb {
  background: rgba(147, 197, 253, 0.3);
  border-radius: 2px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 6px;
  transition: background 0.2s;
}

.queue-item:hover {
  background: rgba(147, 197, 253, 0.15);
}

.queue-item.next {
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.15), rgba(59, 130, 246, 0.08));
}

.item-index {
  width: 18px;
  font-size: 11px;
  color: rgba(30, 58, 95, 0.5);
  text-align: center;
  flex-shrink: 0;
  font-weight: 500;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-title {
  font-size: 11px;
  color: rgba(30, 58, 95, 0.85);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-duration {
  font-size: 10px;
  color: rgba(30, 58, 95, 0.4);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.queue-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(30, 58, 95, 0.35);
  font-size: 10px;
}

.llm-content {
  height: 100%;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.marquee-wrapper {
  display: block;
  width: 100%;
  overflow: hidden;
  position: relative;
}

.marquee-content {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}

.text-content {
  display: inline-block;
  font-size: 26px;
  font-weight: 500;
  color: rgba(30, 58, 95, 0.95);
  font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
  letter-spacing: 1px;
  padding: 0 20px;
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
}

.typing-cursor {
  width: 2px;
  height: 14px;
  background: #8b5cf6;
  animation: blink-cursor 0.8s step-end infinite;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.llm-placeholder {
  font-size: 24px;
  color: rgba(30, 58, 95, 0.35);
  font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
  font-style: normal;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 1s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
