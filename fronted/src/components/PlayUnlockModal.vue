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
      <div v-if="visible" class="modal-overlay" @click="emit('confirm')">
        <div class="modal-content" @click.stop>
          <div class="modal-icon">🎵</div>
          <h3 class="modal-title">音乐播放器</h3>
          <p class="modal-desc">点击任意位置开始播放音乐</p>
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
  font-size: 60px;
  margin-bottom: 16px;
}

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
