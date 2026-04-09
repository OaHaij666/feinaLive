<template>
  <div class="clock-display">
    <span class="time-label">TIME</span>
    <span class="time-value">{{ formattedTime }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useStreamStore } from '@/stores/stream'

const streamStore = useStreamStore()

const formattedTime = computed(() => streamStore.currentTime)
</script>

<style scoped>
.clock-display {
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  flex-shrink: 0;
}

.time-label {
  font-size: 11px;
  font-weight: 600;
  color: #8a9ab0;
  letter-spacing: 1px;
}

.time-value {
  font-size: 18px;
  font-weight: 500;
  color: #4a6aa8;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 1px;
}
</style>
