<template>
  <main class="console-app">
    <SettingsPanel embedded :visible="true" />
    <NotificationToast />
  </main>
</template>

<script setup lang="ts">
import NotificationToast from '@/components/NotificationToast.vue'
import SettingsPanel from '@/components/SettingsPanel.vue'
</script>

<style>
html[data-app='console'],
html[data-app='console'] body,
html[data-app='console'] #app {
  min-width: 320px;
  min-height: 100%;
  overflow: auto;
}

html[data-app='console'] body {
  background:
    radial-gradient(circle at 12% 8%, rgba(124, 58, 237, 0.16), transparent 32rem),
    radial-gradient(circle at 88% 92%, rgba(236, 72, 153, 0.1), transparent 36rem),
    #090d17;
}

html[data-app='console'] body,
html[data-app='console'] .settings-panel,
html[data-app='console'] .settings-header,
html[data-app='console'] .settings-tabs,
html[data-app='console'] .settings-content,
html[data-app='console'] .settings-footer {
  transition: color .2s ease, background-color .2s ease, border-color .2s ease, box-shadow .2s ease;
}

.console-app {
  min-height: 100dvh;
  color: #e5e7eb;
  color-scheme: dark;
}

/* Light theme: high-contrast surfaces, while preserving the violet/pink brand. */
html[data-app='console'][data-theme='light'] body {
  background:
    radial-gradient(circle at 12% 8%, rgba(124, 58, 237, 0.1), transparent 30rem),
    radial-gradient(circle at 88% 92%, rgba(236, 72, 153, 0.07), transparent 34rem),
    #f5f6fb;
}

html[data-app='console'][data-theme='light'] .console-app { color: #172033; color-scheme: light; }
html[data-app='console'][data-theme='light'] .settings-panel.is-embedded {
  color: #334155;
  border-color: #d8ddea;
  background: #ffffff;
  box-shadow: 0 28px 70px rgba(51, 65, 85, .14);
  color-scheme: light;
}
html[data-app='console'][data-theme='light'] .is-embedded .settings-header,
html[data-app='console'][data-theme='light'] .is-embedded .settings-footer { border-color: #e2e5ee; background: rgba(255, 255, 255, .96); }
html[data-app='console'][data-theme='light'] .is-embedded .settings-tabs { border-color: #e1e5ef; background: #f8f9fd; }
html[data-app='console'][data-theme='light'] .is-embedded .settings-content { background: #f4f6fb; }
html[data-app='console'][data-theme='light'] .is-embedded .mobile-tab-picker { border-color: #e1e5ef; background: #f8f9fd; }

html[data-app='console'][data-theme='light'] .settings-panel :is(h1, h2, h3, strong, label) { color: #172033; }
html[data-app='console'][data-theme='light'] .settings-panel :is(p, small, .hint, .section-desc, .last-updated, .s-label, .field-help, .intro, .context-empty, .empty-state) { color: #64748b; }
html[data-app='console'][data-theme='light'] .console-brand > div > span,
html[data-app='console'][data-theme='light'] .section-title,
html[data-app='console'][data-theme='light'] .eyebrow { color: #6d28d9; }

html[data-app='console'][data-theme='light'] .is-embedded .tab-btn { color: #596579; }
html[data-app='console'][data-theme='light'] .is-embedded .tab-btn:hover { color: #312e81; background: #ede9fe; }
html[data-app='console'][data-theme='light'] .is-embedded .tab-btn.active { color: #5b21b6; background: linear-gradient(90deg, #ede9fe, #f5f3ff); }
html[data-app='console'][data-theme='light'] .tab-indicator { background: #a8b0c0; }
html[data-app='console'][data-theme='light'] .tab-btn.active .tab-indicator { background: #7c3aed; box-shadow: 0 0 0 4px rgba(124,58,237,.1); }
html[data-app='console'][data-theme='light'] .connection-pill.online { color: #166534; border-color: #bbf7d0; background: #f0fdf4; }
html[data-app='console'][data-theme='light'] .connection-pill.offline { color: #991b1b; border-color: #fecaca; background: #fff1f2; }

html[data-app='console'][data-theme='light'] .theme-toggle,
html[data-app='console'][data-theme='light'] :is(.btn-secondary, .card-action, .mini-btn, .icon-btn, .workspace-tabs button, .refresh-btn, .heading-actions button, .memory-tabs button, .small-btn) {
  color: #4c1d95;
  border-color: #d8d1eb;
  background: #f5f3ff;
}
html[data-app='console'][data-theme='light'] .theme-toggle:hover,
html[data-app='console'][data-theme='light'] :is(.btn-secondary, .card-action, .mini-btn, .workspace-tabs button, .refresh-btn, .heading-actions button):hover { border-color: #a78bfa; background: #ede9fe; }

html[data-app='console'][data-theme='light'] .settings-panel :is(input[type='text'], input[type='number'], input[type='password'], input[type='search'], select, textarea, .small-input, .flex-input) {
  color: #172033;
  border-color: #cfd5e2;
  background: #ffffff;
  color-scheme: light;
}
html[data-app='console'][data-theme='light'] .settings-panel select option { color: #172033; background: #ffffff; }
html[data-app='console'][data-theme='light'] .mobile-tab-picker select { color: #312e81; border-color: #c4b5fd; background: #ffffff; color-scheme: light; }

html[data-app='console'][data-theme='light'] :is(.runtime-card, .status-item, .avatar-preview, .stat-card, .memory-section, .settings-card, .catalog-section, .specific-section, .specific-card, .agent-runtime, .music-console) {
  border-color: #dce1eb;
  background: #ffffff;
  box-shadow: 0 6px 20px rgba(51, 65, 85, .055);
}
html[data-app='console'][data-theme='light'] :is(.runtime-card-head, .runtime-card p, .track-copy span, .music-heading p, .history-row > span:last-child, .field-label, .switch-label, .field-grid label, .section-heading span, .context-view summary) { color: #64748b; }
html[data-app='console'][data-theme='light'] :is(.now-playing, .queue-row, .result-card, .runtime-metrics article, .context-list > div, .result-item, .event-item, .backup-item) {
  color: #334155;
  border-color: #dde2ec;
  background: #f8fafc;
}
html[data-app='console'][data-theme='light'] .workspace-tabs { border-color: #dce1eb; }
html[data-app='console'][data-theme='light'] .workspace-tabs button.active { color: #5b21b6; border-color: #c4b5fd; background: #ede9fe; }
html[data-app='console'][data-theme='light'] .notice { color: #78350f; background: #fffbeb; }
html[data-app='console'][data-theme='light'] .log-area { color: #334155; background: #eef1f6; }
html[data-app='console'][data-theme='light'] .graph-canvas-wrap { border-color: #dce1eb; background: #ffffff; }
html[data-app='console'][data-theme='light'] .compact-table input { color: #172033; border-color: #cfd5e2; background: #fff; }

@media (prefers-reduced-motion: reduce) {
  html[data-app='console'] body,
  html[data-app='console'] .settings-panel,
  html[data-app='console'] .settings-header,
  html[data-app='console'] .settings-tabs,
  html[data-app='console'] .settings-content,
  html[data-app='console'] .settings-footer { transition: none; }
}
</style>
