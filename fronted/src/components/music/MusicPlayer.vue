<template>
  <div class="music-player" :class="{ minimized: isMinimized }">
    <div class="player-glow"></div>

    <div class="player-header" @click="toggleMinimize">
      <div class="header-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="2"/>
          <circle cx="18" cy="16" r="3" stroke="currentColor" stroke-width="2"/>
        </svg>
      </div>
      <h3 class="player-title">音樂播放器</h3>
      <div class="minimize-btn">
        <svg v-if="isMinimized" width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M18 15l-6-6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
    </div>

    <div class="player-body" v-show="!isMinimized">
      <div class="player-main">
        <div class="album-cover" :class="{ spinning: isPlaying && hasCurrent }">
          <div class="cover-inner" v-if="hasCurrent">
            <img :src="current?.coverUrl" :alt="current?.title" />
          </div>
          <div class="cover-placeholder" v-else>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
              <path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              <circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="18" cy="16" r="3" stroke="currentColor" stroke-width="1.5"/>
            </svg>
          </div>
          <div class="cover-ring" v-if="hasCurrent"></div>
        </div>

        <div class="track-info">
          <div class="track-title" :title="current?.title || '等待播放'">
            {{ current?.title || '等待播放' }}
          </div>
          <div class="track-artist" v-if="hasCurrent">
            <img v-if="current?.upFace" :src="current?.upFace" class="artist-avatar" />
            <span>{{ current?.upName }}</span>
          </div>
          <div class="track-artist placeholder" v-else>暂无歌曲</div>
        </div>
      </div>

      <div class="progress-section" v-if="hasCurrent">
        <div class="progress-bar" @click="seekTo">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
            <div class="progress-handle" :style="{ left: progressPercent + '%' }"></div>
          </div>
        </div>
        <div class="time-display">
          <span>{{ formatTime(currentTime) }}</span>
          <span>{{ formatTime(current?.duration || 0) }}</span>
        </div>
      </div>

      <div class="controls">
        <button class="ctrl-btn" @click="skipPrevious" :disabled="!hasCurrent">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M19 20L9 12l10-8v16zM5 19V5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <button class="ctrl-btn play-btn" @click="togglePlay" :disabled="!hasCurrent">
          <svg v-if="!isPlaying" width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M5 3l14 9-14 9V3z" fill="currentColor"/>
          </svg>
          <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none">
            <rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor"/>
            <rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor"/>
          </svg>
        </button>
        <button class="ctrl-btn" @click="skipNext" :disabled="!hasNext">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M5 4l10 8-10 8V4zM19 5v14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <div class="queue-section">
        <div class="queue-header">
          <span class="queue-label">播放列表</span>
          <span class="queue-count">{{ queue.length }}首</span>
        </div>
        <div class="queue-list" v-if="queue.length > 0">
          <div
            v-for="(item, index) in queue"
            :key="item.id"
            class="queue-item"
            :class="{ playing: current?.id === item.id }"
          >
            <div class="item-index">{{ index + 1 }}</div>
            <div class="item-info">
              <div class="item-title">{{ item.title }}</div>
              <div class="item-artist">{{ item.upName }}</div>
            </div>
            <div class="item-duration">{{ formatTime(item.duration) }}</div>
            <button class="item-remove" @click="removeItem(item.id)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
        </div>
        <div class="queue-empty" v-else>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.5"/>
          </svg>
          <span>歌单为空</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMusicStore } from '@/stores/music'

const musicStore = useMusicStore()
const { current, queue, isPlaying, currentTime } = storeToRefs(musicStore)

const isMinimized = ref(false)

const hasCurrent = computed(() => !!current.value)
const hasNext = computed(() => queue.value.length > 0)

const progressPercent = computed(() => {
  if (!current.value?.duration) return 0
  return (currentTime.value / current.value.duration) * 100
})

let progressInterval: number | null = null

function toggleMinimize() {
  isMinimized.value = !isMinimized.value
}

function togglePlay() {
  musicStore.togglePlay()
}

function skipPrevious() {
  musicStore.skipCurrent()
}

function skipNext() {
  musicStore.playNext()
}

function seekTo(event: MouseEvent) {
  // Placeholder for seek functionality
}

function removeItem(id: string) {
  musicStore.removeFromQueue(id)
}

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(() => {
  musicStore.fetchQueue()
})
</script>

<style scoped>
.music-player {
  width: 320px;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.15),
    0 2px 8px rgba(0, 0, 0, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  overflow: hidden;
  position: relative;
}

.player-glow {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(
    circle at center,
    rgba(99, 179, 237, 0.08) 0%,
    transparent 50%
  );
  pointer-events: none;
}

.player-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.15) 0%,
    rgba(255, 255, 255, 0.05) 100%
  );
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  cursor: pointer;
  user-select: none;
}

.header-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  border-radius: 8px;
  color: white;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
}

.player-title {
  flex: 1;
  margin-left: 10px;
  font-size: 14px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.minimize-btn {
  color: rgba(255, 255, 255, 0.6);
  transition: color 0.2s;
}

.minimize-btn:hover {
  color: rgba(255, 255, 255, 0.9);
}

.player-body {
  padding: 16px;
}

.player-main {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.album-cover {
  width: 72px;
  height: 72px;
  position: relative;
  flex-shrink: 0;
}

.cover-inner,
.cover-placeholder {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.3), rgba(139, 92, 246, 0.3));
  display: flex;
  align-items: center;
  justify-content: center;
}

.cover-inner img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.cover-ring {
  position: absolute;
  top: -4px;
  left: -4px;
  right: -4px;
  bottom: -4px;
  border: 2px solid transparent;
  border-top-color: rgba(96, 165, 250, 0.8);
  border-radius: 16px;
  animation: spin-ring 3s linear infinite;
}

.spinning .cover-ring {
  display: block;
}

@keyframes spin-ring {
  to {
    transform: rotate(360deg);
  }
}

.album-cover.spinning .cover-inner {
  animation: spin-cover 12s linear infinite;
}

@keyframes spin-cover {
  to {
    transform: rotate(360deg);
  }
}

.track-info {
  flex: 1;
  min-width: 0;
}

.track-title {
  font-size: 14px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.track-artist {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.track-artist.placeholder {
  color: rgba(255, 255, 255, 0.4);
  font-style: italic;
}

.artist-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  object-fit: cover;
}

.progress-section {
  margin-bottom: 12px;
}

.progress-bar {
  height: 20px;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.progress-track {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  position: relative;
  overflow: visible;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa, #3b82f6);
  border-radius: 2px;
  transition: width 0.3s linear;
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
}

.progress-handle {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  background: white;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 0.2s;
}

.progress-bar:hover .progress-handle {
  opacity: 1;
}

.time-display {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  font-variant-numeric: tabular-nums;
}

.controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 16px;
}

.ctrl-btn {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.ctrl-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.25);
  color: white;
  transform: scale(1.05);
}

.ctrl-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ctrl-btn.play-btn {
  width: 52px;
  height: 52px;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  color: white;
  box-shadow:
    0 4px 16px rgba(59, 130, 246, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.ctrl-btn.play-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #7bb8fa, #5b9cf6);
  box-shadow:
    0 6px 20px rgba(59, 130, 246, 0.6),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.queue-section {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 12px;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.queue-label {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.queue-count {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
}

.queue-list {
  max-height: 180px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.queue-list::-webkit-scrollbar {
  width: 4px;
}

.queue-list::-webkit-scrollbar-track {
  background: transparent;
}

.queue-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  transition: background 0.2s;
  cursor: default;
}

.queue-item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.queue-item.playing {
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.25), rgba(59, 130, 246, 0.15));
}

.queue-item.playing .item-index {
  color: #60a5fa;
  font-weight: 700;
}

.item-index {
  width: 18px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  text-align: center;
  flex-shrink: 0;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-title {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-artist {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-duration {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.item-remove {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  flex-shrink: 0;
}

.queue-item:hover .item-remove {
  opacity: 1;
}

.item-remove:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.queue-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: rgba(255, 255, 255, 0.3);
  gap: 8px;
}

.queue-empty span {
  font-size: 12px;
}
</style>
