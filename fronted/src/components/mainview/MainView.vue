<template>
  <div class="main-view">
    <div class="view-container">
      <!-- 动态边框效果 -->
      <div class="border-glow"></div>

      <!-- 角落装饰 -->
      <div class="corner corner-tl"></div>
      <div class="corner corner-tr"></div>
      <div class="corner corner-bl"></div>
      <div class="corner corner-br"></div>

      <!-- 视频播放器 -->
      <div v-if="streamUrl" class="video-wrapper">
        <video
          ref="videoRef"
          class="video-player"
          controls
          autoplay
          playsinline
        ></video>

        <!-- 加载状态 -->
        <div v-if="isLoading" class="loading-overlay">
          <div class="spinner"></div>
          <span>正在连接直播源...</span>
        </div>

        <!-- 错误状态 -->
        <div v-if="error" class="error-overlay">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
            <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <span>{{ error }}</span>
          <button @click="retryConnection" class="retry-btn">重试</button>
        </div>

        <!-- LIVE 标签 -->
        <div v-if="isPlaying" class="live-badge">
          <span class="dot"></span>
          <span>LIVE</span>
        </div>
      </div>

      <!-- 占位符（无流时显示） -->
      <div v-else class="placeholder-content">
        <div class="icon-wrapper">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="ratio-text">{{ resolution }}</div>
        <div class="screen-text">{{ isLoading ? '正在连接...' : '等待推流' }}</div>
        <div class="stream-info">
          <span>{{ streamInfo }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useHlsPlayer } from '@/composables/useHlsPlayer'

const streamUrl = ref<string | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
const streamInfo = ref('流服务未启动')
const resolution = ref('16:9')

const {
  isPlaying,
  isLoading,
  error,
  initPlayer,
  destroyPlayer,
} = useHlsPlayer()

async function fetchStreamUrl() {
  try {
    const response = await fetch('/stream/status')
    const data = await response.json()

    if (data.nginx_running && data.urls) {
      const fullUrl = data.urls.hls_url
      const url = new URL(fullUrl)
      streamUrl.value = url.pathname
      streamInfo.value = `HLS: ${streamUrl.value}`
    } else {
      streamUrl.value = null
      streamInfo.value = '流服务未启动'
    }
  } catch (e) {
    streamInfo.value = '无法连接到后端'
    console.error('Failed to fetch stream status:', e)
  }
}

function retryConnection() {
  if (streamUrl.value && videoRef.value) {
    destroyPlayer()
    initPlayer(videoRef.value, streamUrl.value)
  }
}

onMounted(async () => {
  await fetchStreamUrl()

  if (streamUrl.value && videoRef.value) {
    initPlayer(videoRef.value, streamUrl.value)
  } else {
    isLoading.value = false
  }
})

onUnmounted(() => {
  destroyPlayer()
})

defineExpose({
  streamUrl,
})
</script>

<style scoped>
.main-view {
  width: 1369px;
  height: 100%;
  flex-shrink: 0;
}

.view-container {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.42) 0%, rgba(240, 249, 255, 0.35) 50%, rgba(224, 242, 254, 0.32) 100%);
  backdrop-filter: blur(2.4px);
  -webkit-backdrop-filter: blur(2.4px);
  border-radius: 20px;
  position: relative;
  overflow: hidden;
  box-shadow:
    0 10px 40px rgba(59, 130, 246, 0.15),
    0 0 0 1.5px rgba(255, 255, 255, 0.35),
    inset 0 1px 2px rgba(255, 255, 255, 0.8),
    inset 0 -1px 2px rgba(147, 197, 253, 0.2);
}

.view-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    repeating-linear-gradient(
      45deg,
      transparent,
      transparent 12px,
      rgba(147, 197, 253, 0.04) 12px,
      rgba(147, 197, 253, 0.04) 13px
    );
  pointer-events: none;
}

.border-glow {
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: -2px;
  border-radius: 22px;
  background: linear-gradient(45deg,
    #60a5fa,
    #3b82f6,
    #8b5cf6,
    #06b6d4,
    #60a5fa
  );
  background-size: 300% 300%;
  animation: border-flow 6s linear infinite;
  z-index: -1;
  opacity: 0.6;
  filter: blur(8px);
}

.corner {
  position: absolute;
  width: 30px;
  height: 30px;
  border: 3px solid transparent;
  z-index: 10;
}

.corner-tl {
  top: 10px;
  left: 10px;
  border-top-color: #60a5fa;
  border-left-color: #60a5fa;
  border-top-left-radius: 8px;
}

.corner-tr {
  top: 10px;
  right: 10px;
  border-top-color: #60a5fa;
  border-right-color: #60a5fa;
  border-top-right-radius: 8px;
}

.corner-bl {
  bottom: 10px;
  left: 10px;
  border-bottom-color: #60a5fa;
  border-left-color: #60a5fa;
  border-bottom-left-radius: 8px;
}

.corner-br {
  bottom: 10px;
  right: 10px;
  border-bottom-color: #60a5fa;
  border-right-color: #60a5fa;
  border-bottom-right-radius: 8px;
}

/* 视频播放器样式 */
.video-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  gap: 16px;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(255, 255, 255, 0.3);
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  padding: 8px 24px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
}

.retry-btn:hover {
  background: #2563eb;
}

.live-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(239, 68, 68, 0.9);
  border-radius: 6px;
  color: white;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
}

.live-badge .dot {
  width: 6px;
  height: 6px;
  background: white;
  border-radius: 50%;
  animation: blink 1s step-end infinite;
}

/* 占位符样式 */
.placeholder-content {
  text-align: center;
  color: #3b82f6;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.icon-wrapper {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.2), transparent);
  border-radius: 50%;
  animation: pulse-glow 3s ease-in-out infinite;
  margin-bottom: 8px;
}

.icon-wrapper svg {
  color: #3b82f6;
  opacity: 0.7;
}

.ratio-text {
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 4px;
  opacity: 0.8;
  text-shadow: 0 2px 10px rgba(59, 130, 246, 0.2);
}

.screen-text {
  font-size: 18px;
  font-weight: 500;
  opacity: 0.5;
  letter-spacing: 3px;
  text-transform: uppercase;
}

.stream-info {
  margin-top: 12px;
  padding: 8px 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  font-size: 12px;
  color: #60a5fa;
  word-break: break-all;
  max-width: 80%;
}

@keyframes border-flow {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

@keyframes pulse-glow {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.05); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@keyframes scale-in {
  from { transform: scale(0.8); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
</style>
