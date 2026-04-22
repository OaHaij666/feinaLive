# B站弹幕 API

## 概述

B站弹幕模块负责与B站直播间建立 WebSocket 连接，实时接收弹幕消息并分发给前端。

## API 端点

### HTTP API

#### 验证 SESSDATA

验证当前配置的 SESSDATA 是否有效。

```
GET /bilibili/sessdata/verify
```

**响应示例**：

```json
{
  "valid": true,
  "uname": "用户名",
  "error": ""
}
```

**响应字段**：

| 字段 | 类型 | 说明 |
|-----|------|------|
| valid | boolean | SESSDATA 是否有效 |
| uname | string | 用户名（有效时返回） |
| error | string | 错误信息（无效时返回） |

---

#### 更新 SESSDATA

动态更新 SESSDATA 配置。

```
POST /bilibili/sessdata/update
```

**请求体**：

```json
{
  "sessdata": "your_sessdata_value"
}
```

**响应示例**：

```json
{
  "success": true
}
```

**错误响应**：

```json
{
  "success": false,
  "error": "错误信息"
}
```

---

### WebSocket API

#### 弹幕 WebSocket

连接直播间弹幕流。

```
WebSocket /bilibili/ws/{room_id}
```

**参数**：

| 参数 | 类型 | 说明 |
|-----|------|------|
| room_id | string | B站直播间 ID |

**连接流程**：

```
┌─────────────┐     WebSocket      ┌─────────────┐
│   前端      │ ──────────────────▶│   后端      │
│  (浏览器)   │                    │  (FastAPI)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ 连接 B站弹幕服务器
                                          ▼
                                   ┌─────────────┐
                                   │ B站弹幕服务 │
                                   └─────────────┘
```

**消息格式**：

服务端推送的消息统一格式：

```json
{
  "type": "消息类型",
  "data": { /* 消息数据 */ }
}
```

---

## 消息类型

### 1. 弹幕消息 (danmaku)

普通弹幕消息。

```json
{
  "type": "danmaku",
  "data": {
    "id": "bilibili_123456_1700000000",
    "uid": 123456,
    "user": "用户名",
    "uname": "用户名",
    "content": "弹幕内容",
    "msg": "弹幕内容",
    "timestamp": 1700000000,
    "color": "#FFFFFF",
    "badge": "粉丝牌"
  }
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|-----|------|------|
| id | string | 消息唯一 ID |
| uid | number | 用户 UID |
| user | string | 用户名 |
| content | string | 弹幕内容 |
| timestamp | number | 时间戳 |
| color | string | 弹幕颜色 |
| badge | string | 粉丝牌名称 |

---

### 2. 礼物消息 (gift)

用户赠送礼物。

```json
{
  "type": "gift",
  "data": {
    "user": "用户名",
    "giftName": "礼物名称",
    "giftCount": 1,
    "timestamp": "2024-01-01T00:00:00"
  }
}
```

---

### 3. 进入直播间 (welcome)

用户进入直播间。

```json
{
  "type": "welcome",
  "data": {
    "user": "用户名",
    "badge": "粉丝牌",
    "timestamp": "2024-01-01T00:00:00"
  }
}
```

---

### 4. 人气值 (heartbeat)

直播间人气值更新。

```json
{
  "type": "heartbeat",
  "data": {
    "popularity": 1000,
    "timestamp": "2024-01-01T00:00:00"
  }
}
```

---

### 5. 音乐添加通知 (music_added)

点歌成功通知。

```json
{
  "type": "music_added",
  "data": {
    "user": "点歌用户",
    "title": "歌曲名称",
    "artist": "歌手/UP主"
  }
}
```

---

### 6. 音乐错误通知 (music_error)

点歌失败通知。

```json
{
  "type": "music_error",
  "data": {
    "user": "点歌用户",
    "content": "原始弹幕内容",
    "error": "错误原因"
  }
}
```

---

### 7. AI 回复消息

AI 主播回复弹幕。

#### 7.1 开始回复 (start)

```json
{
  "type": "start",
  "data": {}
}
```

#### 7.2 文字内容 (text)

```json
{
  "type": "text",
  "data": {
    "text": "回复的文字内容"
  }
}
```

#### 7.3 音频数据 (audio)

```json
{
  "type": "audio",
  "data": {
    "audio": "base64编码的音频数据",
    "text": "对应的文字",
    "sentence_index": 0,
    "char_offset": 0,
    "char_length": 50
  }
}
```

#### 7.4 结束回复 (end)

```json
{
  "type": "end",
  "data": {
    "text": "完整的回复文本"
  }
}
```

---

## 测试 WebSocket

用于测试环境的模拟弹幕连接。

```
WebSocket /bilibili/ws/test/{room_id}
```

此端点不会连接真实的 B站弹幕服务器，仅用于前端测试。

---

## 错误处理

### 错误码

| 错误码 | 说明 |
|-------|------|
| INVALID_SESSDATA | SESSDATA 无效或已过期 |
| CONNECTION_FAILED | 连接 B站服务器失败 |
| ROOM_NOT_FOUND | 直播间不存在 |

### 错误消息格式

```json
{
  "type": "error",
  "data": {
    "code": "CONNECTION_FAILED",
    "message": "连接失败详情"
  }
}
```

---

## 连接状态图

```
┌─────────────────────────────────────────────────────────────────┐
│                    WebSocket 连接状态                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    ┌─────────┐                                                 │
│    │  初始   │                                                 │
│    └────┬────┘                                                 │
│         │                                                      │
│         │ 前端发起连接                                          │
│         ▼                                                      │
│    ┌─────────┐     连接成功     ┌─────────┐                    │
│    │ 连接中  │ ───────────────▶ │ 已连接  │                    │
│    └─────────┘                  └────┬────┘                    │
│                                      │                          │
│                                      │ 接收弹幕                 │
│                                      ▼                          │
│                                 ┌─────────┐                    │
│                                 │ 消息处理 │                    │
│                                 └────┬────┘                    │
│                                      │                          │
│                         ┌────────────┼────────────┐             │
│                         │            │            │             │
│                         ▼            ▼            ▼             │
│                    ┌─────────┐ ┌─────────┐ ┌─────────┐         │
│                    │ 广播弹幕│ │ 点歌处理│ │ AI回复  │         │
│                    └─────────┘ └─────────┘ └─────────┘         │
│                                                                 │
│                                      │                          │
│                                      │ 断开连接                 │
│                                      ▼                          │
│                                 ┌─────────┐                    │
│                                 │ 已断开  │                    │
│                                 └─────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 相关文档

- [音乐播放 API](./music-api.md)
- [AI对话 API](./ai-api.md)
- [弹幕处理流程](../../4.business/danmaku-flow.md)
