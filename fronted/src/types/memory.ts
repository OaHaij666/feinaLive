export interface MemoryAtom {
  id: number
  parent_memory_id: number
  atom_type: string
  content: string
  entities: string[]
  importance: number
  confidence: number
  created_at: number
  last_accessed_at: number
  last_reinforced_at: number | null
  event_time: number | null
  ttl_days: number
  expires_at: number
  status: string
  reinforcement_count: number
  decay_type: string
  game_id: string | null
  user_id: string | null
  session_id: string | null
  metadata: Record<string, unknown>
  final_score?: number
  bm25_score?: number
  temporal_score?: number
}

export interface AtomListResponse {
  items: MemoryAtom[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface MemoryStats {
  total_atoms: number
  status_breakdown: Record<string, number>
  atom_type_breakdown: Record<string, number>
  importance_distribution: Record<string, number>
  graph_nodes: number
  graph_edges: number
  scope: { games: number; users: number; sessions: number }
  session: {
    active: boolean
    core_length: number
    important_length: number
    recent_length: number
    pending_count: number
    summarized_until_id: number
  }
}

export interface RecallResponse {
  query: string
  k: number
  elapsed_time_ms: number
  total: number
  results: MemoryAtom[]
}

export interface GraphNode {
  id: string
  type: string
  label: string
  weight: number
  degree: number
  metadata: Record<string, unknown>
  x?: number
  y?: number
  vx?: number
  vy?: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation_type: string
  weight: number
  confidence: number
  memory_id?: number
  metadata: Record<string, unknown>
}

export interface GraphPayload {
  enabled: boolean
  mode: string
  query: string | null
  memory_id: number | null
  filters: Record<string, unknown>
  summary: {
    visible_node_count: number
    visible_edge_count: number
    visible_memory_count: number
    node_type_breakdown: Record<string, number>
    relation_breakdown: Record<string, number>
  }
  top_nodes: GraphNode[]
  top_memories: Array<Record<string, unknown>>
  snapshot: {
    nodes: GraphNode[]
    edges: GraphEdge[]
    memories: Array<Record<string, unknown>>
  }
}

export interface SessionMemoryPayload {
  active: boolean
  core: string
  important: string
  recent: string
  pending_events: Array<{
    event_id: number
    event_type: string
    content: string
    metadata: Record<string, unknown>
    created_at: number
  }>
  summarized_until_id: number
}

export interface InjectPreviewPayload {
  target: string
  game_id: string
  user_id: string | null
  content: string
}

export interface MemoryBackup {
  name: string
  path: string
  file_count: number
  size_bytes: number
  created_at: number
}
