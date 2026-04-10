# 飞娜直播间后端服务

## 功能模块

- **Bilibili 直播弹幕**: 获取B站直播间实时弹幕 (✅ 已实现)
- **点歌系统**: 弹幕点歌队列管理 (预留)
- **AI Agent**: 智能对话 (预留)
- **图像合成**: 虚拟形象 (预留)

## 环境要求

- Python 3.11+
- uv 依赖管理工具

## 快速开始

```bash
# 进入后端目录
cd backend

# 安装依赖
uv sync

# 运行服务
uv run uvicorn main:app --reload

# 开发模式 (指定端口)
uv run uvicorn main:app --reload --port 8765
```

## API 端点

### WebSocket 端点
```
ws://localhost:8765/bilibili/ws/{room_id}
```

### REST 端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/bilibili/room/{room_id}/status` | 房间状态 |
| POST | `/bilibili/room/{room_id}/close` | 关闭房间连接 |

## 项目结构

```
backend/
├── main.py                 # FastAPI 应用入口
├── pyproject.toml          # uv 依赖配置
├── apps/
│   ├── bilibili/           # B站直播相关
│   │   ├── models.py       # 数据模型
│   │   ├── handlers.py     # 弹幕事件处理
│   │   ├── client.py       # B站客户端封装
│   │   └── router.py       # WebSocket 路由
│   └── ai/                 # AI Agent (预留)
├── core/
│   └── websocket.py         # WebSocket 连接管理
├── services/               # 服务层
└── utils/                  # 工具函数
```

## 前端连接示例

```javascript
const roomId = 22608112  // 房间号
const ws = new WebSocket(`ws://localhost:8765/bilibili/ws/${roomId}`)

ws.onopen = () => console.log('Connected to danmaku stream')
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  console.log(message.type, message.data)
}
```

## 消息格式

### 后端 -> 前端

**弹幕消息 (danmaku)**
```json
{
  "type": "danmaku",
  "data": {
    "id": "22608112_1234567890",
    "user": "用户名",
    "content": "弹幕内容",
    "timestamp": "2026-04-09T10:30:00",
    "type": "normal",
    "color": "#FFFFFF",
    "badge": "粉丝牌"
  }
}
```

**礼物消息 (gift)**
```json
{
  "type": "gift",
  "data": {
    "user": "用户名",
    "giftName": "辣条",
    "giftCount": 1,
    "timestamp": "2026-04-09T10:30:00"
  }
}
```

**心跳消息 (heartbeat)**
```json
{
  "type": "heartbeat",
  "data": {
    "popularity": 12345,
    "timestamp": "2026-04-09T10:30:00"
  }
}
```
