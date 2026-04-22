<template>
  <div class="marquee-wrapper">
    <div class="marquee-separator">▌</div>
    <div class="marquee-container">
      <div class="marquee-text" :style="{ animationDuration: `${duration}s` }">
        {{ text }}<span class="spacer"></span>{{ text }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useStreamStore } from '@/stores/stream'

const streamStore = useStreamStore()

const text = computed(() => streamStore.announcement)

const duration = computed(() => {
  const baseDuration = 20
  const lengthMultiplier = Math.max(text.value.length / 50, 1)
  return baseDuration * lengthMultiplier
})
</script>

<style scoped>
.marquee-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  overflow: hidden;
  min-width: 0;
}

.marquee-separator {
  color: #6b8cce;
  font-size: 18px;
  margin-right: 12px;
  font-weight: 300;
}

.marquee-container {
  overflow: hidden;
  flex: 1;
}

.marquee-text {
  display: inline-block;
  white-space: nowrap;
  animation: marquee linear infinite;
  color: #4a5a6a;
  font-size: 14px;
  line-height: 1.5;
}

.spacer {
  display: inline-block;
  width: 800px;
}

@keyframes marquee {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-50%);
  }
}
</style>
