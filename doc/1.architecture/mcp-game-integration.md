# MCP 游戏集成架构

## 概述

本文档描述如何将 MCP (Model Context Protocol) 游戏控制集成到 AI 主播系统中，实现 AI 主播边玩游戏边与观众互动的能力。

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         共享存储层 (Shared Storage)                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐ │
│  │ 主播回答历史 (FIFO)  │  │ 游戏LLM历史 (FIFO)   │  │ 总记忆 (异步总结) │ │
│  │ 主播LLM: 读写        │  │ 游戏LLM: 读写        │  │ 专用LLM定时更新  │ │
│  │ 游戏LLM: 只读        │  │                      │ │例如满多少记录就触发│ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌─────────────────────────────────────┐   ┌─────────────────────────────────────┐
        │         MCP Game Graph              │   │         主播 LLM Graph              │
        │         (游戏决策 + 解说请求)         │   │         (风格化解说 + TTS)          │
        └─────────────────────────────────────┘   └─────────────────────────────────────┘
                    │                                           ▲
                    │ request_host_commentary                   │
                    └───────────────────────────────────────────┘
                              消息队列 (优先级队列)
```

## 核心组件

### 1. 共享存储层 (shared_context.py)

管理两个 Graph 之间的共享状态：

| 存储项 | 类型 | 主播LLM权限 | 游戏LLM权限 |
|-------|------|------------|------------|
| 主播回答历史 | FIFO (max 50) | 读写 | 只读 |
| 游戏LLM历史 | FIFO (max 30) | - | 读写 |
| 总记忆 | 异步更新 | 读写 | 只读 |

### 2. MCP 客户端与适配器 (mcp/)

#### MCPClient
- JSON-RPC 2.0 协议通信
- 支持 `tools/list`、`tools/call` 命令
- 健康检查接口

#### BaseGameAdapter (抽象基类)
```python
class BaseGameAdapter(ABC):
    @property
    @abstractmethod
    def game_id(self) -> str: ...
    
    @abstractmethod
    async def get_state(self) -> UnifiedGameState: ...
    
    @abstractmethod
    async def execute_action(self, action: UnifiedAction) -> bool: ...
```

#### UnifiedGameState
统一的游戏状态格式，包含：
- `player`: 玩家状态 (HP、资源等)
- `enemies`: 敌人列表
- `available_actions`: 可用动作
- `turn_info`: 回合信息
- `to_prompt_text()`: 转换为 LLM 可读文本

### 3. 消息队列 (messaging/)

#### PriorityMessageQueue
- 优先级队列 (1=高, 2=中, 3=低)
- 消息过期自动丢弃
- 消息合并 (相同 merge_key)
- 频率限制集成

#### RateLimiter
按来源+动作控制频率：
- `game:tts`: 2秒间隔
- `host:tts`: 3秒间隔
- `danmaku:tts`: 5秒间隔

### 4. 游戏 Graph (game_graph.py)

游戏决策主循环：

```
┌─────────────┐
│   开始循环   │
└──────┬──────┘
       ▼
┌─────────────────────────────────────┐
│ 1. 并行数据收集                      │
│    - MCP 游戏状态                    │
│    - 主播历史 (共享存储)              │
│    - 游戏历史 (共享存储)              │
│    - 总记忆 (共享存储)                │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ 2. 构建提示词                        │
│    - 游戏状态 → 文本                 │
│    - MCP tools + 内置 tool           │
│    - 组合 system prompt              │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ 3. LLM 决策                          │
│    - 调用 LLM 生成 tool_calls        │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ 4. 并发执行                          │
│    - MCP 工具 → 立即执行              │
│    - request_host_commentary → 入队列│
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ 5. 更新历史                          │
│    - 写入共享存储                     │
└──────────────────┬──────────────────┘
                   ▼
            ┌─────────────┐
            │  下一轮循环  │
            └─────────────┘
```

#### 内置工具: request_host_commentary

```json
{
  "name": "request_host_commentary",
  "description": "让主播进行解说",
  "parameters": {
    "key_points": ["要点1", "要点2"],
    "mood": "excited",
    "reference_danmaku": "观众弹幕内容"
  }
}
```

### 5. 主播 Graph (host_graph.py)

消费消息队列，生成风格化解说：

```
┌─────────────┐
│  等待消息    │ ← 阻塞
└──────┬──────┘
       ▼
┌─────────────────────────────────────┐
│ 构建主播提示词                        │
│ - 解说要点                           │
│ - 人设 prompt                        │
│ - 上下文 (主播历史)                   │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ LLM 生成风格化解说                    │
│ - 第一人称                           │
│ - 口语化                             │
│ - 口癖和情感词                        │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ TTS 合成并播放                        │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│ 更新主播历史 (共享存储)               │
└──────────────────┬──────────────────┘
                   ▼
            ┌─────────────┐
            │  继续等待    │
            └─────────────┘
```

### 6. 记忆总结服务 (game_memory.py)

定期总结共享存储中的历史数据：

- **触发条件**: 记录数 ≥ 30 或 距上次总结 > 5分钟
- **处理内容**: 收集历史 → LLM 总结 → 更新总记忆 → 清理过期数据

## 数据流

### 游戏决策流程

```
游戏状态变化
    │
    ▼
Game Graph 检测到玩家回合
    │
    ▼
并行获取: 游戏状态 + 主播历史 + 游戏历史 + 总记忆
    │
    ▼
LLM 决策 → tool_calls
    │
    ├── play_card → MCP 执行
    ├── end_turn → MCP 执行
    └── request_host_commentary → 消息队列
                                    │
                                    ▼
                            Host Graph 消费
                                    │
                                    ▼
                            主播风格化解说 + TTS
```

### 主播互动流程

```
观众弹幕
    │
    ▼
HostBrain 处理 (原有流程)
    │
    ▼
主播回复 → 写入共享存储
    │
    ▼
Game Graph 下次决策时可读取
```

## 配置

```yaml
game:
  enabled: true
  mcp_url: "http://127.0.0.1:8080"
  adapter: "slay_the_spire"
  poll_interval: 1.0
  memory_threshold: 30
```

| 配置项 | 说明 | 默认值 |
|-------|------|-------|
| enabled | 是否启用游戏集成 | false |
| mcp_url | MCP 服务地址 | http://127.0.0.1:8080 |
| adapter | 游戏适配器 | slay_the_spire |
| poll_interval | 轮询间隔(秒) | 1.0 |
| memory_threshold | 记忆总结阈值 | 30 |

## API 接口

| 接口 | 方法 | 说明 |
|-----|------|------|
| /game/status | GET | 获取游戏状态 |
| /game/start | POST | 启动游戏集成 |
| /game/stop | POST | 停止游戏集成 |
| /game/context | GET | 获取共享上下文 |

## 扩展新游戏

1. 创建适配器继承 `BaseGameAdapter`
2. 实现 `get_state()`、`execute_action()` 等方法
3. 在 `game_router.py` 中注册

```python
class MyGameAdapter(BaseGameAdapter):
    @property
    def game_id(self) -> str:
        return "my_game"
    
    async def get_state(self) -> UnifiedGameState:
        # 获取游戏状态并转换为统一格式
        ...
    
    async def execute_action(self, action: UnifiedAction) -> bool:
        # 执行游戏动作
        ...
```

## 文件清单

| 文件 | 说明 |
|-----|------|
| shared_context.py | 共享存储层 |
| game_graph.py | 游戏决策 Graph |
| host_graph.py | 主播解说 Graph |
| game_manager.py | 游戏集成管理器 |
| game_router.py | 游戏 API 路由 |
| mcp/client.py | MCP JSON-RPC 客户端 |
| mcp/base_adapter.py | 游戏适配器基类 |
| mcp/adapters/ | 游戏适配器目录（在此实现具体游戏适配） |
| messaging/queue.py | 优先级消息队列 |
| messaging/rate_limiter.py | 频率限制器 |
| memory/game_memory.py | 游戏记忆总结服务 |
