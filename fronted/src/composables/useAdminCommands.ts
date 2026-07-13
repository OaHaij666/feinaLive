import { ref } from 'vue'
import { useNotification } from '@/utils/notification'

interface AdminCommandResult {
  success: boolean
  message: string
  command: string
  new_state?: {
    is_sleeping: boolean
    face_mode: string
    is_voice_mode: boolean
    is_hide_admin: boolean
    is_agent_running: boolean
  }
}

export function useAdminCommands() {
  const adminState = _adminState

  function updateAdminState(state: AdminCommandResult['new_state']) {
    if (!state) return
    adminState.value = {
      isSleeping: state.is_sleeping,
      faceMode: state.face_mode,
      isVoiceMode: state.is_voice_mode,
      isHideAdmin: state.is_hide_admin,
      isAgentRunning: state.is_agent_running,
    }
  }

  async function refreshAdminState() {
    try {
      const response = await fetch('/ai/admin/state')
      const state = await response.json()
      updateAdminState({
        is_sleeping: !!state.is_sleeping,
        face_mode: state.face_mode || 'wandering',
        is_voice_mode: !!state.is_voice_mode,
        is_hide_admin: !!state.is_hide_admin,
        is_agent_running: !!state.is_agent_running,
      })
    } catch (error) {
      // 后端不可用时静默失败，避免打断前端流程
    }
  }

  function handleCommandResult(result: AdminCommandResult) {
    updateAdminState(result.new_state)
    if (result.command === '/help') {
      const { info } = useNotification()
      info(result.message, 5000)
    } else if (result.success) {
      const { success } = useNotification()
      success(result.message, 3000)
    } else {
      const { warning } = useNotification()
      warning(result.message, 3000)
    }
  }

  async function toggleAgent(): Promise<boolean> {
    try {
      const newState = !adminState.value.isAgentRunning
      const cmd = newState ? '/agent 1' : '/agent 0'
      const res = await fetch('/ai/admin/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      })
      const data = await res.json()
      if (data.success) {
        const { success } = useNotification()
        success(data.message, 3000)
        await refreshAdminState()
        return true
      } else {
        const { warning } = useNotification()
        warning(data.message || '操作失败', 3000)
        return false
      }
    } catch (e) {
      const { error } = useNotification()
      error('网络请求失败', 3000)
      console.error('Agent toggle failed:', e)
      return false
    }
  }

  function shouldHideDanmaku(isAdmin: boolean): boolean {
    return adminState.value.isHideAdmin && isAdmin
  }

  startAdminStateSync(refreshAdminState)

  return {
    adminState,
    handleCommandResult,
    updateAdminState,
    shouldHideDanmaku,
    refreshAdminState,
    toggleAgent,
  }
}

const _adminState = ref({
  isSleeping: false,
  faceMode: 'wandering',
  isVoiceMode: false,
  isHideAdmin: false,
  isAgentRunning: false,
})

let _syncStarted = false
function startAdminStateSync(refreshFn: () => Promise<void>) {
  if (_syncStarted) return
  _syncStarted = true
  void refreshFn()
  setInterval(() => {
    void refreshFn()
  }, 3000)
}
