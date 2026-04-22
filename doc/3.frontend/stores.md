# 前端状态管理

## 概述

前端使用 Pinia 进行状态管理，将不同业务领域的状态分散到不同的 store 中管理。

## Store 结构

```
stores/
├── danmaku.ts    # 弹幕状态
├── music.ts      # 音乐状态
├── llm.ts        # AI对话状态
├── mission.ts    # 任务状态
└── stream.ts     # 流状态
```

## Store 详解

### danmaku.ts - 弹幕状态

**职责**：管理弹幕列表和弹幕显示状态

**状态**：

| 状态 | 类型 | 说明 |
|-----|------|------|
| messages | Danmaku[] | 弹幕消息列表 |
| maxMessages | number | 最大显示数量 |

**Actions**：

| Action | 说明 |
|--------|------|
| addMessage(msg) | 添加弹幕消息 |
| clearMessages() | 清空弹幕列表 |

**使用示例**：

```typescript
import { useDanmakuStore } from '@/stores/danmaku'

const danmakuStore = useDanmakuStore()

// 添加弹幕
danmakuStore.addMessage({
  id: 'xxx',
  user: '用户名',
  content: '弹幕内容',
  timestamp: Date.now()
})

// 读取弹幕列表
const messages = danmakuStore.messages
```

---

### music.ts - 音乐状态

**职责**：管理音乐播放状态

**状态**：

| 状态 | 类型 | 说明 |
|-----|------|------|
| current | MusicItem | 当前播放歌曲 |
| queue | MusicItem[] | 播放队列 |
| volume | number | 音量 (0-1) |
| isPlaying | boolean | 是否播放中 |

**Actions**：

| Action | 说明 |
|--------|------|
| fetchQueue() | 获取播放队列 |
| playNext() | 播放下一首 |
| setVolume(vol) | 设置音量 |
| togglePlay() | 切换播放状态 |

**使用示例**：

```typescript
import { useMusicStore } from '@/stores/music'

const musicStore = useMusicStore()

// 获取队列
await musicStore.fetchQueue()

// 播放下一首
await musicStore.playNext()

// 设置音量
musicStore.setVolume(0.8)
```

---

### llm.ts - AI对话状态

**职责**：管理 AI 对话相关状态

**状态**：

| 状态 | 类型 | 说明 |
|-----|------|------|
| isReplying | boolean | AI是否正在回复 |
| currentReply | string | 当前回复文本 |
| replyHistory | Reply[] | 回复历史 |

**Actions**：

| Action | 说明 |
|--------|------|
| sendReply(user, content) | 发送消息获取AI回复 |
| clearReply() | 清空当前回复 |

---

### stream.ts - 流状态

**职责**：管理直播流相关状态

**状态**：

| 状态 | 类型 | 说明 |
|-----|------|------|
| isLive | boolean | 是否正在直播 |
| streamUrl | string | 流地址 |
| viewerCount | number | 观看人数 |

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Pinia 数据流                                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                              WebSocket / HTTP                                │  │
│   │                                                                             │  │
│   │   ws://localhost:8000/bilibili/ws/{room_id}                                │  │
│   │   http://localhost:8000/music/queue                                        │  │
│   │   http://localhost:8000/ai/reply                                           │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                            │
│                                        │ 数据响应                                   │
│                                        ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                              Composables                                     │  │
│   │                                                                             │  │
│   │   useBilibiliDanmaku()  ──── 处理弹幕消息 ────▶ danmakuStore.addMessage()  │  │
│   │   useHlsPlayer()        ──── 处理音乐状态 ────▶ musicStore.updateState()   │  │
│   │   useAdminCommands()    ──── 处理管理员指令 ───▶ 各 store 更新             │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                            │
│                                        │ 调用 Action                                │
│                                        ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                              Pinia Stores                                    │  │
│   │                                                                             │  │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│   │   │  danmaku    │  │   music     │  │    llm      │  │   stream    │       │  │
│   │   │             │  │             │  │             │  │             │       │  │
│   │   │ state:      │  │ state:      │  │ state:      │  │ state:      │       │  │
│   │   │ - messages  │  │ - current   │  │ - isReplying│  │ - isLive    │       │  │
│   │   │ - maxMsgs   │  │ - queue     │  │ - reply     │  │ - streamUrl │       │  │
│   │   │             │  │ - volume    │  │             │  │             │       │  │
│   │   │ actions:    │  │ actions:    │  │ actions:    │  │ actions:    │       │  │
│   │   │ - addMsg    │  │ - fetchQueue│  │ - sendReply │  │ - setLive   │       │  │
│   │   │ - clear     │  │ - playNext  │  │ - clear     │  │             │       │  │
│   │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │  │
│   │          │                │                │                │              │  │
│   └──────────┼────────────────┼────────────────┼────────────────┼──────────────┘  │
│              │                │                │                │                  │
│              │                │                │                │                  │
│              ▼                ▼                ▼                ▼                  │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                              Vue Components                                 │  │
│   │                                                                             │  │
│   │   组件通过 storeToRefs() 响应式绑定状态                                     │  │
│   │   组件通过直接调用 store.xxx() 触发 Action                                 │  │
│   │                                                                             │  │
│   │   <script setup>                                                           │  │
│   │   const store = useDanmakuStore()                                          │  │
│   │   const { messages } = storeToRefs(store)  // 响应式                       │  │
│   │   store.addMessage(msg)                    // 调用 Action                  │  │
│   │   </script>                                                                │  │
│   │                                                                             │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## 最佳实践

### 1. 使用 storeToRefs

```typescript
// 推荐：保持响应式
const { messages } = storeToRefs(danmakuStore)

// 不推荐：失去响应式
const messages = danmakuStore.messages
```

### 2. 解构 Actions

```typescript
// 推荐：直接解构 action
const { addMessage, clearMessages } = danmakuStore

// 使用
addMessage(msg)
```

### 3. 组合式使用

```typescript
// composables/useBilibiliDanmaku.ts
export function useBilibiliDanmaku(roomId: string) {
  const danmakuStore = useDanmakuStore()
  const musicStore = useMusicStore()
  
  const ws = new WebSocket(`ws://...`)
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    switch (data.type) {
      case 'danmaku':
        danmakuStore.addMessage(data.data)
        break
      case 'music_added':
        musicStore.fetchQueue()
        break
    }
  }
  
  return { ws }
}
```

## 相关文档

- [项目结构](./project-structure.md)
- [组件说明](./components.md)
