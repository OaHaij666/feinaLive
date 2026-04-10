<script setup lang="ts">
import { useNotification } from '@/utils/notification'

const { notifications, remove } = useNotification()

function getIcon(type: string) {
  switch (type) {
    case 'success': return '✓'
    case 'error': return '✕'
    case 'warning': return '⚠'
    case 'info': return 'ℹ'
    default: return ''
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="notification-container">
      <TransitionGroup name="notification">
        <div
          v-for="n in notifications"
          :key="n.id"
          :class="['notification', `notification-${n.type}`]"
          @click="remove(n.id)"
        >
          <span class="notification-icon">{{ getIcon(n.type) }}</span>
          <span class="notification-message">{{ n.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.notification-container {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.notification {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  color: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  pointer-events: auto;
  backdrop-filter: blur(10px);
}

.notification-success { background: rgba(82, 196, 26, 0.9); }
.notification-error { background: rgba(250, 81, 81, 0.9); }
.notification-warning { background: rgba(250, 173, 20, 0.9); }
.notification-info { background: rgba(64, 158, 255, 0.9); }

.notification-icon {
  font-size: 16px;
  font-weight: bold;
}

.notification-enter-active,
.notification-leave-active {
  transition: all 0.3s ease;
}

.notification-enter-from {
  opacity: 0;
  transform: translateX(100px);
}

.notification-leave-to {
  opacity: 0;
  transform: translateX(100px);
}
</style>
