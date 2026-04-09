<template>
  <div class="mission-panel">
    <!-- 光晕效果 -->
    <div class="panel-glow"></div>
    
    <div class="panel-header">
      <div class="header-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <polyline points="14,2 14,8 20,8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <polyline points="10,9 9,9 8,9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span class="panel-title">委托密函</span>
      <span class="countdown">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <polyline points="12,6 12,12 16,14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        {{ countdown }}
      </span>
    </div>
    <div class="panel-content">
      <div v-if="isLoading" class="loading">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else class="mission-list">
        <div class="mission-row">
          <div class="mission-label-wrapper">
            <span class="mission-icon">⚔️</span>
            <span class="mission-label">角色</span>
          </div>
          <span class="mission-value">{{ formatMissions(characterMissions) }}</span>
        </div>
        <div class="mission-row">
          <div class="mission-label-wrapper">
            <span class="mission-icon">🗡️</span>
            <span class="mission-label">武器</span>
          </div>
          <span class="mission-value">{{ formatMissions(weaponMissions) }}</span>
        </div>
        <div class="mission-row">
          <div class="mission-label-wrapper">
            <span class="mission-icon">🔮</span>
            <span class="mission-label">魔之楔</span>
          </div>
          <span class="mission-value">{{ formatMissions(modMissions) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMissionStore } from '@/stores/mission'

const missionStore = useMissionStore()
const { characterMissions, weaponMissions, modMissions, isLoading, error } = storeToRefs(missionStore)

const countdown = ref('0:00')
let timer: number | null = null

function formatMissionName(name: string): string {
  if (name.includes('/')) {
    return name.replace('/', '(') + ')'
  }
  return name
}

function formatMissions(missions: string[]): string {
  return missions.map(formatMissionName).join(' / ')
}

function updateCountdown() {
  const now = new Date()
  const nextHour = new Date(now)
  nextHour.setHours(nextHour.getHours() + 1, 0, 0, 0)
  const diff = nextHour.getTime() - now.getTime()
  const minutes = Math.floor(diff / 60000)
  const seconds = Math.floor((diff % 60000) / 1000)
  countdown.value = `${minutes}:${seconds.toString().padStart(2, '0')}`
}

onMounted(() => {
  missionStore.fetchMissions()
  updateCountdown()
  timer = window.setInterval(updateCountdown, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
})
</script>

<style scoped>
.mission-panel {
  width: 280px;
  height: 160px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.45) 0%, rgba(240, 249, 255, 0.38) 100%);
  backdrop-filter: blur(2.4px);
  -webkit-backdrop-filter: blur(2.4px);
  border: 1.5px solid rgba(255, 255, 255, 0.35);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  overflow: hidden;
  position: relative;
  box-shadow: 
    0 8px 32px rgba(59, 130, 246, 0.15),
    inset 0 1px 2px rgba(255, 255, 255, 0.8),
    inset 0 -1px 2px rgba(147, 197, 253, 0.2);
  transition: all 0.3s ease;
}

.mission-panel:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.52) 0%, rgba(240, 249, 255, 0.45) 100%);
  box-shadow: 
    0 12px 40px rgba(59, 130, 246, 0.22),
    inset 0 1px 2px rgba(255, 255, 255, 0.9),
    inset 0 -1px 2px rgba(147, 197, 253, 0.25);
  transform: translateY(-2px);
}

.panel-glow {
  position: absolute;
  top: -50%;
  right: -20%;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.12), transparent 70%);
  pointer-events: none;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 2px solid rgba(147, 197, 253, 0.25);
}

.header-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  border-radius: 8px;
  color: white;
  animation: pulse-glow 4s ease-in-out infinite;
  box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3);
}

.header-icon svg {
  width: 16px;
  height: 16px;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e3a5f;
  letter-spacing: 2px;
  flex: 1;
}

.countdown {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #3b82f6;
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.15), rgba(59, 130, 246, 0.1));
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid rgba(147, 197, 253, 0.3);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.countdown svg {
  color: #60a5fa;
}

.panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
}

.loading,
.error {
  font-size: 13px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.loading {
  color: #60a5fa;
}

.error {
  color: #ef4444;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(96, 165, 250, 0.2);
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.mission-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.mission-row {
  display: flex;
  align-items: flex-start;
  font-size: 13px;
  line-height: 1.5;
  transition: all 0.2s ease;
  padding: 4px 6px;
  border-radius: 6px;
}

.mission-row:hover {
  background: rgba(147, 197, 253, 0.1);
}

.mission-label-wrapper {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #3b82f6;
  flex-shrink: 0;
  width: 70px;
  font-weight: 600;
}

.mission-icon {
  font-size: 14px;
}

.mission-label {
  font-weight: 600;
}

.mission-value {
  color: #1e3a5f;
  flex: 1;
  word-break: break-all;
  font-weight: 500;
}
</style>
