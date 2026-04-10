<template>
  <div class="live2d-container">
    <canvas ref="canvasRef" class="live2d-canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import testImage from '@/pic/test.jpg'

const canvasRef = ref<HTMLCanvasElement | null>(null)
let image: HTMLImageElement | null = null

const chromaKey = {
  r: 0x31,
  g: 0xf0,
  b: 0x88
}

const threshold = 100

function processImage(ctx: CanvasRenderingContext2D, width: number, height: number) {
  const imageData = ctx.getImageData(0, 0, width, height)
  const data = imageData.data

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i]
    const g = data[i + 1]
    const b = data[i + 2]

    const distance = Math.sqrt(
      Math.pow(r - chromaKey.r, 2) +
      Math.pow(g - chromaKey.g, 2) +
      Math.pow(b - chromaKey.b, 2)
    )

    if (distance < threshold) {
      data[i + 3] = 0
    }
  }

  ctx.putImageData(imageData, 0, 0)
}

onMounted(() => {
  if (!canvasRef.value) return

  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  image = new Image()
  image.src = testImage

  image.onload = () => {
    canvas.width = 336
    canvas.height = 420

    ctx.drawImage(image!, 0, 0, 336, 420)
    processImage(ctx, 336, 420)
  }

  image.onerror = (e) => {
    console.error('图片加载失败:', e)
  }
})

onUnmounted(() => {
  image = null
})
</script>

<style scoped>
.live2d-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.live2d-canvas {
  width: 336px;
  height: 420px;
}
</style>
