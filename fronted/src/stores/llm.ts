import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAvatarInputApi } from '@/composables/useAvatarInput'

export interface LLMMessage {
  id: string
  type: 'user' | 'assistant'
  text: string
  timestamp: number
}

export interface LLMState {
  isGenerating: boolean
  currentText: string
  messages: LLMMessage[]
}

const API_BASE = '/ai'

interface AudioChunk {
  data: string
  index: number
  text: string
  charOffset: number
  charLength: number
  duration: number
}

class AudioPlayer {
  private audioContext: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private audioQueue: AudioChunk[] = []
  private isPlaying: boolean = false
  private currentSource: AudioBufferSourceNode | null = null
  private onFirstAudioPlay: (() => void) | null = null
  private onAudioProgress: ((charIndex: number) => void) | null = null
  private isFirstAudio: boolean = true
  private textDisplayTimer: number | null = null
  private audioLevelTimer: number | null = null
  private currentBuffer: AudioBuffer | null = null

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

  setOnFirstAudioPlay(callback: () => void) {
    this.onFirstAudioPlay = callback
  }

  setOnAudioProgress(callback: (charIndex: number) => void) {
    this.onAudioProgress = callback
  }

  queueAudio(
    base64Data: string,
    index: number,
    text: string,
    charOffset: number,
    charLength: number
  ) {
    this.audioQueue.push({
      data: base64Data,
      index,
      text,
      charOffset,
      charLength,
      duration: 0,
    })
    this.audioQueue.sort((a, b) => a.index - b.index)
    this.playNext()
  }

  private startAudioLevelMonitoring() {
    const api = getAvatarInputApi()
    
    if (!this.analyser) {
      console.warn('Analyser not initialized')
      return
    }
    
    const analyser = this.analyser
    const dataArray = new Uint8Array(analyser.frequencyBinCount)
    
    const updateAudioLevel = () => {
      if (!this.isPlaying) {
        return
      }
      
      analyser.getByteFrequencyData(dataArray)
      
      let sum = 0
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i]
      }
      const average = sum / dataArray.length
      const normalizedLevel = Math.min(average / 100, 1)
      
      console.log('[AudioLevel] level:', normalizedLevel.toFixed(3), 'speaking:', true)
      
      if (api.setSpeaking) {
        api.setSpeaking(true)
      }
      if (api.sendAudioData) {
        api.sendAudioData(normalizedLevel, true)
      }
      
      this.audioLevelTimer = requestAnimationFrame(updateAudioLevel)
    }
    
    updateAudioLevel()
  }

  private stopAudioLevelMonitoring() {
    if (this.audioLevelTimer) {
      cancelAnimationFrame(this.audioLevelTimer)
      this.audioLevelTimer = null
    }
    
    const api = getAvatarInputApi()
    console.log('[AudioLevel] stopped, speaking: false')
    if (api.setSpeaking) {
      api.setSpeaking(false)
    }
    if (api.sendAudioData) {
      api.sendAudioData(0, false)
    }
  }

  private async playNext() {
    if (this.isPlaying || this.audioQueue.length === 0) return

    this.isPlaying = true
    const chunk = this.audioQueue.shift()!

    try {
      const audioContext = this.getAudioContext()

      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }

      const binaryString = atob(chunk.data)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }

      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer)
      chunk.duration = audioBuffer.duration
      this.currentBuffer = audioBuffer

      if (this.isFirstAudio && this.onFirstAudioPlay) {
        this.isFirstAudio = false
        this.onFirstAudioPlay()
      }

      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(this.analyser!)

      this.currentSource = source

      const textLength = chunk.charLength
      const startTime = audioContext.currentTime
      const duration = audioBuffer.duration
      const charDuration = duration / textLength
      const charOffset = chunk.charOffset

      this.startTextAnimation(charOffset, textLength, charDuration, startTime)
      this.startAudioLevelMonitoring()

      await new Promise<void>((resolve) => {
        source.onended = () => {
          this.currentSource = null
          this.currentBuffer = null
          if (this.textDisplayTimer !== null) {
            cancelAnimationFrame(this.textDisplayTimer)
            this.textDisplayTimer = null
          }
          this.stopAudioLevelMonitoring()
          resolve()
        }
        source.start(0)
      })
    } catch (error) {
      console.error('Audio playback error:', error)
      this.stopAudioLevelMonitoring()
    } finally {
      this.isPlaying = false
      this.playNext()
    }
  }

  private startTextAnimation(
    charOffset: number,
    textLength: number,
    charDuration: number,
    audioStartTime: number
  ) {
    const audioContext = this.getAudioContext()

    const animate = () => {
      const elapsed = audioContext.currentTime - audioStartTime
      const charsToShow = Math.min(Math.floor(elapsed / charDuration), textLength)
      const currentIdx = charOffset + charsToShow

      if (this.onAudioProgress) {
        this.onAudioProgress(currentIdx)
      }

      if (charsToShow < textLength && this.isPlaying) {
        this.textDisplayTimer = requestAnimationFrame(animate)
      }
    }

    this.textDisplayTimer = requestAnimationFrame(animate)
  }

  stop() {
    if (this.currentSource) {
      this.currentSource.stop()
      this.currentSource = null
    }
    if (this.textDisplayTimer !== null) {
      cancelAnimationFrame(this.textDisplayTimer)
      this.textDisplayTimer = null
    }
    this.stopAudioLevelMonitoring()
    this.audioQueue = []
    this.isPlaying = false
    this.isFirstAudio = true
  }

  reset() {
    this.isFirstAudio = true
  }
}

const audioPlayer = new AudioPlayer()

export const useLLMStore = defineStore('llm', () => {
  const isGenerating = ref(false)
  const currentText = ref('')
  const displayText = ref('')
  const messages = ref<LLMMessage[]>([])
  const maxMessages = 50
  let pendingText = ''
  let audioReady = false

  const displayMessages = computed(() => {
    return messages.value.slice(-10)
  })

  const latestAssistantMessage = computed(() => {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].type === 'assistant') {
        return messages.value[i]
      }
    }
    return null
  })

  function addMessage(type: 'user' | 'assistant', text: string) {
    const message: LLMMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type,
      text,
      timestamp: Date.now(),
    }
    messages.value.push(message)
    if (messages.value.length > maxMessages) {
      messages.value = messages.value.slice(-maxMessages)
    }
  }

  function appendToCurrentText(text: string) {
    currentText.value += text
  }

  function finalizeCurrentText() {
    if (currentText.value.trim()) {
      addMessage('assistant', currentText.value.trim())
      currentText.value = ''
    }
  }

  function clearMessages() {
    messages.value = []
    currentText.value = ''
    displayText.value = ''
  }

  async function sendReply(user: string, content: string): Promise<void> {
    if (isGenerating.value) {
      return
    }

    addMessage('user', content)
    isGenerating.value = true
    currentText.value = ''
    displayText.value = ''
    pendingText = ''
    audioReady = false
    audioPlayer.stop()
    audioPlayer.reset()

    audioPlayer.setOnFirstAudioPlay(() => {
      audioReady = true
      displayText.value = ''
    })

    audioPlayer.setOnAudioProgress((charIndex: number) => {
      if (pendingText && charIndex <= pendingText.length) {
        displayText.value = pendingText.substring(0, charIndex)
      }
    })

    try {
      const response = await fetch(`${API_BASE}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user, content }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No reader available')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              handleStreamChunk(data)
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }

      finalizeCurrentText()
    } catch (error) {
      console.error('LLM reply error:', error)
      addMessage('assistant', '抱歉，回复生成失败，请稍后重试。')
    } finally {
      isGenerating.value = false
    }
  }

  function handleStreamChunk(data: {
    type: string
    text?: string
    audio?: string
    sentence_index?: number
    char_offset?: number
    char_length?: number
    is_final?: boolean
  }) {
    switch (data.type) {
      case 'start':
        currentText.value = ''
        pendingText = ''
        displayText.value = ''
        break
      case 'text':
        if (data.text) {
          currentText.value += data.text
          pendingText += data.text
          if (audioReady) {
            displayText.value = pendingText
          }
        }
        break
      case 'audio':
        if (data.audio && data.text) {
          audioPlayer.queueAudio(
            data.audio,
            data.sentence_index || 0,
            data.text,
            data.char_offset || 0,
            data.char_length || data.text.length
          )
        }
        break
      case 'end':
        if (data.text) {
          currentText.value = data.text
          pendingText = data.text
          if (!audioReady) {
            displayText.value = data.text
          }
        }
        break
      case 'error':
        currentText.value = data.text || '发生错误'
        displayText.value = data.text || '发生错误'
        break
    }
  }

  return {
    isGenerating,
    currentText,
    displayText,
    messages,
    displayMessages,
    latestAssistantMessage,
    addMessage,
    appendToCurrentText,
    finalizeCurrentText,
    clearMessages,
    sendReply,
  }
})
