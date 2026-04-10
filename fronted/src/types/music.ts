export interface MusicItem {
  id: string
  bvid: string
  title: string
  upName: string
  upFace?: string
  duration: number
  audioUrl: string
  coverUrl: string
  status: MusicStatus
  requestedBy: string
  requestedAt: Date
  playedAt?: Date
}

export enum MusicStatus {
  PENDING = 'pending',
  PLAYING = 'playing',
  COMPLETED = 'completed',
  FAILED = 'failed'
}

export interface QueueStats {
  totalPlayed: number
  totalQueue: number
  current: MusicItem | null
}

export interface QueueResponse {
  current: MusicItem | null
  queue: MusicItem[]
  total: number
}
