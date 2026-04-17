import { ref } from 'vue'
import { useNotification } from '@/utils/notification'

const ADMIN_UID = 378810242
const ADMIN_USERNAME = 'RongR0Ng'

interface AdminCommandResult {
  success: boolean
  message: string
  command: string
  new_state?: {
    is_sleeping: boolean
    face_mode: string
    is_voice_mode: boolean
    is_hide_admin: boolean
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
    }
  }

  async function refreshAdminState() {
    try {
      const response = await fetch('/test/admin/state')
      const state = await response.json()
      updateAdminState({
        is_sleeping: !!state.is_sleeping,
        face_mode: state.face_mode || 'wandering',
        is_voice_mode: !!state.is_voice_mode,
        is_hide_admin: !!state.is_hide_admin,
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

  function shouldHideDanmaku(uid: number, username: string): boolean {
    if (adminState.value.isHideAdmin) {
      return uid === ADMIN_UID || username === ADMIN_USERNAME
    }
    return false
  }

  startAdminStateSync(refreshAdminState)

  return {
    adminState,
    handleCommandResult,
    updateAdminState,
    shouldHideDanmaku,
    refreshAdminState,
  }
}

const _adminState = ref({
  isSleeping: false,
  faceMode: 'wandering',
  isVoiceMode: false,
  isHideAdmin: false,
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
