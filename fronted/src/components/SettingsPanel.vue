<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="settings-overlay" @click.self="close">
        <div class="settings-panel">
          <div class="settings-header">
            <h2>设置</h2>
            <button class="close-btn" @click="close">&times;</button>
          </div>
          
          <div class="settings-tabs">
            <button 
              v-for="tab in tabs" 
              :key="tab.key"
              :class="['tab-btn', { active: activeTab === tab.key }]"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>
          
          <div class="settings-content">
            <div v-if="activeTab === 'host'" class="tab-content">
              <div class="form-group">
                <label>回复间隔 (秒)</label>
                <input type="number" v-model.number="config.host.reply_interval" min="1" max="60" />
              </div>
              <div class="form-group">
                <label>最大回复长度</label>
                <input type="number" v-model.number="config.host.max_reply_length" min="50" max="500" />
              </div>
              <div class="form-group">
                <label>温度</label>
                <input type="range" v-model.number="config.host.temperature" min="0" max="1" step="0.1" />
                <span class="range-value">{{ config.host.temperature }}</span>
              </div>
              <div class="form-group">
                <label>Top P</label>
                <input type="range" v-model.number="config.host.top_p" min="0" max="1" step="0.1" />
                <span class="range-value">{{ config.host.top_p }}</span>
              </div>
            </div>
            
            <div v-if="activeTab === 'tts'" class="tab-content">
              <div class="form-group">
                <label>TTS 语音</label>
                <select v-model="config.tts.voice">
                  <option value="zh-CN-XiaoxiaoNeural">晓晓 (女声)</option>
                  <option value="zh-CN-YunxiNeural">云希 (男声)</option>
                  <option value="zh-CN-YunyangNeural">云扬 (男声)</option>
                  <option value="zh-CN-XiaoyiNeural">晓伊 (女声)</option>
                </select>
              </div>
            </div>
            
            <div v-if="activeTab === 'easyvtuber'" class="tab-content">
              <div class="form-group">
                <label>
                  <input type="checkbox" v-model="config.easyvtuber.enabled" />
                  启用数字人
                </label>
              </div>
              
              <div class="form-group">
                <label>角色</label>
                <select v-model="config.easyvtuber.character">
                  <option v-for="char in characters" :key="char.name" :value="char.name">
                    {{ char.name }}
                  </option>
                </select>
              </div>
              
              <div class="form-group">
                <label>输入源</label>
                <select v-model="config.easyvtuber.input.type">
                  <option value="debug">调试模式</option>
                  <option value="webcam">摄像头</option>
                  <option value="mouse">鼠标控制</option>
                  <option value="openseeface">OpenSeeFace</option>
                </select>
              </div>
              
              <div class="form-group">
                <label>帧率</label>
                <select v-model.number="config.easyvtuber.performance.frame_rate">
                  <option :value="20">20 FPS</option>
                  <option :value="30">30 FPS</option>
                  <option :value="60">60 FPS</option>
                </select>
              </div>
              
              <div class="form-group">
                <label>插帧</label>
                <select v-model="config.easyvtuber.performance.interpolation">
                  <option value="off">关闭</option>
                  <option value="x2">2x</option>
                  <option value="x3">3x</option>
                  <option value="x4">4x</option>
                </select>
              </div>
              
              <div class="form-group">
                <label>超分辨率</label>
                <select v-model="config.easyvtuber.performance.super_resolution">
                  <option value="off">关闭</option>
                  <option value="anime4k">Anime4K</option>
                  <option value="waifu2x">Waifu2x</option>
                  <option value="esrgan">Real-ESRGAN</option>
                </select>
              </div>
              
              <div class="form-group">
                <label>
                  <input type="checkbox" v-model="config.easyvtuber.model.use_tensorrt" />
                  使用 TensorRT 加速
                </label>
              </div>
              
              <div class="form-group">
                <label>WebSocket 端口</label>
                <input type="number" v-model.number="config.easyvtuber.output.websocket.port" min="1000" max="65535" />
              </div>
            </div>
          </div>
          
          <div class="settings-footer">
            <button class="btn btn-secondary" @click="resetConfig">重置</button>
            <button class="btn btn-primary" @click="saveConfig">保存</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

interface Props {
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()

const tabs = [
  { key: 'host', label: 'AI主播' },
  { key: 'tts', label: '语音' },
  { key: 'easyvtuber', label: '数字人' },
]

const activeTab = ref('host')
const characters = ref<{ name: string; path: string }[]>([])

const config = ref({
  host: {
    reply_interval: 5,
    max_reply_length: 100,
    model: 'doubao-seed-character-251128',
    temperature: 0.7,
    top_p: 0.9,
    max_tokens: 200,
    disable_thinking: true,
  },
  tts: {
    voice: 'zh-CN-XiaoxiaoNeural',
  },
  easyvtuber: {
    enabled: true,
    character: 'lambda_00',
    input: {
      type: 'debug',
      osf_address: '127.0.0.1:11573',
      mouse_range: '0,0,1920,1080',
    },
    model: {
      version: 'v3',
      precision: 'half',
      separable: true,
      use_tensorrt: true,
      use_eyebrow: true,
    },
    performance: {
      frame_rate: 30,
      interpolation: 'x2',
      super_resolution: 'off',
      ram_cache: '2gb',
      vram_cache: '2gb',
    },
    output: {
      websocket: {
        enabled: true,
        port: 8765,
        host: 'localhost',
      },
    },
  },
})

async function loadConfig() {
  try {
    const res = await fetch('/config')
    const data = await res.json()
    config.value = data
  } catch (e) {
    console.error('加载配置失败:', e)
  }
}

async function loadCharacters() {
  try {
    const res = await fetch('/config/easyvtuber/characters')
    const data = await res.json()
    characters.value = data.characters || []
  } catch (e) {
    console.error('加载角色列表失败:', e)
  }
}

async function saveConfig() {
  try {
    const res = await fetch('/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config.value),
    })
    if (res.ok) {
      alert('配置已保存')
    } else {
      alert('保存失败')
    }
  } catch (e) {
    alert('保存失败: ' + e)
  }
}

function resetConfig() {
  loadConfig()
}

function close() {
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    close()
  }
  if (e.ctrlKey && e.shiftKey && e.key === 'S') {
    e.preventDefault()
    if (props.visible) {
      close()
    } else {
      emit('close')
    }
  }
}

watch(() => props.visible, (visible) => {
  if (visible) {
    loadConfig()
    loadCharacters()
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  loadConfig()
  loadCharacters()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.settings-panel {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 16px;
  width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.settings-header h2 {
  color: #f1f5f9;
  font-size: 20px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 28px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #f1f5f9;
}

.settings-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.tab-btn {
  padding: 8px 16px;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #f1f5f9;
}

.tab-btn.active {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  color: #cbd5e1;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 10px 14px;
  color: #f1f5f9;
  font-size: 14px;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #3b82f6;
}

.form-group input[type="range"] {
  width: 100%;
  accent-color: #3b82f6;
}

.range-value {
  color: #60a5fa;
  font-size: 12px;
}

.form-group input[type="checkbox"] {
  accent-color: #3b82f6;
  width: 18px;
  height: 18px;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-secondary {
  background: transparent;
  color: #94a3b8;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #f1f5f9;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
