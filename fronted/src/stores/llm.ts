import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getAvatarInputApi } from '@/composables/useAvatarInput'

export interface LLMMessage {
  id: string
  type: 'user' | 'assistant'
  text: string
  timestamp: number
}

interface AudioChunk {
  replyId: string
  data: string
  index: number
  text: string
  charOffset: number
  charLength: number
}

interface ReplyChunk {
  type: string
  reply_id?: string
  chunk_seq?: number
  text?: string
  audio?: string
  sentence_index?: number
  char_offset?: number
  char_length?: number
  is_final?: boolean
  playback_expected?: boolean
  audio_chunks?: number
  data?: Omit<ReplyChunk, 'type' | 'data'>
}

class AudioPlayer {
  private audioContext: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private audioQueue: AudioChunk[] = []
  private isPlaying = false
  private currentSource: AudioBufferSourceNode | null = null
  private activeReplyId: string | null = null
  private generationFinished = false
  private playbackStarted = false
  private textDisplayTimer: number | null = null
  private audioLevelTimer: number | null = null
  private lastAudioLevelSentAt = 0
  private audioMonitorReplyId = ''
  private audioMonitorStartTime = 0
  private audioMonitorOffsetMs = 0
  private playedAudioMs = 0
  private onAudioProgress: ((charIndex: number) => void) | null = null
  private onPlaybackStarted: (() => void) | null = null
  private onPlaybackFinished: (() => void) | null = null
  private onPlaybackFailed: ((error: string) => void) | null = null

  private getAudioContext(): AudioContext {
    if (!this.audioContext) {
      this.audioContext = new AudioContext()
      this.analyser = this.audioContext.createAnalyser()
      this.analyser.fftSize = 256
      this.analyser.smoothingTimeConstant = 0.8
      this.analyser.connect(this.audioContext.destination)
    }
    return this.audioContext
  }

  async unlock(): Promise<void> {
    const context = this.getAudioContext()
    if (context.state !== 'running') {
      await context.resume()
    }
    if (context.state !== 'running') {
      throw new Error('浏览器没有解锁主播语音播放')
    }
  }

  setCallbacks(callbacks: {
    onAudioProgress: (charIndex: number) => void
    onPlaybackStarted: () => void
    onPlaybackFinished: () => void
    onPlaybackFailed: (error: string) => void
  }) {
    this.onAudioProgress = callbacks.onAudioProgress
    this.onPlaybackStarted = callbacks.onPlaybackStarted
    this.onPlaybackFinished = callbacks.onPlaybackFinished
    this.onPlaybackFailed = callbacks.onPlaybackFailed
  }

  begin(replyId: string) {
    if (this.activeReplyId && this.activeReplyId !== replyId) {
      this.failActive('新的回复在上一条播放完成前到达')
    }
    this.stopLocal()
    this.activeReplyId = replyId
    this.generationFinished = false
    this.playbackStarted = false
    this.playedAudioMs = 0
  }

  queueAudio(chunk: AudioChunk) {
    if (!this.activeReplyId || chunk.replyId !== this.activeReplyId) return
    this.audioQueue.push(chunk)
    this.audioQueue.sort((a, b) => a.index - b.index)
    void this.playNext()
  }

  finishGeneration(replyId: string, audioChunks: number) {
    if (replyId !== this.activeReplyId) return
    this.generationFinished = true
    if (audioChunks <= 0) {
      this.failActive('TTS 没有生成可播放音频')
      return
    }
    this.completeIfDrained()
  }

  fail(replyId: string, error: string) {
    if (replyId === this.activeReplyId) this.failActive(error)
  }

  stop(error = '播放被客户端停止') {
    if (this.activeReplyId) this.failActive(error)
    else this.stopLocal()
  }

  private async playNext() {
    if (this.isPlaying || this.audioQueue.length === 0 || !this.activeReplyId) {
      this.completeIfDrained()
      return
    }

    const chunk = this.audioQueue.shift()!
    const replyId = this.activeReplyId
    this.isPlaying = true

    try {
      const audioContext = this.getAudioContext()
      if (audioContext.state !== 'running') await audioContext.resume()
      if (audioContext.state !== 'running') throw new Error('AudioContext 未解锁')

      const binaryString = atob(chunk.data)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }
      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer)
      if (replyId !== this.activeReplyId) return

      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(this.analyser!)
      this.currentSource = source

      if (!this.playbackStarted) {
        this.playbackStarted = true
        getAvatarInputApi().sendPlaybackAck(replyId, 'started')
        this.onPlaybackStarted?.()
      }

      const charDuration = audioBuffer.duration / Math.max(chunk.charLength, 1)
      this.startTextAnimation(
        chunk.charOffset,
        chunk.charLength,
        charDuration,
        audioContext.currentTime,
      )
      const audioStartTime = audioContext.currentTime
      this.startAudioLevelMonitoring(replyId, audioStartTime, this.playedAudioMs)

      await new Promise<void>((resolve) => {
        source.onended = () => resolve()
        source.start(0)
      })
      this.playedAudioMs += audioBuffer.duration * 1000
    } catch (error) {
      if (replyId === this.activeReplyId) {
        this.failActive(error instanceof Error ? error.message : String(error))
      }
      return
    } finally {
      if (replyId === this.activeReplyId) {
        this.currentSource = null
        this.isPlaying = false
        this.stopTextAnimation()
        this.stopAudioLevelMonitoring()
        void this.playNext()
      }
    }
  }

  private completeIfDrained() {
    if (
      !this.activeReplyId ||
      !this.generationFinished ||
      this.isPlaying ||
      this.audioQueue.length > 0
    ) return

    const replyId = this.activeReplyId
    this.activeReplyId = null
    getAvatarInputApi().sendPlaybackAck(replyId, 'finished')
    this.onPlaybackFinished?.()
  }

  private failActive(error: string) {
    const replyId = this.activeReplyId
    this.stopLocal()
    this.activeReplyId = null
    if (replyId) getAvatarInputApi().sendPlaybackAck(replyId, 'failed', error)
    this.onPlaybackFailed?.(error)
  }

  private stopLocal() {
    const source = this.currentSource
    this.currentSource = null
    if (source) {
      source.onended = null
      try { source.stop() } catch { /* already stopped */ }
    }
    this.stopTextAnimation()
    this.stopAudioLevelMonitoring()
    this.audioQueue = []
    this.isPlaying = false
    this.generationFinished = false
    this.playbackStarted = false
    this.playedAudioMs = 0
  }

  private startAudioLevelMonitoring(
    replyId: string,
    audioStartTime: number,
    offsetMs: number,
  ) {
    if (!this.analyser) return
    const analyser = this.analyser
    const dataArray = new Float32Array(analyser.fftSize)
    this.lastAudioLevelSentAt = 0
    this.audioMonitorReplyId = replyId
    this.audioMonitorStartTime = audioStartTime
    this.audioMonitorOffsetMs = offsetMs

    const update = (timestamp: number) => {
      if (!this.isPlaying) return
      if (timestamp - this.lastAudioLevelSentAt >= 40) {
        analyser.getFloatTimeDomainData(dataArray)
        let sumSquares = 0
        for (const value of dataArray) sumSquares += value * value
        const rms = Math.min(Math.sqrt(sumSquares / dataArray.length), 1)
        const audioTimeMs = offsetMs + (
          this.getAudioContext().currentTime - audioStartTime
        ) * 1000
        getAvatarInputApi().sendAudioData(rms, true, replyId, audioTimeMs)
        this.lastAudioLevelSentAt = timestamp
      }
      this.audioLevelTimer = requestAnimationFrame(update)
    }
    this.audioLevelTimer = requestAnimationFrame(update)
  }

  private stopAudioLevelMonitoring() {
    if (this.audioLevelTimer !== null) {
      cancelAnimationFrame(this.audioLevelTimer)
      this.audioLevelTimer = null
    }
    if (this.audioMonitorReplyId) {
      const audioTimeMs = this.audioMonitorOffsetMs + (
        this.getAudioContext().currentTime - this.audioMonitorStartTime
      ) * 1000
      getAvatarInputApi().sendAudioData(
        0,
        false,
        this.audioMonitorReplyId,
        audioTimeMs,
      )
    }
    this.audioMonitorReplyId = ''
    this.audioMonitorStartTime = 0
    this.audioMonitorOffsetMs = 0
  }

  private startTextAnimation(
    charOffset: number,
    textLength: number,
    charDuration: number,
    audioStartTime: number,
  ) {
    const audioContext = this.getAudioContext()
    const animate = () => {
      const elapsed = audioContext.currentTime - audioStartTime
      const charsToShow = Math.min(Math.floor(elapsed / Math.max(charDuration, 0.001)), textLength)
      this.onAudioProgress?.(charOffset + charsToShow)
      if (charsToShow < textLength && this.isPlaying) {
        this.textDisplayTimer = requestAnimationFrame(animate)
      }
    }
    this.textDisplayTimer = requestAnimationFrame(animate)
  }

  private stopTextAnimation() {
    if (this.textDisplayTimer !== null) {
      cancelAnimationFrame(this.textDisplayTimer)
      this.textDisplayTimer = null
    }
  }
}

const audioPlayer = new AudioPlayer()

export const useLLMStore = defineStore('llm', () => {
  const isGenerating = ref(false)
  const currentText = ref('')
  const displayText = ref('')
  const messages = ref<LLMMessage[]>([])
  const audioUnlocked = ref(false)
  const isPlaybackOwner = ref(false)
  const maxMessages = 50
  let pendingText = ''
  let activeReplyId = ''
  let lastChunkSeq = -1
  let playbackExpected = false

  const displayMessages = computed(() => messages.value.slice(-10))
  const avatarInput = getAvatarInputApi()

  audioPlayer.setCallbacks({
    onAudioProgress(charIndex) {
      displayText.value = pendingText.substring(0, Math.min(charIndex, pendingText.length))
    },
    onPlaybackStarted() {
      displayText.value = ''
    },
    onPlaybackFinished() {
      displayText.value = pendingText
      isGenerating.value = false
      activeReplyId = ''
    },
    onPlaybackFailed(error) {
      console.error('[HostPlayback] Playback failed:', error)
      displayText.value = pendingText
      isGenerating.value = false
      activeReplyId = ''
    },
  })

  avatarInput.onPlaybackRole((isOwner) => {
    if (isPlaybackOwner.value && !isOwner && activeReplyId) {
      audioPlayer.stop('播放端租约已转移')
    }
    isPlaybackOwner.value = isOwner
  })

  function addMessage(type: 'user' | 'assistant', text: string) {
    messages.value.push({
      id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
      type,
      text,
      timestamp: Date.now(),
    })
    if (messages.value.length > maxMessages) {
      messages.value = messages.value.slice(-maxMessages)
    }
  }

  async function unlockAudio(): Promise<boolean> {
    try {
      await audioPlayer.unlock()
      audioUnlocked.value = true
      avatarInput.setPlaybackReady(true)
      return true
    } catch (error) {
      audioUnlocked.value = false
      avatarInput.setPlaybackReady(false)
      console.error('[HostPlayback] Audio unlock failed:', error)
      return false
    }
  }

  function handleExternalChunk(raw: ReplyChunk) {
    const chunk = normalizeExternalChunk(raw)
    const replyId = chunk.reply_id || activeReplyId || `legacy_${Date.now()}`

    if (chunk.type === 'start') {
      if (activeReplyId && activeReplyId !== replyId) {
        audioPlayer.stop('收到新的回复')
      }
      activeReplyId = replyId
      lastChunkSeq = chunk.chunk_seq ?? -1
      playbackExpected = Boolean(chunk.playback_expected && isPlaybackOwner.value)
      isGenerating.value = true
      currentText.value = ''
      displayText.value = ''
      pendingText = ''
      if (playbackExpected) audioPlayer.begin(replyId)
      return
    }

    if (!activeReplyId || replyId !== activeReplyId) return
    if (chunk.chunk_seq !== undefined) {
      if (chunk.chunk_seq <= lastChunkSeq) return
      if (lastChunkSeq >= 0 && chunk.chunk_seq !== lastChunkSeq + 1) {
        audioPlayer.fail(replyId, '回复数据序号不连续')
        return
      }
      lastChunkSeq = chunk.chunk_seq
    }

    if (chunk.type === 'text' && chunk.text) {
      currentText.value += chunk.text
      pendingText += chunk.text
    } else if (chunk.type === 'audio' && playbackExpected && chunk.audio && chunk.text) {
      audioPlayer.queueAudio({
        replyId,
        data: chunk.audio,
        index: chunk.sentence_index ?? 0,
        text: chunk.text,
        charOffset: chunk.char_offset ?? 0,
        charLength: chunk.char_length ?? chunk.text.length,
      })
    } else if (chunk.type === 'end') {
      if (chunk.text) {
        currentText.value = chunk.text
        pendingText = chunk.text
        addMessage('assistant', chunk.text.trim())
      }
      if (playbackExpected) {
        audioPlayer.finishGeneration(replyId, chunk.audio_chunks ?? 0)
      } else {
        displayText.value = pendingText
        isGenerating.value = false
        activeReplyId = ''
      }
    } else if (chunk.type === 'error') {
      const errorText = chunk.text || '发生错误'
      currentText.value = errorText
      pendingText = errorText
      displayText.value = errorText
      audioPlayer.fail(replyId, errorText)
      isGenerating.value = false
      activeReplyId = ''
    }
  }

  function clearMessages() {
    audioPlayer.stop('用户清空了回复')
    messages.value = []
    currentText.value = ''
    displayText.value = ''
    pendingText = ''
    activeReplyId = ''
    isGenerating.value = false
  }

  function normalizeExternalChunk(data: ReplyChunk): ReplyChunk {
    const payload = data.data || {}
    return {
      type: data.type,
      reply_id: data.reply_id ?? payload.reply_id,
      chunk_seq: data.chunk_seq ?? payload.chunk_seq,
      text: data.text ?? payload.text,
      audio: data.audio ?? payload.audio,
      sentence_index: data.sentence_index ?? payload.sentence_index,
      char_offset: data.char_offset ?? payload.char_offset,
      char_length: data.char_length ?? payload.char_length,
      is_final: data.is_final ?? payload.is_final,
      playback_expected: data.playback_expected ?? payload.playback_expected,
      audio_chunks: data.audio_chunks ?? payload.audio_chunks,
    }
  }

  avatarInput.onHostChunk((chunk) => {
    handleExternalChunk(chunk as unknown as ReplyChunk)
  })

  return {
    isGenerating,
    currentText,
    displayText,
    messages,
    displayMessages,
    audioUnlocked,
    isPlaybackOwner,
    addMessage,
    clearMessages,
    unlockAudio,
    handleExternalChunk,
  }
})
