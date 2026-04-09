<template>
  <div class="bottom-decoration">
    <!-- 底部光晕线 -->
    <div class="bottom-glow-line"></div>
    
    <div class="flowers-left">
      <svg width="140" height="110" viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="stemGradientLeft" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#93c5fd"/>
            <stop offset="100%" stop-color="#60a5fa"/>
          </linearGradient>
          <radialGradient id="flowerGlowLeft">
            <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.6"/>
            <stop offset="100%" stop-color="#60a5fa" stop-opacity="0"/>
          </radialGradient>
        </defs>
        
        <ellipse cx="30" cy="88" rx="28" ry="10" fill="rgba(147, 197, 253, 0.35)"/>
        <path d="M20 85 Q25 58 35 72 Q40 52 45 68 Q52 54 56 74 Q62 60 68 82" 
              stroke="url(#stemGradientLeft)" stroke-width="2.5" fill="none" opacity="0.7"
              stroke-linecap="round"/>
        
        <circle cx="26" cy="70" r="9" fill="url(#flowerGlowLeft)"/>
        <circle cx="26" cy="70" r="7" fill="#93c5fd" opacity="0.65"/>
        <circle cx="26" cy="70" r="4" fill="#60a5fa" opacity="0.8"/>
        
        <circle cx="42" cy="64" r="7" fill="url(#flowerGlowLeft)"/>
        <circle cx="42" cy="64" r="5.5" fill="#93c5fd" opacity="0.55"/>
        <circle cx="42" cy="64" r="3" fill="#60a5fa" opacity="0.75"/>
        
        <circle cx="54" cy="72" r="8" fill="url(#flowerGlowLeft)"/>
        <circle cx="54" cy="72" r="6" fill="#93c5fd" opacity="0.6"/>
        <circle cx="54" cy="72" r="3.5" fill="#60a5fa" opacity="0.78"/>
        
        <circle cx="66" cy="78" r="6" fill="url(#flowerGlowLeft)"/>
        <circle cx="66" cy="78" r="4.5" fill="#93c5fd" opacity="0.5"/>
        <circle cx="66" cy="78" r="2.5" fill="#60a5fa" opacity="0.7"/>
      </svg>
    </div>
    
    <div class="flowers-right">
      <svg width="140" height="110" viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg" style="transform: scaleX(-1)">
        <defs>
          <linearGradient id="stemGradientRight" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#93c5fd"/>
            <stop offset="100%" stop-color="#60a5fa"/>
          </linearGradient>
          <radialGradient id="flowerGlowRight">
            <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.6"/>
            <stop offset="100%" stop-color="#60a5fa" stop-opacity="0"/>
          </radialGradient>
        </defs>
        
        <ellipse cx="30" cy="88" rx="28" ry="10" fill="rgba(147, 197, 253, 0.35)"/>
        <path d="M20 85 Q25 58 35 72 Q40 52 45 68 Q52 54 56 74 Q62 60 68 82" 
              stroke="url(#stemGradientRight)" stroke-width="2.5" fill="none" opacity="0.7"
              stroke-linecap="round"/>
        
        <circle cx="26" cy="70" r="9" fill="url(#flowerGlowRight)"/>
        <circle cx="26" cy="70" r="7" fill="#93c5fd" opacity="0.65"/>
        <circle cx="26" cy="70" r="4" fill="#60a5fa" opacity="0.8"/>
        
        <circle cx="42" cy="64" r="7" fill="url(#flowerGlowRight)"/>
        <circle cx="42" cy="64" r="5.5" fill="#93c5fd" opacity="0.55"/>
        <circle cx="42" cy="64" r="3" fill="#60a5fa" opacity="0.75"/>
        
        <circle cx="54" cy="72" r="8" fill="url(#flowerGlowRight)"/>
        <circle cx="54" cy="72" r="6" fill="#93c5fd" opacity="0.6"/>
        <circle cx="54" cy="72" r="3.5" fill="#60a5fa" opacity="0.78"/>
        
        <circle cx="66" cy="78" r="6" fill="url(#flowerGlowRight)"/>
        <circle cx="66" cy="78" r="4.5" fill="#93c5fd" opacity="0.5"/>
        <circle cx="66" cy="78" r="2.5" fill="#60a5fa" opacity="0.7"/>
      </svg>
    </div>

    <!-- 中央装饰 -->
    <div class="center-ornament">
      <div class="ornament-dot"></div>
      <div class="ornament-ring"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.bottom-decoration {
  width: 100%;
  height: 110px;
  position: absolute;
  bottom: 70px;
  left: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding: 0 20px;
}

.bottom-glow-line {
  position: absolute;
  bottom: -2px;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg,
    transparent,
    #93c5fd 15%,
    #60a5fa 40%,
    #3b82f6 50%,
    #60a5fa 60%,
    #93c5fd 85%,
    transparent
  );
  box-shadow: 
    0 -2px 12px rgba(59, 130, 246, 0.3),
    0 0 20px rgba(96, 165, 250, 0.2);
}

.flowers-left,
.flowers-right {
  animation: gentle-sway 5s ease-in-out infinite;
  opacity: 0.95;
  filter: drop-shadow(0 4px 8px rgba(96, 165, 250, 0.25));
}

.flowers-right {
  animation-delay: -2s;
}

.center-ornament {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
}

.ornament-dot {
  width: 8px;
  height: 8px;
  background: radial-gradient(circle, #60a5fa, #3b82f6);
  border-radius: 50%;
  animation: pulse-glow 3s ease-in-out infinite;
  box-shadow: 0 0 12px rgba(96, 165, 250, 0.6);
}

.ornament-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 18px;
  height: 18px;
  border: 2px solid rgba(147, 197, 253, 0.4);
  border-radius: 50%;
  animation: gentle-sway 4s ease-in-out infinite reverse;
}
</style>
