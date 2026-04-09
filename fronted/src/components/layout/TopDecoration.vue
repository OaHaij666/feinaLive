<template>
  <div class="top-decoration">
    <div class="lace-border"></div>
    <div class="glow-line"></div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.top-decoration {
  width: 100%;
  height: 30px;
  position: relative;
}

.lace-border {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg,
    transparent,
    #93c5fd 15%,
    #60a5fa 35%,
    #3b82f6 50%,
    #60a5fa 65%,
    #93c5fd 85%,
    transparent
  );
  box-shadow: 
    0 2px 12px rgba(59, 130, 246, 0.35),
    0 0 20px rgba(96, 165, 250, 0.2);
}

.glow-line {
  position: absolute;
  top: 3px;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg,
    transparent,
    rgba(255, 255, 255, 0.6) 20%,
    rgba(255, 255, 255, 0.8) 50%,
    rgba(255, 255, 255, 0.6) 80%,
    transparent
  );
  animation: shimmer 4s linear infinite;
  background-size: 200% 100%;
}
</style>
