<template>
  <div class="livestats-panel">
    <div class="panel-glow"></div>

    <div class="panel-header">
      <div class="header-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3 12h4l3-9 4 18 3-9h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span class="panel-title">直播间统计</span>
      <span class="countdown">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <polyline points="12,6 12,12 16,14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        {{ runtimeFormatted }}
      </span>
    </div>

    <div class="panel-content">
      <div class="metric-row">
        <div class="metric">
          <div class="metric-label">
            <span class="metric-icon">👥</span>
            <span>人气</span>
          </div>
          <span class="metric-value">{{ formatNumber(popularity) }}</span>
        </div>
        <div class="metric">
          <div class="metric-label">
            <span class="metric-icon">💬</span>
            <span>弹幕</span>
          </div>
          <span class="metric-value">{{ formatNumber(danmakuCount) }}</span>
        </div>
      </div>

      <div class="metric-row">
        <div class="metric">
          <div class="metric-label">
            <span class="metric-icon">🎁</span>
            <span>礼物</span>
          </div>
          <span class="metric-value">{{ formatNumber(giftCount) }}</span>
        </div>
        <div class="metric">
          <div class="metric-label">
            <span class="metric-icon">💎</span>
            <span>价值</span>
          </div>
          <span class="metric-value">¥{{ formatMoney(giftValueMinor) }}</span>
        </div>
      </div>

      <div class="top-gifts" v-if="topGifts.length > 0">
        <span class="top-gifts-label">热门</span>
        <div class="top-gifts-list">
          <span v-for="g in topGifts" :key="g.name" class="top-gift-chip">
            <span class="top-gift-name">{{ g.name }}</span>
            <span class="top-gift-count">×{{ g.count }}</span>
          </span>
        </div>
      </div>
      <div class="top-gifts-empty" v-else>
        <span class="top-gifts-label">热门</span>
        <span class="empty-hint">暂无礼物</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useLiveStatsStore } from '@/stores/livestats'

const liveStatsStore = useLiveStatsStore()
const { popularity, danmakuCount, giftCount, giftValueMinor, runtimeFormatted, topGifts } = storeToRefs(liveStatsStore)

function formatNumber(n: number): string {
  return n.toLocaleString('en-US')
}

function formatMoney(minor: number): string {
  return (minor / 100).toFixed(2)
}

onMounted(() => {
  liveStatsStore.startTimer()
})

onUnmounted(() => {
  liveStatsStore.stopTimer()
})
</script>

<style scoped>
.livestats-panel {
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

.livestats-panel:hover {
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
  gap: 6px;
  overflow: hidden;
}

.metric-row {
  display: flex;
  gap: 10px;
}

.metric {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(147, 197, 253, 0.12), rgba(96, 165, 250, 0.06));
  border: 1px solid rgba(147, 197, 253, 0.18);
  transition: all 0.2s ease;
}

.metric:hover {
  background: linear-gradient(135deg, rgba(147, 197, 253, 0.18), rgba(96, 165, 250, 0.1));
  border-color: rgba(147, 197, 253, 0.32);
}

.metric-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #3b82f6;
  font-weight: 600;
}

.metric-icon {
  font-size: 12px;
}

.metric-value {
  font-size: 15px;
  color: #1e3a5f;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.top-gifts,
.top-gifts-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  margin-top: 2px;
  min-height: 22px;
}

.top-gifts-label {
  color: #3b82f6;
  font-weight: 600;
  flex-shrink: 0;
}

.top-gifts-list {
  display: flex;
  gap: 5px;
  overflow: hidden;
  flex: 1;
}

.top-gift-chip {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.22);
  border-radius: 10px;
  white-space: nowrap;
  flex-shrink: 0;
}

.top-gift-name {
  color: #b91c1c;
  font-weight: 600;
}

.top-gift-count {
  color: #ef4444;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.empty-hint {
  color: #94a3b8;
  font-style: italic;
  font-weight: 500;
}

@keyframes pulse-glow {
  0%, 100% {
    box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3);
  }
  50% {
    box-shadow: 0 3px 14px rgba(59, 130, 246, 0.5);
  }
}
</style>
