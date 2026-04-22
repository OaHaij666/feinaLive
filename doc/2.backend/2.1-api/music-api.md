# 音乐播放 API

## 概述

音乐模块提供点歌服务、播放队列管理、音乐库管理等功能。支持通过 BV 号或歌名点歌，自动验证音乐视频并获取音频流。

## API 端点

### 播放队列管理

#### 获取播放队列

获取当前播放队列信息。

```
GET /music/queue
```

**响应示例**：

```json
{
  "current": {
    "id": "uuid-xxx",
    "bvid": "BV1xx...",
    "title": "歌曲名称",
    "upName": "UP主名称",
    "upFace": "https://...",
    "duration": 240,
    "audioUrl": "https://...",
    "coverUrl": "https://...",
    "status": "playing",
    "requestedBy": "用户名",
    "requestedAt": "2024-01-01T00:00:00",
    "playedAt": "2024-01-01T00:00:00"
  },
  "queue": [],
  "total": 0
}
```

**响应字段**：

| 字段 | 类型 | 说明 |
|-----|------|------|
| current | MusicItem | 当前播放的歌曲 |
| queue | MusicItem[] | 等待队列 |
| total | number | 队列中歌曲数量 |

---

#### 获取播放统计

获取播放统计数据。

```
GET /music/stats
```

**响应示例**：

```json
{
  "totalPlayed": 100,
  "totalQueue": 3,
  "current": { /* 当前播放 */ }
}
```

---

#### 获取当前播放

获取当前正在播放的歌曲。

```
GET /music/current
```

**响应示例**：

```json
{
  "id": "uuid-xxx",
  "bvid": "BV1xx...",
  "title": "歌曲名称",
  "upName": "UP主名称",
  "duration": 240,
  "audioUrl": "https://...",
  "coverUrl": "https://..."
}
```

**错误响应**：

```json
{
  "detail": "当前没有播放"
}
```

---

#### 播放下一首

切换到下一首歌曲。

```
POST /music/next
```

**响应示例**：

```json
{
  "id": "uuid-xxx",
  "bvid": "BV1xx...",
  "title": "下一首歌曲",
  "upName": "UP主名称",
  "duration": 180,
  "audioUrl": "https://...",
  "coverUrl": "https://..."
}
```

如果队列为空，会从音乐库随机选取一首歌曲。

---

#### 跳过当前歌曲

跳过当前播放的歌曲。

```
POST /music/skip
```

**响应示例**：

```json
{
  "id": "uuid-xxx",
  "bvid": "BV1yy...",
  "title": "下一首歌曲"
}
```

---

#### 移除当前歌曲并跳过

移除当前歌曲并从音乐库禁用。

```
POST /music/remove-current
```

**响应示例**：

```json
{
  "message": "已移除 BV1xx... 并跳到下一首"
}
```

---

#### 从队列移除指定歌曲

根据 ID 从队列中移除歌曲。

```
DELETE /music/queue/{item_id}
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| item_id | string | 音乐项 ID |

**响应示例**：

```json
{
  "message": "已从队列移除"
}
```

**错误响应**：

```json
{
  "detail": "未找到该音乐项"
}
```

---

#### 清空播放队列

清空整个播放队列。

```
DELETE /music/queue
```

**响应示例**：

```json
{
  "message": "已清空队列，共移除 5 首"
}
```

---

#### 添加歌曲到队列

通过 BV 号添加歌曲到队列。

```
POST /music/add/{bvid}
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| bvid | string | B站视频 BV 号 |
| requestedBy | string | 点歌用户（查询参数，默认 admin） |

**响应示例**：

```json
{
  "id": "uuid-xxx",
  "bvid": "BV1xx...",
  "title": "歌曲名称",
  "upName": "UP主名称",
  "duration": 240,
  "audioUrl": "https://...",
  "coverUrl": "https://..."
}
```

**错误响应**：

```json
{
  "detail": "获取音乐失败，视频可能不存在"
}
```

---

#### 获取播放历史

获取已播放的歌曲历史记录。

```
GET /music/history
```

**响应示例**：

```json
[
  {
    "id": "uuid-xxx",
    "bvid": "BV1xx...",
    "title": "已播放歌曲",
    "upName": "UP主名称",
    "duration": 240,
    "status": "completed",
    "playedAt": "2024-01-01T00:00:00"
  }
]
```

---

### 音量控制

#### 获取音量

获取当前音量设置。

```
GET /music/volume
```

**响应示例**：

```json
{
  "volume": 0.8
}
```

---

#### 设置音量

设置播放音量。

```
PATCH /music/volume?volume=0.5
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| volume | float | 音量值（0.0 - 1.0） |

**响应示例**：

```json
{
  "volume": 0.5
}
```

---

### 音频代理

#### 音频流代理

代理 B站音频流，解决跨域问题。

```
GET /music/proxy/audio?url={audio_url}
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| url | string | B站音频直链 URL（需 URL 编码） |

**响应**：

- Content-Type: `audio/mp4`
- 流式返回音频数据

**使用场景**：

```
前端请求 ──▶ /music/proxy/audio?url=xxx ──▶ B站音频服务器
                                              │
                                              ▼
                                         音频流返回
```

---

### 音乐库管理

#### 获取音乐库列表

获取预备歌单列表。

```
GET /music/library
```

**响应示例**：

```json
{
  "items": [
    {
      "id": "uuid-xxx",
      "bvid": "BV1xx...",
      "title": "歌曲名称",
      "upName": "UP主名称",
      "upFace": "https://...",
      "duration": 240,
      "coverUrl": "https://...",
      "enabled": true
    }
  ],
  "total": 10
}
```

---

#### 添加歌曲到音乐库

将歌曲添加到预备歌单。

```
POST /music/library/{bvid}
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| bvid | string | B站视频 BV 号 |

**响应示例**：

```json
{
  "id": "uuid-xxx",
  "bvid": "BV1xx...",
  "title": "歌曲名称",
  "upName": "UP主名称",
  "enabled": true
}
```

**错误响应**：

```json
{
  "detail": "获取视频信息失败"
}
```

---

#### 从音乐库移除歌曲

从预备歌单移除歌曲。

```
DELETE /music/library/{bvid}
```

**响应示例**：

```json
{
  "message": "已从音乐库移除"
}
```

---

#### 设置歌曲启用状态

启用或禁用音乐库中的歌曲。

```
PATCH /music/library/{bvid}/enabled?enabled=true
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| bvid | string | B站视频 BV 号 |
| enabled | boolean | 是否启用 |

**响应示例**：

```json
{
  "message": "已设置 BV1xx... 启用状态为 true"
}
```

---

#### 初始化音乐库

使用默认歌单初始化音乐库。

```
POST /music/library/init
```

**响应示例**：

```json
{
  "message": "音乐库初始化完成"
}
```

---

### UP主视频管理

#### 刷新 UP主视频

刷新信任 UP主的视频列表。

```
POST /music/up-videos/refresh
```

**响应示例**：

```json
{
  "message": "UP主视频刷新完成"
}
```

---

#### 搜索 UP主视频

在信任 UP主的视频中搜索歌曲。

```
GET /music/up-videos/search?keyword=歌名
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| keyword | string | 搜索关键词 |

**响应示例**：

```json
{
  "keyword": "歌名",
  "count": 5,
  "results": [
    {
      "bvid": "BV1xx...",
      "title": "匹配的歌曲",
      "upName": "UP主名称",
      "duration": 240,
      "coverUrl": "https://..."
    }
  ]
}
```

---

## 数据模型

### MusicItem

```typescript
interface MusicItem {
  id: string;           // 唯一 ID
  bvid: string;         // B站 BV 号
  title: string;        // 歌曲标题
  upName: string;       // UP主名称
  upFace?: string;      // UP主头像
  duration: number;     // 时长（秒）
  audioUrl: string;     // 音频直链
  coverUrl: string;     // 封面 URL
  status: MusicStatus;  // 播放状态
  requestedBy: string;  // 点歌用户
  requestedAt: string;  // 点歌时间
  playedAt?: string;    // 播放时间
}
```

### MusicStatus

```typescript
enum MusicStatus {
  PENDING = "pending",     // 等待播放
  PLAYING = "playing",     // 正在播放
  COMPLETED = "completed", // 已完成
  FAILED = "failed"        // 播放失败
}
```

### MusicLibraryItem

```typescript
interface MusicLibraryItem {
  id: string;           // 唯一 ID
  bvid: string;         // B站 BV 号
  title: string;        // 歌曲标题
  upName: string;       // UP主名称
  upFace?: string;      // UP主头像
  duration: number;     // 时长（秒）
  coverUrl: string;     // 封面 URL
  enabled: boolean;     // 是否启用
}
```

---

## 点歌流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        点歌业务流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    用户弹幕: "点歌 歌曲名" 或 "点歌 BV1xx..."                   │
│                              │                                  │
│                              ▼                                  │
│                    ┌─────────────────┐                         │
│                    │ is_music_request│                         │
│                    │   判断点歌请求  │                         │
│                    └────────┬────────┘                         │
│                              │                                  │
│              ┌───────────────┼───────────────┐                  │
│              │               │               │                  │
│              ▼               ▼               ▼                  │
│         不是点歌        提取 BV 号       提取歌名               │
│              │               │               │                  │
│              ▼               │               │                  │
│         正常弹幕           ──┴───────────────┘                  │
│                              │                                  │
│                              ▼                                  │
│                    ┌─────────────────┐                         │
│                    │  检查用户限制   │                         │
│                    │  - 每人最多2首  │                         │
│                    │  - 队列最多5首  │                         │
│                    └────────┬────────┘                         │
│                              │                                  │
│                    ┌─────────┴─────────┐                       │
│                    │                   │                       │
│                    ▼                   ▼                       │
│               允许点歌            拒绝点歌                     │
│                    │                   │                       │
│                    ▼                   ▼                       │
│         ┌─────────────────┐    返回错误信息                    │
│         │   搜索歌曲      │                                      │
│         └────────┬────────┘                                      │
│                  │                                               │
│     ┌────────────┼────────────┐                                  │
│     │            │            │                                  │
│     ▼            ▼            ▼                                  │
│ 预备歌单     UP主视频      B站搜索                               │
│ 匹配        匹配           (未实现)                              │
│     │            │                                               │
│     └────────────┼────────────┘                                  │
│                  │                                               │
│                  ▼                                               │
│         ┌─────────────────┐                                     │
│         │   LLM 验证      │                                     │
│         │ (非预备歌单时)  │                                     │
│         └────────┬────────┘                                     │
│                  │                                               │
│         ┌────────┴────────┐                                     │
│         │                 │                                     │
│         ▼                 ▼                                     │
│    验证通过          验证失败                                   │
│         │                 │                                     │
│         ▼                 ▼                                     │
│  ┌─────────────┐    返回错误                                   │
│  │ 获取音频URL │                                                │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ 加入播放队列│                                                │
│  └─────────────┘                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 错误码

| 错误码 | HTTP 状态码 | 说明 |
|-------|------------|------|
| MUSIC_NOT_FOUND | 404 | 视频不存在或无法获取 |
| QUEUE_FULL | 400 | 播放队列已满 |
| USER_LIMIT | 400 | 用户点歌数量已达上限 |
| NOT_MUSIC | 400 | 视频不是音乐类型 |
| AUDIO_URL_FAILED | 400 | 获取音频 URL 失败 |

---

## 相关文档

- [B站弹幕 API](./bilibili-api.md)
- [点歌业务流程](../../4.business/music-flow.md)
- [音乐数据模型](../2.3-models/music-models.md)
