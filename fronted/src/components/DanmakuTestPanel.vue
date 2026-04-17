<template>
  <div v-if="visible" class="test-panel-overlay" @click.self="$emit('close')">
    <div class="test-panel">
      <div class="panel-header">
        <h2>弹幕测试面板</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <div class="section">
        <h3>发送测试弹幕</h3>
        <div class="form">
          <div class="form-row">
            <label>用户名:</label>
            <input v-model="danmakuUser" placeholder="输入用户名" />
          </div>
          <div class="form-row">
            <label>UID:</label>
            <input v-model.number="danmakuUid" type="number" placeholder="0" />
          </div>
          <div class="form-row">
            <label>弹幕内容:</label>
            <input v-model="danmakuContent" placeholder="输入弹幕内容" @keyup.enter="sendDanmaku" />
          </div>
          <button @click="sendDanmaku" :disabled="!danmakuContent">发送弹幕</button>
        </div>
      </div>

      <div class="section">
        <h3>管理员指令</h3>
        <div class="command-buttons">
          <button @click="sendCommand('/sleep 1')" :disabled="adminState.isSleeping">/sleep 1 暂停</button>
          <button @click="sendCommand('/sleep 0')" :disabled="!adminState.isSleeping">/sleep 0 恢复</button>
          <button @click="sendCommand('/face 1')" :disabled="adminState.faceMode === 'mouse_tracking'">/face 1 鼠标追踪</button>
          <button @click="sendCommand('/face 0')" :disabled="adminState.faceMode === 'wandering'">/face 0 漫步</button>
          <button @click="sendCommand('/voice 1')" :disabled="adminState.isVoiceMode">/voice 1 接管</button>
          <button @click="sendCommand('/voice 0')" :disabled="!adminState.isVoiceMode">/voice 0 AI主播</button>
          <button @click="sendCommand('/hide 1')" :disabled="adminState.isHideAdmin">/hide 1 隐藏</button>
          <button @click="sendCommand('/hide 0')" :disabled="!adminState.isHideAdmin">/hide 0 显示</button>
          <button @click="sendCommand('/help')">/help 帮助</button>
        </div>
      </div>

      <div class="section">
        <h3>音乐控制</h3>
        <div class="music-controls">
          <div class="volume-control">
            <label>音量 (0-10):</label>
            <input v-model.number="volumeInput" type="number" min="0" max="10" />
            <button @click="setVolume">设置</button>
          </div>
          <div class="command-buttons">
            <button @click="sendCommand('/next')">/next 下一首</button>
            <button @click="sendCommand('/pause 1')" :disabled="adminState.isPaused">/pause 1 暂停</button>
            <button @click="sendCommand('/pause 0')" :disabled="!adminState.isPaused">/pause 0 恢复</button>
            <button @click="sendCommand('/rm')">/rm 移除当前</button>
          </div>
          <div class="add-music">
            <label>添加歌曲 (BV号):</label>
            <input v-model="bvidInput" placeholder="例如: BV1xx41117dM" />
            <button @click="addMusic" :disabled="!bvidInput">/add_music</button>
          </div>
        </div>
      </div>

      <div class="section">
        <h3>状态监控</h3>
        <div class="status-grid">
          <div class="status-item">
            <span class="label">AI回复:</span>
            <span :class="['value', adminState.isSleeping ? 'off' : 'on']">
              {{ adminState.isSleeping ? '已暂停' : '正常' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">数字人模式:</span>
            <span class="value">{{ adminState.faceMode === 'mouse_tracking' ? '鼠标追踪' : '漫步' }}</span>
          </div>
          <div class="status-item">
            <span class="label">弹幕模式:</span>
            <span :class="['value', adminState.isVoiceMode ? 'highlight' : '']">
              {{ adminState.isVoiceMode ? '接管模式' : 'AI主播' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">管理员弹幕:</span>
            <span :class="['value', adminState.isHideAdmin ? 'warning' : '']">
              {{ adminState.isHideAdmin ? '隐藏' : '显示' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">音乐音量:</span>
            <span class="value">{{ Math.round(adminState.volume * 10) }}/10</span>
          </div>
          <div class="status-item">
            <span class="label">播放状态:</span>
            <span :class="['value', adminState.isPaused ? 'warning' : 'on']">
              {{ adminState.isPaused ? '已暂停' : '播放中' }}
            </span>
          </div>
        </div>
        <button @click="refreshStatus" class="refresh-btn">刷新状态</button>
      </div>

      <div class="section">
        <h3>实时日志</h3>
        <div class="log-area">
          <div v-for="(log, index) in logs" :key="index" :class="['log-item', log.type]">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-content">{{ log.content }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useNotification } from '@/utils/notification'
import { useLLMStore } from '@/stores/llm'
import { useDanmakuStore } from '@/stores/danmaku'
import { useMusicStore } from '@/stores/music'
import { DanmakuType } from '@/types/danmaku'

defineProps<{
  visible: boolean
}>()

defineEmits<{
  (e: 'close'): void
}>()

interface LogItem {
  time: string
  content: string
  type: 'danmaku' | 'reply' | 'system' | 'error'
}

const danmakuUser = ref('测试用户')
const danmakuUid = ref(123456)
const danmakuContent = ref('')

const adminState = ref({
  isSleeping: false,
  faceMode: 'wandering',
  isVoiceMode: false,
  isHideAdmin: false,
  volume: 1.0,
  isPaused: false,
})

const volumeInput = ref(10)
const bvidInput = ref('')

const logs = ref<LogItem[]>([])
let ws: WebSocket | null = null

const llmStore = useLLMStore()
const danmakuStore = useDanmakuStore()
const musicStore = useMusicStore()

function addLog(content: string, type: LogItem['type'] = 'system') {
  const now = new Date()
  const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
  logs.value.push({ time, content, type })
  if (logs.value.length > 50) {
    logs.value = logs.value.slice(-50)
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  ws = new WebSocket(`${protocol}//${host}/test/ws/test`)

  ws.onopen = () => {
    addLog('WebSocket 已连接', 'system')
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      
      if (msg.type === 'danmaku') {
        addLog(`[弹幕] ${msg.data.user}: ${msg.data.content}`, 'danmaku')
      } else if (msg.type === 'start') {
        addLog('[AI] 开始生成回复...', 'system')
        llmStore.handleExternalChunk(msg)
      } else if (msg.type === 'text') {
        addLog(`[AI文本] ${msg.data.text}`, 'reply')
        llmStore.handleExternalChunk(msg)
      } else if (msg.type === 'audio') {
        addLog('[AI] 音频已生成', 'system')
        llmStore.handleExternalChunk(msg)
      } else if (msg.type === 'end') {
        addLog('[AI] 回复完成', 'system')
        llmStore.handleExternalChunk(msg)
      } else if (msg.type === 'error') {
        addLog(`[错误] ${msg.data?.text || '未知错误'}`, 'error')
        llmStore.handleExternalChunk(msg)
      } else if (msg.type === 'music_control') {
        const action = msg.data?.action
        if (action === 'volume') {
          musicStore.setVolume(msg.data.volume)
          addLog(`[音乐] 音量设置为 ${Math.round(msg.data.volume * 10)}/10`, 'system')
        } else if (action === 'pause') {
          musicStore.setPaused(msg.data.is_paused)
          addLog(`[音乐] ${msg.data.is_paused ? '已暂停' : '已恢复'}`, 'system')
        } else if (action === 'next') {
          musicStore.fetchQueue()
          addLog('[音乐] 跳到下一首', 'system')
        } else if (action === 'rm') {
          musicStore.fetchQueue()
          addLog('[音乐] 移除当前歌曲', 'system')
        } else if (msg.type === 'music_added') {
          addLog(`[音乐] 点歌成功: ${msg.data.title} - ${msg.data.artist}`, 'system')
        } else if (msg.type === 'music_error') {
          addLog(`[音乐] 点歌失败: ${msg.data.error}`, 'error')
        }
    } catch (e) {
      console.error('WebSocket message parse error:', e)
    }
  }

  ws.onerror = () => {
    addLog('WebSocket 连接错误', 'error')
  }

  ws.onclose = () => {
    addLog('WebSocket 已断开', 'system')
    setTimeout(connectWebSocket, 3000)
  }
}

async function sendDanmaku() {
  if (!danmakuContent.value) return

  try {
    const response = await fetch('/test/danmaku', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user: danmakuUser.value,
        content: danmakuContent.value,
        uid: danmakuUid.value,
      }),
    })
    const result = await response.json()
    if (result.success) {
      addLog(`[发送] ${result.user}: ${result.content}`, 'danmaku')
      danmakuStore.addDanmaku({
        id: result.msg_id || `test-${Date.now()}`,
        user: result.user || danmakuUser.value,
        content: result.content || '',
        timestamp: new Date(),
        type: DanmakuType.NORMAL,
        uid: result.uid || danmakuUid.value || 0,
      })
    }
    danmakuContent.value = ''
    refreshStatus()
  } catch (error) {
    const { error: showError } = useNotification()
    showError('发送弹幕失败')
  }
}

async function sendCommand(command: string) {
  try {
    const response = await fetch('/test/admin/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command }),
    })
    const result = await response.json()
    if (result.success) {
      if (result.state) {
        adminState.value = {
          isSleeping: result.state.is_sleeping,
          faceMode: result.state.face_mode,
          isVoiceMode: result.state.is_voice_mode,
          isHideAdmin: result.state.is_hide_admin,
          volume: result.state.volume ?? 1.0,
          isPaused: result.state.is_paused ?? false,
        }
      }
      const { success, info, warning } = useNotification()
      if (command === '/help') {
        info(result.message, 5000)
      } else {
        success(result.message, 3000)
      }
      addLog(`[指令] ${command} -> ${result.message}`, 'system')
    } else {
      const { warning } = useNotification()
      warning(result.message, 3000)
      addLog(`[错误] ${command} -> ${result.message}`, 'error')
    }
  } catch (error) {
    const { error: showError } = useNotification()
    showError('发送指令失败')
  }
}

async function refreshStatus() {
  try {
    const response = await fetch('/test/admin/state')
    const data = await response.json()
    adminState.value = {
      isSleeping: data.is_sleeping,
      faceMode: data.face_mode,
      isVoiceMode: data.is_voice_mode,
      isHideAdmin: data.is_hide_admin,
      volume: data.volume ?? 1.0,
      isPaused: data.is_paused ?? false,
    }
    volumeInput.value = Math.round((data.volume ?? 1.0) * 10)
  } catch (error) {
    console.error('刷新状态失败:', error)
  }
}

async function setVolume() {
  await sendCommand(`/sound ${volumeInput.value}`)
}

async function addMusic() {
  if (!bvidInput.value) return
  await sendCommand(`/add_music ${bvidInput.value}`)
  bvidInput.value = ''
}

onMounted(() => {
  connectWebSocket()
  refreshStatus()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})
</script>

<style scoped>
.test-panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.test-panel {
  padding: 20px;
  max-width: 800px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  background: white;
  border-radius: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.panel-header h2 {
  margin: 0;
}

.close-btn {
  background: #f44336;
  width: 32px;
  height: 32px;
  font-size: 20px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.section {
  margin-bottom: 24px;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
}

.section h3 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  color: #333;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-row label {
  width: 80px;
  flex-shrink: 0;
}

.form-row input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

button {
  padding: 8px 16px;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.command-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.command-buttons button {
  background: #2196f3;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  background: white;
  border-radius: 4px;
}

.status-item .label {
  color: #666;
}

.status-item .value.on {
  color: #4caf50;
}

.status-item .value.off {
  color: #f44336;
}

.status-item .value.highlight {
  color: #ff9800;
  font-weight: bold;
}

.status-item .value.warning {
  color: #ff5722;
}

.refresh-btn {
  background: #9e9e9e;
}

.log-area {
  max-height: 200px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 8px;
  font-family: monospace;
  font-size: 12px;
}

.log-item {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.log-item.danmaku {
  color: #4fc3f7;
}

.log-item.reply {
  color: #81c784;
}

.log-item.system {
  color: #b0b0b0;
}

.log-item.error {
  color: #ef5350;
}

.log-time {
  color: #666;
  flex-shrink: 0;
}

.log-content {
  word-break: break-all;
}
</style>
