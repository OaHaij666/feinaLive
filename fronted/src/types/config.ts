/** 配置类型定义 - 与后端 FullConfig Pydantic 模型对齐 */

export interface BilibiliConfig {
  room_id: number
  sessdata: string
  uid: number
}

export interface DouyinConfig {
  web_rid: string
  cookie: string
}

export interface LiveConfig {
  platform: 'bilibili' | 'douyin' | 'test'
}

export interface HostConfig {
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

export interface AgentConfig {
  enabled: boolean
  scenario_id: string
  mcp_url: string
  api_url: string
  api_key: string
  model: string
  temperature: number
  max_tokens: number
  disable_thinking: boolean
  poll_interval: number
  memory_threshold: number
  memory_idle_seconds: number
  memory_scan_interval_seconds: number
  memory_context_max_chars: number
  min_step_interval: number
  step_jitter: number
  commentary_interval: number
  min_commentary_interval: number
  commentary_hold_timeout: number
  memory_eagerness: number
  queue_max_size: number
  host_history_maxlen: number
  action_history_maxlen: number
  scenario_config: Record<string, unknown>
}

export interface RegisteredScenarioConfigField {
  key: string
  label: string
  input_type: 'text' | 'number' | 'select' | 'textarea' | 'checkbox'
  default: unknown
  description: string
  required: boolean
  options: Array<{ value: string; label: string }>
}

export interface RegisteredScenarioDefinition {
  scenario_id: string
  display_name: string
  description: string
  category: string
  capability_sources: string[]
  config_fields: RegisteredScenarioConfigField[]
}

export interface ScenarioCatalogPayload {
  selected_scenario_id: string
  scenarios: RegisteredScenarioDefinition[]
  restart_required?: boolean
}

export interface AvatarMotionConfig {
  source: 'autonomous' | 'browser'
  allow_browser_control: boolean
}

export interface AvatarLipSyncConfig {
  source: 'browser_audio' | 'disabled'
  sensitivity: number
  noise_gate: number
  attack_ms: number
  release_ms: number
}

export interface AvatarRendererConfig {
  engine: 'feina_avatar'
  model: 'tha3' | 'tha4' | 'tha4_student'
  backend: 'onnxruntime' | 'tensorrt'
  precision: 'fp32' | 'fp16'
  separable: boolean
  use_eyebrow: boolean
  frame_rate: number
  interpolation: 1 | 2 | 4
  super_resolution: 1 | 2 | 4
  ram_cache_mb: number
  vram_cache_mb: number
}

export interface AvatarSpoutConfig {
  enabled: boolean
  name: string
}

export interface AvatarPreviewConfig {
  enabled: boolean
  frame_rate: number
  quality: number
}

export interface AvatarConfig {
  enabled: boolean
  character: string
  motion: AvatarMotionConfig
  lip_sync: AvatarLipSyncConfig
  renderer: AvatarRendererConfig
  outputs: {
    spout: AvatarSpoutConfig
    preview: AvatarPreviewConfig
  }
}

export interface AIConfig {
  max_history_per_session: number
  summary_interval: number
  summary_idle_seconds: number
  summary_scan_interval_seconds: number
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
  default_provider: string
  min_duration_seconds: number
  max_duration_seconds: number
  queue_capacity: number
  per_user_limit: number
  allow_bare_bv: boolean
  accept_score: number
  reject_score: number
  llm_min_confidence: number
  search_candidates: number
  ducking_factor: number
  ducking_enabled: boolean
  local_directories: string[]
}

export interface StorageConfig {
  sqlite_path: string
  chroma_path: string
  chroma_collection: string
}

export interface AdminConfig {
  username: string
  identities: Record<string, string>
}

export interface EmbeddingConfig {
  provider: string
  model: string
  api_url: string
  api_key: string
  dimensions: number | null
  user_graph_enabled: boolean
  game_graph_enabled: boolean
}

export interface FullConfig {
  live: LiveConfig
  bilibili: BilibiliConfig
  douyin: DouyinConfig
  host: HostConfig
  llm: LLMConfig
  tts: TTSConfig
  volcano: VolcanoConfig
  agent: AgentConfig
  avatar: AvatarConfig
  ai: AIConfig
  messaging: MessagingConfig
  music: MusicConfigModel
  storage: StorageConfig
  announcement: string
  admin: AdminConfig
  embedding: EmbeddingConfig
  restart_required?: boolean
}

/** MASKED_PATTERN: 后端返回敏感字段时使用的掩码 */
export const MASKED = '****'
