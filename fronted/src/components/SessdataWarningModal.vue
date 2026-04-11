<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="handleIgnore">
      <div class="modal-content">
        <div class="modal-header">
          <span class="warning-icon">⚠️</span>
          <h3>B站 SESSDATA 验证失败</h3>
        </div>
        <div class="modal-body">
          <p class="error-message">{{ errorMessage }}</p>
          <p class="hint">填写有效的 SESSDATA 后才能获取评论等功能</p>
          <div class="input-group">
            <label>SESSDATA:</label>
            <input
              v-model="sessdataInput"
              type="text"
              placeholder="粘贴 SESSDATA..."
              @keyup.enter="handleUpdate"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ignore" @click="handleIgnore">忽略</button>
          <button class="btn-update" @click="handleUpdate" :disabled="!sessdataInput">更新</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  ignore: []
  update: [sessdata: string]
}>()

const sessdataInput = ref('')

watch(() => props.visible, (newVal) => {
  if (newVal) {
    sessdataInput.value = ''
  }
})

function handleIgnore() {
  emit('ignore')
}

function handleUpdate() {
  if (sessdataInput.value.trim()) {
    emit('update', sessdataInput.value.trim())
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 24px;
  max-width: 420px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.warning-icon {
  font-size: 28px;
}

.modal-header h3 {
  color: #1f2937;
  font-size: 18px;
  font-weight: 600;
}

.modal-body {
  margin-bottom: 20px;
}

.error-message {
  color: #dc2626;
  font-size: 14px;
  margin-bottom: 8px;
}

.hint {
  color: #6b7280;
  font-size: 13px;
  margin-bottom: 16px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-group label {
  font-size: 13px;
  color: #374151;
  font-weight: 500;
}

.input-group input {
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  width: 100%;
}

.input-group input:focus {
  border-color: #3b82f6;
  outline: none;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-ignore,
.btn-update {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-ignore {
  background: #f3f4f6;
  color: #4b5563;
  border: 1px solid #d1d5db;
}

.btn-ignore:hover {
  background: #e5e7eb;
}

.btn-update {
  background: #3b82f6;
  color: white;
  border: none;
}

.btn-update:hover:not(:disabled) {
  background: #2563eb;
}

.btn-update:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}
</style>
