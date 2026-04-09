export enum DanmakuType {
  NORMAL = 'normal',
  HIGHLIGHT = 'highlight',
  GIFT = 'gift',
  SYSTEM = 'system',
  WELCOME = 'welcome'
}

export interface DanmakuMessage {
  id: string
  user: string
  content: string
  timestamp: Date
  type: DanmakuType
  color?: string
  badge?: string
}
