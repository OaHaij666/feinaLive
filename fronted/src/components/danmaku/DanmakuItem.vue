<template>
  <div 
    class="danmaku-item"
    :class="[`type-${message.type}`, { 'has-badge': message.badge }]"
  >
    <div class="user-info">
      <span class="username" :style="{ color: message.color || undefined }">
        {{ message.user }}
      </span>
      <span v-if="message.badge" class="badge">{{ message.badge }}</span>
    </div>
    <div class="message-content">{{ message.content }}</div>
  </div>
</template>

<script setup lang="ts">
import type { DanmakuMessage } from '@/types/danmaku'

defineProps<{
  message: DanmakuMessage
}>()
</script>

<style scoped>
.danmaku-item {
  padding: 9px 11px;
  background: rgba(255, 255, 255, 0.75);
  border-radius: 10px;
  border-left: 3px solid #a8c4e8;
  flex-shrink: 0;
}

.type-highlight {
  border-left-color: #6b8cce;
  background: rgba(107, 140, 206, 0.15);
}

.type-gift {
  border-left-color: #d4a574;
  background: rgba(212, 165, 116, 0.15);
}

.type-welcome {
  border-left-color: #9b8ec4;
  background: rgba(155, 142, 196, 0.15);
}

.type-system {
  border-left-color: #888;
  background: rgba(136, 136, 136, 0.12);
  font-style: italic;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.username {
  font-size: 13px;
  font-weight: 600;
  color: #4a6aa8;
}

.badge {
  font-size: 10px;
  padding: 1px 5px;
  background: linear-gradient(135deg, #6b8cce, #a8c4e8);
  color: white;
  border-radius: 3px;
  font-weight: 500;
}

.message-content {
  font-size: 14px;
  line-height: 1.45;
  color: #4a5a6a;
  word-break: break-word;
}
</style>
