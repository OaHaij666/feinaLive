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

      <!-- 视频占位区域（纯黑色背景） -->
      <div class="video-placeholder" :class="`ratio-${videoRatio.replace(':', '-')}`">
        <!-- 比例切换按钮（居中） -->
        <div class="ratio-toggle-center">
          <button class="ratio-toggle-btn" @click="toggleRatio" title="切换视频比例">
            <span class="ratio-label">{{ videoRatio }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const videoRatio = ref<'16:9' | '16:10' | '4:3'>('16:9')

function toggleRatio() {
  if (videoRatio.value === '16:9') {
    videoRatio.value = '16:10'
  } else if (videoRatio.value === '16:10') {
    videoRatio.value = '4:3'
  } else {
    videoRatio.value = '16:9'
  }
}
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
  border-radius: 0;
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
  border-radius: 0;
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
}

.corner-tr {
  top: 10px;
  right: 10px;
  border-top-color: #60a5fa;
  border-right-color: #60a5fa;
}

.corner-bl {
  bottom: 10px;
  left: 10px;
  border-bottom-color: #60a5fa;
  border-left-color: #60a5fa;
}

.corner-br {
  bottom: 10px;
  right: 10px;
  border-bottom-color: #60a5fa;
  border-right-color: #60a5fa;
}

/* 视频占位区域样式 */
.video-placeholder {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 16:9 比例 */
.video-placeholder.ratio-16-9 {
  width: 100%;
  height: 100%;
}

/* 16:10 比例 - 视频区域黑色，外层渐变美化 */
.video-placeholder.ratio-16-10 {
  width: auto;
  height: 100%;
  aspect-ratio: 16 / 10;
  background: #000;
  box-shadow:
    0 0 0 100vmax linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(59, 130, 246, 0.15) 50%, rgba(6, 182, 212, 0.15) 100%);
}

/* 4:3 比例 - 视频区域黑色，外层渐变美化 */
.video-placeholder.ratio-4-3 {
  width: auto;
  height: 100%;
  aspect-ratio: 4 / 3;
  background: #000;
  box-shadow:
    0 0 0 100vmax linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(59, 130, 246, 0.15) 50%, rgba(6, 182, 212, 0.15) 100%);
}

/* 比例切换按钮（居中） */
.ratio-toggle-center {
  z-index: 100;
  pointer-events: none;
}

.ratio-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 32px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(12px);
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 0;
  color: white;
  cursor: pointer;
  font-size: 24px;
  font-weight: 600;
  transition: all 0.2s ease;
  pointer-events: auto;
  letter-spacing: 2px;
}

.ratio-toggle-btn:hover {
  background: rgba(59, 130, 246, 0.9);
  border-color: rgba(59, 130, 246, 0.8);
  transform: scale(1.05);
}

.ratio-label {
  font-family: 'Courier New', monospace;
  letter-spacing: 3px;
}

@keyframes border-flow {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
</style>
