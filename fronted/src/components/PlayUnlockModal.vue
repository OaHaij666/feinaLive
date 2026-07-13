<script setup lang="ts">
defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  confirm: []
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="modal-overlay">
        <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="playback-unlock-title">
          <div class="modal-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18V5l10-2v13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.8"/><circle cx="16" cy="16" r="3" stroke="currentColor" stroke-width="1.8"/></svg></div>
          <h3 id="playback-unlock-title" class="modal-title">启用直播音频</h3>
          <p class="modal-desc">浏览器需要一次手动确认，才能播放主播语音和音乐。</p>
          <button class="modal-btn" @click="emit('confirm')">开始播放</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(240, 249, 255, 0.9));
  border-radius: 20px;
  padding: 40px 50px;
  text-align: center;
  box-shadow: 0 20px 60px rgba(59, 130, 246, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.5);
  max-width: 360px;
}

.modal-icon {
  width: 64px;
  height: 64px;
  margin-inline: auto;
  margin-bottom: 16px;
  padding: 14px;
  color: #2563eb;
  border-radius: 18px;
  background: rgba(59, 130, 246, .1);
}
.modal-icon svg { width: 100%; height: 100%; }

.modal-title {
  font-size: 22px;
  font-weight: 700;
  color: #1e3a5f;
  margin: 0 0 10px;
}

.modal-desc {
  font-size: 14px;
  color: #4a6a8a;
  margin: 0 0 24px;
}

.modal-btn {
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  color: #fff;
  border: none;
  padding: 12px 40px;
  border-radius: 25px;
  font-size: 16px;
  font-weight: 600;
  min-height: 48px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
}

.modal-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
}

.modal-enter-active,
.modal-leave-active {
  transition: all 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.9);
}
</style>
