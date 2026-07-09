/** 配置类型定义 - 与后端 FullConfig Pydantic 模型对齐 */

export interface BilibiliConfig {
  room_id: number
  sessdata: string
  uid: number
  use_test_room: boolean
}

export interface HostConfig {
  room_id: number
  reply_interval: number
  max_reply_length: number
  api_url: string
  api_key: string
  model: string
  temperature: number
  top_p: number
  max_tokens: number
  disable_thinking: boolean
}

export interface LLMConfig {
  api_url: string
  api_key: string
  model: string
  temperature: number
  top_p: number
  max_tokens: number
  auto_collect_min_views: number
  disable_thinking: boolean
}

export interface TTSConfig {
  provider: string
  voice: string
  encoding: string
  speed_ratio: number
}

export interface VolcanoConfig {
  appid: string
  access_token: string
  speaker_id: string
}

export interface GameConfig {
  enabled: boolean
  adapter: string
  mcp_url: string
  api_url: string
  api_key: string
  model: string
  temperature: number
  max_tokens: number
  disable_thinking: boolean
  poll_interval: number
  memory_threshold: number
  min_step_interval: number
  step_jitter: number
  commentary_interval: number
  min_commentary_interval: number
  commentary_hold_timeout: number
  memory_eagerness: number
  default_character: string
  queue_max_size: number
  host_history_maxlen: number
  game_history_maxlen: number
}

export interface EasyVtuberInputConfig {
  type: string
  osf_address: string
  mouse_range: string
}

export interface EasyVtuberModelConfig {
  version: string
  precision: string
  separable: boolean
  use_tensorrt: boolean
  use_eyebrow: boolean
}

export interface EasyVtuberPerformanceConfig {
  frame_rate: number
  interpolation: string
  super_resolution: string
  ram_cache: string
  vram_cache: string
}

export interface EasyVtuberWebSocketConfig {
  enabled: boolean
  port: number
  host: string
}

export interface EasyVtuberOutputConfig {
  websocket: EasyVtuberWebSocketConfig
}

export interface EasyVtuberConfig {
  enabled: boolean
  character: string
  input: EasyVtuberInputConfig
  model: EasyVtuberModelConfig
  performance: EasyVtuberPerformanceConfig
  output: EasyVtuberOutputConfig
}

export interface AIConfig {
  max_history_per_session: number
  summary_interval: number
  max_recent_messages: number
  poll_interval_seconds: number
}

export interface MessagingConfig {
  danmaku_starvation_seconds: number
  danmaku_flood_threshold: number
  danmaku_flood_window: number
  gift_starvation_seconds: number
  gift_flood_threshold: number
  gift_flood_window: number
  gift_value_highest: number
  gift_value_high: number
  gift_value_normal: number
  gift_value_low: number
  user_cooldown_seconds: number
  default_ttl_seconds: number
  rate_limit_commentary: number
  rate_limit_danmaku: number
  rate_limit_gift: number
}

export interface MusicConfigModel {
  verify_min_duration: number
  verify_max_duration: number
  verify_max_comments: number
}

export interface DatabaseConfig {
  url: string
}

export interface UpVideosConfig {
  incremental_days: number
  full_refresh_days: number
}

export interface AdminConfig {
  uid: number
  username: string
}

export interface EmbeddingConfig {
  provider: string
  model: string
  api_url: string
  api_key: string
  dimensions: number | null
}

export interface FullConfig {
  bilibili: BilibiliConfig
  host: HostConfig
  llm: LLMConfig
  tts: TTSConfig
  volcano: VolcanoConfig
  game: GameConfig
  easyvtuber: EasyVtuberConfig
  ai: AIConfig
  messaging: MessagingConfig
  music_config: MusicConfigModel
  database: DatabaseConfig
  up_videos: UpVideosConfig
  trusted_ups: Array<{ uid: number | string; name: string; bvid?: string }>
  default_playlist: Array<{ bvid: string; title: string; artist?: string }>
  announcement: string
  admin: AdminConfig
  embedding: EmbeddingConfig
}

/** MASKED_PATTERN: 后端返回敏感字段时使用的掩码 */
export const MASKED = '****'

/** 判断字段是否处于掩码状态（用户未修改） */
export function isMasked(value: string): boolean {
  return value.includes(MASKED)
}
