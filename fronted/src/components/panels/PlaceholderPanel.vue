<template>
  <div class="placeholder-panel">
    <div class="panel-glow"></div>
    
    <div class="panel-header">
      <div class="header-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="3" y="3" width="7" height="7" stroke="currentColor" stroke-width="2" rx="1"/>
          <rect x="14" y="3" width="7" height="7" stroke="currentColor" stroke-width="2" rx="1"/>
          <rect x="14" y="14" width="7" height="7" stroke="currentColor" stroke-width="2" rx="1"/>
          <rect x="3" y="14" width="7" height="7" stroke="currentColor" stroke-width="2" rx="1"/>
        </svg>
      </div>
      <span class="panel-title">待定</span>
    </div>
    <div class="panel-content">
      <span class="placeholder-text">预留位置</span>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.placeholder-panel {
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

.placeholder-panel:hover {
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
}

.panel-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.placeholder-text {
  font-size: 14px;
  font-weight: 500;
  color: #60a5fa;
  opacity: 0.7;
  letter-spacing: 2px;
}
</style>
