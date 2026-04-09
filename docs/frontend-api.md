# 前端 API 文档

本文档描述飞娜直播间前端的数据接口定义，基于 `src/mock/data.ts` 的模拟数据编写。

---

## 目录

1. [弹幕系统 (Danmaku)](#1-弹幕系统-danmaku)
2. [直播状态 (Stream)](#2-直播状态-stream)
3. [委托面板 (Mission)](#3-委托面板-mission)
4. [数据类型枚举](#4-数据类型枚举)

---

## 1. 弹幕系统 (Danmaku)

### 1.1 弹幕消息类型 `DanmakuMessage`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 弹幕唯一标识符 |
| `user` | `string` | ✅ | 发送者用户名 |
| `content` | `string` | ✅ | 弹幕内容 |
| `timestamp` | `Date` | ✅ | 发送时间戳 |
| `type` | `DanmakuType` | ✅ | 弹幕类型 |
| `color` | `string` | ❌ | 弹幕颜色（十六进制） |
| `badge` | `string` | ❌ | 用户徽章/粉丝牌 |

**示例：**
```typescript
{
  id: 'abc123',
  user: '樱花飘落',
  content: '主播今天好漂亮啊~',
  timestamp: new Date('2026-04-09T10:30:00'),
  type: DanmakuType.NORMAL,
  color: '#FFFFFF',
  badge: '粉丝牌'
}
```

### 1.2 弹幕状态管理 `useDanmakuStore`

**文件位置：** `src/stores/danmaku.ts`

**状态：**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `danmakuList` | `DanmakuMessage[]` | 弹幕列表 |
| `sortedList` | `DanmakuMessage[]` | 按时间排序的弹幕列表 |
| `isConnected` | `boolean` | WebSocket 连接状态 |
| `maxCount` | `number` | 最大保存弹幕数（默认 9） |

**方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `addDanmaku(message)` | `DanmakuMessage` | `void` | 添加一条弹幕 |
| `clearDanmaku()` | - | `void` | 清空所有弹幕 |
| `connect()` | - | `void` | 建立 WebSocket 连接 |
| `disconnect()` | - | `void` | 断开 WebSocket 连接 |
| `startMockGeneration()` | - | `void` | 启动模拟弹幕生成（用于测试） |

**使用示例：**
```typescript
import { useDanmakuStore } from '@/stores/danmaku'
import { DanmakuType } from '@/types/danmaku'

const danmakuStore = useDanmakuStore()

// 添加弹幕
danmakuStore.addDanmaku({
  id: 'msg-001',
  user: '月兔酱',
  content: '测试消息',
  timestamp: new Date(),
  type: DanmakuType.NORMAL
})

// 获取排序后的弹幕
const messages = danmakuStore.sortedList
```

---

## 2. 直播状态 (Stream)

### 2.1 直播状态类型 `StreamStatus`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `isLive` | `boolean` | ✅ | 是否正在直播 |
| `title` | `string` | ✅ | 直播间标题 |
| `startTime` | `Date` | ❌ | 直播开始时间 |
| `viewerCount` | `number` | ✅ | 当前观看人数 |
| `currentTopic` | `string` | ❌ | 当前话题 |

**示例：**
```typescript
{
  isLive: true,
  title: '🌸 春日游戏时光 - 和大家一起玩游戏',
  startTime: new Date('2026-04-09T09:00:00'),
  viewerCount: 1234,
  currentTopic: '讨论游戏配置推荐'
}
```

### 2.2 直播状态管理 `useStreamStore`

**文件位置：** `src/stores/stream.ts`

**状态：**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `currentTime` | `string` | 当前时钟（格式：`HH:MM.SS`） |
| `formattedTime` | `string` | 格式化后的时间（同 currentTime） |
| `isStreaming` | `boolean` | 是否正在直播 |
| `streamTitle` | `string` | 直播间标题 |
| `announcement` | `string` | 直播间公告/跑马灯文本 |
| `viewerCount` | `number` | 当前观看人数 |
| `currentTopic` | `string` | 当前话题 |

**方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `updateClock()` | - | `void` | 更新当前时钟 |
| `updateAnnouncement(text)` | `string` | `void` | 更新公告文本 |
| `setStreaming(status)` | `boolean` | `void` | 设置直播状态 |
| `startClock()` | - | `void` | 启动时钟更新（每 100ms） |
| `stopClock()` | - | `void` | 停止时钟更新 |

**使用示例：**
```typescript
import { useStreamStore } from '@/stores/stream'

const streamStore = useStreamStore()

// 启动时钟
streamStore.startClock()

// 更新公告
streamStore.updateAnnouncement('欢迎来到直播间！')

// 获取当前观看人数
const viewers = streamStore.viewerCount
```

---

## 3. 委托面板 (Mission)

### 3.1 委托数据类型 `MissionData`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `number` | ✅ | 委托 ID |
| `server` | `string` | ✅ | 服务器名称（如 `"cn"`） |
| `missions` | `string[][]` | ✅ | 委托内容数组（三维度：角色/武器/模组） |
| `createdAt` | `string` | ✅ | 数据创建时间 |

**missions 结构说明：**
```typescript
missions: [
  ['角色委托1', '角色委托2', ...],  // 下标 0: 角色任务
  ['武器委托1', '武器委托2', ...],  // 下标 1: 武器任务
  ['模组委托1', '模组委托2', ...]   // 下标 2: 模组任务
]
```

**示例：**
```typescript
{
  id: 20260409,
  server: 'cn',
  missions: [
    ['委托-角色-01', '委托-角色-02', '委托-角色-03'],
    ['委托-武器-01', '委托-武器-02'],
    ['委托-模组-01']
  ],
  createdAt: '2026-04-09T10:00:00Z'
}
```

### 3.2 委托状态管理 `useMissionStore`

**文件位置：** `src/stores/mission.ts`

**状态：**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `missionData` | `MissionData \| null` | 委托数据 |
| `isLoading` | `boolean` | 是否正在加载 |
| `error` | `string \| null` | 错误信息 |
| `lastFetchTime` | `Date \| null` | 最后获取时间 |
| `characterMissions` | `string[]` | 角色委托列表 |
| `weaponMissions` | `string[]` | 武器委托列表 |
| `modMissions` | `string[]` | 模组委托列表 |
| `refreshCountdown` | `string` | 刷新倒计时（格式：`MM:SS`） |

**方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `fetchMissions()` | - | `Promise<void>` | 获取最新的委托数据 |

**API 调用：**
```typescript
POST https://api.dna-builder.cn/graphql
Content-Type: application/json

{
  "query": "{ missionsIngame(server: \"cn\") { id server missions createdAt } }"
}
```

**响应示例：**
```json
{
  "data": {
    "missionsIngame": {
      "id": 20260409,
      "server": "cn",
      "missions": [
        ["角色委托1", "角色委托2", "角色委托3"],
        ["武器委托1", "武器委托2"],
        ["模组委托1"]
      ],
      "createdAt": "2026-04-09T10:00:00Z"
    }
  }
}
```

**使用示例：**
```typescript
import { useMissionStore } from '@/stores/mission'

const missionStore = useMissionStore()

// 获取委托数据
await missionStore.fetchMissions()

// 获取角色委托
const characterTasks = missionStore.characterMissions

// 获取刷新倒计时
const countdown = missionStore.refreshCountdown  // 如 "45:30"
```

---

## 4. 数据类型枚举

### 4.1 弹幕类型 `DanmakuType`

**文件位置：** `src/types/danmaku.ts`

```typescript
export enum DanmakuType {
  NORMAL = 'normal',      // 普通弹幕
  HIGHLIGHT = 'highlight', // 高亮弹幕
  GIFT = 'gift',          // 礼物弹幕
  SYSTEM = 'system',      // 系统消息
  WELCOME = 'welcome'     // 欢迎消息
}
```

| 枚举值 | 说明 | 使用场景 |
|--------|------|----------|
| `NORMAL` | 普通弹幕 | 一般用户发送的消息 |
| `HIGHLIGHT` | 高亮弹幕 | 重点消息、有颜色的弹幕 |
| `GIFT` | 礼物弹幕 | 用户赠送礼物时的通知 |
| `SYSTEM` | 系统消息 | 平台系统通知 |
| `WELCOME` | 欢迎消息 | 新用户进入直播间的欢迎 |

---

## 附录：Mock 数据参考

### 随机用户名池
```typescript
['樱花飘落', '游戏达人', '月兔酱', '技术宅', '星空漫步者',
 '咖啡爱好者', '音乐精灵', '动漫迷', '程序员小王', '设计师小李']
```

### 随机弹幕内容池
```typescript
['主播加油！', '这个操作太秀了！', '哈哈哈笑死我了',
 '学到了学到了', '666666', '主播声音好好听~',
 '这游戏我也在玩！', '求推荐配置', '几点下播呀？',
 '第一次来，关注了！', '太厉害了吧', '主播好可爱',
 '冲冲冲！', '支持支持', '来了老铁']
```

### 默认直播状态
```typescript
{
  isLive: true,
  title: '🌸 春日游戏时光 - 和大家一起玩游戏',
  startTime: new Date(Date.now() - 3600000),
  viewerCount: 1234,
  currentTopic: '讨论游戏配置推荐'
}
```

### 默认公告文本
```
'欢迎来到直播间！这里是个人简介/活动信息，这里是个人的简介/活动信息这里是个人的简介/活动信息，个人简介'
```
