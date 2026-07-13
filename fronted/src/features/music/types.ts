export type QueueEntryStatus =
  | 'pending'
  | 'playing'
  | 'paused'
  | 'completed'
  | 'skipped'
  | 'rejected'
  | 'failed'
  | 'cancelled'

export interface Track {
  id: string
  provider: string
  source_id: string
  title: string
  artists: string[]
  duration_seconds: number
  cover_url: string
  metadata: Record<string, unknown>
}

export interface QueueEntry {
  id: string
  track: Track
  requested_by: string
  request_id: string
  status: QueueEntryStatus
  requested_at: string
  started_at?: string | null
  finished_at?: string | null
  failure_reason: string
}

export interface MusicState {
  revision: number
  current: QueueEntry | null
  queue: QueueEntry[]
  paused: boolean
  volume: number
  ducking_factor: number
  ducking_enabled: boolean
  effective_volume: number
  playback_owner_id?: string | null
}

export interface ProviderSearchResult {
  source_id: string
  title: string
  artist: string
  duration_seconds: number
  cover_url: string
  metadata: Record<string, unknown>
}

export interface MusicRequestResult {
  accepted: boolean
  intercepted: boolean
  entry?: QueueEntry | null
  error_code: string
  error: string
  classification?: {
    verdict: 'accept' | 'reject' | 'review'
    source: 'cache' | 'rules' | 'llm' | 'provider'
    confidence?: number | null
    reason: string
  } | null
}
