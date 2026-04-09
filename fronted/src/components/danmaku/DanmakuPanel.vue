<template>
  <div class="danmaku-panel">
    <!-- 动态光晕边框 -->
    <div class="panel-glow"></div>
    
    <div class="panel-header">
      <div class="header-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <h3 class="panel-title">實時評論</h3>
      <div class="message-count">
        <span>{{ displayList.length }}</span>
      </div>
    </div>
    
    <div class="panel-body">
      <TransitionGroup 
        name="queue" 
        tag="div" 
        class="danmaku-queue"
        :css="false"
        @enter="onEnter"
        @leave="onLeave"
        @before-move="onBeforeMove"
        @move="onMove"
      >
        <DanmakuItem
          v-for="msg in displayList"
          :key="msg.id"
          :message="msg"
          :data-id="msg.id"
        />
      </TransitionGroup>
    </div>
    
    <div class="panel-footer">
      <div class="footer-decoration"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import DanmakuItem from './DanmakuItem.vue'
import { useDanmakuStore } from '@/stores/danmaku'
import type { DanmakuMessage } from '@/types/danmaku'

const danmakuStore = useDanmakuStore()

const { danmakuList } = storeToRefs(danmakuStore)

const displayList = computed(() => {
  return [...danmakuList.value]
    .sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
})

function onEnter(el: Element, done: () => void) {
  const element = el as HTMLElement
  const height = element.offsetHeight
  
  element.style.maxHeight = '0'
  element.style.opacity = '0'
  element.style.transform = 'translateY(60px)'
  element.style.overflow = 'hidden'
  
  requestAnimationFrame(() => {
    element.style.transition = 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)'
    element.style.maxHeight = `${height}px`
    element.style.opacity = '1'
    element.style.transform = 'translateY(0)'
    
    setTimeout(() => {
      element.style.transition = ''
      element.style.maxHeight = ''
      element.style.overflow = ''
      done()
    }, 400)
  })
}

function onLeave(el: Element, done: () => void) {
  const element = el as HTMLElement
  
  element.style.transition = 'all 0.35s ease-in'
  element.style.maxHeight = `${element.offsetHeight}px`
  element.style.opacity = '1'
  element.style.transform = 'translateY(0)'
  element.style.overflow = 'hidden'
  
  requestAnimationFrame(() => {
    element.style.maxHeight = '0'
    element.style.opacity = '0'
    element.style.transform = 'translateY(-60px)'
    element.style.marginBottom = '0'
    element.style.paddingTop = '0'
    element.style.paddingBottom = '0'
    
    setTimeout(() => {
      done()
    }, 350)
  })
}

function onBeforeMove(el: Element) {
  const element = el as HTMLElement
  element.style.transition = 'transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94)'
}

function onMove(el: Element, done: () => void) {
  setTimeout(done, 400)
}
</script>

<style scoped>
.danmaku-panel {
  width: 380px;
  height: 100%;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.45) 0%, rgba(240, 249, 255, 0.38) 100%);
  backdrop-filter: blur(2.4px);
  -webkit-backdrop-filter: blur(2.4px);
  border-radius: 20px;
  position: relative;
  overflow: hidden;
  box-shadow: 
    0 10px 40px rgba(59, 130, 246, 0.12),
    0 0 0 1.5px rgba(255, 255, 255, 0.35),
    inset 0 1px 2px rgba(255, 255, 255, 0.8),
    inset 0 -1px 2px rgba(147, 197, 253, 0.2);
  display: flex;
  flex-direction: column;
}

.panel-glow {
  position: absolute;
  top: -50%;
  right: -30%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.15), transparent 70%);
  pointer-events: none;
  animation: float 8s ease-in-out infinite;
}

.danmaku-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg,
    transparent,
    #60a5fa 20%,
    #3b82f6 50%,
    #60a5fa 80%,
    transparent
  );
  animation: shimmer 4s linear infinite;
  background-size: 200% 100%;
}

.panel-header {
  padding: 18px 24px;
  border-bottom: 2px solid rgba(147, 197, 253, 0.3);
  background: linear-gradient(180deg, rgba(147, 197, 253, 0.15), transparent);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
}

.header-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  border-radius: 10px;
  color: white;
  animation: pulse-glow 3s ease-in-out infinite;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.header-icon svg {
  width: 18px;
  height: 18px;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e3a5f;
  letter-spacing: 3px;
  flex: 1;
}

.message-count {
  min-width: 28px;
  height: 24px;
  padding: 0 8px;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
  animation: bounce-soft 2s ease-in-out infinite;
}

.panel-body {
  flex: 1;
  overflow: hidden;
  padding: 16px;
  position: relative;
}

.danmaku-queue {
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: flex-end;
  min-height: 100%;
}

.panel-footer {
  height: 44px;
  border-top: 2px solid rgba(147, 197, 253, 0.3);
  background: linear-gradient(0deg, rgba(147, 197, 253, 0.12), transparent);
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

.footer-decoration {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg,
    transparent,
    rgba(96, 165, 250, 0.4) 30%,
    rgba(59, 130, 246, 0.6) 50%,
    rgba(96, 165, 250, 0.4) 70%,
    transparent
  );
}
</style>
