<template>
  <div class="live2d-container">
    <canvas ref="canvasRef" class="live2d-canvas"></canvas>
    <div v-if="!connected" class="connecting-overlay">
      <span>连接中...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const connected = ref(false)

let ws: WebSocket | null = null
let animationFrameId: number | null = null
let lastFrameTime = 0
const targetFPS = 30
const frameInterval = 1000 / targetFPS

const WS_URL = 'ws://localhost:8765'

function connectWebSocket() {
  if (ws) {
    ws.close()
  }

  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    console.log('WebSocket 连接成功')
    connected.value = true
  }

  ws.onclose = () => {
    console.log('WebSocket 连接关闭')
    connected.value = false
    setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWebSocket()
      }
    }, 3000)
  }

  ws.onerror = (error) => {
    console.error('WebSocket 错误:', error)
    connected.value = false
  }

  ws.onmessage = (event) => {
    const now = performance.now()
    if (now - lastFrameTime < frameInterval) {
      return
    }
    lastFrameTime = now

    try {
      const frameData = event.data
      if (typeof frameData === 'string') {
        const img = new Image()
        img.onload = () => {
          drawImageToCanvas(img)
        }
        if (frameData.startsWith('data:image')) {
          img.src = frameData
        } else {
          img.src = 'data:image/png;base64,' + frameData
        }
      }
    } catch (e) {
      console.error('帧处理错误:', e)
    }
  }
}

function drawFrame(dataUrl: string) {
  const img = new Image()
  img.onload = () => {
    drawImageToCanvas(img)
  }
  img.src = dataUrl
}

function drawImageToCanvas(img: HTMLImageElement) {
  if (!canvasRef.value) return

  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  canvas.width = 336
  canvas.height = 420

  const scale = Math.min(336 / img.width, 420 / img.height)
  const x = (336 - img.width * scale) / 2
  const y = (420 - img.height * scale) / 2

  ctx.clearRect(0, 0, 336, 420)
  ctx.drawImage(img, x, y, img.width * scale, img.height * scale)
}

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
})
</script>

<style scoped>
.live2d-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.live2d-canvas {
  width: 336px;
  height: 420px;
}

.connecting-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  font-size: 14px;
}
</style>
