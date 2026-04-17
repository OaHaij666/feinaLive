<template>
  <div class="app-container">
    <div class="live-stream-layout" :style="layoutStyle">
      <!-- 全局背景层 -->
      <div class="bg-layer"></div>

      <!-- 粒子动画层 -->
      <div class="particles-container">
        <div
          v-for="(particle, index) in particles"
          :key="index"
          class="particle"
          :style="particle.style"
        ></div>
      </div>

      <!-- 光晕效果 -->
      <div class="glow-orb glow-orb-1"></div>
      <div class="glow-orb glow-orb-2"></div>
      <div class="glow-orb glow-orb-3"></div>

      <!-- 顶部装饰 -->
      <TopDecoration />

      <!-- AI主播开关 -->
      <button class="avatar-toggle-btn" @click="toggleAvatar" :class="{ active: avatarRunning }">
        <span class="avatar-toggle-icon">{{ avatarRunning ? '🎮' : '⏸' }}</span>
        <span class="avatar-toggle-text">{{ avatarRunning ? 'AI主播' : 'AI停止' }}</span>
      </button>

      <!-- 主内容区 -->
      <div class="main-content">
        <MainView />
        <DanmakuPanel />
      </div>

      <!-- 底部信息窗口区 -->
      <div class="bottom-panels">
        <MissionPanel />
        <PlaceholderPanel />
      </div>

      <!-- 底部装饰 -->
      <BottomDecoration />

      <!-- 通知提示组件 -->
      <NotificationToast />

      <!-- SESSDATA警告弹窗 -->
      <SessdataWarningModal
        :visible="showSessdataWarning"
        :error-message="sessdataError"
        @ignore="handleSessdataIgnore"
        @update="handleSessdataUpdate"
      />

      <!-- 音乐播放解锁弹窗 -->
      <PlayUnlockModal :visible="showPlayUnlock" @confirm="handlePlayUnlock" />

      <!-- 信息栏 -->
      <InfoBar />

      <!-- 设置面板 -->
      <SettingsPanel :visible="showSettings" @close="toggleSettings" />

      <!-- 测试面板 -->
      <DanmakuTestPanel :visible="showTestPanel" @close="showTestPanel = false" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, onUnmounted, reactive } from 'vue'
import TopDecoration from './components/layout/TopDecoration.vue'
import BottomDecoration from './components/layout/BottomDecoration.vue'
import MainView from './components/mainview/MainView.vue'
import DanmakuPanel from './components/danmaku/DanmakuPanel.vue'
import InfoBar from './components/infobar/InfoBar.vue'
import MissionPanel from './components/panels/MissionPanel.vue'
import PlaceholderPanel from './components/panels/PlaceholderPanel.vue'
import NotificationToast from './components/NotificationToast.vue'
import PlayUnlockModal from './components/PlayUnlockModal.vue'
import SessdataWarningModal from './components/SessdataWarningModal.vue'

import SettingsPanel from './components/SettingsPanel.vue'
import DanmakuTestPanel from './components/DanmakuTestPanel.vue'
import { useDanmakuStore } from '@/stores/danmaku'
import { useStreamStore } from '@/stores/stream'
import { useMusicStore } from '@/stores/music'
import { useAvatarInput } from '@/composables/useAvatarInput'
import { storeToRefs } from 'pinia'

const danmakuStore = useDanmakuStore()
const streamStore = useStreamStore()
const musicStore = useMusicStore()
const avatarInput = useAvatarInput()
const { current, isPlaying, audioUnlocked } = storeToRefs(musicStore)

const showPlayUnlock = computed(() => {
  const hasCurrent = !!current.value
  const locked = !audioUnlocked.value
  const notPlaying = !isPlaying.value
  console.log('[MusicModal] current:', hasCurrent, 'locked:', locked, 'notPlaying:', notPlaying)
  return locked && notPlaying
})

const showSessdataWarning = ref(false)
const sessdataError = ref('')
const sessdataIgnored = ref(false)
const showSettings = ref(false)
const showTestPanel = ref(false)
const avatarRunning = ref(false)
const bilibiliRoomId = ref<number | null>(null)

async function fetchConfig() {
  try {
    const res = await fetch('/config')
    const data = await res.json()
    const roomId = data.bilibili?.room_id || data.host?.room_id || null
    bilibiliRoomId.value = roomId
  } catch (e) {
    console.error('Failed to fetch config:', e)
  }
}

async function toggleAvatar() {
  try {
    if (avatarRunning.value) {
      await fetch('/api/easyvtuber/avatar/stop', { method: 'POST' })
      avatarRunning.value = false
    } else {
      await fetch('/api/easyvtuber/avatar/start', { method: 'POST' })
      avatarRunning.value = true
    }
  } catch (e) {
    console.error('Avatar toggle error:', e)
  }
}

async function checkAvatarStatus() {
  try {
    const res = await fetch('/api/easyvtuber/avatar/status')
    const data = await res.json()
    avatarRunning.value = data.running
  } catch (e) {
    console.error('Avatar status error:', e)
  }
}

function toggleSettings() {
  showSettings.value = !showSettings.value
}

async function checkSessdata() {
  try {
    const res = await fetch('/api/bilibili/sessdata/verify')
    const data = await res.json()
    if (!data.valid) {
      sessdataError.value = data.error || 'SESSDATA无效'
      if (!sessdataIgnored.value) {
        showSessdataWarning.value = true
      }
    } else {
      console.log('[SESSDATA] 验证成功:', data.uname)
    }
  } catch (e) {
    console.error('[SESSDATA] 验证请求失败:', e)
  }
}

function handleSessdataIgnore() {
  sessdataIgnored.value = true
  showSessdataWarning.value = false
}

async function handleSessdataUpdate(newSessdata: string) {
  try {
    const res = await fetch('/api/bilibili/sessdata/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newSessdata),
    })
    const data = await res.json()
    if (data.success) {
      showSessdataWarning.value = false
      sessdataIgnored.value = false
      await checkSessdata()
    } else {
      alert('更新失败: ' + (data.error || '未知错误'))
    }
  } catch (e) {
    alert('更新失败: ' + e)
  }
}

function handlePlayUnlock() {
  musicStore.unlockAndPlay()
}

const baseWidth = 1920
const baseHeight = 1080

const scale = ref(1)

const particles = reactive(
  Array.from({ length: 20 }, (_, i) => ({
    style: {
      left: `${Math.random() * 100}%`,
      animationDelay: `${Math.random() * 8}s`,
      animationDuration: `${6 + Math.random() * 6}s`,
      width: `${4 + Math.random() * 8}px`,
      height: `${4 + Math.random() * 8}px`,
      opacity: 0.3 + Math.random() * 0.5,
    },
  }))
)

function updateScale() {
  const scaleX = window.innerWidth / baseWidth
  const scaleY = window.innerHeight / baseHeight
  scale.value = Math.min(scaleX, scaleY)
}

const layoutStyle = computed(() => ({
  transform: `translate(-50%, -50%) scale(${scale.value})`
}))

onMounted(() => {
  streamStore.startClock()
  updateScale()
  window.addEventListener('resize', updateScale)
  checkSessdata()
  checkAvatarStatus()
  avatarInput.connect()
  fetchConfig().then(() => {
    if (bilibiliRoomId.value) {
      danmakuStore.connectToRoom(bilibiliRoomId.value)
    }
  })
  
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'S') {
      e.preventDefault()
      toggleSettings()
    }
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
      e.preventDefault()
      showTestPanel.value = !showTestPanel.value
    }
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', updateScale)
  avatarInput.disconnect()
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  outline: none;
  border: none;
}

html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border: none;
  outline: none;
}
</style>

<style scoped>
.app-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(135deg, #e0f2fe 0%, #dbeafe 50%, #ede9fe 100%);
}

.live-stream-layout {
  width: 1920px;
  height: 1080px;
  position: absolute;
  left: 50%;
  top: 50%;
  overflow: hidden;
  background: transparent;
  transform-origin: 50% 50%;
}

.bg-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: url('./pic/bg.jpg');
  background-size: cover;
  background-position: center;
  opacity: 0.75;
  filter: blur(1.4px) brightness(0.7);
  z-index: 0;
}

.particles-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 1;
  overflow: hidden;
}

.particle {
  position: absolute;
  bottom: -20px;
  background: radial-gradient(circle, rgba(147, 197, 253, 0.8), rgba(59, 130, 246, 0.4));
  border-radius: 50%;
  animation: float-particle linear infinite;
  box-shadow: 0 0 10px rgba(147, 197, 253, 0.6), 0 0 20px rgba(59, 130, 246, 0.3);
}

.glow-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.4;
  pointer-events: none;
  z-index: 0;
  animation: pulse-glow 8s ease-in-out infinite;
}

.glow-orb-1 {
  width: 400px;
  height: 400px;
  top: 10%;
  right: 15%;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.5), transparent);
  animation-delay: 0s;
}

.glow-orb-2 {
  width: 300px;
  height: 300px;
  bottom: 20%;
  left: 10%;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.4), transparent);
  animation-delay: -3s;
}

.glow-orb-3 {
  width: 350px;
  height: 350px;
  top: 50%;
  left: 45%;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.4), transparent);
  animation-delay: -5s;
}

.main-content {
  display: flex;
  gap: 20px;
  padding: 15px 40px 10px 40px;
  height: calc(1080px - 30px - 180px - 70px);
  position: relative;
  z-index: 2;
}

.bottom-panels {
  position: absolute;
  top: 840px;
  left: 40px;
  display: flex;
  gap: 16px;
  z-index: 99;
}

.avatar-toggle-btn {
  position: absolute;
  top: 12px;
  left: 16px;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 20px;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.2s, background 0.2s;
  font-size: 12px;
  color: #666;
}

.avatar-toggle-btn:hover {
  opacity: 0.8;
  background: rgba(255, 255, 255, 0.25);
}

.avatar-toggle-btn.active {
  opacity: 0.9;
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.4);
  color: #3b82f6;
}

.avatar-toggle-icon {
  font-size: 14px;
}

.avatar-toggle-text {
  font-weight: 500;
}
</style>
