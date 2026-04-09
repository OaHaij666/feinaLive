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

      <div class="placeholder-content">
        <div class="icon-wrapper">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="ratio-text">16:9</div>
        <div class="screen-text">Screen Capture</div>
        <div class="live-indicator">
          <span class="dot"></span>
          <span>LIVE</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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
  z-index: 2;
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

.live-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 16px;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 20px;
  animation: scale-in 0.5s ease-out;
}

.live-indicator .dot {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: blink 1s step-end infinite;
  box-shadow: 0 0 10px rgba(239, 68, 68, 0.6);
}

.live-indicator span:last-child {
  font-size: 13px;
  font-weight: 700;
  color: #ef4444;
  letter-spacing: 2px;
}
</style>
