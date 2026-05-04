# MCP 游戏集成架构

## 概述

本文档描述 MCP (Model Context Protocol) 游戏控制集成到 AI 主播系统的实现。系统通过双 Graph 架构（GameGraph + HostGraph）实现 AI 主播边玩游戏边与观众互动的能力。

GameGraph 负责游戏决策（通过 MCP 协议操控游戏），HostGraph 负责消费消息队列统一生成话术并 TTS 输出。两者通过 SharedContext 共享状态，通过 PriorityMessageQueue 传递消息。

## 架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         共享存储层 (SharedContext)                            │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │ 主播回答历史 FIFO  │  │ 游戏操作历史 FIFO  │  │ 三层记忆 (LongTermMemory)  │ │
│  │ (max 50)          │  │ (max 30)          │  │ core / important / recent  │ │
│  │ HostGraph: 读写    │  │ GameGraph: 读写    │  │ GameGraph: 读写(含tool)    │ │
│  │ GameGraph: 只读    │  │                    │  │ HostGraph: 读写            │ │
│  └──────────────────┘  └──────────────────┘  │  MemorySummarizer: 异步更新 │ │
│                                               └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                    │                                        │
                    │ 读取上下文                              │ 读取上下文
                    ▼                                        ▼
        ┌──────────────────────────┐            ┌──────────────────────────┐
        │     GameGraph            │            │     HostGraph            │
        │  (游戏决策 + 解说请求)    │            │  (统一话术生成 + TTS)     │
        │                          │            │                          │
        │  消费: MCP游戏状态        │            │  消费: 消息队列           │
        │  产出: MCP动作 + 消息入队  │            │  产出: TTS语音输出        │
        └───────────┬──────────────┘            └──────────────────────────┘
                    │                                       ▲
                    │ commentary_request (PRIORITY_HIGH)     │
                    │─────────────────────────────────────────│
                    │ danmaku (PRIORITY_NORMAL)               │
                    │ gift_thanks (PRIORITY_LOW)              │
                    │                                         │
                    │       PriorityMessageQueue               │
                    └─────────────────────────────────────────┘
                                       ▲
                                       │ 弹幕入队
                              ┌────────┴────────┐
                              │   AIHostBrain    │
                              │  (弹幕缓冲+入队)  │
                              └─────────────────┘
```

## 核心组件

### 1. 共享存储层 (shared_context.py)

管理两个 Graph 之间的共享状态，所有操作通过 `asyncio.Lock` 保证线程安全。

| 存储项 | 类型 | HostGraph权限 | GameGraph权限 | 说明 |
|-------|------|-------------|-------------|------|
| 主播回答历史 | deque (max 50) | 读写 | 只读 | 主播说了什么，GameGraph可感知 |
| 游戏操作历史 | deque (max 30) | - | 读写 | 游戏做了什么，含动作+结果 |
| 三层记忆 | LongTermMemory | 读写 | 读写(含tool) | core/important/recent |

#### LongTermMemory 三层记忆结构

```python
@dataclass
class LongTermMemory:
    core: str = ""        # 核心记忆: 游戏机制、规则、规律
    important: str = ""   # 重要记忆: 牌组构成、遗物策略、关键事件
    recent: str = ""      # 近期记忆: 近期战术要点、操作细节
    key_events: list = [] # 关键事件列表
    last_updated: float = 0.0
```

记忆更新方式：
- **GameGraph 内置工具 `request_memory_update`**: 支持 `rewrite`(完全重写) 和 `search_replace`(搜索替换) 两种模式
- **MemorySummarizer 异步服务**: 定期调用专用 LLM，使用 `search_replace_memory` 和 `rewrite_memory` 工具更新记忆

#### SharedContext 关键方法

| 方法 | 说明 |
|-----|------|
| `add_host_entry(danmaku, reply, user)` | 添加主播互动记录 |
| `add_game_entry(action, params, result)` | 添加游戏操作记录 |
| `get_host_history_text(limit)` | 获取主播历史文本 |
| `get_game_history_text(limit)` | 获取游戏历史文本 |
| `get_memory()` | 获取三层记忆快照 |
| `rewrite_memory(memory_type, content)` | 完全重写某层记忆 |
| `search_replace_memory(memory_type, mode, search, replace, end)` | 搜索替换记忆 |
| `clear_all_memory()` | 清空所有记忆（新游戏开始时） |
| `trim_histories(keep_seconds)` | 清理过期历史记录 |

### 2. MCP 客户端与适配器 (mcp/)

#### MCPClient (mcp/client.py)
- 基于 HTTP 的 JSON-RPC 2.0 协议通信（非 WebSocket）
- 通过 `{base_url}/mcp` 端点发送请求
- 支持 `tools/list`、`tools/call` 方法
- 工具列表缓存（60秒刷新）
- 独立的健康检查接口（`{base_url}/health`）

```python
class MCPClient:
    async def call(method, params) -> Any          # 通用 JSON-RPC 调用
    async def get_tools(force_refresh) -> list     # 获取工具列表(带缓存)
    async def call_tool(tool_name, arguments) -> Any # 调用指定工具
    async def health_check() -> bool               # 健康检查
```

#### BaseGameAdapter (mcp/base_adapter.py) — 抽象基类

```python
class BaseGameAdapter(ABC):
    @property
    @abstractmethod
    def game_id(self) -> str: ...

    @property
    @abstractmethod
    def game_type(self) -> str: ...

    @abstractmethod
    async def get_state(self) -> UnifiedGameState: ...

    @abstractmethod
    async def execute_action(self, action: UnifiedAction) -> tuple[bool, str]: ...

    @abstractmethod
    async def get_available_actions(self) -> list[UnifiedAction]: ...

    @abstractmethod
    def is_my_turn(self, state: UnifiedGameState) -> bool: ...

    @abstractmethod
    async def get_tools_definition(self) -> list[dict]: ...

    async def health_check(self) -> bool: ...
```

注意 `execute_action` 返回 `tuple[bool, str]`（成功标志 + 错误消息），而非文档旧版中的 `bool`。

#### UnifiedGameState
统一的游戏状态格式：

| 字段 | 类型 | 说明 |
|-----|------|------|
| game_id | str | 游戏标识 |
| game_type | str | 游戏类型 |
| player | dict | 玩家状态 (HP、资源等) |
| enemies | list[dict] | 敌人列表 |
| available_actions | list[dict] | 可用动作 |
| turn_info | dict | 回合信息 |
| screen_type | str | 当前画面类型 |
| game_specific | dict | 游戏特有数据 |
| raw_state | dict | 原始状态数据(完整保留) |

`to_prompt_text()` 方法将状态转换为 LLM 可读文本。

#### SlayTheSpireAdapter (mcp/adapters/slay_the_spire.py)

杀戮尖塔的具体适配器实现，特点：
- 自动回退获取状态：`get_game_state` → `get_screen_state` → `get_available_commands`
- 支持丰富的动作类型：`start_game`, `execute_actions`, `play_card`, `end_turn`, `choose`, `use_potion`, `proceed`, `confirm`, `skip`, `cancel`, `select_cards` 等
- `is_my_turn()` 判断逻辑：检查 `ready_for_command` + 画面类型
- `get_tools_definition()` 将 MCP 工具定义转换为 OpenAI function calling 格式
- `start_game` 前自动调用 `abandon_run` 清理旧存档
- 角色名自动修正（支持别名如 `character_index`, `role`, `class`, `char`）

### 3. 消息队列 (messaging/)

#### PriorityMessageQueue (messaging/queue.py)

所有消息由主播 LLM 统一消费，生成话术后 TTS 输出。

**5级优先级**：

| 优先级 | 常量 | 值 | 说明 |
|-------|------|---|------|
| 中断 | PRIORITY_INTERRUPT | 0 | 最高优先，永不丢弃 |
| 高 | PRIORITY_HIGH | 1 | 游戏解说请求，永不丢弃 |
| 中 | PRIORITY_NORMAL | 2 | 弹幕回复 |
| 低 | PRIORITY_LOW | 3 | 一般消息 |
| 可丢弃 | PRIORITY_DISPOSABLE | 4 | 最低优先 |

**消息来源与类型**：

| 来源 | 消息类型 | 优先级 | 说明 |
|-----|---------|-------|------|
| game | commentary_request | 1 (HIGH) | GameGraph 请求主播解说 |
| danmaku | danmaku | 2 (NORMAL) | 观众弹幕原文 |
| gift | gift_thanks | 3 (LOW) | 礼物感谢 |

**消息结构 (Message)**：

| 字段 | 类型 | 说明 |
|-----|------|------|
| id | str | 唯一ID（自动生成） |
| priority | int | 优先级 |
| source | str | 来源标识 |
| msg_type | str | 消息类型 |
| content | str | 消息内容 |
| data | dict | 附加数据 |
| expire_at | float | 过期时间 |
| allow_skip | bool | 是否允许跳过 |
| merge_key | str | 合并键（相同key的消息合并内容） |
| cancel_key | str | 取消键 |
| user_id | str | 用户ID（用于冷却） |

**核心特性**：
- 消息过期自动丢弃（allow_skip=True时）
- 消息合并（相同 merge_key 的消息内容拼接）
- 消息取消（通过 cancel_key）
- 用户冷却（同一用户 3 秒内只能发一条消息）
- 队列满时按优先级丢弃（PRIORITY_INTERRUPT 和 PRIORITY_HIGH 永不丢弃）
- 全局静音（mute/unmute，休眠时使用）
- 统计信息（入队/丢弃/消费计数、丢弃率）

#### RateLimiter (messaging/rate_limiter.py)

按 `source:action` 控制消息发送频率：

| 规则键 | 最小间隔 | 说明 |
|-------|---------|------|
| game:commentary_request | 4.0s | 游戏解说请求间隔 |
| danmaku:danmaku | 3.0s | 弹幕回复间隔 |
| gift:gift_thanks | 10.0s | 礼物感谢间隔 |

支持突发（burst）机制：`max_burst=1`, `burst_window=1.0s`

### 4. 游戏 Graph (game_graph.py)

游戏决策主循环，使用独立的 LLM 客户端（`get_game_ai_client()`，disable_thinking=True）。

```
┌─────────────┐
│   开始循环   │
└──────┬──────┘
       ▼
┌─────────────────────────────────────────────┐
│ 1. 并行数据收集 (asyncio.gather)              │
│    - MCP 游戏状态 (adapter.get_state)         │
│    - 主播历史 (shared_context, limit=5)       │
│    - 游戏历史 (shared_context, limit=12)      │
│    - 三层记忆 (shared_context.get_memory)     │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 2. 回合判断                                   │
│    - adapter.is_my_turn(state)?              │
│    - GAME_OVER → 自动重启                     │
│    - 非玩家回合 → sleep(poll_interval)        │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 3. 构建提示词 (build_game_system_prompt)      │
│    - 三层记忆 → 记忆段落                      │
│    - 游戏状态 → _format_game_state 文本化     │
│    - MCP tools 定义 → 工具说明段落             │
│    - 内置 tools (commentary + memory_update)  │
│    - 解说积极性 (commentary_eagerness)         │
│    - 记忆积极性 (memory_eagerness)             │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 4. LLM 决策 (_llm_decide)                    │
│    - 调用游戏 LLM 生成 JSON 格式决策           │
│    - 解析 tool_calls (_parse_tool_calls)      │
│    - 支持 markdown code block 包裹的 JSON     │
│    - 支持多种格式: actions/tool_calls/list    │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 5. 并发执行 (_execute_parallel)               │
│    - 非游戏工具 (commentary/memory) → 并行     │
│    - 游戏动作 → 串行(每步间隔+随机抖动)        │
│    - start_game 成功时清空记忆                 │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 6. 更新历史                                   │
│    - 记录决策时间                              │
│    - 游戏动作结果写入 shared_context           │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 7. 步进间隔等待                               │
│    max(game_min_step_interval - elapsed,     │
│        poll_interval)                        │
└─────────────────────────────────────────────┘
```

#### 内置工具 1: request_host_commentary

```json
{
  "name": "request_host_commentary",
  "description": "让主播进行解说，主播会以自己的风格表达这些要点",
  "parameters": {
    "key_points": ["要点1", "要点2"],
    "mood": "excited|confident|nervous|happy|sad|angry|neutral",
    "reference_danmaku": "可参考的弹幕内容"
  }
}
```

解说请求有最小间隔控制（默认15秒），避免过于频繁。入队优先级为 HIGH。

#### 内置工具 2: request_memory_update

```json
{
  "name": "request_memory_update",
  "description": "更新游戏记忆系统。三层记忆: core(机制规律)、important(牌组遗物策略)、recent(近期战术要点)",
  "parameters": {
    "memory_type": "core|important|recent",
    "mode": "rewrite|search_replace",
    "content": "替换内容",
    "search": "search_replace模式时: 要替换掉的原文"
  }
}
```

- `rewrite` 模式：完全重写该层记忆
- `search_replace` 模式：模糊搜索替换（内部使用 fuzzy 模式匹配）

#### _format_game_state 游戏状态文本化

将 `raw_state` 格式化为 LLM 可读的文本，包含：
- 画面类型、楼层、HP
- 战斗状态：费用、敌人列表（HP、意图、格挡）、手牌（费用、可出、需目标）
- 选项列表

#### _normalize_tool_calls 响应解析

支持 LLM 返回的多种 JSON 格式：
- `{"actions": [...]}` — 标准 actions 格式
- `{"tool_calls": [...]}` — OpenAI tool_calls 格式
- `[...]` — 直接列表格式
- 每个元素支持 `{"function": {"name": ..., "arguments": ...}}` 或 `{"action": ..., ...}` 或 `{"name": ...}` 格式

#### GAME_OVER 自动重启

检测到 `screen_type == "GAME_OVER"` 时：
1. 调用 `proceed` 退出结算画面
2. 等待1秒
3. 调用 `start_game(character="IRONCLAD")` 开始新游戏
4. 清空所有记忆

### 5. 主播 Graph (host_graph.py)

消费消息队列，统一由主播 LLM 生成话术后 TTS 输出。所有消息类型统一走主播 LLM，TTS 只是最后把话转语音的工具步骤。

**消费的消息类型**：

| 消息类型 | 处理方法 | 说明 |
|---------|---------|------|
| commentary_request | `_handle_commentary` | GameGraph 请求游戏解说(带草稿要点) → 主播 LLM 风格化 → TTS |
| danmaku | `_handle_danmaku` | 观众弹幕原文 → 主播 LLM 生成回复 → TTS |
| gift_thanks | `_handle_gift_thanks` | 礼物感谢 → 主播 LLM 生成感谢语 → TTS |

```
┌─────────────┐
│  等待消息    │ ← queue.get(timeout=5s)
└──────┬──────┘
       ▼
┌─────────────────────────────────────────────┐
│ 按 msg_type 分发处理                          │
│                                              │
│ commentary_request:                          │
│   构建 COMMENTARY_SYSTEM_PROMPT              │
│   - host_personality (人设)                   │
│   - key_points (解说要点)                     │
│   - mood (建议情绪)                           │
│   - host_history (主播历史, limit=10)         │
│   - reference_danmaku (参考弹幕)              │
│                                              │
│ danmaku:                                     │
│   构建 DANMAKU_REPLY_PROMPT                  │
│   - host_personality                         │
│   - danmaku (弹幕内容)                        │
│   - host_history (limit=10)                  │
│                                              │
│ gift_thanks:                                 │
│   构建 GIFT_THANKS_PROMPT                    │
│   - host_personality                         │
│   - gift_info (礼物信息)                      │
│   - host_history (limit=5)                   │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 主播 LLM 生成话术 (_llm_generate)             │
│ - 使用 host_model (独立模型配置)               │
│ - 超长截断 (host_max_reply_length)            │
│ - 风格要求: 第一人称、口语化、口癖情感词        │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ TTS 合成播放 (_speak)                         │
│ - 最小 TTS 间隔 3 秒                          │
│ - 不足3秒则等待补齐                            │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 更新 SharedContext                            │
│ - add_host_entry (让 GameGraph 感知)          │
│ - 回调 on_reply (如有)                        │
└──────────────────┬──────────────────────────┘
                   ▼
            ┌─────────────┐
            │  继续等待    │
            └─────────────┘
```

**三种 Prompt 模板**：

1. **COMMENTARY_SYSTEM_PROMPT** — 游戏解说（20-50字）
   - 包含解说要点、建议情绪、主播历史、参考弹幕
2. **DANMAKU_REPLY_PROMPT** — 弹幕回复（20-50字）
   - 包含弹幕内容、主播历史
3. **GIFT_THANKS_PROMPT** — 礼物感谢（15-30字）
   - 包含礼物信息、主播历史
   - 当前为空实现（消息入队但 gift_thanks 消息暂无来源触发）

### 6. 记忆总结服务 (game_memory.py)

异步记忆总结服务，定期调用专用 LLM 更新三层记忆。

**触发条件**：
- 主播历史 + 游戏历史总条数 ≥ 30（trigger_threshold）
- 或距上次总结 > 5分钟且总条数 > 5

**总结流程**：
1. 收集所有历史数据（各取最近100条，取最后20条构建文本）
2. 获取当前三层记忆
3. 调用 LLM（使用 `llm_model`，temperature=0.3，max_tokens=500）
4. LLM 通过 tool_calls 执行记忆更新

**LLM 可用的记忆工具**：

| 工具名 | 说明 |
|-------|------|
| search_replace_memory | 搜索替换记忆，支持 exact/fuzzy/range 三种模式 |
| rewrite_memory | 完全重写某层记忆 |

5. 清理过期历史（保留最近300秒）

### 7. 游戏集成管理器 (game_manager.py)

统一管理 GameGraph 和 HostGraph 的生命周期：

```python
class GameManager:
    _game_graphs: dict[str, GameGraph]  # 支持多游戏
    _host_graph: HostGraph | None       # 单一主播 Graph

    def register_game(adapter)    # 注册游戏适配器
    async def start()             # 启动所有 Graph
    async def stop()              # 停止所有 Graph
    def mute() / unmute()         # 静音/取消静音消息队列
    def get_game_status() -> dict # 获取运行状态
```

**启动流程**：
1. 注册所有游戏适配器（当前仅 slay_the_spire）
2. 创建 HostGraph（带 on_reply 回调）
3. 启动所有 GameGraph
4. 启动 HostGraph

**休眠联动**：
- 管理员执行 `/sleep` → `game_manager.mute()` → 消息队列静音
- 管理员执行 `/wake` → `game_manager.unmute()` → 消息队列恢复

## 数据流

### 游戏决策完整流程

```
游戏状态变化
    │
    ▼
GameGraph._game_loop()
    │
    ▼
并行获取: 游戏状态 + 主播历史(5条) + 游戏历史(12条) + 三层记忆
    │
    ▼
is_my_turn? ─── 否 → sleep(poll_interval)
    │
    │ 是
    ▼
GAME_OVER? ─── 是 → proceed + start_game + clear_memory
    │
    │ 否
    ▼
构建 system prompt (记忆 + 历史 + 状态 + MCP工具说明)
    │
    ▼
游戏 LLM 决策 → JSON tool_calls
    │
    ├── request_host_commentary → 消息队列 (PRIORITY_HIGH)
    ├── request_memory_update → SharedContext 直接更新
    └── 游戏动作 → MCP 串行执行 (间隔+抖动)
                    │
                    ▼
            SharedContext.add_game_entry
```

### 弹幕回复流程（新架构）

```
观众弹幕
    │
    ▼
AIHostBrain.push_danmaku()
    │
    ▼
AIHostBrain.try_reply()
    │
    ▼
_enqueue_danmaku() → Message(priority=NORMAL, msg_type="danmaku")
    │
    ▼
PriorityMessageQueue.put()
    │
    ▼
HostGraph._host_loop() 消费
    │
    ▼
_handle_danmaku() → 主播 LLM 生成回复 → TTS
    │
    ▼
SharedContext.add_host_entry() (GameGraph可感知)
```

### 礼物感谢流程（空实现）

```
礼物消息
    │
    ▼
(目前无代码将礼物消息入队)
    │
    ▼
HostGraph._handle_gift_thanks() 已实现但暂无触发源
```

## 配置

```yaml
game:
  enabled: true
  mcp_url: "http://127.0.0.1:8080"
  adapter: "slay_the_spire"
  poll_interval: 1.0
  memory_threshold: 30
  model: "game-model-name"
  temperature: 0.4
  max_tokens: 500
  api_url: "https://api.example.com/v1"
  api_key: "your-game-api-key"
  min_step_interval: 3.0
  step_jitter: 0.5
  commentary_eagerness: 3
  memory_eagerness: 3

host:
  model: "host-model-name"
  temperature: 0.7
  max_tokens: 200
  reply_interval: 5
  max_reply_length: 100
```

| 配置项 | 说明 | 默认值 |
|-------|------|-------|
| game.enabled | 是否启用游戏集成 | false |
| game.mcp_url | MCP 服务地址 | http://127.0.0.1:8080 |
| game.adapter | 游戏适配器 | slay_the_spire |
| game.poll_interval | 轮询间隔(秒) | 1.0 |
| game.memory_threshold | 记忆总结阈值 | 30 |
| game.model | 游戏 LLM 模型 | (独立配置) |
| game.temperature | 游戏 LLM 温度 | 0.4 |
| game.max_tokens | 游戏 LLM 最大token | 500 |
| game.api_url | 游戏 LLM API地址 | (独立配置) |
| game.api_key | 游戏 LLM API密钥 | (独立配置) |
| game.min_step_interval | 游戏操作最小间隔(秒) | 3.0 |
| game.step_jitter | 游戏操作随机抖动(秒) | 0.5 |
| game.commentary_eagerness | 解说积极性(1-5) | 3 |
| game.memory_eagerness | 记忆更新积极性(1-5) | 3 |
| host.model | 主播 LLM 模型 | (独立配置) |
| host.temperature | 主播 LLM 温度 | 0.7 |
| host.max_tokens | 主播 LLM 最大token | 200 |
| host.reply_interval | 回复间隔(秒) | 5 |
| host.max_reply_length | 回复最大长度 | 100 |

## API 接口

| 接口 | 方法 | 说明 |
|-----|------|------|
| /game/status | GET | 获取游戏运行状态 |
| /game/start | POST | 启动游戏集成 |
| /game/stop | POST | 停止游戏集成 |
| /game/context | GET | 获取共享上下文摘要 |
| /game/mute | POST | 静音消息队列 |
| /game/unmute | POST | 取消静音消息队列 |
| /game/queue | GET | 获取消息队列统计 |

## 扩展新游戏

1. 创建适配器继承 `BaseGameAdapter`
2. 实现所有抽象方法：`game_id`, `game_type`, `get_state()`, `execute_action()`, `get_available_actions()`, `is_my_turn()`, `get_tools_definition()`
3. 在 `GameManager` 中注册适配器

```python
class MyGameAdapter(BaseGameAdapter):
    @property
    def game_id(self) -> str:
        return "my_game"

    @property
    def game_type(self) -> str:
        return "action"

    async def get_state(self) -> UnifiedGameState:
        raw = await self._mcp.call_tool("get_state")
        return self._raw_to_unified(raw)

    async def execute_action(self, action: UnifiedAction) -> tuple[bool, str]:
        result = await self._mcp.call_tool(action.action_type, action.params)
        if result is None:
            return False, f"{action.action_type} returned None"
        return True, ""

    async def get_available_actions(self) -> list[UnifiedAction]:
        ...

    def is_my_turn(self, state: UnifiedGameState) -> bool:
        ...

    async def get_tools_definition(self) -> list[dict]:
        ...
```

## 文件清单

| 文件 | 行数 | 说明 |
|-----|------|------|
| shared_context.py | 266 | 共享存储层（主播历史+游戏历史+三层记忆） |
| game_graph.py | 661 | 游戏决策 Graph（MCP决策主循环） |
| host_graph.py | 277 | 主播 Graph（消息队列消费+话术生成+TTS） |
| game_manager.py | 97 | 游戏集成管理器（统一生命周期管理） |
| game_router.py | 73 | 游戏 API 路由 |
| mcp/client.py | 79 | MCP HTTP JSON-RPC 客户端 |
| mcp/base_adapter.py | 95 | 游戏适配器基类 + UnifiedGameState/UnifiedAction |
| mcp/adapters/slay_the_spire.py | 264 | 杀戮尖塔适配器 |
| messaging/queue.py | 209 | 优先级消息队列 |
| messaging/rate_limiter.py | 82 | 频率限制器 |
| memory/game_memory.py | 274 | 游戏记忆总结服务 |
