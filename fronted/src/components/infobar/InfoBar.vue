<template>
  <div class="info-bar">
    <!-- 光晕效果 -->
    <div class="bar-glow"></div>
    
    <div class="info-container">
      <ClockDisplay />
      <MarqueeText />
      <NoticeBadge />
    </div>
  </div>
</template>

<script setup lang="ts">
import ClockDisplay from './ClockDisplay.vue'
import MarqueeText from './MarqueeText.vue'
import NoticeBadge from './NoticeBadge.vue'
</script>

<style scoped>
.info-bar {
  position: absolute;
  bottom: 10px;
  left: 20px;
  right: 20px;
  height: 64px;
}

.info-container {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.45) 0%, rgba(240, 249, 255, 0.38) 100%);
  backdrop-filter: blur(2.4px);
  -webkit-backdrop-filter: blur(2.4px);
  border: 1.5px solid rgba(255, 255, 255, 0.35);
  border-radius: 32px;
  display: flex;
  align-items: center;
  padding: 0 28px;
  gap: 18px;
  position: relative;
  overflow: hidden;
  box-shadow: 
    0 10px 40px rgba(59, 130, 246, 0.15),
    inset 0 1px 2px rgba(255, 255, 255, 0.8),
    inset 0 -1px 2px rgba(147, 197, 253, 0.2);
}

.info-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 200%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.3),
    transparent
  );
  animation: shimmer 5s linear infinite;
}

.bar-glow {
  position: absolute;
  bottom: -50%;
  left: 50%;
  transform: translateX(-50%);
  width: 80%;
  height: 200%;
  background: radial-gradient(ellipse at center, rgba(96, 165, 250, 0.08), transparent);
  pointer-events: none;
}
</style>
